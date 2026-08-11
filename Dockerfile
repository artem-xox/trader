# Single image for both components (agent service + telegram worker).
# Each App Platform component overrides the run_command; the default CMD runs the agent.

# The web client is built into the same image rather than deployed as an App
# Platform static site: an app containing a static site cannot turn off edge
# caching, and edge caching is what buffers SSE (docs/WEB.md §7.1). Shipping one
# artifact also means index.html can never be served beside assets from a
# different build.
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim

# uv binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Install dependencies first for better layer caching (project not yet installed).
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

# Install the project itself.
COPY src ./src
RUN uv sync --frozen --no-dev

# Must match `web_dist_dir` in common/config.py, resolved from WORKDIR.
COPY --from=web /web/dist ./web/dist

EXPOSE 8080

# Default: the agent HTTP API. The telegram worker overrides this in the app spec.
CMD ["uv", "run", "uvicorn", "trader.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
