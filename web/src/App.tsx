/** Phase 0 walking skeleton (docs/WEB.md §9).
 *
 * This page exists to answer two infrastructure questions from the deployed
 * origin, before any real UI is written:
 *
 *   1. does the API answer under `/api` once FastAPI is also serving this SPA?
 *   2. do SSE frames arrive incrementally, or does something between the
 *      service and the browser buffer the whole response into one chunk?
 *
 * (2) is the project's main technical risk — App Platform's edge cache is the
 * documented cause of buffered SSE, and the escape hatch (`disable_edge_cache`)
 * is only available to apps with no static-site component, which is why the SPA
 * is served by FastAPI at all. The probe measures arrival times client-side, so
 * a buffered response is visible rather than merely suspected.
 *
 * Phase 2 replaces this page with the real chat. `api/stream.ts` stays.
 */
import { useEffect, useState } from 'react';

import { streamSse } from './api/stream';

/** One frame from `POST /api/stream-probe`. */
type ProbeFrame = {
  seq: number;
  total: number;
  /** Server clock when the frame was written, epoch seconds. */
  sent_at: number;
};

type Arrival = ProbeFrame & { offsetMs: number };

/** Frames are emitted a second apart, so anything under this means the whole
 *  response landed at once — the failure this page is looking for. */
const INCREMENTAL_THRESHOLD_MS = 1500;

type Health = { state: 'checking' } | { state: 'ok'; ms: number } | { state: 'failed'; error: string };

function HealthPanel() {
  const [health, setHealth] = useState<Health>({ state: 'checking' });

  useEffect(() => {
    const started = performance.now();
    fetch('/api/health')
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`responded ${response.status}`);
        }
        await response.json();
        setHealth({ state: 'ok', ms: Math.round(performance.now() - started) });
      })
      .catch((error: unknown) => {
        setHealth({ state: 'failed', error: error instanceof Error ? error.message : String(error) });
      });
  }, []);

  return (
    <section className="panel">
      <h2>API reachable under /api</h2>
      {health.state === 'checking' && <p className="muted">checking…</p>}
      {health.state === 'ok' && (
        <p className="verdict verdict--good">GET /api/health → ok · {health.ms} ms</p>
      )}
      {health.state === 'failed' && <p className="verdict verdict--bad">failed: {health.error}</p>}
    </section>
  );
}

function StreamPanel() {
  const [arrivals, setArrivals] = useState<Arrival[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setArrivals([]);
    setError(null);
    setRunning(true);
    const started = performance.now();
    try {
      for await (const frame of streamSse<ProbeFrame>('/api/stream-probe', {})) {
        setArrivals((previous) => [
          ...previous,
          { ...frame, offsetMs: Math.round(performance.now() - started) },
        ]);
      }
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRunning(false);
    }
  };

  const span = arrivals.length > 1 ? arrivals[arrivals.length - 1].offsetMs - arrivals[0].offsetMs : 0;
  const complete = arrivals.length > 0 && arrivals.length === arrivals[0].total;
  const incremental = span >= INCREMENTAL_THRESHOLD_MS;

  return (
    <section className="panel">
      <h2>SSE arrives incrementally</h2>
      <button type="button" onClick={run} disabled={running}>
        {running ? 'streaming…' : 'run probe'}
      </button>

      {arrivals.length > 0 && (
        <ol className="frames">
          {arrivals.map((arrival) => (
            <li key={arrival.seq}>
              <span className="muted">frame {arrival.seq + 1}</span>
              <span>+{arrival.offsetMs} ms</span>
            </li>
          ))}
        </ol>
      )}

      {error !== null && <p className="verdict verdict--bad">failed: {error}</p>}

      {complete && (
        <p className={`verdict ${incremental ? 'verdict--good' : 'verdict--bad'}`}>
          {incremental
            ? `incremental — ${arrivals.length} frames spread over ${span} ms`
            : `buffered — all ${arrivals.length} frames landed within ${span} ms; ` +
              'set disable_edge_cache on the app and re-run'}
        </p>
      )}
    </section>
  );
}

export function App() {
  return (
    <main className="page">
      <header>
        <h1>AI Trader</h1>
        <p className="muted">Phase 0 skeleton — infrastructure probes, no agent yet.</p>
      </header>
      <HealthPanel />
      <StreamPanel />
    </main>
  );
}
