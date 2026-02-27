"""
Chat repository for managing chat sessions and messages.
"""

import hashlib
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import ChatMessage, ChatSession, ChatSessionShare
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

    async def list_sessions(
        self,
        owner_id: Optional[int] = None,
        source: Optional[str] = None,
        exclude_source: Optional[str] = None,
        workspace_id: Optional[int] = None,
    ) -> List[dict]:
        """Get list of sessions with summary info, filtered by owner and source."""
        query = (
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .order_by(ChatSession.pinned.desc(), ChatSession.updated.desc())
        )
        query = self._apply_workspace_filter(query, workspace_id)
        if owner_id is not None:
            shared_subq = (
                select(ChatSessionShare.session_id)
                .where(ChatSessionShare.user_id == owner_id)
                .scalar_subquery()
            )
            query = query.where(
                (ChatSession.owner_id == owner_id)
                | (ChatSession.owner_id.is_(None))
                | (ChatSession.id.in_(shared_subq))
            )
        if source is not None:
            db_source = "telegram_bot" if source == "telegram" else source
            query = query.where(ChatSession.source == db_source)
        if exclude_source is not None:
            db_exclude = "telegram_bot" if exclude_source == "telegram" else exclude_source
            query = query.where(
                (ChatSession.source != db_exclude) & (ChatSession.source.is_not(None))
            )
        result = await self.session.execute(query)
        sessions = result.scalars().all()
        return [s.to_summary() for s in sessions]

    async def get_session(
        self,
        session_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Get full session with messages, with Redis caching."""
        # Try cache first (skip cache if owner/workspace filtering needed)
        if owner_id is None and workspace_id is None:
            cached = await get_cached_session(session_id)
            if cached:
                return cached

        # Fetch from database
        query = (
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == session_id)
        )
        query = self._apply_workspace_filter(query, workspace_id)
        if owner_id is not None:
            shared_subq = (
                select(ChatSessionShare.session_id)
                .where(
                    ChatSessionShare.user_id == owner_id,
                    ChatSessionShare.session_id == session_id,
                )
                .scalar_subquery()
            )
            query = query.where(
                (ChatSession.owner_id == owner_id)
                | (ChatSession.owner_id.is_(None))
                | (ChatSession.id.in_(shared_subq))
            )
        result = await self.session.execute(query)
        session = result.scalar_one_or_none()

        if session:
            data: dict[str, Any] = session.to_dict()
            # Cache for 5 minutes
            await cache_session(session_id, data, ttl_seconds=300)
            return data
        return None

    async def create_session(
        self,
        title: Optional[str] = None,
        system_prompt: Optional[str] = None,
        source: Optional[str] = None,
        source_id: Optional[str] = None,
        owner_id: Optional[int] = None,
        rag_mode: Optional[str] = None,
        knowledge_collection_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> dict:
        """Create new chat session."""
        session_id = self._generate_session_id()
        now = datetime.utcnow()

        kwargs: dict[str, Any] = dict(
            id=session_id,
            title=title or "Новый чат",
            system_prompt=system_prompt,
            source=source,
            source_id=source_id,
            owner_id=owner_id,
            rag_mode=rag_mode,
            knowledge_collection_id=knowledge_collection_id,
            created=now,
            updated=now,
        )
        if workspace_id is not None:
            kwargs["workspace_id"] = workspace_id

        session = ChatSession(**kwargs)

        self.session.add(session)
        await self.session.commit()

        # Return dict manually to avoid lazy loading issues
        return {
            "id": session.id,
            "title": session.title,
            "system_prompt": session.system_prompt,
            "source": session.source,
            "source_id": session.source_id,
            "rag_mode": session.rag_mode,
            "knowledge_collection_id": session.knowledge_collection_id,
            "created": session.created.isoformat() if session.created else None,
            "updated": session.updated.isoformat() if session.updated else None,
            "messages": [],  # New session has no messages
        }

    async def update_session(
        self,
        session_id: str,
        title: Optional[str] = None,
        system_prompt: Optional[str] = None,
        pinned: Optional[bool] = None,
        rag_mode: Optional[str] = None,
        knowledge_collection_id: Optional[int] = None,
        knowledge_collection_ids: Optional[list[int]] = None,
        context_files: Optional[list] = None,
    ) -> Optional[dict]:
        """Update session title, system prompt, pinned status, RAG config, or context files."""
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
        if pinned is not None:
            session.pinned = pinned
        if rag_mode is not None:
            session.rag_mode = rag_mode
        if knowledge_collection_id is not None:
            # Allow unsetting with 0 or -1
            session.knowledge_collection_id = (
                knowledge_collection_id if knowledge_collection_id > 0 else None
            )
        if knowledge_collection_ids is not None:
            import json as _json

            session.knowledge_collection_ids = (
                _json.dumps(knowledge_collection_ids) if knowledge_collection_ids else None
            )
        if context_files is not None:
            import json

            session.context_files = (
                json.dumps(context_files, ensure_ascii=False) if context_files else None
            )
        session.updated = datetime.utcnow()

        await self.session.commit()
        await invalidate_session_cache(session_id)

        data_result: dict[str, Any] = session.to_dict()
        return data_result

    async def delete_session(
        self, session_id: str, owner_id: Optional[int] = None, workspace_id: Optional[int] = None
    ) -> bool:
        """Delete session and all its messages."""
        query = delete(ChatSession).where(ChatSession.id == session_id)
        if workspace_id is not None and hasattr(ChatSession, "workspace_id"):
            query = query.where(ChatSession.workspace_id == workspace_id)
        if owner_id is not None:
            query = query.where(
                (ChatSession.owner_id == owner_id) | (ChatSession.owner_id.is_(None))
            )
        result = await self.session.execute(query)
        await self.session.commit()
        await invalidate_session_cache(session_id)
        return bool(result.rowcount > 0)  # type: ignore[attr-defined]

    async def delete_sessions_bulk(
        self,
        session_ids: List[str],
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> int:
        """Delete multiple sessions by ID list."""
        if not session_ids:
            return 0

        query = delete(ChatSession).where(ChatSession.id.in_(session_ids))
        if workspace_id is not None and hasattr(ChatSession, "workspace_id"):
            query = query.where(ChatSession.workspace_id == workspace_id)
        if owner_id is not None:
            query = query.where(
                (ChatSession.owner_id == owner_id) | (ChatSession.owner_id.is_(None))
            )
        result = await self.session.execute(query)
        await self.session.commit()

        # Invalidate cache for all deleted sessions
        for sid in session_ids:
            await invalidate_session_cache(sid)

        return int(result.rowcount)  # type: ignore[attr-defined]

    async def list_sessions_grouped(
        self, owner_id: Optional[int] = None, workspace_id: Optional[int] = None
    ) -> dict:
        """Get sessions grouped by source."""
        query = (
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .order_by(ChatSession.pinned.desc(), ChatSession.updated.desc())
        )
        query = self._apply_workspace_filter(query, workspace_id)
        if owner_id is not None:
            shared_subq = (
                select(ChatSessionShare.session_id)
                .where(ChatSessionShare.user_id == owner_id)
                .scalar_subquery()
            )
            query = query.where(
                (ChatSession.owner_id == owner_id)
                | (ChatSession.owner_id.is_(None))
                | (ChatSession.id.in_(shared_subq))
            )
        result = await self.session.execute(query)
        sessions = result.scalars().all()

        grouped: Dict[str, List[dict[str, Any]]] = {
            "admin": [],
            "telegram": [],
            "widget": [],
            "whatsapp": [],
            "unknown": [],
        }

        for s in sessions:
            summary = s.to_summary()
            source = s.source or "unknown"
            # Normalize DB value to frontend key
            if source == "telegram_bot":
                source = "telegram"
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
        parent_id: Optional[str] = None,
    ) -> Optional[dict]:
        """Add message to session. Auto-detects parent if not provided."""
        result = await self.session.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == session_id)
        )
        session = result.scalar_one_or_none()

        if not session:
            return None

        # Auto-detect parent: last active message in the session
        if parent_id is None:
            active_msgs = [m for m in session.messages if m.is_active]
            if active_msgs:
                parent_id = active_msgs[-1].id

        message = ChatMessage(
            id=self._generate_message_id(),
            session_id=session_id,
            role=role,
            content=content,
            edited=False,
            created=datetime.utcnow(),
            parent_id=parent_id,
            is_active=True,
        )

        self.session.add(message)

        # Auto-generate title from first message
        active_msgs = [m for m in session.messages if m.is_active]
        if len(active_msgs) == 0 and session.title == "Новый чат":
            session.title = content[:50] + ("..." if len(content) > 50 else "")

        session.updated = datetime.utcnow()

        await self.session.commit()
        await invalidate_session_cache(session_id)

        return message.to_dict()

    async def edit_message(
        self,
        session_id: str,
        message_id: str,
        content: str,
    ) -> Optional[dict]:
        """Non-destructive edit: deactivate old branch, create new sibling."""
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.id == message_id)
            .where(ChatMessage.session_id == session_id)
        )
        message = result.scalar_one_or_none()

        if not message:
            return None

        # Deactivate this message and all its active descendants
        await self._deactivate_branch(session_id, message_id)

        # Create new message as sibling (same parent_id as original)
        new_message = ChatMessage(
            id=self._generate_message_id(),
            session_id=session_id,
            role=message.role,
            content=content,
            edited=True,
            created=datetime.utcnow(),
            parent_id=message.parent_id,
            is_active=True,
        )

        self.session.add(new_message)

        # Update session timestamp
        session = await self.session.get(ChatSession, session_id)
        if session:
            session.updated = datetime.utcnow()

        await self.session.commit()
        await invalidate_session_cache(session_id)

        return new_message.to_dict()

    async def branch_regenerate(
        self,
        session_id: str,
        message_id: str,
    ) -> Optional[dict]:
        """Non-destructive regenerate: deactivate assistant message, return parent user msg."""
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.id == message_id)
            .where(ChatMessage.session_id == session_id)
        )
        message = result.scalar_one_or_none()

        if not message:
            return None

        # Deactivate this message and all its active descendants
        await self._deactivate_branch(session_id, message_id)

        # Update session timestamp
        session = await self.session.get(ChatSession, session_id)
        if session:
            session.updated = datetime.utcnow()

        await self.session.commit()
        await invalidate_session_cache(session_id)

        # Return the parent message (user message) so caller can generate response
        if message.parent_id:
            parent_result = await self.session.execute(
                select(ChatMessage).where(ChatMessage.id == message.parent_id)
            )
            parent = parent_result.scalar_one_or_none()
            if parent:
                return parent.to_dict()

        return message.to_dict()

    async def _deactivate_branch(self, session_id: str, message_id: str) -> None:
        """Deactivate a message and all its active descendants recursively."""
        # Deactivate the message itself
        await self.session.execute(
            update(ChatMessage).where(ChatMessage.id == message_id).values(is_active=False)
        )

        # Find active children
        children_result = await self.session.execute(
            select(ChatMessage.id)
            .where(ChatMessage.parent_id == message_id)
            .where(ChatMessage.is_active.is_(True))
        )
        child_ids = [row[0] for row in children_result.all()]

        for child_id in child_ids:
            await self._deactivate_branch(session_id, child_id)

    async def get_active_messages(self, session_id: str) -> List[dict]:
        """Get ordered list of active messages for display."""
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .where(ChatMessage.is_active.is_(True))
            .order_by(ChatMessage.created.asc())
        )
        messages = result.scalars().all()
        return [m.to_dict() for m in messages]

    async def get_branch_tree(
        self, session_id: str, visible_ids: Optional[set[str]] = None
    ) -> List[dict]:
        """Get branch tree structure for a session.

        If visible_ids is provided, only messages in the set are included.
        """
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created.asc())
        )
        all_messages = result.scalars().all()

        if not all_messages:
            return []

        # Build lookup maps
        children_map: Dict[Optional[str], List[ChatMessage]] = {}
        for m in all_messages:
            if visible_ids is not None and m.id not in visible_ids:
                continue
            children_map.setdefault(m.parent_id, []).append(m)

        def build_node(msg: ChatMessage) -> dict:
            kids = children_map.get(msg.id, [])
            return {
                "id": msg.id,
                "role": msg.role,
                "content_preview": msg.content[:50] + ("..." if len(msg.content) > 50 else ""),
                "is_active": msg.is_active,
                "children": [build_node(c) for c in kids],
            }

        # Root nodes are messages with no parent (or whose parent is filtered out)
        roots = children_map.get(None, [])
        return [build_node(r) for r in roots]

    async def compute_branch_visible_ids(self, session_id: str, branch_message_id: str) -> set[str]:
        """Compute visible message IDs for a shared branch.

        Returns the set of ancestors (linear path to root) + the tip message
        + all descendants of the tip (with sub-branches).
        """
        result = await self.session.execute(
            select(ChatMessage.id, ChatMessage.parent_id).where(
                ChatMessage.session_id == session_id
            )
        )
        rows = result.all()

        parent_map: Dict[str, Optional[str]] = {}
        children_map: Dict[str, List[str]] = {}
        for msg_id, parent_id in rows:
            parent_map[msg_id] = parent_id
            if parent_id:
                children_map.setdefault(parent_id, []).append(msg_id)

        if branch_message_id not in parent_map:
            return set()

        visible: set[str] = set()

        # Walk ancestors from tip to root
        current: Optional[str] = branch_message_id
        while current:
            visible.add(current)
            current = parent_map.get(current)

        # BFS descendants from tip
        queue = [branch_message_id]
        while queue:
            mid = queue.pop()
            for child_id in children_map.get(mid, []):
                visible.add(child_id)
                queue.append(child_id)

        return visible

    async def get_sibling_info(self, session_id: str) -> Dict[str, dict]:
        """Get sibling info for messages that have alternatives.

        Returns dict mapping message_id to {index, total, siblings: [id, ...]}.
        """
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created.asc())
        )
        all_messages = result.scalars().all()

        # Group by parent_id
        by_parent: Dict[Optional[str], List[ChatMessage]] = {}
        for m in all_messages:
            by_parent.setdefault(m.parent_id, []).append(m)

        sibling_info: Dict[str, dict] = {}
        for parent_id, siblings in by_parent.items():
            if len(siblings) <= 1:
                continue
            sibling_ids = [s.id for s in siblings]
            for i, s in enumerate(siblings):
                sibling_info[s.id] = {
                    "index": i,
                    "total": len(siblings),
                    "siblings": sibling_ids,
                }

        return sibling_info

    async def start_new_branch(self, session_id: str) -> bool:
        """Deactivate all active messages to start a fresh branch."""
        await self.session.execute(
            update(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .where(ChatMessage.is_active.is_(True))
            .values(is_active=False)
        )
        await self.session.commit()
        await invalidate_session_cache(session_id)
        return True

    async def switch_branch(self, session_id: str, message_id: str) -> bool:
        """Switch active branch to the given message.

        Deactivates siblings and their descendants, activates this message
        and its ancestors up to root.
        """
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.id == message_id)
            .where(ChatMessage.session_id == session_id)
        )
        message = result.scalar_one_or_none()

        if not message:
            return False

        # Find siblings (messages with same parent_id in same session)
        siblings_result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .where(ChatMessage.parent_id == message.parent_id)
            .where(ChatMessage.id != message_id)
        )
        siblings = siblings_result.scalars().all()

        # Deactivate siblings and their descendants
        for sibling in siblings:
            if sibling.is_active:
                await self._deactivate_branch(session_id, sibling.id)

        # Activate this message
        message.is_active = True

        # Activate the active path from this message downward (first active child chain)
        await self._activate_default_path(session_id, message_id)

        # Activate all ancestors up to root
        current_parent_id = message.parent_id
        while current_parent_id:
            parent_result = await self.session.execute(
                select(ChatMessage).where(ChatMessage.id == current_parent_id)
            )
            parent = parent_result.scalar_one_or_none()
            if not parent:
                break
            parent.is_active = True
            current_parent_id = parent.parent_id

        # Update session timestamp
        session = await self.session.get(ChatSession, session_id)
        if session:
            session.updated = datetime.utcnow()

        await self.session.commit()
        await invalidate_session_cache(session_id)

        return True

    async def _activate_default_path(self, session_id: str, message_id: str) -> None:
        """Activate the first child chain from a message (default path forward)."""
        children_result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.parent_id == message_id)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created.desc())
        )
        children = children_result.scalars().all()

        if not children:
            return

        # Pick the most recent child as the active one
        active_child = children[0]
        active_child.is_active = True

        # Deactivate other children
        for child in children[1:]:
            if child.is_active:
                await self._deactivate_branch(session_id, child.id)

        # Continue down the chain
        await self._activate_default_path(session_id, active_child.id)

    async def _collect_descendant_ids(self, session_id: str, message_id: str) -> list[str]:
        """Collect all descendant message IDs recursively (children, grandchildren, etc.)."""
        ids: list[str] = []
        result = await self.session.execute(
            select(ChatMessage.id)
            .where(ChatMessage.session_id == session_id)
            .where(ChatMessage.parent_id == message_id)
        )
        child_ids = [row[0] for row in result.all()]
        for child_id in child_ids:
            ids.append(child_id)
            ids.extend(await self._collect_descendant_ids(session_id, child_id))
        return ids

    async def delete_message(
        self,
        session_id: str,
        message_id: str,
    ) -> bool:
        """Delete message and all its descendants (branch-aware)."""
        # Get the target message
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.id == message_id)
            .where(ChatMessage.session_id == session_id)
        )
        message = result.scalar_one_or_none()

        if not message:
            return False

        # Collect the target + all descendants via parent_id tree
        ids_to_delete = [message_id]
        ids_to_delete.extend(await self._collect_descendant_ids(session_id, message_id))

        # Delete in batches (SQLite IN clause limit safe for typical chat sizes)
        await self.session.execute(delete(ChatMessage).where(ChatMessage.id.in_(ids_to_delete)))

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
        system_prompt: Optional[str] = None,
    ) -> List[dict]:
        """Get active messages in LLM format (role, content)."""
        result = await self.session.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == session_id)
        )
        session = result.scalar_one_or_none()

        if not session:
            return []

        messages = []

        # Add system prompt (passed system_prompt already includes session prompt + RAG)
        prompt = system_prompt or session.system_prompt
        if prompt:
            messages.append({"role": "system", "content": prompt})

        # Add active message history only
        for msg in session.messages:
            if msg.is_active:
                messages.append({"role": msg.role, "content": msg.content})

        return messages

    async def get_branch_path(self, session_id: str, message_id: str) -> List[dict]:
        """Get ordered message path from root to a specific message (ancestor chain)."""
        result = await self.session.execute(
            select(ChatMessage).where(ChatMessage.session_id == session_id)
        )
        all_messages = result.scalars().all()
        msg_map = {m.id: m for m in all_messages}

        path = []
        current_id: Optional[str] = message_id
        while current_id:
            msg = msg_map.get(current_id)
            if not msg:
                break
            path.append(msg)
            current_id = msg.parent_id

        path.reverse()
        return [{"role": m.role, "content": m.content} for m in path]

    async def get_session_count(self) -> int:
        """Get total number of sessions."""
        return await self.count()

    async def get_message_count(self) -> int:
        """Get total number of messages across all sessions."""
        from sqlalchemy import func

        result = await self.session.execute(select(func.count()).select_from(ChatMessage))
        return result.scalar() or 0

    async def fork_session(
        self,
        session_id: str,
        new_owner_id: int,
        new_title: Optional[str] = None,
        workspace_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Deep copy a session with active messages to a new owner."""
        result = await self.session.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == session_id)
        )
        source_session = result.scalar_one_or_none()
        if not source_session:
            return None

        # Create new session
        new_session_id = self._generate_session_id()
        now = datetime.utcnow()
        title = new_title or f"{source_session.title} (fork)"

        kwargs: dict[str, Any] = dict(
            id=new_session_id,
            title=title,
            system_prompt=source_session.system_prompt,
            source=source_session.source,
            owner_id=new_owner_id,
            rag_mode=source_session.rag_mode,
            knowledge_collection_id=source_session.knowledge_collection_id,
            knowledge_collection_ids=source_session.knowledge_collection_ids,
            context_files=source_session.context_files,
            created=now,
            updated=now,
        )
        if workspace_id is not None:
            kwargs["workspace_id"] = workspace_id

        new_session = ChatSession(**kwargs)
        self.session.add(new_session)

        # Copy active messages with parent_id remapping
        active_msgs = sorted(
            [m for m in source_session.messages if m.is_active],
            key=lambda m: m.created,
        )
        id_map: Dict[str, str] = {}

        for msg in active_msgs:
            new_msg_id = self._generate_message_id()
            id_map[msg.id] = new_msg_id
            new_parent_id = id_map.get(msg.parent_id) if msg.parent_id else None

            new_msg = ChatMessage(
                id=new_msg_id,
                session_id=new_session_id,
                role=msg.role,
                content=msg.content,
                edited=False,
                created=now,
                parent_id=new_parent_id,
                is_active=True,
            )
            self.session.add(new_msg)

        await self.session.commit()

        # Return the new session
        return await self.get_session(new_session_id)
