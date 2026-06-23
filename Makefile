.PHONY: install app bot test lint fmt

install:
	uv sync

# Run the FastAPI agent app (serves the agent over HTTP)
app:
	uv run uvicorn trader.agent.app.main:app --reload --port 8000

# Run the Telegram bot (long-polling). Requires the app to be running.
bot:
	uv run python -m trader.bot.main

test:
	uv run pytest -q tests/unit

# LLM smoke tests — real model calls, needs OPENAI_API_KEY in .env
test-llm:
	uv run pytest -q -m llm tests/llm

lint:
	uv run ruff check src tests

fmt:
	uv run ruff format src tests
