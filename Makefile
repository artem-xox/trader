.PHONY: install app bot test lint fmt eval

install:
	uv sync

# Run the FastAPI agent app (serves the agent over HTTP)
app:
	uv run uvicorn trader.app.main:app --reload --port 8000

# Run the Telegram bot (long-polling). Requires the app to be running.
bot:
	uv run python -m trader.ui.telegram.main

test:
	uv run pytest -q tests/unit

# LLM smoke tests — real model calls, needs OPENAI_API_KEY in .env
test-llm:
	uv run pytest -q -m llm tests/llm

# Run evaluations (one skill: `make eval SKILL=find`; all skills if SKILL unset).
# Optional experiment postfix: `make eval NAME=smarter-models` → trader-{skill}-smarter-models.
# Real model + tool calls; results land in LangSmith. Needs OPENAI/TAVILY/LANGSMITH keys.
eval:
	uv run python -m tests.eval.cli run $(if $(SKILL),--skill $(SKILL),) $(if $(NAME),--name $(NAME),)

lint:
	uv run ruff check src tests

fmt:
	uv run ruff format src tests
