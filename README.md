# AI Trader

A semi-autonomous research assistant for [Polymarket](https://polymarket.com).

Under the hood it's a **custom ReAct agent with a skills layer**, built and validated
around the task of trading prediction markets. A `skills` node routes each turn to one
skill (or to normal mode); the skill decides the planner/guard prompts, the available
tools, and the structured output the agent must produce.

Today two skills are implemented, both read-only:

- **`/find <topic>`** — find, rank and risk-assess interesting markets on a topic.
- **`/analyze <market url>`** — deep dive on a single market with a fair-value + risk model.

Anything else is handled in **normal mode** (a plain assistant). Real order placement is
intentionally out of scope for now.

## Quickstart

```bash
make install                 # uv sync
cp .env.template .env         # fill in OPENAI_API_KEY, TAVILY_API_KEY, TELEGRAM_API_TOKEN
make app                      # FastAPI agent on :8000  (terminal 1)
make bot                      # Telegram bot, long-polling (terminal 2)
```

Then message the bot: `/find AI regulation 2026` or `/analyze <polymarket url>`.

## Tests

```bash
make test        # offline unit tests (no network, no LLM)
make test-llm    # LLM smoke tests (real model calls, needs OPENAI_API_KEY)
make lint        # ruff
```

## Docs

- [docs/DESIGN.md](docs/DESIGN.md) — architecture: the graph, the skills layer, components, models.
- [docs/PLAN.md](docs/PLAN.md) — status, scope and roadmap.
