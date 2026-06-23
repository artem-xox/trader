# Single image for both components (agent service + telegram worker).
# Each App Platform component overrides the run_command; the default CMD runs the agent.
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

EXPOSE 8080

# Default: the agent HTTP API. The telegram worker overrides this in the app spec.
CMD ["uv", "run", "uvicorn", "trader.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
