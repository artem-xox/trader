# Autonomous AI Agent for Trading on Polymarket

Polymarket's live trading venue is no longer best understood as a classic prediction-market AMM. In production, it is a hybrid-decentralised central limit order book: orders are signed offchain, matched by an operator, and settled atomically on Polygon through audited exchange contracts. Since the April 2026 CLOB V2 cutover, the exchange contracts, backend, and collateral token changed materially; pUSD replaced USDC.e for production collateral, fees are now dynamic per market, and legacy V1 SDKs and signed orders are no longer supported in production. For a new autonomous trading system, the correct mental model is therefore event-driven CLOB trading with onchain settlement, not "AMM-first DeFi execution". The best automated Polymarket agents today fall into a few families. Official and community projects show three clear patterns: market-making bots that continuously cancel and replace two-sided quotes; arbitrage engines that exploit bundle mispricings and cross-platform dislocations; and LLM-assisted "research agents" that retrieve news, estimate event probabilities, and then either paper-trade or place orders through the CLOB. The strongest publicly visible lesson is that execution and risk control matter as much as forecasting: recent Polymarket research finds successful traders disproportionately provide liquidity with limit orders, while less successful traders more often take liquidity with marketable orders. Other recent work finds that liquidity and large-trade order imbalance materially affect price discovery and subsequent returns. A robust autonomous agent should therefore separate its work into three explicit skills. /find should rank markets by tradability and expected edge, not by raw narrative appeal. /analyze should convert research into calibrated probabilities, all-in expected value, and conservative position sizes after fees, slippage, and model uncertainty. /distribute should treat positions as a correlated portfolio of binary claims with hard event-cluster limits, liquidity caps, and rebalance triggers. That division maps cleanly onto Polymarket's API surface: Gamma for discovery, Data API for positions/trades/activity, CLOB REST and WebSocket for price formation and execution, and Relayer/Bridge for inventory and wallet operations. The key operational recommendation is to start with a semi-conservative architecture: market discovery and research at broad scale, but execution only in liquid markets with narrow spreads, bounded time-to-resolution, explicit geoblock checks, server-side key custody, heartbeat-based dead-man protection, and a paper-trading/shadow mode before production. If the system later graduates into active market making, it should adopt inventory-aware quoting, toxicity filters, and restart-aware order handling rather than naïve spread capture.[^4]

## Polymarket mechanics and developer surface

### What Polymarket is now

Polymarket's current production trading stack is a hybrid CLOB. Orders are EIP-712 signed messages; they are matched offchain and settled onchain via the Exchange contract on Polygon. The operator's role is constrained to matching and ordering, and Polymarket's docs state that operators cannot set prices or execute unauthorised trades. The current production CLOB V2 went live on 28 April 2026; at that cutover, Polymarket introduced rewritten exchange contracts, a rewritten CLOB backend, and pUSD as the production collateral token, while V1 SDKs ceased to work against production. For an agent developer, the most important market primitive is still the binary outcome token. Polymarket represents positions as ERC-1155 tokens on Polygon using the Gnosis Conditional Token Framework. Each market has a YES token and a NO token, and every YES/NO pair is fully backed by exactly $1 of pUSD locked in the CTF contract. Splitting turns pUSD into paired YES/NO inventory; merging converts matched YES/NO pairs back to pUSD; redeeming converts winning tokens after resolution back into pUSD. This split/merge/redeem lifecycle matters operationally because market-making inventory management is not just order placement - it is also token inventory transformation.[^5]

### AMM context and why it still matters

The user asked specifically for AMM mechanics, but the key point is that current Polymarket production execution is not AMM-based. The docs now foreground the CLOB, and the V2 migration guide is explicit about the exchange/backend rewrite. That said, market schemas still expose legacy or parallel fields such as ammType, liquidityAmm, volumeAmm , fpmmLive , and liquidityClob, which is a signal that integrations need to normalise mixed historical/current schema rather than assuming all market metadata is CLOB-only or homogeneous. AMM theory remains useful as a reference model for older prediction markets and comparable venues. Hanson's logarithmic market scoring rule and later liquidity-sensitive automated market maker work explain the classic prediction-market AMM design space: guaranteed continuous quotes, bounded-loss market making, and price movement as a deterministic function of inventory and liquidity parameterisation. Those mechanisms contrast sharply with Polymarket's present CLOB, where price formation is emergent from bids, asks, queue position, and order flow rather than a scoring-rule cost function. For an autonomous Polymarket agent, AMM mechanics are therefore mainly useful for cross-venue reasoning, legacy data interpretation, and understanding why strategies that work on LMSR-style systems do not transfer directly to a live order book.[^7]

### Resolution, market types, fees, and order types

Polymarket's resolution flow is straightforward at a high level but operationally important. A market closes when trading ends, resolves to the winning outcome once the result is known, and then pays $1 per winning token while losing tokens redeem for $0. Polymarket states that markets normally resolve within a few days once a question's outcome is determined, though some can take longer if the resolution source is ambiguous or delayed. In practice, the current concept docs describe a market as a tradable binary outcome within an event. Multi-outcome events are expressed as multiple binary markets, and Polymarket's "negative risk" mechanism relates mutually exclusive outcomes within one event so that capital can be used more efficiently through conversion. On top of that, Polymarket now supports Combos, which package multiple legs into one YES/NO multi-leg position executed through an RFQ workflow rather than simple book matching. For sports markets specifically, outstanding limit orders are automatically cancelled once the game begins, with the warning that early starts can still create operational edge cases. Polymarket's fee model changed in CLOB V2. Fees are now operator-set at match time rather than embedded in the signed order, and the docs provide a contract-level formula: Fee = baseRate × min(price, 1-price) × size for takers, with category-dependent base rates. By category, the current public schedule shows 0.015 for popular highly liquid markets such as sports, crypto, politics, economy, and weather; 0.050 for topical but less liquid markets such as business, science, culture, world, and tech; and 0 for geopolitical world-event markets. Makers pay 0 , and separate maker rebates can apply when orders are scoring-eligible. All Polymarket orders are expressed as limit orders. What the UI or an agent may think of as a "market order" is implemented by submitting a marketable limit order that crosses the book immediately. Official order types exposed in the docs include GTC , GTD , FOK , FAK , and postOnly ; postOnly is especially important for market making and during post-restart restricted mode, while FOK and FAK are useful for aggressive execution when predicted edge is fleeting.[^11]

