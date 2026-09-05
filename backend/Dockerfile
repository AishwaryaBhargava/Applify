# Alternative to render.yaml: the same service as a container, for any host
# that takes an image (Render's Docker runtime, Fly, Cloud Run, a local run).
#
# Build and run from this directory:
#   docker build -t applify-api .
#   docker run --rm -p 8000:8000 --env-file .env applify-api
FROM python:3.11-slim

# PYTHONUNBUFFERED matters here: without it Python blocks up its stdout, and
# the logs this app writes would reach the platform in delayed batches -- or
# not at all, if the process dies first.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# Copied and installed before the source so an edit to the application does not
# invalidate the dependency layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root, and owning nothing it does not need to: the application writes no
# files at runtime (resumes are parsed in memory and discarded), so the source
# tree is read-only to the process running it.
RUN useradd --create-home --uid 10001 applify \
    && chown -R applify:applify /app
USER applify

EXPOSE 8000

# Migrations first, and the `&&` is deliberate: a failed migration must stop
# the container rather than serve an app against an old schema. $PORT is read
# here rather than in code, so the same image runs anywhere.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
