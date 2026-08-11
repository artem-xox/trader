import { useRef, useState, type KeyboardEvent } from 'react';

/** Enter sends, Shift+Enter breaks the line — the convention every chat client shares,
 *  and the reason this is a textarea rather than an input. */
export function Composer({
  onSend,
  disabled,
}: {
  onSend: (message: string) => void;
  disabled: boolean;
}) {
  const [value, setValue] = useState('');
  const textarea = useRef<HTMLTextAreaElement>(null);

  const send = () => {
    const message = value.trim();
    if (message === '' || disabled) {
      return;
    }
    onSend(message);
    setValue('');
    textarea.current?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  };

  return (
    <div className="composer">
      <textarea
        ref={textarea}
        rows={1}
        value={value}
        disabled={disabled}
        placeholder="Ask something, or /find <topic> · /analyze <market url>"
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
      />
      <button type="button" onClick={send} disabled={disabled || value.trim() === ''}>
        {disabled ? '…' : 'Send'}
      </button>
    </div>
  );
}