### APIs, authentication, rate limits, and data formats

Polymarket exposes three core APIs plus ancillary services. The Gamma API is the discovery surface for markets, events, search, tags, comments, sports metadata, and public profiles. The Data API covers positions, trades, account activity, holders, open interest, leaderboards, and builder analytics. The CLOB API handles order books, prices, spreads, histories, and authenticated order management. There are also Bridge and Relayer APIs, and public/authenticated WebSocket channels for market data and user activity. Authentication is two-layered. L1 authentication uses the wallet private key to sign an EIP-712 ClobAuthDomain message and is used to create or derive API credentials. L2 authentication uses apiKey, secret , and passphrase to produce HMAC-SHA256 request signatures for authenticated CLOB methods. Trading endpoints require five L2 headers: POLY_ADDRESS, POLY_SIGNATURE, POLY_TIMESTAMP, POLY_API_KEY , and POLY_PASSPHRASE . Even with L2 headers, order-creating methods still require the order payload itself to be signed. New API users are directed to use deposit wallets with signature type POLY_1271 ( 3 ), while older proxy and Safe flows remain supported. Rate limits are generous for read paths and very high for bursts on trade submission, but they are not infinite. Gamma is capped at 4,000 requests per 10 seconds in general, with 300 per 10 seconds on /markets ; Data API general reads are 1,000 per 10 seconds; and CLOB general reads are 9,000 per 10 seconds, with /book at 1,500 per 10 seconds and /prices-history at 1,000 per 10 seconds. Trading routes also have sustained windows: for example, POST /order allows 5,000 requests per 10 seconds burst and 120,000 per 10 minutes sustained, while POST /orders allows 2,000 per 10 seconds burst and 21,000 per 10 minutes sustained. Cloudflare throttling delays or queues requests after limit breaches rather than always hard-rejecting immediately. The data format details matter because Polymarket's schemas are mixed. Gamma market objects are broad and include both discovery fields and venue fields: examples in the docs show string fields such as liquidity, volume , fee , outcomes , outcomePrices , and clobTokenIds , alongside numeric convenience fields such as liquidityNum, volume24hr , bestBid , bestAsk , lastTradePrice , oneDayPriceChange , and openInterest in search responses. CLOB order-book responses, by contrast, use precise string numerics for price, size , tick_size , and timestamps. Batch variants exist for order books, prices, midpoints, and spreads, and official docs state that batch orderbook-style requests support up to 500 tokens per request. Ingestion code should therefore normalise types aggressively at the edge and keep a canonical internal schema. The real-time interface is strong enough for agentic trading. The public market WebSocket at wss://ws-subscriptions-clob.polymarket.com/ws/market streams orderbook snapshots, price changes, last-trade updates, tick-size changes, and optionally best_bid_ask, new_market , and market_resolved events when custom_feature_enabled is turned on. The authenticated user channel streams order and trade updates, including trade states such as MATCHED , MINED , CONFIRMED , RETRYING , and FAILED . RTDS separately streams comments and reference crypto/equity prices, which is useful for market-context features in /find and /analyze.[^17]

The table below is the shortest practical developer map.

| Surface | Best use in an autonomous agent | Typical high-value endpoints or streams | Auth | Notes |
|---------|--------------------------------|----------------------------------------|------|-------|
| Gamma API | Universe construction and market metadata | `GET /markets`, `GET /events`, `GET /public-search`, tags, sports metadata | Public | Discovery-first surface; mixed schema with venue and editorial fields.[^18] |
| Data API | Positions, trades, holders, open interest, account analytics | positions, closed positions, user activity, open interest, leaderboards | Public (many reads) | Useful for trader-behaviour and portfolio state features.[^19] |
| CLOB REST | Live pricing and execution | `/book`, `/books`, `/prices`, `/midpoints`, `/prices-history`, `POST /order`, `POST /orders`, cancels, heartbeat | Mixed | Core execution venue. Batch up to 500 tokens on major read paths.[^20] |
| CLOB WebSocket | Low-latency market state | market channel, user channel | Public / authenticated | Preferred over polling for live quoting or event-driven taker logic.[^21] |
| Relayer | Gasless wallet and inventory ops | submit tx, wallet deploy, nonce, transaction status | Authenticated | Particularly relevant for split/merge/redeem flows.[^22] |
| Bridge | Funding and withdrawals | supported assets, quotes, tx status | Mixed | Separate proxy service for deposits/withdrawals.[^19] |
| Combos RFQ | Advanced multi-leg pricing | combo markets, submit/cancel quote, last look, quoter gateway | Maker role | Quote window is 400 ms; last-look timing is strict.[^23] |

## Existing automation and agent landscape

### What the public repo ecosystem already shows

