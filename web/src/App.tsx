/** Layout: conversation list on the left, one conversation on the right.
 *
 * Phase 0's probe page lived here; the probe *endpoints* remain as diagnostics
 * (`/api/health`, `POST /api/stream-probe`) and are worth re-running by hand if SSE
 * ever looks buffered again.
 */
import { useState } from 'react';

import { getKey } from './api/client';
import { KeyGate } from './auth/KeyGate';
import { ChatPane } from './chat/ChatPane';
import { Sidebar } from './sidebar/Sidebar';
import { useConversations } from './sidebar/useConversations';

function Workspace() {
  const { conversations, currentId, error, open, create, remove, refresh } = useConversations();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const current = conversations.find((conversation) => conversation.id === currentId);

  return (
    <div className={`workspace ${drawerOpen ? 'is-drawer-open' : ''}`}>
      <Sidebar
        conversations={conversations}
        currentId={currentId}
        onOpen={(id) => {
          open(id);
          setDrawerOpen(false);
        }}
        onCreate={() => {
          void create();
          setDrawerOpen(false);
        }}
        onDelete={(id) => void remove(id)}
      />

      <main className="main">
        <header className="topbar">
          <button
            type="button"
            className="topbar__toggle"
            aria-label="Toggle conversations"
            onClick={() => setDrawerOpen((previous) => !previous)}
          >
            ☰
          </button>
          <h1>{current?.title ?? 'AI Trader'}</h1>
        </header>

        {error !== null && <p className="verdict verdict--bad">{error}</p>}

        {currentId === null ? (
          <div className="empty">
            <p className="muted">Pick a conversation, or start a new one.</p>
            <button type="button" onClick={() => void create()}>
              + New chat
            </button>
          </div>
        ) : (
          // Keyed by id so switching conversations remounts rather than briefly
          // showing the previous transcript under the new title.
          <ChatPane key={currentId} conversationId={currentId} onActivity={() => void refresh()} />
        )}
      </main>
    </div>
  );
}

export function App() {
  const [unlocked, setUnlocked] = useState(getKey() !== null);
  return unlocked ? <Workspace /> : <KeyGate onUnlocked={() => setUnlocked(true)} />;
}
