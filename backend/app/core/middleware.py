"""ASGI middleware: request ids, security headers, a body cap, and the safety net.

All four are written as plain ASGI middleware rather than
``BaseHTTPMiddleware``. That is not stylistic: ``BaseHTTPMiddleware`` pumps the
response through an anyio memory stream, which breaks the SSE routes -- tokens
would arrive in a burst at the end instead of one at a time, which is the
entire point of streaming them.

Order matters, and Starlette applies ``add_middleware`` in reverse, so
``main.py`` adds these bottom-up. Outermost to innermost:

1. :class:`RequestIDMiddleware` -- so *every* response carries the header,
   including a CORS preflight and an error produced further in.
2. :class:`SecurityHeadersMiddleware` -- same reason.
3. ``CORSMiddleware`` -- outside the error handling, so a 500 still arrives
   with the ``Access-Control-Allow-Origin`` header the browser needs before it
   will let the frontend read the message. Without that, every server error
   would surface as an opaque network failure.
4. :class:`ExceptionResponseMiddleware` -- turns anything that escaped a route
   into the JSON body :mod:`app.core.errors` defines.
5. :class:`BodySizeLimitMiddleware` -- rejects an oversized upload before the
   route reads it into memory.
"""

import logging
import uuid

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_response, response_for_unhandled
from app.core.logging import request_id_var

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

# The route already refuses a resume over 10MB, with a message naming the
# limit. This is the floor under that: multipart framing adds a few hundred
# bytes to a 10MB file, so 11MB rejects what is unambiguously too large while
# leaving every legitimate upload to the route's friendlier error.
MAX_BODY_BYTES = 11 * 1024 * 1024
BODY_TOO_LARGE = "Request body is too large."
CONTENT_TOO_LARGE_STATUS = 413

# No HSTS: Render terminates TLS in front of this process and sets its own
# transport security. Emitting a second one from here would let this service
# pin a policy for a domain it does not own.
SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    # Stop a browser re-interpreting a JSON error body as HTML.
    ("x-content-type-options", "nosniff"),
    # Send the origin, not the full URL with its chat id, to third parties.
    ("referrer-policy", "strict-origin-when-cross-origin"),
    # This API is never a frame, so both framing headers are sent: CSP for
    # current browsers, X-Frame-Options for the ones that predate it.
    ("x-frame-options", "DENY"),
    ("content-security-policy", "frame-ancestors 'none'"),
)


class _BodyTooLarge(Exception):
    """Raised from the wrapped receive when a request body exceeds the cap."""


class RequestIDMiddleware:
    """Give every request an id, in the logs and on the response.

    An inbound ``X-Request-ID`` is honoured when it is short and plausible, so
    a proxy's or a client's own correlation id survives into these logs instead
    of being replaced by a second, unrelated one.
    """

    #: Longest inbound id accepted before one is generated instead.
    MAX_INBOUND_LENGTH = 200

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    def _incoming_id(self, scope: Scope) -> str:
        """Return a usable inbound request id, or a fresh one."""
        candidate = (Request(scope).headers.get(REQUEST_ID_HEADER) or "").strip()
        if candidate and len(candidate) <= self.MAX_INBOUND_LENGTH:
            return candidate
        return uuid.uuid4().hex

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Bind the id for the request and echo it on the response."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._incoming_id(scope)
        scope["request_id"] = request_id
        token = request_id_var.set(request_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            request_id_var.reset(token)


class SecurityHeadersMiddleware:
    """Add the response headers that cost nothing and close easy holes."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Set each header on the response unless it was already set."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS:
                    if name not in headers:
                        headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodySizeLimitMiddleware:
    """Refuse an oversized request body before the application reads it.

    The upload route also checks the size, but only *after* the whole file has
    been read into this process's memory. On a 512MB Render instance that check
    is too late to be a control, so the cap is enforced here as well: a declared
    ``Content-Length`` is rejected without reading a byte, and a chunked body is
    cut off as soon as it goes over.
    """

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    def _declared_length(self, scope: Scope) -> int | None:
        """Return the request's Content-Length, or None when it has none."""
        raw = Request(scope).headers.get("content-length")
        if raw is None:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    async def _too_large(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Send the 413 in the API's standard error shape."""
        response = error_response(CONTENT_TOO_LARGE_STATUS, BODY_TOO_LARGE)
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Enforce the cap, answering 413 when it is exceeded."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = self._declared_length(scope)
        if declared is not None and declared > self.max_bytes:
            logger.warning(
                "rejected %s %s: declared body of %d bytes over the %d byte cap",
                scope.get("method"),
                scope.get("path"),
                declared,
                self.max_bytes,
            )
            await self._too_large(scope, receive, send)
            return

        received = 0
        started = False

        async def counted_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counted_receive, tracking_send)
        except _BodyTooLarge:
            if started:
                raise
            logger.warning(
                "rejected %s %s: body exceeded the %d byte cap while streaming",
                scope.get("method"),
                scope.get("path"),
                self.max_bytes,
            )
            await self._too_large(scope, receive, send)


class ExceptionResponseMiddleware:
    """Turn any exception that escaped the routes into the JSON error shape.

    Starlette's own ``ServerErrorMiddleware`` would answer a plain-text
    "Internal Server Error" and then re-raise, so this sits inside it and
    answers first. Once the response has started -- mid-SSE, say -- there is no
    status code left to change, and the exception is re-raised for the server to
    log and drop the connection. That case is handled where it belongs, in the
    stream itself, which emits an ``error`` event instead.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the application, converting an escaped exception into JSON."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:  # noqa: BLE001 - converting it is the point
            if started:
                # Half a response is already on the wire; nothing to do but let
                # the server tear the connection down.
                raise
            response = response_for_unhandled(Request(scope), exc)
            await response(scope, receive, send)
