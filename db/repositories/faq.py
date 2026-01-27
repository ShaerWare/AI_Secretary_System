"""
FAQ repository for managing FAQ entries with caching.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import FAQEntry
from db.redis_client import cache_faq, get_cached_faq, invalidate_faq_cache
from db.repositories.base import BaseRepository


class FAQRepository(BaseRepository[FAQEntry]):
    """Repository for FAQ entries with Redis caching."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, FAQEntry)

    async def get_all_entries(self, enabled_only: bool = True) -> List[dict]:
        """Get all FAQ entries."""
        query = select(FAQEntry).order_by(FAQEntry.question)
        if enabled_only:
            query = query.where(FAQEntry.enabled == True)

        result = await self.session.execute(query)
        entries = result.scalars().all()
        return [e.to_dict() for e in entries]

    async def get_as_dict(self) -> Dict[str, str]:
        """
        Get FAQ as question->answer dict for LLM matching.
        Uses Redis cache for performance.
        """
        # Try cache first
        cached = await get_cached_faq()
        if cached:
            return cached

        # Fetch from database
        result = await self.session.execute(select(FAQEntry).where(FAQEntry.enabled == True))
        entries = result.scalars().all()

        faq_dict = {e.question: e.answer for e in entries}

        # Cache for 10 minutes
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
        entry = result.scalar_one_or_none()

        if entry:
            entry.hit_count += 1
            await self.session.commit()
            return entry.answer

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
        keywords: List[str] = None,
    ) -> dict:
        """Create new FAQ entry."""
        entry = FAQEntry(
            question=question.lower().strip(),
            answer=answer,
            keywords=json.dumps(keywords, ensure_ascii=False) if keywords else None,
            enabled=True,
            hit_count=0,
            created=datetime.utcnow(),
            updated=datetime.utcnow(),
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
        question: str = None,
        answer: str = None,
        keywords: List[str] = None,
        enabled: bool = None,
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

        return entry.to_dict()

    async def delete_entry(self, entry_id: int) -> bool:
        """Delete FAQ entry by ID."""
        result = await self.session.execute(delete(FAQEntry).where(FAQEntry.id == entry_id))
        await self.session.commit()
        await invalidate_faq_cache()
        return result.rowcount > 0

    async def delete_by_question(self, question: str) -> bool:
        """Delete FAQ entry by question."""
        result = await self.session.execute(
            delete(FAQEntry).where(FAQEntry.question == question.lower())
        )
        await self.session.commit()
        await invalidate_faq_cache()
        return result.rowcount > 0

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

    async def search(self, query: str) -> List[dict]:
        """Search FAQ entries by question or answer content."""
        pattern = f"%{query.lower()}%"
        result = await self.session.execute(
            select(FAQEntry)
            .where((FAQEntry.question.ilike(pattern)) | (FAQEntry.answer.ilike(pattern)))
            .order_by(FAQEntry.hit_count.desc())
        )
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