The official Polymarket/agents repository is the clearest statement of how Polymarket itself imagines agentic trading: modular connectors around Polymarket and Gamma data, a CLI, LLM utilities, local/remote RAG, and data sourcing from betting services, news providers, and web search. Architecturally, it is a research-and-execution framework rather than a single complete strategy, which makes it a good starting point for /find and /analyze , but not a ready-made institutional execution engine. Its own README also highlights a compliance constraint that matters operationally: Polymarket's terms prohibit US persons and persons in certain other jurisdictions from trading via UI or API, including agents. The most battle-tested open-source Polymarket-native market-making repo in public view is warproxxx/poly-maker . Its architecture is recognisably practical: WebSocket order-book monitoring, risk controls, spread and price management, position merging, and a parameter layer managed through Google Sheets. That configuration style is convenient for traders but brittle for a serious autonomous agent. More importantly, the author's own README warns that in the current market the bot is not profitable as-is and should be treated as a reference implementation rather than deployable alpha. That admission is unusually valuable: it signals how competitive Polymarket quoting has become. ImMike/polymarket-arbitrage represents a second family: scan first, execute selectively. It watches thousands of markets, supports both single-platform "bundle arbitrage" when YES and NO do not approximately sum to one, and cross-platform arbitrage between Polymarket and Kalshi. Its README also says real markets are highly efficient and arbitrage opportunities are rare, which is consistent with recent academic work showing Polymarket often leads price discovery when liquidity is high. Architecturally, the bot combines market discovery, cross-platform matching, a dashboard, simulation mode, and explicit fee accounting. phenomenon0/polymarket-agents is the most interesting public example of an explicitly agentic system. It uses a DAG orchestrator, separates forecaster, policy, and paper engine, routes across many LLMs, and couples this to Gamma/CLOB/WebSocket connectivity and a backtesting path. That architecture is close to what a serious Manychat-style multi-skill agent should look like: discrete modules for discovery, inference, risk, and execution rather than one overgrown prompt. Its weakness is the familiar one of LLM-heavy systems: orchestration sophistication does not guarantee calibrated probability estimates or reliable execution. There are also heavier "enterprise" or promotional repos such as advaricorp/Polymarketbot and ConteurShadow/Polymarket-Market-Maker-Bot . These tend to advertise microservices architecture, event-driven systems, copy-trading extensions, or institutional deployment patterns. They are useful as architecture inspiration for service decomposition, but public README claims are much stronger than public empirical evidence. In a rigorous build, they should be treated as implementation sketches rather than proof of live-edge viability. A different but highly relevant project is sculptdotfun/tremor , which is not a trader at all but a market-intelligence monitor. It tracks around 500 active Polymarket markets, scores abrupt moves on a 0-10 intensity scale, and blends Polymarket data with social-context retrieval. This is exactly the kind of upstream signal service that belongs inside /find : not as a decision-maker, but as a trigger generator for "something changed faster than our steady-state polling would notice".[^28]

### Similar prediction-market projects and adjacent lessons

The most useful adjacent open-source comparison is the Kalshi market maker by zachdaube/kalshi-market-maker . It explicitly uses the Avellaneda-Stoikov quoting model, adjusts reservation price for inventory, widens spreads under toxic flow, and runs in a simple loop of position sync, orderbook fetch, order-flow analysis, quote generation, and cancel/replace. That is a very good conceptual template for Polymarket market making, even though the exact fill mechanics, book conventions, and fee schedules differ. Its main lesson is structural: inventory-aware quoting beats symmetric quoting. On the retail/agentic side, the Manifold ecosystem shows how LLM trading is usually implemented when real-money execution friction is lower. microprediction/manifoldbot uses GPT-derived probability estimates, compares them with market probabilities, and places bets when the gap is large enough, while explicitly discussing market-impact-adjusted fractional Kelly sizing. faizalmy/manifoldbot pushes further into multi-agent reasoning, consensus mechanisms, external search APIs, Kelly-style sizing, and performance tracking. These repos are useful not because Manifold is microstructurally similar to Polymarket - it is not - but because they show the agent pattern for event forecasting: retrieve, synthesise, predict, compare to the market, size conservatively, and log thoroughly. Academic work now provides unusually direct support for that split between forecasting and execution. Recent Polymarket research finds that gains are highly concentrated, that successful traders are more likely to supply liquidity with favourable limit orders, and that poorer traders disproportionately take liquidity. Another recent paper on modern prediction markets finds that Polymarket often leads Kalshi in price discovery when liquidity and trading activity are high, and that net order imbalance from large trades predicts subsequent returns. A further Polymarket study finds overtrading in the default and YES option, while a separate paper argues that forecast accuracy comes largely from a persistently skilled minority reacting to public information and eliminating violations of the law of one price. That bundle of evidence implies a practical conclusion: the strongest autonomous Polymarket architectures will usually combine public-information forecasting, relative-value detection, and microstructure-aware execution. Pure LLM narrative trading without a disciplined cost model is weak. Pure market making without toxicity filters is also weak. The best public projects each capture one piece of the puzzle, but none visibly closes all of it.[^33]

The comparison below is the most useful synthesis.

| Project | Core architecture | Main strategy style | What it gets right | Main limitation |
|---------|-------------------|---------------------|--------------------|-----------------|
| Polymarket/agents | Modular connectors + RAG + CLI + trading hooks | Research-agent framework | Clean separation between data retrieval and execution tooling.[^34] | Not a proven production strategy by itself. |
| poly-maker | WebSockets + risk controls + sheet-configured market maker | Passive/active market making | Real operational focus on spread control, inventory, merging.[^35] | Author states it is not profitable as shipped. |
| polymarket-arbitrage | Cross-platform scanners + dashboard + simulation | Bundle and Polymarket/Kalshi arbitrage | Explicit fee accounting and large-universe scanning.[^36] | Public mispricings are rare; mapping markets across venues is messy. |
| phenomenon0/polymarket-agents | DAG orchestrator + forecaster + policy + paper engine | LLM ensemble forecasting | Strong decomposition of forecasting, policy, and backtesting.[^27] | Depends heavily on model quality and calibration discipline. |
| tremor | Real-time monitoring pipeline with intensity scoring | Signal discovery / anomaly detection | Excellent upstream trigger layer for /find.[^29] | Not an execution engine. |
| kalshi-market-maker | Inventory-aware quote engine | Avellaneda-Stoikov market making | Good template for inventory-aware quoting loops.[^30] | Different venue mechanics and order conventions. |
| manifoldbot repos | LLM prediction + thresholding + fractional Kelly | Narrative/event trading | Good prompt/forecasting pattern and sizing ideas.[^31] | Weaker transfer to live CLOB execution. |

## Quantitative design for /find, /analyze, and /distribute

### Market selection for /find

A serious /find module should not simply return "most interesting markets". It should return the top tradable opportunities after considering edge, cost, and execution feasibility. The available Polymarket metadata is already rich enough to support this: Gamma and search responses expose liquidity, open interest, volume24hr , bestBid , bestAsk , price-change fields, category, endDate , sports timing, reward configuration, and CLOB-enablement flags. CLOB endpoints add live spreads, depth, midpoints, last-trade prices, and price history, while RTDS and comments streams can proxy information flow. A high-confidence composite score is:[^7]

