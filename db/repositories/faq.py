"""
FAQ repository for managing FAQ entries with caching.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import FAQEntry
from db.redis_client import cache_faq, get_cached_faq, invalidate_faq_cache
from db.repositories.base import BaseRepository


class FAQRepository(BaseRepository[FAQEntry]):
    """Repository for FAQ entries with Redis caching."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, FAQEntry)

    async def get_all_entries(
        self, enabled_only: bool = True, workspace_id: Optional[int] = None
    ) -> List[dict]:
        """Get all FAQ entries, filtered by workspace."""
        query = select(FAQEntry).order_by(FAQEntry.question)
        if enabled_only:
            query = query.where(FAQEntry.enabled == True)
        query = self._apply_workspace_filter(query, workspace_id)

        result = await self.session.execute(query)
        entries = result.scalars().all()
        return [e.to_dict() for e in entries]

    async def get_as_dict(self, workspace_id: Optional[int] = None) -> Dict[str, str]:
        """
        Get FAQ as question->answer dict for LLM matching.
        Uses Redis cache when no workspace filter.
        """
        # Try cache first (only when no workspace filter)
        if workspace_id is None:
            cached = await get_cached_faq()
            if cached:
                return cached

        # Fetch from database
        query = select(FAQEntry).where(FAQEntry.enabled == True)
        query = self._apply_workspace_filter(query, workspace_id)
        result = await self.session.execute(query)
        entries = result.scalars().all()

        faq_dict = {e.question: e.answer for e in entries}

        # Cache for 10 minutes (only when no workspace filter)
        if workspace_id is None:
            await cache_faq(faq_dict, ttl_seconds=600)

        return faq_dict

    async def find_answer(self, question: str) -> Optional[str]:
        """
        Find exact match answer for question.
        Increments hit count on match.
        """
        normalized = question.lower().strip()

        result = await self.session.execute(
            select(FAQEntry).where(FAQEntry.question == normalized).where(FAQEntry.enabled == True)
        )
        entry: Optional[FAQEntry] = result.scalar_one_or_none()

        if entry:
            entry.hit_count += 1
            await self.session.commit()
            answer: str = entry.answer
            return answer

        return None

    async def get_by_question(self, question: str) -> Optional[dict]:
        """Get FAQ entry by question."""
        result = await self.session.execute(
            select(FAQEntry).where(FAQEntry.question == question.lower())
        )
        entry = result.scalar_one_or_none()
        return entry.to_dict() if entry else None

    async def create_entry(
        self,
        question: str,
        answer: str,
        keywords: Optional[List[str]] = None,
        workspace_id: Optional[int] = None,
    ) -> dict:
        """Create new FAQ entry."""
        create_kwargs: dict[str, Any] = {}
        if workspace_id is not None:
            create_kwargs["workspace_id"] = workspace_id

        entry = FAQEntry(
            question=question.lower().strip(),
            answer=answer,
            keywords=json.dumps(keywords, ensure_ascii=False) if keywords else None,
            enabled=True,
            hit_count=0,
            created=datetime.utcnow(),
            updated=datetime.utcnow(),
            **create_kwargs,
        )

        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)

        # Invalidate cache
        await invalidate_faq_cache()

        return entry.to_dict()

    async def update_entry(
        self,
        entry_id: int,
        question: Optional[str] = None,
        answer: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[dict]:
        """Update existing FAQ entry."""
        entry = await self.session.get(FAQEntry, entry_id)

        if not entry:
            return None

        if question is not None:
            entry.question = question.lower().strip()
        if answer is not None:
            entry.answer = answer
        if keywords is not None:
            entry.keywords = json.dumps(keywords, ensure_ascii=False)
        if enabled is not None:
            entry.enabled = enabled
        entry.updated = datetime.utcnow()

        await self.session.commit()
        await invalidate_faq_cache()

        data_result: dict[str, Any] = entry.to_dict()
        return data_result

    async def delete_entry(self, entry_id: int) -> bool:
        """Delete FAQ entry by ID."""
        result = await self.session.execute(delete(FAQEntry).where(FAQEntry.id == entry_id))
        await self.session.commit()
        await invalidate_faq_cache()
        return bool(result.rowcount > 0)  # type: ignore[attr-defined]

    async def delete_by_question(self, question: str, workspace_id: Optional[int] = None) -> bool:
        """Delete FAQ entry by question, optionally scoped to workspace."""
        stmt = delete(FAQEntry).where(FAQEntry.question == question.lower())
        if workspace_id is not None and hasattr(FAQEntry, "workspace_id"):
            stmt = stmt.where(FAQEntry.workspace_id == workspace_id)
        result = await self.session.execute(stmt)
        await self.session.commit()
        await invalidate_faq_cache()
        return bool(result.rowcount > 0)  # type: ignore[attr-defined]

    async def import_from_dict(self, faq_dict: Dict[str, str]) -> int:
        """
        Import FAQ from legacy dict format.
        Returns number of imported entries.
        """
        count = 0
        for question, answer in faq_dict.items():
            # Check if exists
            existing = await self.get_by_question(question)
            if existing:
                continue

            entry = FAQEntry.from_legacy(question, answer)
            self.session.add(entry)
            count += 1

        await self.session.commit()
        await invalidate_faq_cache()
        return count

    async def export_to_dict(self) -> Dict[str, str]:
        """Export FAQ to legacy dict format."""
        return await self.get_as_dict()

    async def search(self, query: str, workspace_id: Optional[int] = None) -> List[dict]:
        """Search FAQ entries by question or answer content."""
        pattern = f"%{query.lower()}%"
        stmt = (
            select(FAQEntry)
            .where((FAQEntry.question.ilike(pattern)) | (FAQEntry.answer.ilike(pattern)))
            .order_by(FAQEntry.hit_count.desc())
        )
        stmt = self._apply_workspace_filter(stmt, workspace_id)
        result = await self.session.execute(stmt)
        entries = result.scalars().all()
        return [e.to_dict() for e in entries]

    async def get_stats(self) -> dict:
        """Get FAQ statistics."""
        from sqlalchemy import func

        total = await self.count()

        result = await self.session.execute(
            select(func.count()).select_from(FAQEntry).where(FAQEntry.enabled == True)
        )
        enabled = result.scalar() or 0

        result = await self.session.execute(
            select(func.sum(FAQEntry.hit_count)).select_from(FAQEntry)
        )
        total_hits = result.scalar() or 0

        return {
            "total": total,
            "enabled": enabled,
            "disabled": total - enabled,
            "total_hits": total_hits,
        }
