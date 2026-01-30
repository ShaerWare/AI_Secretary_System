"""
Chat repository for managing chat sessions and messages.
"""

import hashlib
import time
from datetime import datetime
from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import ChatMessage, ChatSession
from db.redis_client import (
    cache_session,
    get_cached_session,
    invalidate_session_cache,
)
from db.repositories.base import BaseRepository


class ChatRepository(BaseRepository[ChatSession]):
    """Repository for chat sessions and messages."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ChatSession)

    def _generate_session_id(self) -> str:
        """Generate unique session ID."""
        return f"chat_{int(time.time() * 1000)}"

    def _generate_message_id(self) -> str:
        """Generate unique message ID."""
        ts = str(time.time())
        hash_suffix = hashlib.md5(ts.encode()).hexdigest()[:6]
        return f"msg_{int(time.time() * 1000)}_{hash_suffix}"

    async def list_sessions(self) -> List[dict]:
        """Get list of all sessions with summary info."""
        result = await self.session.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .order_by(ChatSession.updated.desc())
        )
        sessions = result.scalars().all()
        return [s.to_summary() for s in sessions]

    async def get_session(self, session_id: str) -> Optional[dict]:
        """Get full session with messages, with Redis caching."""
        # Try cache first
        cached = await get_cached_session(session_id)
        if cached:
            return cached

        # Fetch from database
        result = await self.session.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == session_id)
        )
        session = result.scalar_one_or_none()

        if session:
            data = session.to_dict()
            # Cache for 5 minutes
            await cache_session(session_id, data, ttl_seconds=300)
            return data
        return None

    async def create_session(
        self,
        title: str = None,
        system_prompt: str = None,
        source: str = None,
        source_id: str = None,
    ) -> dict:
        """Create new chat session."""
        session_id = self._generate_session_id()
        now = datetime.utcnow()

        session = ChatSession(
            id=session_id,
            title=title or "Новый чат",
            system_prompt=system_prompt,
            source=source,
            source_id=source_id,
            created=now,
            updated=now,
        )

        self.session.add(session)
        await self.session.commit()
        await self.session.refresh(session)

        # Return dict manually to avoid lazy loading issues
        return {
            "id": session.id,
            "title": session.title,
            "system_prompt": session.system_prompt,
            "source": session.source,
            "source_id": session.source_id,
            "created": session.created.isoformat() if session.created else None,
            "updated": session.updated.isoformat() if session.updated else None,
            "messages": [],  # New session has no messages
        }

    async def update_session(
        self,
        session_id: str,
        title: str = None,
        system_prompt: str = None,
    ) -> Optional[dict]:
        """Update session title or system prompt."""
        result = await self.session.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == session_id)
        )
        session = result.scalar_one_or_none()

        if not session:
            return None

        if title is not None:
            session.title = title
        if system_prompt is not None:
            session.system_prompt = system_prompt
        session.updated = datetime.utcnow()

        await self.session.commit()
        await invalidate_session_cache(session_id)

        return session.to_dict()

    async def delete_session(self, session_id: str) -> bool:
        """Delete session and all its messages."""
        result = await self.session.execute(delete(ChatSession).where(ChatSession.id == session_id))
        await self.session.commit()
        await invalidate_session_cache(session_id)
        return result.rowcount > 0

    async def delete_sessions_bulk(self, session_ids: List[str]) -> int:
        """Delete multiple sessions by ID list."""
        if not session_ids:
            return 0

        result = await self.session.execute(
            delete(ChatSession).where(ChatSession.id.in_(session_ids))
        )
        await self.session.commit()

        # Invalidate cache for all deleted sessions
        for sid in session_ids:
            await invalidate_session_cache(sid)

        return result.rowcount

    async def list_sessions_grouped(self) -> dict:
        """Get sessions grouped by source."""
        result = await self.session.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .order_by(ChatSession.updated.desc())
        )
        sessions = result.scalars().all()

        grouped = {
            "admin": [],
            "telegram": [],
            "widget": [],
            "unknown": [],
        }

        for s in sessions:
            summary = s.to_summary()
            source = s.source or "unknown"
            if source in grouped:
                grouped[source].append(summary)
            else:
                grouped["unknown"].append(summary)

        return grouped

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> Optional[dict]:
        """Add message to session."""
        result = await self.session.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == session_id)
        )
        session = result.scalar_one_or_none()

        if not session:
            return None

        message = ChatMessage(
            id=self._generate_message_id(),
            session_id=session_id,
            role=role,
            content=content,
            edited=False,
            created=datetime.utcnow(),
        )

        self.session.add(message)

        # Auto-generate title from first message
        if len(session.messages) == 0 and session.title == "Новый чат":
            session.title = content[:50] + ("..." if len(content) > 50 else "")

        session.updated = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(message)
        await invalidate_session_cache(session_id)

        return message.to_dict()

    async def edit_message(
        self,
        session_id: str,
        message_id: str,
        content: str,
    ) -> Optional[dict]:
        """Edit existing message."""
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.id == message_id)
            .where(ChatMessage.session_id == session_id)
        )
        message = result.scalar_one_or_none()

        if not message:
            return None

        message.content = content
        message.edited = True
        message.created = datetime.utcnow()

        # Update session timestamp
        session = await self.session.get(ChatSession, session_id)
        if session:
            session.updated = datetime.utcnow()

        await self.session.commit()
        await invalidate_session_cache(session_id)

        return message.to_dict()

    async def delete_message(
        self,
        session_id: str,
        message_id: str,
    ) -> bool:
        """Delete message and all subsequent messages."""
        # Get the target message
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.id == message_id)
            .where(ChatMessage.session_id == session_id)
        )
        message = result.scalar_one_or_none()

        if not message:
            return False

        # Delete this message and all messages after it
        await self.session.execute(
            delete(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .where(ChatMessage.created >= message.created)
        )

        # Update session timestamp
        session = await self.session.get(ChatSession, session_id)
        if session:
            session.updated = datetime.utcnow()

        await self.session.commit()
        await invalidate_session_cache(session_id)

        return True

    async def get_messages_for_llm(
        self,
        session_id: str,
        system_prompt: str = None,
    ) -> List[dict]:
        """Get messages in LLM format (role, content)."""
        result = await self.session.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == session_id)
        )
        session = result.scalar_one_or_none()

        if not session:
            return []

        messages = []

        # Add system prompt
        prompt = session.system_prompt or system_prompt
        if prompt:
            messages.append({"role": "system", "content": prompt})

        # Add message history
        for msg in session.messages:
            messages.append({"role": msg.role, "content": msg.content})

        return messages

    async def get_session_count(self) -> int:
        """Get total number of sessions."""
        return await self.count()

    async def get_message_count(self) -> int:
        """Get total number of messages across all sessions."""
        from sqlalchemy import func

        result = await self.session.execute(select(func.count()).select_from(ChatMessage))
        return result.scalar() or 0
