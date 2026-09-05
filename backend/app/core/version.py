"""The build identifier ``GET /health`` reports.

Answers "which code is actually running on Render right now" without a build
step or a version file to keep in sync. Resolution order:

1. ``APP_VERSION`` -- an explicit override, for anywhere that sets one.
2. ``RENDER_GIT_COMMIT`` -- set by Render on every deploy.
3. The checked-out git commit, read straight from ``.git`` (no subprocess).
4. ``"dev"`` -- a working tree with no git metadata, e.g. a Docker image built
   from a copy of the source.
"""

from functools import lru_cache
from pathlib import Path

from app.core.config import BACKEND_DIR, settings

DEV_VERSION = "dev"
SHORT_SHA_LENGTH = 7


def _read_git_sha(start: Path) -> str:
    """Return the short sha of the checked-out commit, or an empty string.

    Reads ``.git/HEAD`` and the ref it names directly. A packed ref (a fresh
    clone that has not written loose refs) is not chased -- the caller falls
    back to ``"dev"``, which is honest about not knowing.
    """
    for directory in (start, *start.parents):
        git_dir = directory / ".git"
        if not git_dir.is_dir():
            continue
        try:
            head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
            if head.startswith("ref:"):
                ref = head.partition(":")[2].strip()
                head = (git_dir / ref).read_text(encoding="utf-8").strip()
            if head:
                return head[:SHORT_SHA_LENGTH]
        except OSError:
            return ""
        return ""
    return ""


@lru_cache
def app_version() -> str:
    """Return the running build's identifier, cached for the process."""
    return settings.version or _read_git_sha(BACKEND_DIR) or DEV_VERSION
