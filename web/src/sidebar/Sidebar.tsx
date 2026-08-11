import type { Conversation } from '../api/types';

/** Coarse buckets rather than timestamps — the useful question about an old chat is
 *  "roughly when", and exact times would only add noise to a narrow column. */
function bucket(updatedAt: string): string {
  const days = (Date.now() - new Date(updatedAt).getTime()) / 86_400_000;
  if (days < 1) return 'Today';
  if (days < 2) return 'Yesterday';
  if (days < 7) return 'This week';
  if (days < 30) return 'This month';
  return 'Older';
}

type Props = {
  conversations: Conversation[];
  currentId: string | null;
  onOpen: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
};

export function Sidebar({ conversations, currentId, onOpen, onCreate, onDelete }: Props) {
  let lastBucket = '';

  return (
    <nav className="sidebar">
      <button type="button" className="sidebar__new" onClick={onCreate}>
        + New chat
      </button>

      <ol className="sidebar__list">
        {conversations.map((conversation) => {
          const group = bucket(conversation.updated_at);
          const heading = group === lastBucket ? null : group;
          lastBucket = group;
          return (
            <li key={conversation.id}>
              {heading !== null && <h2 className="sidebar__bucket">{heading}</h2>}
              <div
                className={`sidebar__item ${conversation.id === currentId ? 'is-current' : ''}`}
              >
                <button type="button" onClick={() => onOpen(conversation.id)}>
                  {conversation.title}
                </button>
                <button
                  type="button"
                  className="sidebar__delete"
                  aria-label={`Delete ${conversation.title}`}
                  onClick={() => onDelete(conversation.id)}
                >
                  ×
                </button>
              </div>
            </li>
          );
        })}
      </ol>

      {conversations.length === 0 && <p className="muted sidebar__empty">No conversations yet.</p>}
    </nav>
  );
}
