/** The shared-secret screen.
 *
 * This is a single-user tool behind one key (docs/WEB.md D3): the key lives in
 * localStorage and travels as `X-API-Key`. It is not a session — there is no expiry
 * and no revocation beyond rotating the secret and re-entering it here.
 */
import { useState, type FormEvent } from 'react';

import { UnauthorizedError, checkKey, setKey } from '../api/client';

export function KeyGate({ onUnlocked }: { onUnlocked: () => void }) {
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (value.trim() === '') {
      return;
    }
    setChecking(true);
    setError(null);
    setKey(value.trim());
    try {
      // Verify before letting the user in, so a wrong key fails here rather than
      // halfway through their first question.
      await checkKey();
      onUnlocked();
    } catch (caught: unknown) {
      setError(
        caught instanceof UnauthorizedError
          ? 'That key was rejected.'
          : caught instanceof Error
            ? caught.message
            : String(caught),
      );
      setChecking(false);
    }
  };

  return (
    <main className="gate">
      <form className="gate__form" onSubmit={submit}>
        <h1>AI Trader</h1>
        <p className="muted">Enter the agent API key to continue.</p>
        <input
          type="password"
          value={value}
          autoFocus
          placeholder="API key"
          onChange={(event) => setValue(event.target.value)}
        />
        <button type="submit" disabled={checking || value.trim() === ''}>
          {checking ? 'checking…' : 'unlock'}
        </button>
        {error !== null && <p className="verdict verdict--bad">{error}</p>}
      </form>
    </main>
  );
}
