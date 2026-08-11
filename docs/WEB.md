# AI Trader — Web UI (design & plan)

A single-user web client for the agent at **https://trader.iamxox.space**: a chat with a
conversation sidebar, live run progress, and rich Polymarket cards instead of chat markdown.

This document is both the design and the build plan. For the agent itself see
[DESIGN.md](DESIGN.md); for the agent roadmap see [PLAN.md](PLAN.md).

---

## 1. Goals & non-goals

**Goals**

1. **Conversations in a sidebar** — list, open, rename, delete; history survives restarts and
   is the same on laptop and phone.
2. **Market widgets** — every suggested/analyzed market renders as a card (probability,
   tradability metrics, sparkline, risk) instead of a markdown bullet.
3. **Live progress** — the same "searching markets → reading the order book → writing the
   answer" trail Telegram shows today, but as a step list.
4. **Deploy parity with farkle** — DigitalOcean App Platform, spec in the repo, applied by
   GitHub Actions after tests, custom domain via Cloudflare.

**Non-goals (explicit)**

- Multi-user accounts, sign-up, roles. One person, one shared secret.
- Trading actions in the UI. The agent stays read-only (PLAN.md Phase 5 gates that).
- Replacing Telegram. Both clients keep working against the same agent.
- Mobile app, offline mode, PWA install, i18n.

---

## 2. Decisions

| # | Decision | Why |
|---|----------|-----|
| D1 | **History in managed Postgres**, not the browser | The sidebar must be the same on every device, and it closes the `InMemorySaver` shortcut in PLAN.md §2 in the same move. |
| D2 | **One environment (`trader-prod`)** | farkle's dev app is free because it is static; here a second app duplicates a paid service *and* a paid worker. CI still gates deploys on tests. |
| D3 | **Shared secret via `X-API-Key`** | Already implemented server-side (`AGENT_API_KEY`, `app/main.py:35`). Zero backend work: a key screen writes it to `localStorage`, every request carries the header. |
| D4 | **The SPA is served by FastAPI**, not by a separate static-site component | See §7.1 — App Platform *cannot disable edge caching for apps that contain a static site*, and edge caching is the documented cause of SSE arriving as one buffered chunk. Keeping the app static-site-free keeps that escape hatch open. Also: no CORS, no version skew between `index.html` and the API. |
| D5 | **The server writes the transcript, not the client** | The streaming endpoint persists the user message before the run and the assistant message when the run ends. Closing the tab mid-run no longer loses the answer. |
| D6 | **The UI renders `result` (structured), not `response` (markdown)** | `ResearchResult` / `MarketAnalysis` already carry everything a card needs. `app/formatting.py` stays what it is: the chat-markdown renderer for Telegram. |
| D7 | **Hand-written TS types**, mirroring the pydantic models | Three small schemas, changed rarely. `openapi-typescript` generation is blocked by `SerializeAsAny[SkillResult]` collapsing the union in the OpenAPI schema; not worth reshaping the API for. |

---

## 3. Architecture

```
                    Cloudflare DNS (CNAME, DNS-only / grey cloud)
                              trader.iamxox.space
                                      │
                    ┌─────────────────▼──────────────────┐
                    │  DigitalOcean App Platform          │
                    │  app: trader-prod (region fra)      │
                    │                                     │
   browser ────────▶│  service: agent  (Dockerfile)       │
   React SPA        │    FastAPI                          │
                    │    ├─ /            → SPA (static)   │
                    │    ├─ /api/*       → web BFF        │
                    │    ├─ /agent/*     → agent API      │
                    │    └─ /health                       │
                    │              │            │         │
                    │  worker: telegram          │        │
                    │    aiogram ──PRIVATE_URL───┘        │
                    │                             │       │
                    │  database: db (PG, dev tier)◀┘      │
                    └─────────────────────────────────────┘
                                      │
                    Gamma API · CLOB API · Tavily · OpenAI · LangSmith
```

One process serves the SPA, the web BFF and the agent API. The Telegram worker is untouched
and keeps calling `${agent.PRIVATE_URL}/agent/stream` over the internal network.

---

## 4. What is reused (the "малой кровью" ledger)

The three headline features are mostly **already built**:

