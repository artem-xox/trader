import { describeStep } from './labels';

export type Step = { label: string; detail: string | null };

/** The run as it happens: finished steps keep a tick, the last one pulses.
 *
 * A trail rather than Telegram's single edited line — a browser has the room, and
 * seeing which tools ran is most of what makes a slow answer tolerable. It is not
 * persisted: reopening an old conversation shows the answer, not how it was reached.
 */
export function ProgressTrail({ steps, done }: { steps: Step[]; done: boolean }) {
  if (steps.length === 0) {
    return <p className="trail__waiting muted">💭 Thinking…</p>;
  }

  return (
    <ol className="trail">
      {steps.map((step, index) => {
        const { icon, text } = describeStep(step.label);
        const running = !done && index === steps.length - 1;
        return (
          <li key={`${step.label}-${index}`} className={running ? 'is-running' : 'is-done'}>
            <span className="trail__mark">{running ? '⟳' : '✓'}</span>
            <span className="trail__icon">{icon}</span>
            <span>{text}</span>
            {step.detail !== null && <span className="trail__detail">{step.detail}</span>}
          </li>
        );
      })}
    </ol>
  );
}
