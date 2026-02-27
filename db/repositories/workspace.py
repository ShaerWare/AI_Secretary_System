"""Repository for workspace operations."""

import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Workspace, WorkspaceInvite, WorkspaceMember
from db.repositories.base import BaseRepository


class WorkspaceRepository(BaseRepository[Workspace]):
    """Repository for workspace CRUD and membership management."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Workspace)

    async def get_member_role_name(self, user_id: int, workspace_id: int) -> Optional[str]:
        """Get role_name for (user_id, workspace_id) from workspace_members."""
        result = await self.session.execute(
            select(WorkspaceMember.role_name).where(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def ensure_membership(self, workspace_id: int, user_id: int, role_name: str) -> None:
        """Insert or update workspace membership (idempotent)."""
        result = await self.session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        if member:
            member.role_name = role_name
        else:
            self.session.add(
                WorkspaceMember(
                    workspace_id=workspace_id,
                    user_id=user_id,
                    role_name=role_name,
                )
            )
        await self.session.commit()

    async def get_default_workspace(self) -> Optional[dict]:
        """Get workspace with id=1."""
        ws = await self.get_by_id(1)
        return ws.to_dict() if ws else None

    async def create_default(self, name: str = "Default", slug: str = "default") -> dict:
        """Create the default workspace (id=1)."""
        ws = Workspace(name=name, slug=slug)
        self.session.add(ws)
        await self.session.flush()
        await self.session.commit()
        return ws.to_dict()

    # ============== Members Management ==============

    async def get_workspace_info(self, workspace_id: int) -> Optional[dict]:
        """Get workspace by ID with member count."""
        ws = await self.get_by_id(workspace_id)
        if not ws:
            return None
        data = ws.to_dict()
        count_result = await self.session.execute(
            select(func.count())
            .select_from(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id)
        )
        data["member_count"] = count_result.scalar() or 0
        return data

    async def list_members(self, workspace_id: int) -> List[dict]:
        """List all members of a workspace with user details."""
        result = await self.session.execute(
            select(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .options(selectinload(WorkspaceMember.user))
            .order_by(WorkspaceMember.joined_at)
        )
        members = result.scalars().all()
        out: List[dict] = []
        for m in members:
            d = m.to_dict()
            if m.user:
                d["username"] = m.user.username
                d["display_name"] = m.user.display_name
                d["email"] = m.user.email
                d["is_active"] = m.user.is_active
                d["last_login"] = m.user.last_login.isoformat() if m.user.last_login else None
            out.append(d)
        return out

    async def update_member_role(
        self, workspace_id: int, user_id: int, role_name: str
    ) -> Optional[dict]:
        """Change a member's role. Returns updated member dict or None."""
        result = await self.session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            return None
        member.role_name = role_name
        await self.session.commit()
        return member.to_dict()

    async def remove_member(self, workspace_id: int, user_id: int) -> bool:
        """Remove a member from workspace. Returns True if removed."""
        result = await self.session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            return False
        await self.session.delete(member)
        await self.session.commit()
        return True

    async def get_workspace_owner_id(self, workspace_id: int) -> Optional[int]:
        """Get the owner_id for a workspace."""
        ws = await self.get_by_id(workspace_id)
        return ws.owner_id if ws else None

    # ============== Invites ==============

    async def create_invite(
        self,
        workspace_id: int,
        role_name: str,
        created_by: int,
        email: Optional[str] = None,
        max_uses: Optional[int] = None,
        expires_hours: Optional[int] = None,
    ) -> dict:
        """Create a new invite link."""
        invite = WorkspaceInvite(
            workspace_id=workspace_id,
            invite_code=secrets.token_urlsafe(32),
            role_name=role_name,
            created_by=created_by,
            email=email,
            max_uses=max_uses,
            expires_at=(
                datetime.utcnow() + timedelta(hours=expires_hours) if expires_hours else None
            ),
        )
        self.session.add(invite)
        await self.session.flush()
        await self.session.commit()
        return invite.to_dict()

    async def list_invites(self, workspace_id: int) -> List[dict]:
        """List all invites for a workspace."""
        result = await self.session.execute(
            select(WorkspaceInvite)
            .where(WorkspaceInvite.workspace_id == workspace_id)
            .order_by(WorkspaceInvite.id.desc())
        )
        return [inv.to_dict() for inv in result.scalars().all()]

    async def get_invite_by_code(self, invite_code: str) -> Optional[WorkspaceInvite]:
        """Get invite ORM object by code."""
        result = await self.session.execute(
            select(WorkspaceInvite).where(WorkspaceInvite.invite_code == invite_code)
        )
        return result.scalar_one_or_none()

    async def use_invite(self, invite: WorkspaceInvite, user_id: int) -> None:
        """Record invite usage: increment used_count, set used_at/used_by."""
        invite.used_count += 1
        invite.used_at = datetime.utcnow()
        invite.used_by = user_id
        await self.session.commit()

    async def delete_invite(self, workspace_id: int, invite_id: int) -> bool:
        """Delete an invite. Returns True if deleted."""
        result = await self.session.execute(
            select(WorkspaceInvite).where(
                WorkspaceInvite.id == invite_id,
                WorkspaceInvite.workspace_id == workspace_id,
            )
        )
        invite = result.scalar_one_or_none()
        if not invite:
            return False
        await self.session.delete(invite)
        await self.session.commit()
        return True
