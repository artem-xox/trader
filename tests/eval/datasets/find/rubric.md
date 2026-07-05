Judge a `find` research turn — a ranked shortlist of Polymarket bets.

A strong answer:
- Surfaces markets genuinely relevant to the user's topic (not loosely related). For an
  abstract ask ("undervalued", "most promising"), covers several distinct themes rather
  than one search's worth of results.
- Gives a concrete, QUANTIFIED edge per suggestion — implied probability vs. the
  analyst's fair estimate and the evidence for the gap — not a generic restatement of
  the question.
- Is tradability-aware: suggestions carry order-book execution data (spread, depth,
  find_score) from the tradability tool, and no suggested market was rejected by that
  tool as untradeable (wide spread, thin depth, extreme price, empty book).
- Is diverse: no pile of near-identical outcomes from one event, and no padding with
  dead longshots priced near 0 or 1 where the market is obviously right.
- Calibrates confidence and risk honestly (liquidity, resolution horizon, ambiguity).
- Stays grounded: every market it names is real; no invented prices, spreads, or scores.
- Is decisive and useful — a shortlist a sharp bettor could act on, or an honest
  "nothing worth suggesting" when that is true.

Penalize: irrelevant markets, hand-wavy or unquantified rationale, suggesting markets
the tradability data says are untradeable, near-duplicate suggestions, longshot spam,
miscalibrated certainty, padding.