| Requirement | Exists today | Work needed |
|---|---|---|
| Live progress | `POST /agent/stream` emits semantic `ProgressEvent`s (`core/models/streaming.py`); Telegram renders them as one edited message | Frontend only: a different renderer for the same event stream |
| Market cards | `Suggestion` carries `market_id`, `question`, `url`, `implied_probability`, `spread_bps`, `depth_usd`, `find_score`, `maker_or_taker`, `confidence`, `risk`; `MarketAnalysis` adds `fair_probability`, `stance`, `key_factors`, `resolution_criteria` | Frontend components + one read-only enrichment endpoint (image, volume, end date, price history) |
| Auth | `_require_api_key` + `AGENT_API_KEY` | Frontend key screen |
| Conversation threading | `thread_id` already scopes per-chat memory through the checkpointer | Make `thread_id` a conversation UUID; swap the checkpointer to Postgres |
| Deploy | `.do/app.yaml`, `Dockerfile`, DO app already live | Add SPA build stage, DB, domain, CI-gated deploy |

Net new backend code is roughly **250–300 lines** (store + two routers + a Dockerfile stage).
Everything else is the frontend.

---

## 5. Backend

### 5.1 API surface

Existing endpoints keep their paths and contracts. Everything new lives under `/api` and is
gated by `X-API-Key`.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/conversations` | List `{id, title, updated_at, message_count}`, newest first |
| POST | `/api/conversations` | Create an empty conversation → `{id, title}` |
| GET | `/api/conversations/{id}` | Full transcript: `{id, title, messages: [{id, role, content, result, trace_url, created_at}]}` |
| PATCH | `/api/conversations/{id}` | Rename (`{title}`) |
| DELETE | `/api/conversations/{id}` | Delete transcript **and** the agent's checkpoints for that thread |
| POST | `/api/conversations/{id}/turns` | **The write path.** Body `{message, debug}`. Streams SSE (`status` … `final`/`error`) and persists both messages |
| GET | `/api/markets/{market_id}` | Card enrichment (image, volume, end date, price history), `Cache-Control: public, max-age=60` |
| GET | `/api/health`, POST `/api/stream-probe` | Delivery-path probes (Phase 0): the API answers under `/api`, and SSE is not buffered |
| GET | `/health` | Unchanged (used by the App Platform health check) |
| POST | `/agent/invoke`, `/agent/stream` | Unchanged — Telegram and the eval harness keep using these |

`GET /`, `/assets/*` and any unmatched path serve the SPA (mounted last, so API routes win).

### 5.2 Persistence

Two things go to Postgres, for two different reasons.

**a) The agent's own memory** — swap `InMemorySaver` → `AsyncPostgresSaver`
(`langgraph-checkpoint-postgres`). `bootstrap.build_agent()` already takes a `checkpointer`
argument, so this is a change at the call site in the FastAPI lifespan, not in the core.
Tests and the eval harness pass no checkpointer and keep the in-memory default.

**b) The transcript the UI renders** — our own two tables. The checkpointer stores LangChain
messages; it does not store the `SkillResult` the cards are built from, and reconstructing a
card from a checkpoint would be fragile. The duplication is deliberate and small.

```sql
create table if not exists conversations (
    id         uuid primary key,
    title      text        not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists messages (
    id              bigserial   primary key,
    conversation_id uuid        not null references conversations(id) on delete cascade,
    role            text        not null check (role in ('user', 'assistant')),
    content         text        not null,   -- user text, or the assistant's markdown summary
    result          jsonb,                  -- the SkillResult; assistant rows only → cards
    trace_url       text,
    created_at      timestamptz not null default now()
);

create index if not exists messages_conversation_idx on messages (conversation_id, id);
```

- **`thread_id` = `conversation_id`.** A new chat is a new row and therefore a new agent
  thread — no epoch trick like the Telegram bot's `chat:epoch`.
- **Migrations:** an idempotent `schema.sql` executed at startup, mirroring how
  `AsyncPostgresSaver.setup()` migrates its own tables. Two tables do not justify Alembic.
  Revisit if a third table or a destructive change appears.
- **Title:** the first user message trimmed to 60 chars, renameable. No LLM call.
- **Pools:** the store and the checkpointer each get a small `psycopg_pool` (max 3). A dev
  database has a low connection cap; two modest pools stay well under it.
- **Deleting a conversation** also calls the checkpointer's thread deletion, so checkpoint
  rows don't outlive their conversation.

### 5.3 Streaming contract

`POST /api/conversations/{id}/turns` is `/agent/stream` plus persistence:

```
insert user message ──▶ agent.astream(thread_id=conversation_id)
                              │
                     status frames ──▶ browser (progress trail)
                              │
                     final ──▶ insert assistant message (content + result + trace_url)
                              │
                              └──▶ final frame (response, result, trace_url) ──▶ browser
```

The tracing modes in `_agent_sse` (no key / compressed / debug) are identical, so that
generator moves to `app/streaming.py` and both routers call it — with an `on_final` hook for
the persistence write. Wire-level details:

- Response headers `Cache-Control: no-cache`, `X-Accel-Buffering: no`, `Connection: keep-alive`.
- A `: keepalive` comment frame every 15 s while the agent is quiet, so idle-connection
  timeouts along the path don't kill a long `find` run.
- The browser reads it with `fetch` + `ReadableStream` (not `EventSource` — that is GET-only).
- **Degradation is safe:** if something upstream buffers the response, the trail simply
  doesn't animate and the whole thing lands at once. The answer is never lost, because the
  server — not the client — writes it (D5).

### 5.4 Market enrichment for cards

`Suggestion` has no image, volume, or end date, so cards hydrate lazily from one read-only
endpoint that reuses the existing clients:

```
GET /api/markets/{market_id}
{
  "market_id": "512345",
  "question": "...",
  "url": "https://polymarket.com/event/...",
  "image": "https://polymarket-upload.../x.png",
  "outcomes": [{"name": "Yes", "price": 0.62}, {"name": "No", "price": 0.38}],
  "volume": 1234567.0, "volume_24h": 45678.0, "liquidity": 89012.0,
  "ends_at": "2026-11-03T00:00:00Z", "closed": false,
  "history": [[1754870400, 0.61], [1754874000, 0.62], ...]   // best-effort, YES token
}
```

- Gamma lookup by id, then CLOB `prices_history` for the YES token — best-effort, exactly
  like `orderbook_snapshot` treats history today.
- `GammaMarket` gains parsing for `image`, `volume_24h` and `clob_token_ids` plus a new
  `to_card()` serializer. **`to_summary()` / `to_detail()` are not touched** — the agent's
  tool output must not grow noise fields it will never reason over.
- Caching is an HTTP header, not code. If Gamma starts rate-limiting, add a TTL cache then.

### 5.5 Auth

`_require_api_key` already covers every new router. The frontend shows a key screen when
`localStorage.traderKey` is missing or a request returns 401. Honest limitations, accepted
for a single-user tool:

- The secret lives in the browser; rotating it means editing one env var and re-entering it.
- It is not a session — no expiry, no revocation list.
- The upgrade path, if this ever gets shared, is Cloudflare Access in front (§7.3 note).

### 5.6 Code map (new / changed)

```
src/trader/
├── app/
│   ├── main.py           ~ lifespan: pools + Postgres checkpointer; mount routers; mount SPA
│   ├── streaming.py      + the SSE generator extracted from main.py, with an on_final hook
│   ├── store.py          + psycopg pool, schema.sql bootstrap, conversation/message queries
│   ├── schemas.py        ~ + Conversation, Message, TurnRequest
│   ├── conversations.py  + APIRouter: CRUD + POST /turns
│   ├── markets.py        + APIRouter: GET /markets/{id}
│   └── formatting.py     unchanged (Telegram markdown)
├── common/config.py      ~ + database_url, web_dist_dir
└── core/
    ├── bootstrap.py      unchanged (already accepts a checkpointer)
    ├── models/domain.py  ~ + `kind` discriminator (see below)
    └── clients/polymarket/models.py  ~ + image/volume_24h/clob_token_ids parsing + to_card()
```

**The `kind` discriminator.** The UI must pick a renderer for `result`. Sniffing fields
(`"suggestions" in result`) works but is brittle; a `kind: "general" | "research" | "analysis"`
literal is cleaner. It must **not** reach the LLM: add it as a pydantic `@computed_field`, so
it appears in the serialization schema (FastAPI, the browser) but not in the validation schema
that `with_structured_output` sends to the model. A unit test asserting the responder's JSON
schema has no `kind` property locks that in. If it turns out to leak, fall back to field
sniffing in the frontend and drop the field — it is a convenience, not a requirement.

---

## 6. Frontend

### 6.1 Stack & structure

React 19 + TypeScript + Vite — same as farkle, so the tooling knowledge and the build carry
over. Dependencies: `react`, `react-dom`, `react-markdown`. No router (the conversation id is
a `?c=<uuid>` query param, which also keeps the SPA fallback trivial), no chart library
(sparklines are ~30 lines of inline SVG), no CSS framework.

```
web/
├── index.html
├── package.json          # name @trader/web, node 20 (.node-version)
├── tsconfig.json
├── vite.config.ts        # dev proxy: /api + /agent → http://127.0.0.1:8000
└── src/
    ├── main.tsx
    ├── App.tsx           # layout: Sidebar | ChatPane, key gate, mobile drawer
    ├── styles.css        # one stylesheet, CSS custom properties, dark by default
    ├── api/
    │   ├── client.ts     # fetch wrapper, X-API-Key, 401 → key screen
    │   ├── stream.ts     # POST + ReadableStream → AsyncIterable<StreamEvent>
    │   └── types.ts      # hand-written mirrors of the pydantic schemas
    ├── auth/KeyGate.tsx
    ├── sidebar/
    │   ├── Sidebar.tsx
    │   └── useConversations.ts
    ├── chat/
    │   ├── ChatPane.tsx
    │   ├── MessageList.tsx
    │   ├── Composer.tsx      # textarea; ⌘↵ to send; /find and /analyze hints
    │   ├── ProgressTrail.tsx # status events → step list
    │   └── labels.ts         # label → {icon, text}; the web's answer to messages.py:_STATUS
    └── markets/
        ├── MarketCard.tsx    # Suggestion  → card
        ├── AnalysisCard.tsx  # MarketAnalysis → expanded card
        ├── ProbabilityBar.tsx
        ├── Sparkline.tsx
        ├── MetricPill.tsx
        └── useMarket.ts      # lazy hydration + per-session Map cache
```

### 6.2 State & data flow

State is small enough for `useState` + two hooks; no state library.

```
KeyGate ─ key present? ─▶ App
                           ├─ useConversations()  → list, create, rename, delete
                           └─ ChatPane(conversationId)
                                ├─ GET /api/conversations/{id}          (on open)
                                ├─ POST /api/conversations/{id}/turns   (on send)
                                │     status → ProgressTrail (live)
                                │     final  → append assistant message
                                └─ MarketCard → useMarket(market_id) → GET /api/markets/{id}
```

- **Optimistic user message**, then the trail, then the assistant message. On error the trail
  is replaced by an inline error with a retry button.
- **Reload during a run**: the SSE connection dies, but the server still finishes and writes
  the answer (D5). Reopening the conversation shows it. Phase 4 can add a "run in progress"
  marker; v1 does not need it.
- **Cards never block.** They render immediately from `result`; hydration only adds the image,
  sparkline, volume and end date. A failed hydration is silent.

### 6.3 Layout

```
┌────────────┬─────────────────────────────────────────────┐
│ + New chat │  ← conversation title                  ⚙ 🐞 │
│────────────│─────────────────────────────────────────────│
│ Today      │  you: /find AI regulation 2026              │
│  AI reg…   │                                             │
│  BTC 100k  │  ✓ 🔎 picked skill: find                    │
│ Yesterday  │  ✓ 🌐 searching the web: EU AI act           │
│  F1 Austr… │  ✓ 📈 reading the order book                 │
│            │  ⟳ ✍️ writing the answer…                    │
│            │                                             │
│            │  summary paragraph…                         │
│            │  ┌───────────────────────────────────────┐  │
│            │  │ 1. Will the EU pass … ?          62% │  │
│            │  │ ▁▂▃▅▆▅▆  score .71 · 84bps · $12k    │  │
│            │  │ rationale…            🎯 high  🟡 med │  │
│            │  └───────────────────────────────────────┘  │
│            │─────────────────────────────────────────────│
│            │  [ ask something…                    ⌘↵ ]  │
└────────────┴─────────────────────────────────────────────┘
```

Below 768 px the sidebar becomes a drawer behind a hamburger; the composer sticks to the
bottom; cards go single-column.

### 6.4 Widget spec

**`MarketCard`** — one `Suggestion`:

| Zone | Content | Source |
|------|---------|--------|
| Header | rank, question (link to Polymarket), market thumbnail | `result` + hydration |
| Probability | implied % chip + horizontal bar | `implied_probability` |
| Sparkline | 24 h YES price, inline SVG | hydration (`history`) |
| Metrics | `find_score`, `spread_bps`, `depth_usd`, `maker`/`taker` badge, 24 h volume, "ends in N d" | `result` + hydration |
| Body | rationale | `rationale` |
| Footer | confidence chip, risk chip, risk note | `confidence`, `risk` |

**`AnalysisCard`** — one `MarketAnalysis`: stance banner (📈 lean YES / 📉 lean NO / ⏸ pass);
a **dual-marker bar showing implied vs. fair probability with the gap labelled** — the single
most valuable visual in the app; the edge paragraph; key factors; the risk block; resolution
criteria in a collapsible; and an order-book strip (best bid/ask, spread, depth).

**Color rules.** `risk` uses low = green → high = red (same semantics as `formatting.py`'s
`_LIGHT`). `confidence` uses the **inverse** scale (high = green): reusing one palette for both
would paint a confident, high-risk suggestion in contradictory colors. Probability bars stay
neutral accent — they are not a verdict.

**Degraded states.** No `implied_probability` → hide the bar, keep the card. No hydration →
no sparkline, no volume. Missing tradability fields (tool not called) → those pills are absent,
exactly as `_tradability_line` omits them today.

### 6.5 Styling

One `styles.css` with CSS custom properties (dark by default, farkle's single-stylesheet
approach). No CSS-in-JS, no Tailwind: the surface is one screen and a handful of cards.

---

## 7. Deployment

### 7.1 Component layout — and why it differs from farkle

farkle is a `static_sites` component because farkle has no backend. Trader has one, and that
changes the calculus:

| | A: static site + service (farkle-shaped) | B: SPA served by FastAPI (**chosen**) |
|---|---|---|
| Components | 2 + ingress path rules | 1 |
| CORS | none (same origin) | none (same origin) |
| Assets on CDN | yes | no (irrelevant for one user) |
| `disable_edge_cache` available | **no** — App Platform refuses it for apps containing a static site | **yes** — the escape hatch if SSE turns out buffered |
| Stale `index.html` vs. new assets | a real failure mode (farkle's smoke check exists because of it) | impossible — one artifact |
| Frontend-only change | rebuilds the static site | rebuilds and restarts the service (~2–3 min) |

B trades a CDN and fast frontend-only deploys for one component and a guaranteed answer to the
one risk that could actually break the product. The deploy *mechanism* stays identical to
farkle: spec in the repo, applied by GitHub Actions after tests, Cloudflare CNAME.

The `Dockerfile` gains a build stage:

```dockerfile
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim
# … existing uv stages, unchanged …
COPY --from=web /web/dist ./web/dist
```

FastAPI mounts `web/dist` last, and only if the directory exists — so `make app` still runs
without a frontend build.

### 7.2 App spec sketch (`.do/app.yaml`)

The app keeps the name it already has — **`ai-trader`**, not `trader-prod`. The deploy action
matches an app by the `name` in the spec, so renaming would create a *second* app: new
hostname, secrets re-entered by hand, and the original left running and billing until someone
notices. The farkle-style `-prod` suffix earns its keep only where there is also a `-dev`, and
here there is not (D2).

```yaml
name: ai-trader
region: fra

alerts:
  - rule: DEPLOYMENT_FAILED
  - rule: DOMAIN_FAILED

domains:
  # Needs the Cloudflare CNAME to exist first, DNS-only, or certificate issuance
  # fails and DOMAIN_FAILED fires (farkle learned this — see .do/app.prod.yaml there).
  - domain: trader.iamxox.space
    type: PRIMARY

databases:                     # added in Phase 1, not before: it bills from the
  - name: db                   # moment it is applied, and nothing reads it yet
    engine: PG
    version: "16"
    production: false          # dev database: $7/mo, 512 MiB, no backups

services:
  - name: agent
    dockerfile_path: Dockerfile
    source_dir: /
    github:
      repo: artem-xox/trader
      branch: main
      deploy_on_push: false    # CI applies the spec; see §7.4
    http_port: 8080
    health_check: { http_path: /health }
    envs:
      - { key: DATABASE_URL, scope: RUN_TIME, value: "${db.DATABASE_URL}" }
      - { key: AGENT_API_KEY, scope: RUN_TIME, type: SECRET, value: REPLACE_IN_DASHBOARD }
      # … existing OPENAI_* / TAVILY_* / LANGSMITH_* …

workers:
  - name: telegram           # unchanged
```

### 7.3 Cloudflare

```
trader.iamxox.space   CNAME   trader-prod-xxxxx.ondigitalocean.app   (DNS only / grey cloud)
```

Order matters and is the same trap farkle documented: create the CNAME **before** adding the
`domains:` block, and keep it unproxied — behind Cloudflare's proxy the CA's HTTP validation
reaches Cloudflare instead of App Platform and never completes. Grey cloud also keeps
Cloudflare out of the SSE path entirely.

*(If access ever needs to be shared, Cloudflare Access would require flipping to the orange
cloud after the certificate is issued, and SSE would need re-verifying. Not now.)*

### 7.4 CI/CD

Extend `.github/workflows/python-app.yml` — one workflow, three jobs:

```
python (ruff + pytest)  ─┐
                          ├─▶ deploy (main only): digitalocean/app_action/deploy@v2
web (tsc --noEmit + build)┘        app_spec_location: .do/app.yaml
                                   then smoke: /health, then the SPA serves
```

**The spec is the app.** `.do/app.yaml` is applied on every deploy, so the domain, the
components and every environment variable are described in source and the app can be rebuilt
with `doctl apps create --spec`. A dashboard edit survives only until the next deploy.

That only works because an App Platform spec is **declarative**, which is also the sharpest
edge here: whatever stands in the file replaces the live value, and an env var the file omits
is deleted rather than left alone. There is no "leave this one alone" — so secrets cannot be
kept in the dashboard while the spec is applied from CI. Two consequences:

- **Secret values are `${NAME}` references**, resolved at deploy time from repository secrets
  of the same name (a documented feature of `digitalocean/app_action`). A literal secret must
  never be written into the file — nor a placeholder: on 2026-08-11 the file still carried
  `REPLACE_IN_DASHBOARD` when CI first applied it, which replaced six live secrets with that
  string. The repository is public, so `AGENT_API_KEY` briefly became a documented working
  credential for the live agent, and a blanked `TELEGRAM_ALLOWED_CHAT_IDS` crash-looped the
  worker.
- **A missing repository secret is equally dangerous** — it expands to an empty string and
  wipes the value just as thoroughly. So the deploy job's first step refuses to run unless
  every referenced secret is present and non-empty. Adding a secret to the spec means adding
  it to that list too.
- **`deploy_on_push: false`.** Left true, DigitalOcean's own webhook deploys on every push in
  parallel with CI — the first of the two deploys ungated by tests. Expect one canceled
  deployment on the changeover: the flag only takes effect once the spec carrying it is live.

Local dev loop:

```
make app     # FastAPI on :8000
make web     # vite on :5173, proxying /api and /agent to :8000
```

### 7.5 Cost

| Item | Now | After |
|---|---|---|
| `agent` service (basic-xs) | ~$12/mo | ~$12/mo |
| `telegram` worker (basic-xxs) | ~$5/mo | ~$5/mo |
| dev Postgres | — | **$7/mo** |
| static site | — | — (not used) |

**+$7/mo.** Caveat worth knowing: an App Platform dev database is not backed up and is
**destroyed with the app**. For chat history that is an acceptable risk at this price; a
monthly `pg_dump` is the cheap insurance, and a standalone managed cluster (~$15/mo) is the
upgrade if the history ever matters more than that.

---

## 8. Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| **SSE buffered at DO's edge** — the trail arrives as one chunk | medium | POST responses are documented as not edge-cached, so this should not bite; `X-Accel-Buffering: no` + keepalives; if it does, set `disable_edge_cache: true` (available because there is no static-site component — D4). Worst case the product still works, just without live progress. |
| Long `find` run exceeds an idle timeout | low | 15 s keepalive frames; the server persists the answer regardless (D5) |
| Public endpoint burning OpenAI credit | low | Long random `AGENT_API_KEY`; LangSmith already shows every run; add a per-day run cap if anything shows up |
| Checkpoint bloat in a 512 MiB dev DB | low | Delete checkpoints with their conversation; prune old threads if it ever grows |
| `kind` computed field leaking into the LLM schema | low | Unit test on the responder's schema; fall back to field sniffing |
| Frontend deploy restarts the agent | certain, by design | Deploy when no run is in flight; it is a 2–3 min window |

---

## 9. Plan

Each phase states what "done" means so it can be built and verified independently
(CLAUDE.md §4). Sizes are rough solo-dev days.

### Phase 0 — walking skeleton *(≈0.5 d)*

De-risk the infrastructure **before** writing any UI. A blank React page, one `/api/health`
call, one hand-made SSE call, deployed to the real domain.

- `web/` scaffold (Vite + TS + React), Dockerfile build stage, FastAPI static mount.
- `.do/app.yaml`: domain, `deploy_on_push: false`; the Cloudflare CNAME must exist first.
- CI: `web` job + `deploy` job with a smoke check.
- Two probe endpoints (`app/probe.py`) and a page that runs them: `GET /api/health` proves the
  API answers on the path the browser uses now that FastAPI also serves the SPA, and
  `POST /api/stream-probe` emits five frames a second apart so the page can measure their
  **arrival times** and say plainly whether the stream was incremental or buffered.
- **Done when:** `https://trader.iamxox.space` serves the page, and both probes pass **from
  that origin** — the SSE one is the answer to the top risk; if it reports "buffered", set
  `disable_edge_cache: true` on the app and re-run it.

### Phase 1 — persistence *(≈1 d)* — ✅ done

- Dev database attached; `DATABASE_URL` wired; `store.py` + `schema.sql` bootstrap at startup.
- `AsyncPostgresSaver` replaces `InMemorySaver` in the FastAPI lifespan.
- `conversations.py`: CRUD + `POST /turns` streaming with persistence; `streaming.py` extracted.
- **Done when:** unit tests cover the store against a local Postgres; `curl` creates a
  conversation, runs a turn, and `GET /api/conversations/{id}` returns both messages with the
  structured `result` intact; restarting the service preserves history *and* agent context.

### Phase 2 — chat UI *(≈2 d)* — ✅ done

- `KeyGate`, `Sidebar` (list / new / open / delete), `ChatPane`, `Composer`, `MessageList`,
  `ProgressTrail`, markdown answers via `react-markdown`.
- `api/stream.ts` SSE reader; `?c=<uuid>` deep links; error + retry states.
- **Done when:** a full `/find` run is driven end-to-end from the browser, the trail animates
  step by step, the answer renders, and a reload restores the conversation from the server.

### Phase 3 — market widgets *(≈1.5 d)*

- `GET /api/markets/{id}` + `to_card()` parsing; `MarketCard`, `AnalysisCard`,
  `ProbabilityBar`, `Sparkline`, `MetricPill`, `useMarket`.
- `kind` discriminator + its schema test.
- **Done when:** a `/find` answer renders as cards with sparklines and metric pills, an
  `/analyze` answer renders the implied-vs-fair bar, and killing the enrichment endpoint
  degrades the cards without breaking them.

### Phase 4 — polish *(≈1 d)*

- Mobile drawer, rename, debug toggle (trace link on the message), empty states, favicon/OG,
  `robots.txt` disallow (this is a private tool), keyboard shortcuts.
- Docs: link `WEB.md` from `README.md` and `DESIGN.md`; add a "Web UI" line to `PLAN.md`.
- **Done when:** it is usable one-handed on a phone and `make test` + `npm run build` are green
  in CI.

**Total ≈6 days.** Phases 0–2 alone are a working product.

---

## 10. Open questions

- **Streaming markdown.** The agent returns the answer only at the end (the responder is one
  structured call). Token-by-token typing would need `astream_events` on the responder — worth
  it, or is the progress trail enough? *(Assumed: enough.)*
- **Should the progress trail be persisted** with the assistant message, so reopening an old
  conversation shows how the answer was reached? Cheap (`jsonb` column), unclear value.
- **Conversation titles** — dumb truncation vs. a cheap LLM call on the first turn.
- **Run concurrency.** One instance, one user; two parallel runs are already possible and
  untested. PLAN.md §7 lists this as an open question for the agent generally.
