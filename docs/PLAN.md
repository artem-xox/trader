# AI Trader — Design & Plan

Autonomous agent that researches and (later) trades prediction markets on
[Polymarket](https://polymarket.com). The user interacts with it through Telegram.

This document is the living design doc. Keep it updated as decisions change.

---

## 0. Current status

Skeleton is up and a minimal ReAct loop runs locally end-to-end:

- `src/trader/common/config.py` — pydantic-settings config from `.env`.
- `src/trader/agent/core/` — `TradingAgent` (wraps LangGraph prebuilt ReAct agent) +
  `polymarket_search` tool (Gamma API, no auth) + system prompt.
- `src/trader/agent/app/` — FastAPI app: `GET /health`, `POST /agent/invoke`.
- `src/trader/bot/` — aiogram bot (long-polling locally), `/find <topic>` → calls the app.
- Tracing flows to **LangSmith** (verified: traces appear in project `trader`).

**Bootstrap deviations from the target design (to revisit):**
- Observability uses **LangSmith** for now (zero-setup) instead of self-hosted Langfuse.
- Agent uses LangGraph's **prebuilt** `create_react_agent`, not the custom graph yet.
- Telegram runs via **long-polling** locally; webhook is for prod.
- bot → agent over **HTTP** (validates the app/bot split). No Postgres/memory wired yet.

Run locally: `make app` (one terminal) + `make bot` (another), then send `/find <topic>`.

---

## 1. Vision

A self-driving trading agent for Polymarket:

- **Long term:** the agent autonomously finds, evaluates, and places bets, manages a
  portfolio, and reports performance.
- **Now (v1):** a research assistant. The user asks (via Telegram) to find interesting
  bets on a topic; the agent runs a short ReAct loop over web search + Polymarket data
  and returns ranked suggestions with rationale. **No real trading in v1.**

---

## 2. Scope

### In scope (v1)
- ReAct agent loop with tools.
- `web_search` tool (Tavily).
- `polymarket_*` read-only tools (Gamma API): search markets, fetch market detail.
- Telegram command: "find interesting bets on topic X" → agent loops → returns
  ranked suggestions.
- Postgres-backed agent memory (conversation state per chat).
- Observability: full tracing of every agent step (Langfuse).
- Eval harness: offline dataset + LLM-as-judge for suggestion quality.
- Deploy on DigitalOcean.

### Out of scope (v1)
- Placing real orders / trading / wallet / funds management (CLOB API).
- Portfolio tracking, PnL, position management.
- Scheduled/autonomous runs (only user-triggered for now).
- Multi-user accounts / auth beyond a Telegram allowlist.
- Fine-grained risk models.

---

## 3. Tech stack (decided)

| Concern            | Choice                                   |
|--------------------|------------------------------------------|
| Agent framework    | LangGraph + LangChain                    |
| LLM provider       | **OpenAI**                               |
| Web search         | **Tavily**                               |
| Market data        | Polymarket **Gamma API** (read-only)     |
| Chat interface     | Telegram via **aiogram**                 |
| Service            | FastAPI (async)                          |
| Memory / DB        | Postgres (LangGraph checkpointer + runs) |
| Observability      | **Langfuse** (self-hosted)               |
| Deploy             | DigitalOcean                             |
| Language / tooling | Python 3.12, `uv`, ruff, pytest          |

---

## 4. Architecture

```
              ┌──────────────┐
  Telegram ──▶│  aiogram      │
   user       │  webhook      │
              └──────┬───────┘
                     │ POST /telegram/webhook
              ┌──────▼─────────────────────────────┐
              │            FastAPI service          │
              │  ┌──────────────────────────────┐   │
              │  │  Agent Runner                 │   │
              │  │  (LangGraph ReAct graph)      │   │
              │  │   LLM ⇄ tools loop            │   │
              │  └───────┬───────────────┬──────┘   │
              │          │               │          │
              │   ┌──────▼─────┐   ┌─────▼───────┐  │
              │   │ web_search │   │ polymarket  │  │
              │   │  (Tavily)  │   │ (Gamma API) │  │
              │   └────────────┘   └─────────────┘  │
              └──────┬───────────────────┬─────────┘
                     │                   │
             ┌───────▼──────┐    ┌───────▼────────┐
             │   Postgres    │    │   Langfuse     │
             │ checkpointer  │    │  (tracing)     │
             │ + runs log    │    │                │
             └──────────────┘    └────────────────┘
```

### Components

1. **Telegram layer (aiogram).** Receives updates via webhook. Parses commands, maps
   `chat_id` → agent `thread_id`. Sends "working…" ack immediately, then delivers the
   final answer (long-running agent runs in a background task). Allowlist of chat IDs.

2. **FastAPI service.** Hosts everything in one deployable process for v1.
   - `POST /telegram/webhook` — Telegram updates.
   - `GET /health` — liveness for DO.
   - Owns the agent runner, DB pool, and Langfuse client.

3. **Agent runner (LangGraph).** A ReAct loop with a hard iteration cap. See §5.

4. **Tools.** `web_search`, `polymarket_search`, `polymarket_market_detail`. See §6.

5. **Postgres.** LangGraph checkpointer (per-thread conversation state) + a `runs`
   audit table. See §7.

6. **Langfuse.** Traces every LLM call and tool call (inputs, outputs, tokens,
   latency). Used both for debugging and as a source for eval data.

---

## 5. Agent design

### Loop
- Custom LangGraph graph (not the off-the-shelf `create_react_agent`) for control over
  iteration limits and final output formatting:
  - `agent` node: LLM call with bound tools.
  - `tools` node: executes requested tool calls.
  - Conditional edge: if the LLM emitted tool calls → `tools` → back to `agent`;
    else → `END`.
- **Hard cap** on iterations (`recursion_limit`, e.g. 8) so the "small loop" stays small.
- Final node enforces a **structured suggestion output** (see below).

### State (graph state)
- `messages`: running conversation (LangGraph `add_messages`).
- `topic`: the user's requested topic.
- `suggestions`: structured list produced at the end.
- `iteration` / budget counters.

### System prompt (role)
"You are a prediction-market research analyst. Given a topic, find relevant Polymarket
markets, gather context via web search, and evaluate each candidate on: relevance to the
topic, implied probability vs. your read of reality (edge), liquidity/volume, and time
horizon. Never invent markets — only suggest markets returned by the polymarket tools.
Return a ranked shortlist with a one-line rationale each."

### Output contract (per suggestion)
```json
{
  "market_id": "...",
  "question": "...",
  "url": "...",
  "implied_probability": 0.62,
  "liquidity": 12000,
  "ends_at": "2026-09-01",
  "rationale": "Short why-this-is-interesting",
  "confidence": "low|medium|high"
}
```

### Guardrails
- Validate every suggested `market_id` against tool results before returning
  (anti-hallucination).
- Iteration budget + per-run wall-clock timeout.
- Token/cost ceiling per run (logged, soft-enforced).

---

## 6. Tools

### `web_search(query: str, max_results: int = 5)`
- Tavily API. Returns title, url, snippet, published date.
- Used for context/news around the topic to inform edge assessment.

### `polymarket_search(query: str, limit: int = 10, active_only: bool = True)`
- Gamma API (`https://gamma-api.polymarket.com`). Returns markets matching the query:
  id, question, url, outcome prices (implied probabilities), volume/liquidity, end date,
  active/closed flags.

### `polymarket_market_detail(market_id: str)`
- Full detail for one market: outcomes, current prices, volume, resolution criteria,
  end date.

**Notes**
- Gamma API is public/read-only — no auth or wallet needed for v1.
- Normalize all prices to implied probabilities (0–1) in the tool layer so the LLM
  reasons in one consistent unit.
- Add light caching (per-run) to avoid duplicate calls within a loop.

---

## 7. Data model (Postgres)

1. **LangGraph checkpointer tables** — managed by `langgraph-checkpoint-postgres`
   (`PostgresSaver`). Stores per-`thread_id` conversation state. We don't hand-write
   these; the library migrates them.

2. **`runs`** — one row per agent invocation (audit + eval source):
   ```
   id              uuid pk
   thread_id       text
   chat_id         bigint
   topic           text
   status          text         -- running | done | error
   suggestions     jsonb        -- final structured output
   tool_calls      jsonb        -- list of {tool, args, latency_ms}
   tokens_input    int
   tokens_output   int
   cost_usd        numeric
   latency_ms      int
   error           text
   created_at      timestamptz
   ```

3. **(Later)** `markets_cache`, `positions`, `orders` — for trading iterations.

---

## 8. API surface (FastAPI)

| Method | Path                  | Purpose                              |
|--------|-----------------------|--------------------------------------|
| POST   | `/telegram/webhook`   | Receive Telegram updates             |
| GET    | `/health`             | Liveness/readiness for DO            |
| GET    | `/runs/{id}`          | (Internal/debug) inspect a run       |

Agent execution is kicked off as an asyncio background task from the webhook handler so
the webhook returns fast; the result is pushed back to Telegram when ready.

---

## 9. Telegram UX

- Commands:
  - `/find <topic>` — research bets on a topic.
  - `/start`, `/help` — usage.
- Flow:
  1. User: `/find AI regulation 2026`.
  2. Bot: "🔎 Researching…" (immediate ack).
  3. Agent loops.
  4. Bot: ranked suggestions (markdown), each with question, implied %, liquidity,
     end date, 1-line rationale, and a Polymarket link.
- Access control: allowlist of chat IDs in config (env). Non-allowlisted → polite deny.

---

## 10. Observability (Langfuse, self-hosted)

- Self-host Langfuse in DO (Docker, its own Postgres or schema).
- Instrument via LangChain callback handler → every LLM call, tool call, prompt,
  completion, token count, and latency becomes a Langfuse trace tied to a `thread_id`.
- Tag traces with `topic` and `run_id` to join with the `runs` table.
- Use Langfuse to: debug loops, watch cost/latency, and curate eval datasets from real
  traffic.

---

## 11. Evaluation

- **Dataset:** 10–20 curated topics (varied: politics, crypto, sports, tech), stored as
  a fixture (`evals/dataset.jsonl`).
- **Run:** execute the agent on each topic offline.
- **Judges (LLM-as-judge + heuristics):**
  - *Validity:* every suggested market actually exists in Polymarket results (hard check
    against tool output — no hallucinated markets).
  - *Relevance:* suggestions match the topic (LLM judge, 1–5).
  - *Rationale quality:* rationale is grounded and non-generic (LLM judge, 1–5).
  - *Loop health:* iterations ≤ cap, latency and cost within budget.
- **Where:** runnable locally and in CI; results logged to Langfuse for tracking over
  time. Gate: no regression on validity (must stay 100%).

---

## 12. Deployment (DigitalOcean)

- Containerize the FastAPI service (Docker).
- Options: DO App Platform (simplest) or a Droplet + docker-compose.
  - **v1 recommendation:** Droplet + `docker-compose` running: app, Langfuse, Postgres
    (managed DO Postgres preferred for the app DB; Langfuse can share or have its own).
- Telegram webhook → public HTTPS URL (DO provides; or Caddy/Traefik for TLS on a
  Droplet).
- Secrets via env (`.env` not committed). See §13.

---

## 13. Configuration & secrets

Env vars (load via pydantic-settings):
- `OPENAI_API_KEY`, `OPENAI_MODEL`
- `TAVILY_API_KEY`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_IDS`
- `DATABASE_URL`
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`
- `AGENT_MAX_ITERATIONS`, `AGENT_RUN_TIMEOUT_S`, `AGENT_COST_CEILING_USD`

---

## 14. Proposed repo structure

```
trader/
├── app/
│   ├── main.py              # FastAPI app, routes, lifespan
│   ├── config.py            # pydantic-settings
│   ├── telegram/            # aiogram bot, handlers, formatting
│   ├── agent/
│   │   ├── graph.py         # LangGraph ReAct graph
│   │   ├── state.py         # graph state schema
│   │   ├── prompts.py       # system prompt(s)
│   │   └── runner.py        # invoke + background execution + runs logging
│   ├── tools/
│   │   ├── web_search.py
│   │   └── polymarket.py
│   ├── db/
│   │   ├── pool.py
│   │   ├── runs.py          # runs table CRUD
│   │   └── migrations/
│   └── observability/
│       └── langfuse.py
├── evals/
│   ├── dataset.jsonl
│   └── run_eval.py
├── docs/
│   └── PLAN.md
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── README.md
```

---

## 15. Milestones

- **M0 — Skeleton.** Repo scaffolding, config, FastAPI `/health`, Postgres pool, CI.
- **M1 — Tools.** `web_search` + `polymarket_*` working and unit-tested against live APIs.
- **M2 — Agent loop.** LangGraph ReAct graph with iteration cap + structured output;
  runnable from a script.
- **M3 — Telegram.** aiogram webhook, `/find`, background execution, formatted replies.
- **M4 — Memory + runs.** Checkpointer wired, `runs` table populated.
- **M5 — Observability.** Langfuse self-hosted + tracing end-to-end.
- **M6 — Eval.** Dataset + judges + CI gate on validity.
- **M7 — Deploy.** docker-compose on DO, webhook live, smoke test.

---

## 16. Open questions / decisions to revisit

- Streaming partial results to Telegram vs. single final message?
- Managed DO Postgres vs. self-managed in compose for the app DB.
- Model tier per node (cheaper model for tool-deciding, stronger for final synthesis)?
- How to source the eval dataset — handcrafted vs. curated from real Langfuse traffic.
- Rate limiting / concurrency cap on agent runs per user.
