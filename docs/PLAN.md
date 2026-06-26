# AI Trader — Status & Roadmap

What's built, what's in scope, and what's next. For *how it works*, see
[DESIGN.md](DESIGN.md). The roadmap below is **research-driven**: it operationalises
[knowledges/research-gpt-20260626.md](knowledges/research-gpt-20260626.md), a study of
Polymarket's CLOB V2 venue and the public agent landscape.

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
  with an iteration budget and a guard/verifier feedback channel. The executor is LangGraph's
  `ToolNode` (per-tool error capture); the LLM nodes carry a `RetryPolicy` for transient API
  failures.
- Skills layer (`Skill` + `SkillRegistry` + selector node), with first-class normal mode.
  Selection by explicit slash command or LLM intent. One skill per turn.
- Skills: **`find`** (rank interesting bets) and **`analyze`** (deep dive on one market with
  a fair-value + risk model).
- Structured output per skill (`ResearchResult`, `MarketAnalysis`, `GeneralAnswer`) with an
  anti-hallucination verifier (every referenced market id must come from tool output).
- Tools: `polymarket_search`, `polymarket_market` (Gamma API, read-only), `web_search`
  (Tavily), plus general read-only helpers (`calculator`, `current_datetime`, `web_fetch`),
  built via a factory and injected at the composition root.
- Two model tiers (strong planner / weak everything else).
- Per-thread memory via a checkpointer (`InMemorySaver` for now).
- FastAPI service (`/agent/invoke` with API-key auth, `/health`) + aiogram Telegram bot.
- Tests: offline (parsers, wiring) + LLM smoke (selection, structured output,
  anti-hallucination, tool use). Tracing to LangSmith.
- Eval harness (`tests/eval/`, CLI): per-skill YAML datasets; evaluators `grounding`,
  `routing`, `tool_calls`, `quality` (LLM-judge), `depth` (LLM-judge); LangSmith backend
  behind a vendor-neutral `EvalBackend` protocol; `add-case` from traces.
- Deploy: Dockerized, DigitalOcean App Platform (`.do/app.yaml`).

**Known shortcuts (revisit):**

- Memory is in-process (`InMemorySaver`); lost on restart. Postgres is a one-line swap.
- The guard runs an LLM judge but is permissive for read-only tools — the real value
  arrives with trading skills.
- No persisted `runs` audit table yet.

---

## 3. The core gap (why the roadmap below)

We read **only the Gamma API** — Polymarket's discovery surface. The research's central
empirical finding is that on the current CLOB V2 venue, **execution and cost discipline
matter as much as forecasting**: successful traders provide liquidity with limit orders,
poorer traders take liquidity; and "pure LLM narrative trading without a disciplined cost
model is weak."

