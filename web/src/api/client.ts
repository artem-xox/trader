/** Talking to the agent app.
 *
 * The API is same-origin in production (FastAPI serves this build) and proxied in
 * dev, so every path here is relative and there is no CORS anywhere.
 */
import type { Conversation, ConversationDetail } from './types';

const KEY_STORAGE = 'trader.apiKey';

export function getKey(): string | null {
  return localStorage.getItem(KEY_STORAGE);
}

export function setKey(key: string): void {
  localStorage.setItem(KEY_STORAGE, key);
}

export function clearKey(): void {
  localStorage.removeItem(KEY_STORAGE);
}

/** Thrown on 401 so the UI can send the user back to the key screen instead of
 *  showing a generic failure they cannot act on. */
export class UnauthorizedError extends Error {
  constructor() {
    super('Invalid API key');
    this.name = 'UnauthorizedError';
  }
}

export function authHeaders(): Record<string, string> {
  const key = getKey();
  return key === null ? {} : { 'X-API-Key': key };
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...init.headers },
  });

  if (response.status === 401) {
    throw new UnauthorizedError();
  }
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

/** FastAPI puts a human-readable reason in `detail` — including the one that matters
 *  most here, "storage is not configured". A 422 carries a list instead. */
async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === 'string') {
      return body.detail;
    }
  } catch {
    // fall through to the status line
  }
  return `Request failed (${response.status})`;
}

/** Verifies the key by making the cheapest authenticated call there is. */
export async function checkKey(): Promise<void> {
  await request<Conversation[]>('/api/conversations');
}

export const api = {
  listConversations: () => request<Conversation[]>('/api/conversations'),
  createConversation: () => request<Conversation>('/api/conversations', { method: 'POST' }),
  getConversation: (id: string) => request<ConversationDetail>(`/api/conversations/${id}`),
  renameConversation: (id: string, title: string) =>
    request<Conversation>(`/api/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),
  deleteConversation: (id: string) =>
    request<void>(`/api/conversations/${id}`, { method: 'DELETE' }),
};
