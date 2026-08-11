/** Hand-written mirrors of the server's pydantic schemas.
 *
 * Generated types would be better in principle, but `SerializeAsAny[SkillResult]`
 * collapses the result union in the OpenAPI schema, so generation produces a base
 * type with only `summary` on it. These three shapes change rarely; when they do,
 * `src/trader/core/models/domain.py` is the source of truth.
 */

export type Level = 'low' | 'medium' | 'high';
export type Stance = 'lean_yes' | 'lean_no' | 'pass';

export type RiskAssessment = {
  level: Level;
  factors: string[];
  note: string;
};

/** One ranked market from the `find` skill. Phase 3 renders this as a card. */
export type Suggestion = {
  market_id: string;
  question: string;
  url: string | null;
  implied_probability: number | null;
  rationale: string;
  confidence: Level;
  risk: RiskAssessment;
  // Execution metrics, copied verbatim from the tradability tool. Absent when it
  // was not called for this market.
  spread_bps: number | null;
  depth_usd: number | null;
  find_score: number | null;
  maker_or_taker: 'maker' | 'taker' | null;
};

/** The `analyze` skill's deep dive on one market. */
export type MarketAnalysis = {
  summary: string;
  market_id: string;
  question: string;
  url: string | null;
  resolution_criteria: string | null;
  implied_probability: number | null;
  fair_probability: number | null;
  edge: string;
  stance: Stance;
  confidence: Level;
  key_factors: string[];
  risk: RiskAssessment;
};

export type ResearchResult = { summary: string; suggestions: Suggestion[] };
export type GeneralAnswer = { summary: string };

/** Whatever the responder produced. Phase 3 adds a `kind` discriminator; until then
 *  the renderer decides by which fields are present. */
export type SkillResult = Partial<ResearchResult & MarketAnalysis> & { summary: string };

export type Message = {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  result: SkillResult | null;
  trace_url: string | null;
  created_at: string;
};

export type Conversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
};

export type ConversationDetail = Conversation & { messages: Message[] };

/** One frame of `POST /api/conversations/{id}/turns`. */
export type StreamEvent = {
  kind: 'status' | 'final' | 'error';
  label: string;
  detail: string | null;
  response: string | null;
  result: SkillResult | null;
  trace_url: string | null;
};