$$S = 0.30L_i + 0.25E_i + 0.15V_i + 0.20I_i + 0.10T_i$$

where:

- $L_i$ is liquidity quality, not just nominal liquidity
- $E_i$ is model-derived net edge after cost
- $V_i$ is realised probability volatility
- $I_i$ is information-flow intensity
- $T_i$ is time-to-resolution fit

This weighting is a recommended design, not an official standard, but it is grounded in the Polymarket API fields above and in recent evidence that liquidity and directional order flow materially affect return predictability and cross-platform price discovery.[^38]

A practical implementation of each component should look like this:

| Component | Recommended definition | Why it matters |
|-----------|------------------------|----------------|
| Liquidity $L_i$ | Blend of quoted spread, top-of-book depth, depth within ±2 ticks of mid, 24h volume, and estimated fill ratio for target notional | A market with high "headline liquidity" but poor near-touch depth is not genuinely tradable. CLOB fields and batch books make this measurable.[^39] |
| Edge $E_i$ | $|\hat{q}_i - p_{\text{mid},i}|$ / all-in-cost, with a hard minimum absolute EV threshold | Edge must survive spread, fee, and slippage. Makers/takers should be scored separately.[^11] |
| Volatility $V_i$ | Realised stdev of midpoint or last-trade probability over 5m/1h/24h from `/prices-history` | Volatility creates opportunity, but when combined with toxicity it can destroy makers.[^40] |
| Information flow $I_i$ | Trade-count acceleration, order-imbalance z-score, comment/news velocity, external source count, and unexplained move intensity | Large-trade order imbalance predicts returns; upstream anomaly detection is useful.[^41] |
| Time fit $T_i$ | Utility curve over time-to-resolution relative to strategy mandate, with penalties for ambiguous late-stage resolution risk | Short-horizon taker alpha and multi-week maker inventory are different businesses.[^42] |

A sensible /find hard filter set is at least as important as the score. A production agent should exclude: blocked jurisdictions; markets not yet accepting orders; books with stale timestamps; spreads wider than a configured maximum; top-of-book notional below a multiple of intended trade size; sports markets too close to start without special handling; and markets whose time-to-resolution or resolution source is outside the mandate. Those conditions map directly to geoblocking docs, market-ready/error responses, sports behaviour, and orderbook state.[^43]

### Probability estimation and trade analysis for /analyze

A disciplined /analyze module should treat the market price as a prior, not as truth. In current Polymarket-style event markets, the best baseline is usually the midpoint probability pmid , adjusted for book imbalance and recent trade direction. From there, the module should layer external evidence: official data feeds, domain-specific models, structured retrieval from high-authority sources, and event-specific heuristics. Recent Polymarket research suggests prices are often accurate overall, but skilled minorities still exploit behavioural mistakes, public-news reaction lags, and law-of-one-price violations; that is precisely the niche where /analyze should operate. A useful posterior-construction recipe is log-odds pooling:[^44]

$$\text{logit}(\hat{q}) = w_m \text{logit}(p_{\text{mid}}) + \sum_j w_j \text{logit}(q_j)$$

For a binary YES token bought at price before costs is: c and held to resolution, the clean expected value per share EV= YES− q^ c and after all-in transaction costs: EV= q^ YES,net− c− fees − slippage − latency_penalty For a NO token at price n (1 − ) , the same logic applies with q^ replacing q^ . This is the right way to analyse prediction-market positions: treat a share as a bounded claim paying 1 0 or , not as an open-ended asset. Fees are not trivial here because Polymarket's taker fee depends on both price and category. For takers, slippage should be computed directly from the book:[^46]

For takers, slippage should be computed directly from the book:

$$\bar{c}(Q) = \frac{1}{Q} \sum_k p_k \cdot \Delta q_k$$

where $\Delta q_k$ is the filled amount at each price level. Then:

(Q) = Q ∑k Δqk p⋅ k where Δqk is the filled amount at each price level. Then:[^1]

For takers, slippage should be computed directly from the book:

$$\bar{c}(Q) = \frac{1}{Q} \sum_k p_k \cdot \Delta q_k$$

where $\Delta q_k$ is the filled amount at each price level. Then:

slippage = (Q) − a1 for a buy, where a1 is the best ask. For makers, replace direct slippage with fill uncertainty plus adverse-selection cost. In practice, that means your quote engine should estimate "probability of fill before adverse move" rather than merely "probability of fill". That distinction is central in the toxicity literature and in modern market-making simulation work. The Kelly fraction remains the cleanest starting point for sizing a single bounded binary bet. If you buy YES at effective cost ceff , then the net odds are b= (1 − c )/c eff eff , and the full Kelly fraction is:[^9]

$$f^* = \frac{\hat{q} \cdot b - (1 - \hat{q})}{b} = \frac{\hat{q} - c_{\text{eff}}}{1 - c_{\text{eff}}}$$

That logic comes directly from Kelly's log-growth criterion. For real trading, however, full Kelly is usually too aggressive because model error, correlation, and non-stationarity dominate in event markets. A practical agent should default to fractional Kelly - usually one-quarter to one-half Kelly - and scale further down when calibration worsens or correlation uncertainty rises.

### Portfolio construction and capital allocation for /distribute

