"""Postgres storage for web conversations.

Owns the two tables in `schema.sql` and nothing else — the agent's own memory lives
in the LangGraph checkpointer, keyed by the same conversation id (docs/WEB.md §5.2).

Raw SQL over psycopg: the checkpointer already brings psycopg in, so this adds no
driver, and two tables do not justify an ORM.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from trader.app.schemas import Conversation, Message

_SCHEMA = Path(__file__).with_name("schema.sql")

# A dev database allows few connections and this app is single-user; the checkpointer
# opens a second pool of its own, so both stay small.
_MAX_POOL_SIZE = 3

# Sidebar titles come from the first user message. No LLM call: it is renameable, and a
# wrong guess is more annoying than a truncation.
_TITLE_MAX = 60


def title_from(message: str) -> str:
    title = " ".join(message.split())
    if len(title) <= _TITLE_MAX:
        return title or "New chat"
    return title[: _TITLE_MAX - 1].rstrip() + "…"


class Store:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> Store:
        """Open the pool and apply the schema. Every statement is idempotent, so this
        runs on every boot rather than through a migration tool."""
        pool = AsyncConnectionPool(
            dsn, min_size=1, max_size=_MAX_POOL_SIZE, open=False, kwargs={"row_factory": dict_row}
        )
        await pool.open(wait=True)
        async with pool.connection() as conn:
            await conn.execute(_SCHEMA.read_text())
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def create_conversation(self, title: str = "New chat") -> Conversation:
        async with self._pool.connection() as conn:
            row = await (
                await conn.execute(
                    "INSERT INTO conversations (id, title) VALUES (%s, %s) "
                    "RETURNING id, title, created_at, updated_at",
                    (uuid4(), title),
                )
            ).fetchone()
        return Conversation(**row, message_count=0)

    async def list_conversations(self) -> list[Conversation]:
        async with self._pool.connection() as conn:
            rows = await (
                await conn.execute(
                    "SELECT c.id, c.title, c.created_at, c.updated_at, "
                    "       count(m.id) AS message_count "
                    "FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id "
                    "GROUP BY c.id ORDER BY c.updated_at DESC"
                )
            ).fetchall()
        return [Conversation(**row) for row in rows]

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        async with self._pool.connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT c.id, c.title, c.created_at, c.updated_at, "
                    "       count(m.id) AS message_count "
                    "FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id "
                    "WHERE c.id = %s GROUP BY c.id",
                    (conversation_id,),
                )
            ).fetchone()
        return Conversation(**row) if row else None

    async def get_messages(self, conversation_id: UUID) -> list[Message]:
        async with self._pool.connection() as conn:
            rows = await (
                await conn.execute(
                    "SELECT id, role, content, result, trace_url, created_at FROM messages "
                    "WHERE conversation_id = %s ORDER BY id",
                    (conversation_id,),
                )
            ).fetchall()
        return [Message(**row) for row in rows]

    async def rename_conversation(self, conversation_id: UUID, title: str) -> bool:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "UPDATE conversations SET title = %s WHERE id = %s", (title, conversation_id)
            )
        return cur.rowcount > 0

    async def delete_conversation(self, conversation_id: UUID) -> bool:
        """Messages cascade. The caller also drops the agent's checkpoints for this
        thread, so nothing outlives the conversation."""
        async with self._pool.connection() as conn:
            cur = await conn.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))
        return cur.rowcount > 0

    async def add_message(
        self,
        conversation_id: UUID,
        role: str,
        content: str,
        *,
        result: dict | None = None,
        trace_url: str | None = None,
    ) -> Message:
        async with self._pool.connection() as conn, conn.transaction():
            row = await (
                await conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, result, trace_url) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "RETURNING id, role, content, result, trace_url, created_at",
                    (conversation_id, role, content, Jsonb(result) if result else None, trace_url),
                )
            ).fetchone()
            # Keeps the sidebar ordered by activity rather than by creation.
            await conn.execute(
                "UPDATE conversations SET updated_at = now() WHERE id = %s", (conversation_id,)
            )
        return Message(**row)