By that yardstick our agent today is exactly the weak pattern: it judges "edge" narratively
(implied probability vs. the model's read of the news) with **no spread, depth, slippage, or
fee model**. `MarketAnalysis` returns `fair_probability` and an `edge` string but nothing
*execution-ready* — no all-in EV, no sizing.

The roadmap closes that gap **while staying read-only**: add the CLOB data the cost model
needs, make `analyze`/`find` cost-aware, add a portfolio skill, then upgrade evaluation.
Real order placement stays deferred to a clearly-gated later phase.

---

## 4. Scope

**In scope (current + near-term):** read-only research, analysis, and portfolio skills;
CLOB **read** data (order book, spread, depth, price history); cost/EV/sizing models;
Telegram UX; per-chat memory; tracing; structured + verified output.

**Out of scope (deferred to Phase 5):** placing real orders / wallet / funds (CLOB order
management, Relayer), live WebSocket subscriptions, market-making, portfolio PnL tracking
against real positions, scheduled/autonomous runs, multi-user accounts beyond a chat-id
allowlist.

---

## 5. Roadmap (phased)

Sequencing decided 2026-06-25: **Phase 0 first** (it unblocks the rest), then skills in
**`analyze → find → distribute`** order (the cost model built in `analyze` is reused by the
other two). All phases are read-only; trading is Phase 5 and is not built until 0–4 land.

Each phase states its **success criteria** so the work can loop to "done" independently.

### Phase 0 — CLOB read-only data client *(foundation)*

The prerequisite for everything else: pull live price-formation data, not just Gamma's
editorial/venue metadata.

- New `core/clients/clob/` — a pure HTTP wrapper over CLOB REST (base
  `https://clob.polymarket.com`): `/book`, `/midpoint`, `/spread`, `/prices-history`.
  **REST snapshots only — no WebSocket yet.**
- Normalize the mixed schema at the edge (CLOB returns string numerics for price/size/
  tick_size); keep a canonical internal shape.
- Pure derived metrics (no LLM): `spread_bps`, `depth_within_2_ticks_usd`,
  `realised_vol` over 5m/1h/24h from price history, `mid`.
- New tool `polymarket_orderbook(token_id)` → compact JSON. The `token_id` comes from
  Gamma's `clobTokenIds` field, which we already receive — wire it through `parse_market`.
- **Success criteria:**
  - offline test: parser turns a fixed `/book` fixture into the canonical shape +
    correct `spread_bps` / `depth_within_2_ticks`.
  - `-m live` test: against a liquid market, `book`/`midpoint`/`spread` return sane values
    and `mid` ≈ midpoint endpoint.
- ⚠️ **CLOB V2 caveat:** the 28 Apr 2026 cutover killed V1 SDKs and changed contracts/fees/
  collateral. Verify endpoint paths against docs.polymarket.com (via `web_fetch`) before
  coding; treat fee schedule and routes as runtime config, not constants.

### Phase 1 — cost-aware `/analyze` *(highest ROI)*

Turn the deep dive into an *execution-ready* trade plan. The cost model built here becomes
the shared core for `find` and `distribute`.

- Extend `MarketAnalysis` with:
  - `cost_model { fee_per_share, slippage_per_share, all_in_cost_per_share }`
  - `ev { yes_net_per_share, no_net_per_share }` — `EV = q̂ − price − fees − slippage`.
  - `sizing { kelly_fraction_raw, kelly_fraction_used, recommended_notional_usd, max_shares }`
    — fractional Kelly, default ¼–½, scaled down when calibration/correlation worsens.
  - `execution_hint: maker | taker | no_trade`.
- **Slippage is computed deterministically from the book** (walk the levels), not by the
  LLM. Fees follow Polymarket's `baseRate × min(price, 1−price) × size` taker formula with
  category base rates. The existing `calculator` tool can cross-check EV/Kelly arithmetic.
- Planner prompt: "market price is a prior, not truth; recommend `no_trade` if the edge
  disappears after costs or confidence is below the floor."
- **Success criteria:**
  - new eval cases where edge survives narratively but dies after fees+slippage → stance
    must be `pass` / `execution_hint=no_trade`.
  - a deterministic evaluator checks EV arithmetic is internally consistent (EV equals
    `q̂ − all_in_cost` within tolerance).

### Phase 2 — tradability `/find`

Rank by **tradability + net edge**, not narrative appeal.

- Composite score `S = 0.30·L + 0.25·E + 0.15·V + 0.20·I + 0.10·T`
  (liquidity quality, net edge after cost, realised volatility, information-flow intensity,
  time-to-resolution fit), built on the Phase 0 CLOB metrics.
- **Hard filters applied before scoring:** spread wider than max; top-of-book depth below a
  multiple of intended size; stale book timestamp; geoblocked; sports market too close to
  start. Rejected markets are summarised by reason, not silently dropped.
- Extend `Suggestion` with `spread_bps`, `depth_usd`, `find_score`,
  `maker_or_taker_preference`.
- **Success criteria:** eval case "loud but untradeable" (wide spread / thin depth) is
  filtered out, not ranked top; a genuinely tradable market with modest narrative beats it.

### Phase 3 — new `/distribute` skill

Treat positions as a **correlated portfolio of binary claims**, not a list of isolated
edges.

- New skill module (prompts + schema + tools, registered in `skills/__init__.py`) — no
  graph changes, per the skills design.
- Input: analyzed candidates (EV, confidence, liquidity, sizing). Output: target weights +
  concrete rebalance actions + a risk summary.
- **Hard caps:** single market 0.5–2% NAV; event-cluster 3–8% across linked markets on the
  same real-world event; illiquid exposure ≤ 10–20% of depth within two ticks;
  correlation cap on shared-driver markets; keep dry powder for new catalysts.
- Clustering starts simple — by Gamma `event` id / category — before any covariance model.
- **Success criteria:** eval case with two markets on the same event lands them in one
  cluster and binds the cluster cap; total allocation respects single-market and cash caps.

### Phase 4 — evaluation: forecasting vs. trading

Measure forecast quality separately from trading quality.

- New dataset of **already-resolved** markets (known outcome) → deterministic
  **Brier / log-loss / calibration** evaluators for `analyze`'s `fair_probability`.
- Treat the V2 cutover (Apr 2026) as a regime boundary in any historical data
  (regime-split backtests); never assume frictionless fills.
- Keep the existing `quality`/`depth` LLM judges for prose; add the quantitative track
  alongside.
- **Success criteria:** `make eval SKILL=analyze` prints a calibration curve / Brier score
  over the resolved-markets set.

### Phase 5+ — trading `/buy` *(deferred — record only, do not build yet)*

Only after 0–4. The guard becomes a real approval gate. Order of operations:
geoblock gate → server-side key custody → human-in-the-loop confirmation (LangGraph
`interrupt()`) before any irreversible action → heartbeat dead-man loop + restart-aware
logic (HTTP 425, post-only windows) + stale-book detection → maker-first execution. Adds
positions/orders, the Relayer split/merge/redeem path, and live WebSocket. **Explicitly not
taken now:** market-making / Avellaneda–Stoikov, naïve spread capture.

### Independent of phases

- **Persistence.** Swap `InMemorySaver` → `PostgresSaver`; add a `runs` audit table.
- **Eval breadth.** More cases, a `normal` dataset, CI gate on `grounding == 1.0`.
- **Skill ergonomics.** Optionally move "what to verify / how to format" onto the `Skill`
  so the verifier and formatter stop knowing about concrete schemas.

#### LangGraph features to adopt

Our graph already uses `StateGraph`, the `add_messages` reducer, conditional edges, and a
checkpointer. These are the unused capabilities worth pulling in, each tied to the phase it
serves. *(Done: `ToolNode` now backs the executor; `RetryPolicy` wraps the LLM nodes.)*

- **Human-in-the-loop guard via `interrupt()` — gates Phase 5.** Today the guard is a
  permissive stub. When trading tools land, make it a real approval gate with LangGraph
  `interrupt()`: the graph pauses on the checkpointer, the proposed order is surfaced to the
  user in Telegram, and the run resumes via `Command(resume=...)` on approval. The
  checkpointer + `thread_id` plumbing this needs already exists, so no bespoke approval
  state machine — this is the natural mechanism for the Phase 5 "human-in-the-loop
  confirmation before any irreversible action" step. (See Phase 5+.)
- **Streaming to Telegram — serves the UX open question, useful from Phase 1 on.** Replace
  the single `invoke()` blob with `graph.astream(stream_mode="updates")` to push progress
  ("selected skill → searching markets → checking order book") during long `find`/`analyze`
  loops, and `get_stream_writer()` (`stream_mode="custom"`) to emit custom status lines from
  inside the planner. Resolves the "streaming partial results vs. one final message" open
  question without a rewrite.
- **`Send` fan-out (map-reduce) — serves Phase 2/3.** When `distribute` allocates across N
  markets and `find` analyses several candidates, use LangGraph's `Send` to dispatch N
  parallel per-market sub-runs and fan the results back in, instead of a hand-rolled
  `asyncio.gather` inside one node. The graph is strictly sequential today; `Send` is the
  idiomatic way to parallelise the multi-market work those skills introduce.
- **`BaseStore` cross-thread memory — serves cost-aware personalisation.** The checkpointer
  persists one `thread_id`'s history; `langgraph.store.BaseStore` adds cross-thread memory
  (user risk profile, prior recommendations, budget) that `analyze`/`distribute` can read to
  tailor sizing across conversations. Pairs with the Persistence item above (Postgres-backed
  store).

---

## 6. Compliance & security notes (carry into Phase 5)

Recorded now so they are not forgotten when trading is built:

- **Jurisdiction.** Availability is jurisdiction-dependent; Polymarket prohibits US persons
  and certain other jurisdictions from trading via UI or API, **including agents**. Enforce
  the geoblock check before any execution.
- **Key custody.** Private keys and L2 API secrets belong in server-side env / KMS, never
  client-side; separate research workers from signing workers.
- **Market-abuse stance.** Public-information only; no insider/leaked data, no spoofing or
  quote-stuffing, human review when apparent edge comes from unexplained order-flow
  anomalies rather than verifiable public information.

---

## 7. Open questions

- Streaming partial results to Telegram vs. a single final message.
- Per-component model tiers vs. the current strong/weak split.
- Whether `/find`'s information-flow term `I` warrants a lightweight anomaly/"tremor"
  signal, or stays a simple trade-count/order-imbalance heuristic for now.
- Rate limiting / concurrency cap on agent runs per user.
