"""Chat services."""

import hashlib
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

from db.database import AsyncSessionLocal
from db.repositories import ChatRepository, ChatShareRepository, UserRepository
from db.retry import retry_on_busy
from modules.chat.image_service import delete_session_images


logger = logging.getLogger(__name__)


class ChatService:
    """Async-compatible ChatManager that uses database.
    Provides same API as the old synchronous ChatManager for easy migration.
    """

    def _generate_id(self) -> str:
        return f"chat_{int(time.time() * 1000)}"

    def _generate_message_id(self) -> str:
        ts = str(time.time())
        return f"msg_{int(time.time() * 1000)}_{hashlib.md5(ts.encode()).hexdigest()[:6]}"

    async def list_sessions(
        self,
        owner_id: Optional[int] = None,
        source: Optional[str] = None,
        exclude_source: Optional[str] = None,
        workspace_id: Optional[int] = None,
    ) -> List[dict]:
        """List all sessions with summary info."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.list_sessions(
                owner_id=owner_id,
                source=source,
                exclude_source=exclude_source,
                workspace_id=workspace_id,
            )

    async def get_session(
        self,
        session_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Get full session with messages."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.get_session(session_id, owner_id=owner_id, workspace_id=workspace_id)

    @retry_on_busy()
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
        """Create new session."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            result = await repo.create_session(
                title,
                system_prompt,
                source,
                source_id,
                owner_id=owner_id,
                rag_mode=rag_mode,
                knowledge_collection_id=knowledge_collection_id,
                workspace_id=workspace_id,
            )
            await session.commit()
            return result

    @retry_on_busy()
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
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            result = await repo.update_session(
                session_id,
                title,
                system_prompt,
                pinned=pinned,
                rag_mode=rag_mode,
                knowledge_collection_id=knowledge_collection_id,
                knowledge_collection_ids=knowledge_collection_ids,
                context_files=context_files,
            )
            await session.commit()
            return result

    @retry_on_busy()
    async def delete_session(
        self,
        session_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> bool:
        """Delete session and its images."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            result = await repo.delete_session(
                session_id, owner_id=owner_id, workspace_id=workspace_id
            )
            await session.commit()
            if result:
                delete_session_images(session_id)
            return result

    @retry_on_busy()
    async def delete_sessions_bulk(
        self,
        session_ids: List[str],
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> int:
        """Delete multiple sessions and their images."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            result = await repo.delete_sessions_bulk(
                session_ids, owner_id=owner_id, workspace_id=workspace_id
            )
            await session.commit()
            if result:
                for sid in session_ids:
                    delete_session_images(sid)
            return result

    async def list_sessions_grouped(
        self, owner_id: Optional[int] = None, workspace_id: Optional[int] = None
    ) -> dict:
        """Get sessions grouped by source."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.list_sessions_grouped(owner_id=owner_id, workspace_id=workspace_id)

    async def get_branch_path(self, session_id: str, message_id: str) -> List[dict]:
        """Get ordered message path from root to a specific message."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.get_branch_path(session_id, message_id)

    async def get_active_messages(self, session_id: str) -> List[dict]:
        """Get active (visible) messages for a session."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.get_active_messages(session_id)

    @retry_on_busy()
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        parent_id: Optional[str] = None,
        extra_data: Optional[str] = None,
    ) -> Optional[dict]:
        """Add message to session."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            result = await repo.add_message(
                session_id, role, content, parent_id=parent_id, extra_data=extra_data
            )
            await session.commit()
            return result

    @retry_on_busy()
    async def edit_message(
        self,
        session_id: str,
        message_id: str,
        content: str,
    ) -> Optional[dict]:
        """Non-destructive edit: creates new sibling branch."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            result = await repo.edit_message(session_id, message_id, content)
            await session.commit()
            return result

    @retry_on_busy()
    async def branch_regenerate(
        self,
        session_id: str,
        message_id: str,
    ) -> Optional[dict]:
        """Non-destructive regenerate: deactivate and return parent user msg."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            result = await repo.branch_regenerate(session_id, message_id)
            await session.commit()
            return result

    @retry_on_busy()
    async def delete_message(
        self,
        session_id: str,
        message_id: str,
    ) -> bool:
        """Delete message and all subsequent messages."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            result = await repo.delete_message(session_id, message_id)
            await session.commit()
            return result

    async def get_branch_tree(
        self, session_id: str, visible_ids: Optional[set[str]] = None
    ) -> List[dict]:
        """Get branch tree structure for a session."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.get_branch_tree(session_id, visible_ids=visible_ids)

    async def compute_branch_visible_ids(self, session_id: str, branch_message_id: str) -> set[str]:
        """Compute visible message IDs for a shared branch."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.compute_branch_visible_ids(session_id, branch_message_id)

    async def get_sibling_info(self, session_id: str) -> dict:
        """Get sibling info for messages with alternatives."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.get_sibling_info(session_id)

    @retry_on_busy()
    async def switch_branch(self, session_id: str, message_id: str) -> bool:
        """Switch active branch to the given message."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            result = await repo.switch_branch(session_id, message_id)
            await session.commit()
            return result

    @retry_on_busy()
    async def start_new_branch(self, session_id: str) -> bool:
        """Deactivate all active messages to start a fresh branch."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            result = await repo.start_new_branch(session_id)
            await session.commit()
            return result

    async def count_messages(
        self,
        session_id: str,
        role: str,
        since: datetime,
    ) -> int:
        """Count messages in a session by role since a given time."""
        # Lazy import to avoid circular dependency
        from sqlalchemy import func, select

        from db.models import ChatMessage

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(func.count())
                .select_from(ChatMessage)
                .where(
                    ChatMessage.session_id == session_id,
                    ChatMessage.role == role,
                    ChatMessage.created >= since,
                )
            )
            return result.scalar() or 0

    async def get_messages_for_llm(
        self,
        session_id: str,
        system_prompt: Optional[str] = None,
    ) -> List[dict]:
        """Get messages in LLM format."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.get_messages_for_llm(session_id, system_prompt)


class ChatShareService:
    """Async manager for chat session sharing between users."""

    async def get_shares(self, session_id: str) -> List[dict]:
        """Get all shares for a session with user info."""
        async with AsyncSessionLocal() as session:
            repo = ChatShareRepository(session)
            return await repo.get_shares_for_session(session_id)

    async def add_share(
        self,
        session_id: str,
        user_id: int,
        permission: str = "read",
        shared_by: Optional[int] = None,
        branch_message_id: Optional[str] = None,
    ) -> dict:
        """Add or update a share."""
        async with AsyncSessionLocal() as session:
            repo = ChatShareRepository(session)
            result = await repo.add_share(
                session_id, user_id, permission, shared_by, branch_message_id
            )
            await session.commit()
            return result

    async def get_user_share(self, session_id: str, user_id: int) -> Optional[dict]:
        """Get full share record for a user (with branch_message_id)."""
        async with AsyncSessionLocal() as session:
            repo = ChatShareRepository(session)
            share = await repo.get_share(session_id, user_id)
            return share.to_dict() if share else None

    async def remove_share(self, session_id: str, user_id: int) -> bool:
        """Remove a share."""
        async with AsyncSessionLocal() as session:
            repo = ChatShareRepository(session)
            result = await repo.remove_share(session_id, user_id)
            await session.commit()
            return result

    async def update_permission(self, session_id: str, user_id: int, permission: str) -> bool:
        """Update share permission."""
        async with AsyncSessionLocal() as session:
            repo = ChatShareRepository(session)
            result = await repo.update_permission(session_id, user_id, permission)
            await session.commit()
            return result

    async def get_user_permission(self, session_id: str, user_id: int) -> Optional[str]:
        """Get user's permission for a session."""
        async with AsyncSessionLocal() as session:
            repo = ChatShareRepository(session)
            return await repo.get_user_permission(session_id, user_id)

    async def get_share_counts(self, session_ids: list[str]) -> dict[str, int]:
        """Get share counts for multiple sessions in a single query."""
        async with AsyncSessionLocal() as session:
            repo = ChatShareRepository(session)
            return await repo.get_share_counts(session_ids)

    async def get_shared_sessions_with_permissions(self, user_id: int) -> Dict[str, str]:
        """Get dict of session_id -> permission for all sessions shared with user."""
        async with AsyncSessionLocal() as session:
            repo = ChatShareRepository(session)
            return await repo.get_shared_sessions_with_permissions(user_id)

    async def fork_session(
        self,
        session_id: str,
        new_owner_id: int,
        new_title: Optional[str] = None,
    ) -> Optional[dict]:
        """Fork (deep copy) a session to a new owner."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            result = await repo.fork_session(session_id, new_owner_id, new_title)
            await session.commit()
            return result

    async def list_shareable_users(self, exclude_user_id: Optional[int] = None) -> List[dict]:
        """Get list of active non-guest users for sharing."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            users = await repo.list_users()
            return [
                {
                    "id": u["id"],
                    "username": u["username"],
                    "display_name": u["display_name"],
                    "role": u["role"],
                }
                for u in users
                if u.get("is_active", True)
                and u.get("role") != "guest"
                and u["id"] != exclude_user_id
            ]


# Singletons
chat_service = ChatService()
chat_share_service = ChatShareService()