Prediction-market portfolios are not ordinary coin-flip bundles. They are often highly correlated, sometimes nested, and occasionally mutually exclusive. That means /distribute should operate on a scenario PnL matrix, not a list of isolated edges. At minimum, the module should model dependencies by event cluster, category, narrative theme, jurisdictional driver, and time-to-resolution bucket. Classical diversification logic still applies, but it must be adapted to bounded binary payoffs and event dependence. A good default portfolio objective is one of these: max w ⊤ ∑i i λw Σw w μ− i for a mean-variance overlay, or max r )] E[log(1 + p w for correlation-adjusted growth optimisation. In either case, use scenario stress rather than naïve Gaussian assumptions wherever possible, because event outcomes can create discontinuous portfolio jumps. Expected shortfall or CVaR is a useful hard constraint even if the objective is log-growth or mean-variance.[^50]

Recommended hard constraints are:

| Constraint | Recommendation | Rationale |
|------------|----------------|-----------|
| Single market cap | 0.5%–2.0% NAV for taker signals; somewhat higher only for very high-confidence liquid trades | Protects against model error on any one question. |
| Event-cluster cap | 3%–8% NAV across all linked markets on the same real-world event | Prevents hidden concentration across "different" markets that settle on the same catalyst. |
| Illiquid-book cap | Dollar exposure no more than 10%–20% of depth within two ticks | Ensures plausible exit. |
| Time-bucket cap | Keep a reserve for near-term catalysts and reduce long-dated inventory concentration | Bounded capital in event markets should stay mobile. |
| Correlation cap | Penalise markets with similar drivers or explicit combinatorial dependence | Prevents pseudo-diversification.[^51] |

These are recommendations, not official limits; they operationalise standard portfolio logic for a venue where correlation is often semantic rather than purely statistical. Rebalancing should be event-driven first, clock-driven second. Trigger a rebalance when one of the following occurs: posterior probability moves by more than a threshold relative to entry; the market moves enough to erase expected value; a risk limit is breached; a correlated event cluster changes materially; spreads widen sharply; or time-to-resolution crosses a policy boundary. Clock-based housekeeping - for example every 5-15 minutes in highly liquid books and every 30-60 minutes elsewhere - is still useful for health checks and stale-position review, but it should not be the primary driver of alpha decisions.[^51]

## Execution architecture and operational controls

The architecture below is the most robust pattern for a production agent. It mirrors the official API split, the public project landscape, and the empirical lesson that research, risk, and execution should not live in one opaque loop.

```mermaid
flowchart LR
A[Gamma discovery and search] --> B[/find]
C[Data API trades positions open interest] --> B
D[CLOB market WebSocket and RTDS] --> B
B --> E[/analyze]
F[Official sources news models retrieval] --> E
E --> G[/distribute]
G --> H[Execution policy]
H --> I[CLOB REST order placement]
I --> J[User WebSocket fills and status]
J --> K[Risk monitor and portfolio state]
K --> B
K --> E
A live trading decision should then pass through a smaller gating flow so that the agent does not
```

overtrade newsy but untradeable markets.[^11]

```text
Candidate market
Geoblock and policy OK
Yes
Book fresh and liquid
enough
No
Yes
Net EV after fees and
slippage > threshold
No
Yes
No
Portfolio and event-cluster
limits OK
No
Yes
Execution mode
Reject
Strong short-lived alpha
Taker using FOK or
marketable limit Moderate alpha and good
liquidity
Passive maker or postOnly
Post trade monitor
Relative-value basket
Combo or paired
execution
```

The first execution choice is maker versus taker. Recent Polymarket research strongly suggests that successful traders more often behave like liquidity providers, and that modern prediction-market price discovery is heavily conditioned by liquidity and order flow. That does not mean "always make"; it means that a serious agent should make whenever its edge is durable enough to survive fill uncertainty, and take when the catalyst window is short or the model edge is large enough that waiting is costlier than crossing. For order submission, Polymarket already gives the agent good primitives. All orders are signed limit orders; marketable limits emulate market orders; FOK and FAK are appropriate for urgency; postOnly is essential for maker flow and mandatory during post-restart post-only windows. Batch submission through POST /orders is operationally valuable for quote updates or basket repositioning, and official rate limits comfortably support industrial-scale quoting if the system is engineered responsibly. For inventory operations, Polymarket's Relayer path is strategically important. Inventory docs state that splitting, merging, and redeeming can be executed gaslessly through the Relayer Client, which reduces some friction for makers who need both sides of a book. That is superior to ignoring inventory and letting the strategy accumulate one-sided exposure it never intended to hold. Operational resilience is not optional on this venue. The heartbeat endpoint is a dead-man switch: if a valid heartbeat is not received for roughly 10 seconds, open orders are cancelled. The matching engine can return HTTP 425 during restart windows, and after a restart there is a two-minute post-only phase in which non-post-only orders are rejected, while cancels are still allowed. A production agent must therefore support: exponential backoff on responses, and explicit restart observability. 425 , dynamic mode switching on post-only or cancel-only Latency management is mostly about architecture rather than raw colocation. The official docs already nudge developers toward WebSockets for real-time book handling instead of polling, and batch read paths reduce needless load during broad market scans. In practice, the agent should maintain a live market-state cache, subscribe only to active trade candidates, and reserve REST for point queries, authenticated actions, and periodic reconciliation. Front-running and MEV need to be framed carefully on Polymarket. Because Polymarket's core order matching is offchain and orders are signed before operator submission, the venue is not exposed to the exact same publicly visible pending-order leakage that fully onchain AMM execution suffers. That said, settlement still lands on Polygon, and direct wallet actions such as approvals, wrapping, split/merge/ redeem, or any self-routed onchain operations can still face public-mempool reordering unless routed more privately. Polygon's own 2026 private-mempool launch explicitly positions itself as protection against frontrunning and sandwich attacks, so if your agent ever submits its own Polygon transactions outside Polymarket's relayer path, a private submission route is now worth serious consideration. That is an inference from the Polymarket offchain/onchain split plus Polygon's mempool design, not a Polymarket-specific documented claim.[^60]

The minimum execution safety checklist should therefore include the following:

| Control | Why it is mandatory | Evidence |
|---------|---------------------|----------|
| Server-side key custody | Prevents API secret or private-key leakage | Polymarket explicitly says never expose private keys or API secrets client-side.[^61] |
| Geoblock check before trading | Avoids prohibited execution | Official geoblock endpoint and docs.[^62] |
| Balance and allowance pre-checks | Prevents rejected or invalid orders | Official order validity checks and error codes.[^63] |
| Tick-size and min-size validation | Prevents avoidable rejects | Official order validation errors.[^64] |
| Heartbeat loop | Cancels stale risk if the bot dies | Open orders auto-cancel if heartbeat lapses.[^64] |
| Restart-aware logic | Handles 425, post-only windows, cancel-only mode | Official restart handling docs.[^65] |
| Sports start-time guardrails | Avoids accidental exposure through book clears | Sports market orders are auto-cancelled at game start, but schedules can shift.[^66] |
| Stale-book detection | Prevents trading on old state | Necessary in any CLOB; supported by snapshot timestamps and WebSocket state.[^67] |

## Security, compliance, and ethics

The most important compliance fact is simple: availability is jurisdiction-dependent. Polymarket provides an official geoblock check and says restrictions are driven by sanctions, local financial regulation, prediction-market or gambling rules, AML, and KYC requirements. The official Polymarket/agents README also reiterates that Polymarket's terms prohibit US persons and persons in certain other jurisdictions from trading via the UI or API, including agents. Any autonomous trader must enforce venue eligibility before doing anything else. From a security standpoint, the threat model is dominated by wallet compromise, API-secret leakage, and unsafe signing architecture. Polymarket's own documentation is unambiguous: private keys belong in environment variables or secure key-management systems; authenticated requests should originate only from backend environments; and L2 secrets must never appear in client-side code. In practice, that means using HSM/KMS-backed signing where possible, separating research workers from signing workers, and rotating/re-deriving API credentials on incident response rather than embedding them into monolithic services. The next layer of risk is market abuse and governance. Prediction markets are especially vulnerable to public/private information asymmetry, manipulative narratives, and correlated trader behaviour. Recent work on Polymarket argues that much of the venue's accuracy comes from skilled traders reacting to public information rather than insider trading, which is the ethical lane an autonomous system should stay in. Separately, a 2025 NBER paper shows reinforcement-learning trading agents can autonomously drift into collusive outcomes in simulation without explicit coordination. Taken together, the right governance stance is: no private or leaked-information use, no astroturfing or social-manipulation feedback loops, no quote stuffing or spoofing, and explicit human review when the system's apparent edge is driven by unexplained order-flow anomalies rather than verifiable public information. Recent press coverage adds a reputational warning. Business Insider covered a live-monitoring tool explicitly marketed around spotting unexplained Polymarket moves that might reflect informational advantage, and recent Wall Street Journal reporting has described deceptive sponsored-content practices and marketing narratives around "easy insider trading" on Polymarket. Whether or not those reports bear directly on your own integration, they increase the importance of strong internal rules on public communications, influencer use, and the handling of suspicious information sources.[^70]

## Prompt templates, backtesting, and evaluation

Ready-to-use instruction sets for the three skills The templates below are designed for a three-skill agent where each skill produces structured output and hands off cleanly to the next stage. They are intentionally conservative.

### /find prompt template

#### System instruction

You are FIND, a Polymarket market-selection skill. Your job is to rank tradable markets, not merely interesting markets. Priorities: - Use Polymarket discovery and market-data inputs first. - Penalise wide spreads, shallow depth, stale books, unclear resolution sources, and blocked jurisdictions. - Prefer markets where expected edge can survive fees and slippage. - Distinguish between maker-friendly and taker-friendly setups. - Output only markets that pass all hard risk filters.[^14]

#### Required inputs

- universe: categories, tags, explicit market IDs, or "all active"
- account_mode: maker | taker | mixed
- max_candidates: integer
- target_horizon_hours: integer or range
- min_depth_usd: float
- max_spread_bps: float
- min_edge_pct: float
- exclude_categories: array
- exclude_near_start_sports_minutes: integer
- geoblock_status: allowed | blocked
- stale_book_seconds: integer
- portfolio_context: current category/event exposures

#### Scoring

Rank using: liquidity_quality, net_edge, realised_volatility, information_flow, time_to_resolution_fit

#### Return JSON with:

```json
{
"timestamp_utc": "",
"top_markets": [
{
"market_id": "",
"token_id": "",
"question": "",
"category": "",
"resolution_source": "",
"best_bid": 0.0,
"best_ask": 0.0,
"mid": 0.0,
"spread_bps": 0.0,
"depth_within_2_ticks_usd": 0.0,
"vol_24h_usd": 0.0,
"time_to_resolution_hours": 0.0,
"info_flow_score": 0.0,
"edge_prelim_pct": 0.0,
"maker_or_taker_preference": "",
"find_score": 0.0,
"why_selected": ["", ""],
"key_risks": ["", ""]
}
],
"rejected_summary": {
"blocked": [],
"illiquid": [],
"too_wide": [],
"unclear_resolution": [],
"portfolio_conflict": []
}
}
```

Parameter Example universe ["politics", "economy", "crypto"] account_mode mixed target_horizon_hours 6-168 min_depth_usd 5000 max_spread_bps 150 min_edge_pct 2.0 exclude_near_start_sports_minutes 30

#### Example invocation

/find universe=["crypto","tech"] account_mode=mixed max_candidates=5 target_horizon_hours=24-240 min_depth_usd=10000 max_spread_bps=100 min_edge_pct=2.5 exclude_categories=["sports"] geoblock_status=allowed stale_book_seconds=3

### /analyze prompt template

#### System instruction

You are ANALYZE, a Polymarket trade-analysis skill. Your job is to convert evidence into a calibrated probability and an execution-ready trade plan.

#### Rules:

- Start from market-implied probability but do not stop there.
- Use only high-authority public evidence or explicitly provided features.
- Compute all-in EV after fees and slippage.
- Recommend no trade if the edge disappears after costs or if confidence is

low.

- Produce both maker and taker versions when relevant.
- Use fractional Kelly unless full Kelly is explicitly requested.

#### Required inputs

- market_id
- token_id
- side_to_evaluate: YES | NO | both
- current_bid
- current_ask
- orderbook_depth
- fee_category_rate
- expected_slippage_model
- posterior_inputs: market_prior, external_model_probs, retrieved_evidence
- bankroll_usd
- kelly_fraction: 0.25 | 0.50 | 1.00
- max_position_usd
- confidence_floor
- hold_to_resolution: true | false

#### Return JSON with:

```json
{
"posterior_prob_yes": 0.0,
"market_mid_prob_yes": 0.0,
"confidence": 0.0,
"evidence_summary": ["", ""],
"cost_model": {
"expected_fee_per_share": 0.0,
"expected_slippage_per_share": 0.0,
"all_in_cost_per_share": 0.0
},
"ev": {
"yes_ev_per_share": 0.0,
"no_ev_per_share": 0.0
},
"sizing": {
"kelly_fraction_raw": 0.0,
"kelly_fraction_used": 0.0,
"recommended_notional_usd": 0.0,
"max_shares": 0.0
},
"execution_plan": {
"preferred_mode": "maker|taker|no_trade",
"order_type": "",
"entry_price_limit": 0.0,
"cancel_if_not_filled_seconds": 0,
"thesis_invalidates_if": ["", ""]
}
}
```

/analyze market_id=0x... token_id=5211... side_to_evaluate=both current_bid=0.57 current_ask=0.59 fee_category_rate=0.015 bankroll_usd=250000 kelly_fraction=0.25 max_position_usd=4000 confidence_floor=0.62 hold_to_resolution=true

### /distribute prompt template

#### System instruction

You are DISTRIBUTE, a Polymarket portfolio-allocation skill. Your job is to size and combine candidate trades into a coherent portfolio.

#### Rules:

- Treat related markets as correlated until proven otherwise.
- Enforce hard market, event-cluster, category, liquidity, and time-bucket

limits.

- Prefer diversified edge over concentration in one narrative.
- Keep dry powder for new catalysts.
- Output both target weights and concrete rebalance actions.

#### Required inputs

- candidates: analyzed trades with EV, confidence, liquidity, and sizing data
- current_positions
- bankroll_usd
- dry_powder_pct
- event_cluster_map
- category_caps
- single_market_cap_pct
- event_cap_pct
- illiquid_cap_pct
- rebalance_threshold_pct
- objective: log_growth | mean_variance | risk_parity | cvar_constrained

#### Return JSON with:

```json
{
"objective_used": "",
"target_allocations": [
{
"market_id": "",
"token_id": "",
"side": "",
"target_notional_usd": 0.0,
"target_weight_pct": 0.0,
"reason": ""
}
],
"risk_summary": {
"category_exposure": {},
"event_cluster_exposure": {},
"illiquid_exposure_pct": 0.0,
"cash_buffer_pct": 0.0
},
"rebalance_actions": [
{
"action": "increase|reduce|exit|hold",
"market_id": "",
"token_id": "",
"delta_usd": 0.0,
"priority": 0
}
],
"blocked_allocations": [
{
"market_id": "",
"reason": ""
}
]
}
```

/distribute objective=cvar_constrained bankroll_usd=250000 dry_powder_pct=20 single_market_cap_pct=1.2 event_cap_pct=5 illiquid_cap_pct=10 rebalance_threshold_pct=0.35

## Recommended evaluation metrics and backtesting design

Forecasting quality should be measured separately from trading quality. For forecasting, the core metrics are Brier score, log loss, calibration slope/intercept, reliability by probability bucket, and resolution by category or horizon. Those are the proper ways to assess a probabilistic event trader; raw hit rate alone is an inferior metric because 80% predictions and 55% predictions should not be judged identically. Trading quality should then be measured with net PnL, expectancy per trade, turnover, cost drag, maker/taker mix, quote-to-fill ratio, adverse-fill rate, max drawdown, and a downside-sensitive portfolio metric such as expected shortfall. For market making, also track inventory half-life, realised spread, effective spread, and whether filled quotes subsequently moved against you. Recent prediction-market and market-making research strongly suggests that adverse selection, large-trade imbalance, and realistic fill assumptions determine whether a simulated edge is real.[^73]

Backtesting should be done in three layers.

| Layer | What to test | Why |
|-------|--------------|-----|
| Research replay | Reconstruct what information was public at each decision time and score posterior probabilities | Prevents hindsight leakage in /analyze. |
| Execution replay | Use historical prices, trade histories, and self-collected or archived book states to simulate realistic fills and queue outcomes | Needed because naive mid-price fills materially overstate performance.[^74] |
| Shadow live paper trading | Run the full stack against live data without capital | Catches integration bugs, stale-book logic problems, and operational timing errors before money is at risk. |

The most important simulation rule is to avoid "frictionless fills". The literature is now very clear that realistic fill probabilities and adverse fills materially change market-making results, and Polymarket's own CLOB mechanics reinforce that: you must model spread crossing, queue placement, partial fills, cancellations, restart windows, and heartbeat-triggered order loss. One additional Polymarket-specific caveat is dataset consistency. Because CLOB V2 changed contracts, fee handling, and collateral token conventions in April 2026, pre-cutover and post-cutover data should not be treated as one stationary regime. Fee logic, wallet/inventory flows, and execution details differ enough that regime-split backtests are the safer default.[^75]

### Strategy and risk trade-off table

| Strategy | Typical edge source | Best market conditions | Main costs | Main risks | Suitable skill emphasis |
|----------|--------------------|-----------------------|------------|------------|----------------------|
| Passive market making | Spread capture, rebates, inventory transformation | Liquid, slower markets with stable books | Opportunity cost, adverse selection | Toxic flow, inventory build-up, restart handling | /find microstructure + /distribute inventory control |
| Opportunistic taker | Fast public-information reaction | Clear catalysts, narrow spreads | Spread + taker fee + slippage | Chasing stale news, crowd overreaction | /analyze retrieval and calibration |
| Bundle / law-of-one-price arb | YES/NO or linked-market inconsistencies | Markets with mechanical relationships | Crossing costs on both legs | Legging risk, false equivalence | /find structure detection |
| Cross-platform arb | Polymarket vs Kalshi dislocations | High-liquidity common contracts | Venue-specific fees and transfer frictions | Mapping error, timing basis risk | /find and execution sync |
| Neg-risk / combo relative value | Structural inconsistency across mutually exclusive legs | Multi-outcome events | RFQ complexity, wider specialised spread | Model complexity, leg correlation error | /distribute dependency modelling |
| LLM-assisted event trading | Public-information synthesis | Newsy markets with tractable evidence | Research compute + execution cost | Hallucination, weak calibration, latency | /analyze |

## Open questions and limitations

The public documentation is strong on current books, price history, execution, and wallet operations, but it is less explicit about a turnkey full historical level-two depth replay dataset suitable for institutional-grade backtesting. In practice, a serious team may need to archive its own market-channel snapshots and trade events over time rather than rely solely on historical midpoint or price-history endpoints. That is an inference from the documented endpoint surface, not a claim that deeper internal datasets do not exist. Public GitHub repositories are useful architecture evidence, but they are not audited proof of live profitability. Several strong-looking projects are best read as reference implementations or design patterns rather than verified alpha sources, and one of the most popular Polymarket market-making repos explicitly says it is not profitable in today's environment as shipped. Finally, prediction-market regulation and venue structure are moving quickly. Polymarket's own infrastructure changed materially in 2026, and the broader prediction-market ecosystem is becoming more competitive and more politically visible. Any production deployment should therefore treat route-level docs, SDK versions, fee schedules, and venue-availability constraints as runtime configuration, not as constants baked into prompts or code. ecosystem developmentsturn31news29,turn29news40,turn30news49,turn30news50[^78]

## References

[^1]: https://docs.polymarket.com/trading/overview
[^2]: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6443103
[^3]: https://docs.polymarket.com/api-reference/introduction
[^4]: https://docs.polymarket.com/api-reference/geoblock
[^5]: https://docs.polymarket.com/trading/overview
[^6]: https://docs.polymarket.com/concepts/positions-tokens
[^7]: https://docs.polymarket.com/trading/overview
[^8]: https://mason.gmu.edu/~rhanson/mktscore.pdf
[^9]: https://docs.polymarket.com/concepts/resolution
[^10]: https://docs.polymarket.com/market-data/overview
[^11]: https://docs.polymarket.com/trading/fees
[^12]: https://docs.polymarket.com/trading/orders/create
[^13]: https://docs.polymarket.com/api-reference/introduction
[^14]: https://docs.polymarket.com/api-reference/authentication
[^15]: https://docs.polymarket.com/api-reference/rate-limits
[^16]: https://docs.polymarket.com/api-reference/markets/get-market-by-id
[^17]: https://docs.polymarket.com/market-data/websocket/market-channel
[^18]: https://docs.polymarket.com/api-reference/introduction
[^19]: https://docs.polymarket.com/api-reference/introduction
[^20]: https://docs.polymarket.com/api-reference/market-data/get-order-book
[^21]: https://docs.polymarket.com/market-data/websocket/market-channel
[^22]: https://docs.polymarket.com/api-reference/markets/get-market-by-id
[^23]: https://docs.polymarket.com/market-makers/combos
[^24]: https://github.com/polymarket/agents
[^25]: https://github.com/warproxxx/poly-maker
[^26]: https://github.com/ImMike/polymarket-arbitrage
[^27]: https://github.com/phenomenon0/polymarket-agents
[^28]: https://github.com/advaricorp/Polymarketbot
[^29]: https://github.com/sculptdotfun/tremor
[^30]: https://github.com/zachdaube/kalshi-market-maker
[^31]: https://github.com/microprediction/manifoldbot
[^32]: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6443103
[^33]: https://github.com/polymarket/agents
[^34]: https://github.com/polymarket/agents
[^35]: https://github.com/warproxxx/poly-maker
[^36]: https://github.com/ImMike/polymarket-arbitrage
[^37]: https://docs.polymarket.com/api-reference/search/search-markets-events-and-profiles
[^38]: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5331995
[^39]: https://docs.polymarket.com/api-reference/market-data/get-order-book
[^40]: https://docs.polymarket.com/trading/orderbook
[^41]: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5331995
[^42]: https://docs.polymarket.com/concepts/resolution
[^43]: https://docs.polymarket.com/api-reference/geoblock
[^44]: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5910522
[^45]: https://journals.ametsoc.org/view/journals/mwre/78/1/1520-0493_1950_078_0001_vofeit_2_0_co_2.xml
[^46]: https://docs.polymarket.com/trading/fees
[^47]: https://docs.polymarket.com/api-reference/market-data/get-order-book
[^48]: https://www.princeton.edu/~wbialek/rome/refs/kelly_56.pdf
[^49]: https://www.jstor.org/stable/2975974
[^50]: https://www.jstor.org/stable/2975974
[^51]: https://www.jstor.org/stable/2975974
[^52]: https://docs.polymarket.com/market-data/websocket/market-channel
[^53]: https://docs.polymarket.com/api-reference/introduction
[^54]: https://docs.polymarket.com/api-reference/market-data/get-order-book
[^55]: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6443103
[^56]: https://docs.polymarket.com/trading/orders/overview
[^57]: https://docs.polymarket.com/market-makers/inventory
[^58]: https://docs.polymarket.com/trading/orders/overview
[^59]: https://docs.polymarket.com/trading/orderbook
[^60]: https://docs.polymarket.com/trading/overview
[^61]: https://docs.polymarket.com/api-reference/authentication
[^62]: https://docs.polymarket.com/api-reference/geoblock
[^63]: https://docs.polymarket.com/trading/orders/overview
[^64]: https://docs.polymarket.com/trading/orders/overview
[^65]: https://docs.polymarket.com/trading/matching-engine
[^66]: https://docs.polymarket.com/concepts/markets-events
[^67]: https://docs.polymarket.com/api-reference/market-data/get-order-book
[^68]: https://docs.polymarket.com/api-reference/geoblock
[^69]: https://docs.polymarket.com/api-reference/authentication
[^70]: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6617059
[^71]: https://www.businessinsider.com/polymarket-spot-tremors-prediction-markets-ai-2025-9
[^72]: https://journals.ametsoc.org/view/journals/mwre/78/1/1520-0493_1950_078_0001_vofeit_2_0_co_2.xml
[^73]: https://law.stanford.edu/publications/adverse-selection-in-prediction-markets-evidence-from-kalshi/
[^74]: https://arxiv.org/html/2409.12721v2
[^75]: https://arxiv.org/html/2409.12721v2
[^76]: https://docs.polymarket.com/v2-migration
[^77]: https://docs.polymarket.com/api-reference/introduction
[^78]: https://docs.polymarket.com/v2-migration