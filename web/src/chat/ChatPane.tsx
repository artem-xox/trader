import { useCallback, useEffect, useRef, useState } from 'react';

import { api, authHeaders } from '../api/client';
import { streamSse } from '../api/stream';
import type { Message, StreamEvent } from '../api/types';
import { Composer } from './Composer';
import { MessageList } from './MessageList';
import { ProgressTrail, type Step } from './ProgressTrail';

/** An id for the message shown while the server is still writing the real one.
 *  Negative so it can never collide with a bigserial. */
const optimistic = (content: string): Message => ({
  id: -Date.now(),
  role: 'user',
  content,
  result: null,
  trace_url: null,
  created_at: new Date().toISOString(),
});

export function ChatPane({
  conversationId,
  onActivity,
}: {
  conversationId: string;
  /** The first turn renames the conversation and every turn reorders the list. */
  onActivity: () => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [steps, setSteps] = useState<Step[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    const conversation = await api.getConversation(conversationId);
    setMessages(conversation.messages);
  }, [conversationId]);

  useEffect(() => {
    setMessages([]);
    setSteps([]);
    setError(null);
    void load();
  }, [load]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, steps]);

  const send = async (text: string) => {
    setRunning(true);
    setSteps([]);
    setError(null);
    setMessages((previous) => [...previous, optimistic(text)]);

    try {
      const events = streamSse<StreamEvent>(
        `/api/conversations/${conversationId}/turns`,
        { message: text },
        { headers: authHeaders() },
      );
      for await (const event of events) {
        if (event.kind === 'status') {
          setSteps((previous) => [...previous, { label: event.label, detail: event.detail }]);
        } else if (event.kind === 'error') {
          throw new Error('The agent failed on this turn.');
        }
      }
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRunning(false);
      setSteps([]);
      // The server owns the transcript, so the truth is whatever it wrote — including
      // when the stream died mid-run and the answer landed anyway.
      await load();
      onActivity();
    }
  };

  return (
    <section className="chat">
      <div className="chat__scroll">
        <MessageList messages={messages} />
        {running && (
          <article className="message message--assistant">
            <ProgressTrail steps={steps} done={false} />
          </article>
        )}
        {error !== null && (
          <p className="verdict verdict--bad">
            {error} <span className="muted">— the answer may still have been saved; reload.</span>
          </p>
        )}
        <div ref={bottom} />
      </div>
      <Composer onSend={(message) => void send(message)} disabled={running} />
    </section>
  );
}
