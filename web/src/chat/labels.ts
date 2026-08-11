/** Progress events arrive as semantic keys — `tool:web_search`, `synthesize` — and each
 *  client renders them its own way. This is the web's rendering; the Telegram bot's
 *  lives in `src/trader/ui/telegram/content/messages.py` and reads the same stream.
 */
const STEPS: Record<string, { icon: string; text: string }> = {
  'skill:find': { icon: '🔎', text: 'Finding bets' },
  'skill:analyze': { icon: '📊', text: 'Analyzing the market' },
  'tool:polymarket_search': { icon: '🔎', text: 'Searching markets' },
  'tool:polymarket_market': { icon: '📄', text: 'Reading the market' },
  'tool:polymarket_orderbook': { icon: '📈', text: 'Reading the order book' },
  'tool:polymarket_tradability': { icon: '⚖️', text: 'Scoring tradability' },
  'tool:web_search': { icon: '🌐', text: 'Searching the web' },
  'tool:web_fetch': { icon: '🌐', text: 'Reading a page' },
  'tool:calculator': { icon: '🧮', text: 'Crunching numbers' },
  'tool:current_datetime': { icon: '🕐', text: 'Checking the date' },
  'tool:think': { icon: '🤔', text: 'Thinking it through' },
  synthesize: { icon: '✍️', text: 'Writing the answer' },
  revise: { icon: '🔁', text: 'Refining the answer' },
};

const UNKNOWN = { icon: '💭', text: 'Working' };

export function describeStep(label: string): { icon: string; text: string } {
  return STEPS[label] ?? UNKNOWN;
}
