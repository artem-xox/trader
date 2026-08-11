"""Store tests against a real Postgres.

These exercise SQL, so a stand-in would test nothing. They run when DATABASE_URL is
set — always in CI (a postgres service container), on demand locally — and skip
otherwise, which keeps the default `make test` offline and free.

They never truncate: each test creates the rows it needs and drops them afterwards, so
pointing DATABASE_URL at a database with real conversations cannot destroy it.
"""

from __future__ import annotations

import os

import pytest

from trader.app.store import Store, title_from

@pytest.fixture
async def store():
    """A connected store that removes whatever the test created.

    The skip lives here rather than on the module so the pure `title_from` tests
    still run without a database.
    """
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        pytest.skip("needs DATABASE_URL pointing at a Postgres")

    store = await Store.connect(dsn)
    before = {c.id for c in await store.list_conversations()}
    try:
        yield store
    finally:
        for conversation in await store.list_conversations():
            if conversation.id not in before:
                await store.delete_conversation(conversation.id)
        await store.close()


async def test_create_then_read_back(store: Store) -> None:
    conversation = await store.create_conversation()
    fetched = await store.get_conversation(conversation.id)
    assert fetched is not None
    assert (fetched.id, fetched.title, fetched.message_count) == (conversation.id, "New chat", 0)


async def test_messages_keep_order_and_structured_result(store: Store) -> None:
    conversation = await store.create_conversation()
    await store.add_message(conversation.id, "user", "/find bitcoin")
    result = {"summary": "one idea", "suggestions": [{"market_id": "42", "question": "Will it?"}]}
    await store.add_message(
        conversation.id, "assistant", "**one idea**", result=result, trace_url="https://trace"
    )

    messages = await store.get_messages(conversation.id)
    assert [m.role for m in messages] == ["user", "assistant"]
    # The jsonb round trip is the point: the browser renders market cards from this.
    assert messages[1].result == result
    assert messages[1].trace_url == "https://trace"
    assert messages[0].result is None


async def test_message_count_and_ordering_by_activity(store: Store) -> None:
    older = await store.create_conversation()
    newer = await store.create_conversation()
    await store.add_message(older.id, "user", "hello")

    listed = {c.id: c for c in await store.list_conversations()}
    assert listed[older.id].message_count == 1
    assert listed[newer.id].message_count == 0
    # `older` was created first but touched last, so the sidebar puts it on top.
    order = [c.id for c in await store.list_conversations() if c.id in {older.id, newer.id}]
    assert order == [older.id, newer.id]


async def test_rename(store: Store) -> None:
    conversation = await store.create_conversation()
    assert await store.rename_conversation(conversation.id, "Bitcoin research")
    fetched = await store.get_conversation(conversation.id)
    assert fetched is not None and fetched.title == "Bitcoin research"


async def test_delete_takes_the_messages_with_it(store: Store) -> None:
    conversation = await store.create_conversation()
    await store.add_message(conversation.id, "user", "hello")

    assert await store.delete_conversation(conversation.id)
    assert await store.get_conversation(conversation.id) is None
    assert await store.get_messages(conversation.id) == []
    assert not await store.delete_conversation(conversation.id)  # already gone


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("/find bitcoin 2026", "/find bitcoin 2026"),
        ("  spaced   out  \n text ", "spaced out text"),
        ("x" * 80, "x" * 59 + "…"),
    ],
)
def test_title_from(message: str, expected: str) -> None:
    assert title_from(message) == expected
