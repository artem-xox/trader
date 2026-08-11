import Markdown from 'react-markdown';

import type { Message } from '../api/types';

/** Answers are CommonMark (`app/formatting.py`), so they render as markdown here just
 *  as the bot converts them to Telegram's dialect. Phase 3 replaces this with cards
 *  built from `message.result`, keeping the markdown only for normal-mode answers. */
export function MessageList({ messages }: { messages: Message[] }) {
  return (
    <>
      {messages.map((message) => (
        <article key={message.id} className={`message message--${message.role}`}>
          {message.role === 'user' ? (
            <p>{message.content}</p>
          ) : (
            <Markdown>{message.content}</Markdown>
          )}
          {message.trace_url !== null && (
            <a className="message__trace" href={message.trace_url} target="_blank" rel="noreferrer">
              🔗 trace
            </a>
          )}
        </article>
      ))}
    </>
  );
}
