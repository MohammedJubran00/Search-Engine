"""Conversation ownership tests. Chat HTTP wiring is not covered here."""

import asyncio
import uuid

from src.search_engine.core.security import hash_password
from src.search_engine.database.database import SessionLocal, engine
from src.search_engine.repositories.conversation_repository import ConversationRepository
from src.search_engine.repositories.message_repository import MessageRepository
from src.search_engine.repositories.user_repository import UserRepository


async def _isolation_scenario() -> None:
    async with SessionLocal() as session:
        users = UserRepository(session)
        conversations = ConversationRepository(session)
        messages = MessageRepository(session)

        owner = await users.create(
            full_name="Owner",
            email=f"owner-{uuid.uuid4().hex}@example.com",
            password_hash=hash_password("Str0ng!Pass"),
        )
        other = await users.create(
            full_name="Other",
            email=f"other-{uuid.uuid4().hex}@example.com",
            password_hash=hash_password("Str0ng!Pass"),
        )

        thread = await conversations.create(user_id=owner.id, title="Owner chat")
        await messages.create(
            conversation_id=thread.id,
            role="user",
            content="hello",
        )

        owned = await conversations.get_by_id_for_user(thread.id, owner.id)
        leaked = await conversations.get_by_id_for_user(thread.id, other.id)
        listed_other = await conversations.list_for_user(other.id)
        listed_owner = await conversations.list_for_user(owner.id)
        turns = await messages.list_for_conversation(thread.id)

        await session.commit()

    assert owned is not None
    assert owned.id == thread.id
    assert leaked is None
    assert listed_other == []
    assert [item.id for item in listed_owner] == [thread.id]
    assert len(turns) == 1
    assert turns[0].role == "user"
    assert turns[0].content == "hello"


def test_user_cannot_load_another_users_conversation() -> None:
    try:
        asyncio.run(_isolation_scenario())
    finally:
        asyncio.run(engine.dispose())
