# AI Trader — Status & Roadmap

What's built, what's in scope, and what's next. For *how it works*, see
[DESIGN.md](DESIGN.md).

---

## 1. Vision

A self-driving trading agent for Polymarket:

- **Long term:** the agent autonomously finds, evaluates, and places bets, manages a
  portfolio, and reports performance.
- **Now:** a semi-autonomous research assistant. The user (via Telegram) asks it to find or
  analyze bets; it runs a skill-routed ReAct loop over web search + Polymarket data and
  returns structured, risk-assessed suggestions. **No real trading yet.**

---

## 2. Current status

The custom ReAct-with-skills agent runs end-to-end locally and is deployed to DigitalOcean.

**Done:**

- Custom LangGraph graph: `skills → planner → guard → executor → responder → verifier`,
  with an iteration budget and a guard/verifier feedback channel.
- Skills layer (`Skill` + `SkillRegistry` + selector node), with first-class normal mode.
  Selection by explicit slash command or LLM intent. One skill per turn.
- Skills: **`find`** (rank interesting bets) and **`analyze`** (deep dive on one market with
  a fair-value + risk model).
- Structured output per skill (`ResearchResult`, `MarketAnalysis`, `GeneralAnswer`) with an
  anti-hallucination verifier (every referenced market id must come from tool output).
- Tools: `polymarket_search`, `polymarket_market` (Gamma API, read-only), `web_search`
  (Tavily), built via a factory and injected at the composition root.
- Two model tiers (strong planner / weak everything else).
- Per-thread memory via a checkpointer (`InMemorySaver` for now).
- FastAPI service (`/agent/invoke` with API-key auth, `/health`) + aiogram Telegram bot.
- Tests: offline (parsers, wiring) + LLM smoke (selection, structured output,
  anti-hallucination, tool use). Tracing to LangSmith.
- Deploy: Dockerized, DigitalOcean App Platform (`.do/app.yaml`).

**Known shortcuts (revisit):**

- Memory is in-process (`InMemorySaver`); lost on restart. Postgres is a one-line swap.
- The guard runs an LLM judge but is permissive for read-only tools — the real value
  arrives with trading skills.
- No persisted `runs` audit table / eval dataset yet.

---

## 3. Scope

**In scope (current):** read-only research and analysis skills, Telegram UX, per-chat
memory, tracing, structured + verified output.

**Out of scope (for now):** placing real orders / wallet / funds (CLOB API), portfolio &
PnL tracking, scheduled/autonomous runs, multi-user accounts beyond a chat-id allowlist.

---

## 4. Roadmap

- **Persistence.** Swap `InMemorySaver` → `PostgresSaver`; add a `runs` audit table.
- **Evaluation.** Curated topic dataset + LLM-as-judge for suggestion/analysis quality;
  CI gate on the anti-hallucination invariant (must stay 100%).
- **More skills.** e.g. `/compare` (rank related markets), `/watch` (track a market over time).
- **Trading phase (`/buy`).** The guard becomes a real approval gate with human-in-the-loop
  confirmation (LangGraph `interrupt()`) before any irreversible action; add positions/orders.
- **Skill ergonomics.** Optionally move "what to verify / how to format" onto the `Skill`
  so the verifier and formatter stop knowing about concrete schemas.

---

## 5. Open questions

- Streaming partial results to Telegram vs. a single final message.
- Per-component model tiers vs. the current strong/weak split.
- Sourcing the eval dataset: handcrafted vs. curated from real LangSmith traffic.
- Rate limiting / concurrency cap on agent runs per user.
