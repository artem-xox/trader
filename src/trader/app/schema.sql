-- Transcript storage for the web client (docs/WEB.md §5.2).
--
-- Applied at startup, which is why every statement is idempotent: two tables do not
-- justify a migration tool, and this mirrors how the LangGraph checkpointer migrates
-- its own tables. Revisit if a destructive change ever becomes necessary.
--
-- This duplicates content the checkpointer also holds, deliberately: checkpoints store
-- LangChain messages, not the SkillResult the market cards are rendered from, and
-- rebuilding a card from a checkpoint would be fragile.

CREATE TABLE IF NOT EXISTS conversations (
    id         uuid        PRIMARY KEY,
    title      text        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id              bigserial   PRIMARY KEY,
    conversation_id uuid        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            text        NOT NULL CHECK (role IN ('user', 'assistant')),
    -- The user's text, or the assistant's rendered markdown answer.
    content         text        NOT NULL,
    -- The structured SkillResult. Assistant rows only; this is what the UI renders
    -- market cards from.
    result          jsonb,
    trace_url       text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Every read is "the messages of one conversation, in order".
CREATE INDEX IF NOT EXISTS messages_conversation_idx ON messages (conversation_id, id);

-- The sidebar lists conversations most-recently-touched first.
CREATE INDEX IF NOT EXISTS conversations_updated_idx ON conversations (updated_at DESC);
