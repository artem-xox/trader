/** The conversation list, and which one is open.
 *
 * The open conversation lives in the URL as `?c=<uuid>` rather than in state alone,
 * so reload and the browser's back button work. A query parameter rather than a path
 * segment keeps the SPA fallback trivial: FastAPI's StaticFiles serves index.html for
 * `/` and never has to route unknown paths.
 */
import { useCallback, useEffect, useState } from 'react';

import { api } from '../api/client';
import type { Conversation } from '../api/types';

function idFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get('c');
}

function pushId(id: string | null): void {
  const url = new URL(window.location.href);
  if (id === null) {
    url.searchParams.delete('c');
  } else {
    url.searchParams.set('c', id);
  }
  window.history.pushState({}, '', url);
}

export function useConversations() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(idFromUrl);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setConversations(await api.listConversations());
      setError(null);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // The back button changes the URL without a reload, so the app follows it.
  useEffect(() => {
    const onPop = () => setCurrentId(idFromUrl());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const open = useCallback((id: string | null) => {
    pushId(id);
    setCurrentId(id);
  }, []);

  const create = useCallback(async () => {
    const conversation = await api.createConversation();
    setConversations((previous) => [conversation, ...previous]);
    open(conversation.id);
  }, [open]);

  const remove = useCallback(
    async (id: string) => {
      await api.deleteConversation(id);
      setConversations((previous) => previous.filter((c) => c.id !== id));
      setCurrentId((previous) => {
        if (previous !== id) {
          return previous;
        }
        pushId(null);
        return null;
      });
    },
    [],
  );

  return { conversations, currentId, error, open, create, remove, refresh };
}
