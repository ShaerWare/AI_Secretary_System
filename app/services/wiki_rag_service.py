"""
Wiki RAG service — retrieves relevant wiki sections for user queries.

Tiered search:
1. Semantic embeddings (if provider available) — best for "сколько стоит" → "тарифы"
2. BM25 Okapi with Russian/English stemming — always available as fallback

Parses wiki-pages/*.md on startup, builds inverted index and optional
embedding vectors. Returns top-k relevant sections for LLM system prompt injection.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import snowballstemmer


if TYPE_CHECKING:
    from app.services.embedding_provider import BaseEmbeddingProvider
    from app.services.vector_search_client import VectorSearchClient


logger = logging.getLogger(__name__)

# Stemmers — singleton per language
_ru_stemmer = snowballstemmer.stemmer("russian")
_en_stemmer = snowballstemmer.stemmer("english")

# BM25 Okapi parameters
BM25_K1 = 1.5  # term frequency saturation
BM25_B = 0.75  # document length normalization
MIN_SCORE = 0.3  # ignore garbage matches (lowered from 0.5 for better recall)

# Базовые стоп-слова (русские + английские) — фильтруем шум из запросов
STOP_WORDS = frozenset(
    {
        # Russian
        "и",
        "в",
        "на",
        "с",
        "по",
        "для",
        "что",
        "как",
        "это",
        "не",
        "из",
        "к",
        "от",
        "за",
        "до",
        "или",
        "но",
        "а",
        "о",
        "у",
        "же",
        "ли",
        "бы",
        "то",
        "все",
        "так",
        "его",
        "мне",
        "мой",
        "уже",
        "при",
        "про",
        "ещё",
        "еще",
        "нет",
        "да",
        "вот",
        "тут",
        "там",
        "где",
        "кто",
        "чем",
        "вы",
        "мы",
        "он",
        "она",
        "они",
        # English
        "the",
        "is",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "and",
        "or",
        "a",
        "an",
        "it",
        "by",
        "with",
        "as",
        "be",
        "are",
        "was",
        "do",
        "if",
        "no",
        "not",
        "how",
        "what",
        "this",
        "that",
    }
)

# Минимальная длина токена для индексации
MIN_TOKEN_LEN = 2


def _is_cyrillic(word: str) -> bool:
    """Check if word contains Cyrillic characters."""
    return any("\u0400" <= ch <= "\u04ff" for ch in word)


def _stem(word: str) -> str:
    """Stem a single word using the appropriate language stemmer."""
    if _is_cyrillic(word):
        return _ru_stemmer.stemWord(word)
    return _en_stemmer.stemWord(word)


@dataclass
class WikiSection:
    """One indexed section from a wiki page."""

    title: str
    body: str
    source_file: str
    tokens: Counter = field(default_factory=Counter)


@dataclass
class CollectionIndex:
    """BM25 index for a single knowledge collection."""

    collection_id: int
    sections: list[WikiSection]
    doc_freqs: Counter
    avg_dl: float
    total_docs: int
    files_indexed: int


class WikiRAGService:
    """Retrieves relevant wiki sections via embeddings (primary) or BM25 (fallback)."""

    def __init__(self, wiki_dir: Optional[Path] = None):
        self.sections: list[WikiSection] = []
        self.doc_freqs: Counter = Counter()
        self.avg_dl: float = 0.0
        self.total_docs: int = 0
        self._files_indexed: int = 0

        # Per-collection indexes (collection_id → CollectionIndex)
        self._collection_indexes: dict[int, CollectionIndex] = {}

        # Embedding search state
        self._embedding_provider: Optional[BaseEmbeddingProvider] = None
        self._embeddings: dict[str, list[float]] = {}  # section_id → vector
        self._embedding_cache_path = Path("data/wiki_embeddings.json")

        # Vector Search microservice client
        self._vector_search_client: Optional[VectorSearchClient] = None

        if wiki_dir and wiki_dir.exists():
            self._load_and_index(wiki_dir)

    def _tokenize(self, text: str) -> list[str]:
        """Unicode-aware tokenization with stemming — works with Cyrillic."""
        tokens = re.findall(r"\w+", text.lower())
        return [_stem(t) for t in tokens if len(t) >= MIN_TOKEN_LEN and t not in STOP_WORDS]

    def _split_md_by_headers(self, content: str) -> list[tuple[str, str]]:
        """Split markdown by ## and ### headers. Returns (header, body) pairs."""
        sections = []
        pattern = r"^(#{2,3})\s+(.+?)$"
        current_header = ""
        current_body: list[str] = []

        for line in content.split("\n"):
            match = re.match(pattern, line)
            if match:
                if current_header and current_body:
                    sections.append((current_header, "\n".join(current_body)))
                current_header = match.group(2).strip()
                current_body = []
            else:
                current_body.append(line)

        if current_header and current_body:
            sections.append((current_header, "\n".join(current_body)))

        return sections

    def _load_and_index(self, wiki_dir: Path) -> None:
        """Parse all .md files in wiki_dir, build BM25 index."""
        self.sections = []
        self.doc_freqs = Counter()
        total_tokens = 0

        md_files = sorted(wiki_dir.glob("*.md"))
        files_processed = 0

        for md_file in md_files:
            if md_file.name.startswith("_"):
                continue

            try:
                content = md_file.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Wiki RAG: не удалось прочитать {md_file.name}: {e}")
                continue

            raw_sections = self._split_md_by_headers(content)
            files_processed += 1

            for title, body in raw_sections:
                body_stripped = body.strip()
                if len(body_stripped) < 50:
                    continue

                # Токенизируем заголовок + тело (заголовок весомее — 4x boost)
                text = f"{title} {title} {title} {title} {body_stripped}"
                tokens = Counter(self._tokenize(text))

                section = WikiSection(
                    title=title,
                    body=body_stripped,
                    source_file=md_file.stem,
                    tokens=tokens,
                )
                self.sections.append(section)

                # Обновляем document frequency
                for token in tokens:
                    self.doc_freqs[token] += 1

                total_tokens += sum(tokens.values())

        # BM25 stats
        self.total_docs = len(self.sections)
        self.avg_dl = total_tokens / self.total_docs if self.total_docs > 0 else 1.0

        self._files_indexed = files_processed
        logger.info(
            f"📚 Wiki RAG (BM25): проиндексировано {self.total_docs} секций "
            f"из {files_processed} файлов, "
            f"{len(self.doc_freqs)} уникальных стемов, "
            f"avg_dl={self.avg_dl:.1f}"
        )

    def _bm25_score(self, query_tokens: list[str], section: WikiSection) -> float:
        """Compute BM25 Okapi score for a section against query tokens."""
        score = 0.0
        doc_len = sum(section.tokens.values())
        for token in query_tokens:
            if token not in section.tokens:
                continue
            tf = section.tokens[token]
            df = self.doc_freqs.get(token, 0)
            idf = math.log((self.total_docs - df + 0.5) / (df + 0.5) + 1.0)
            tf_norm = (tf * (BM25_K1 + 1)) / (
                tf + BM25_K1 * (1 - BM25_B + BM25_B * doc_len / self.avg_dl)
            )
            score += idf * tf_norm
        return score

    # ---- Collection index methods ----

    def load_collection(
        self, collection_id: int, filenames: list[str], wiki_dir: Path
    ) -> CollectionIndex:
        """Build BM25 index for a specific collection's files."""
        sections: list[WikiSection] = []
        doc_freqs: Counter = Counter()
        total_tokens = 0
        files_processed = 0

        for fname in filenames:
            md_file = wiki_dir / fname
            if not md_file.exists() or md_file.name.startswith("_"):
                continue

            try:
                content = md_file.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Wiki RAG collection {collection_id}: can't read {fname}: {e}")
                continue

            raw_sections = self._split_md_by_headers(content)
            files_processed += 1

            for title, body in raw_sections:
                body_stripped = body.strip()
                if len(body_stripped) < 50:
                    continue

                text = f"{title} {title} {title} {title} {body_stripped}"
                tokens = Counter(self._tokenize(text))

                section = WikiSection(
                    title=title,
                    body=body_stripped,
                    source_file=md_file.stem,
                    tokens=tokens,
                )
                sections.append(section)

                for token in tokens:
                    doc_freqs[token] += 1
                total_tokens += sum(tokens.values())

        total_docs = len(sections)
        avg_dl = total_tokens / total_docs if total_docs > 0 else 1.0

        idx = CollectionIndex(
            collection_id=collection_id,
            sections=sections,
            doc_freqs=doc_freqs,
            avg_dl=avg_dl,
            total_docs=total_docs,
            files_indexed=files_processed,
        )
        self._collection_indexes[collection_id] = idx

        logger.info(
            f"📚 Wiki RAG collection {collection_id}: "
            f"{total_docs} секций из {files_processed} файлов"
        )
        return idx

    def unload_collection(self, collection_id: int) -> bool:
        """Remove a collection index from memory."""
        if collection_id in self._collection_indexes:
            del self._collection_indexes[collection_id]
            return True
        return False

    def reload_collection(
        self, collection_id: int, filenames: list[str], wiki_dir: Path
    ) -> CollectionIndex:
        """Re-index a specific collection."""
        self.unload_collection(collection_id)
        return self.load_collection(collection_id, filenames, wiki_dir)

    def _bm25_score_with_index(
        self,
        query_tokens: list[str],
        section: WikiSection,
        doc_freqs: Counter,
        total_docs: int,
        avg_dl: float,
    ) -> float:
        """Compute BM25 Okapi score using a specific index's stats."""
        score = 0.0
        doc_len = sum(section.tokens.values())
        for token in query_tokens:
            if token not in section.tokens:
                continue
            tf = section.tokens[token]
            df = doc_freqs.get(token, 0)
            idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1.0)
            tf_norm = (tf * (BM25_K1 + 1)) / (
                tf + BM25_K1 * (1 - BM25_B + BM25_B * doc_len / avg_dl)
            )
            score += idf * tf_norm
        return score

    # ---- Embedding methods ----

    def set_embedding_provider(self, provider: BaseEmbeddingProvider) -> None:
        """Set the embedding provider and try to load cached embeddings."""
        self._embedding_provider = provider
        self._load_embedding_cache()

    def _section_id(self, section: WikiSection) -> str:
        """Stable ID for a section (used as cache key)."""
        raw = f"{section.source_file}::{section.title}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Pure Python cosine similarity — fine for ~600 vectors."""
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _load_embedding_cache(self) -> None:
        """Load cached embeddings from JSON if provider matches."""
        if not self._embedding_cache_path.exists():
            return
        try:
            data = json.loads(self._embedding_cache_path.read_text(encoding="utf-8"))
            cached_provider = data.get("provider", "")
            cached_model = data.get("model", "")
            if (
                self._embedding_provider
                and cached_provider == self._embedding_provider.provider_name()
                and cached_model == self._embedding_provider.model_name
            ):
                self._embeddings = data.get("embeddings", {})
                logger.info(
                    f"📦 Wiki RAG: загружено {len(self._embeddings)} эмбеддингов из кэша "
                    f"({cached_provider}/{cached_model})"
                )
            else:
                logger.info(
                    "📦 Wiki RAG: кэш эмбеддингов устарел "
                    f"(cached={cached_provider}/{cached_model}), будет перестроен"
                )
                self._embeddings = {}
        except Exception as e:
            logger.warning(f"Wiki RAG: ошибка загрузки кэша эмбеддингов: {e}")
            self._embeddings = {}

    def _save_embedding_cache(self) -> None:
        """Save embeddings to JSON cache."""
        if not self._embedding_provider or not self._embeddings:
            return
        try:
            self._embedding_cache_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "provider": self._embedding_provider.provider_name(),
                "model": self._embedding_provider.model_name,
                "sections_count": len(self._embeddings),
                "embeddings": self._embeddings,
            }
            self._embedding_cache_path.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
            logger.info(f"💾 Wiki RAG: сохранено {len(self._embeddings)} эмбеддингов в кэш")
        except Exception as e:
            logger.warning(f"Wiki RAG: ошибка сохранения кэша эмбеддингов: {e}")

    def build_embeddings(self) -> dict:
        """Batch embed all indexed sections. Returns stats."""
        if not self._embedding_provider:
            return {"status": "no_provider"}
        if not self.sections:
            return {"status": "no_sections"}

        # Identify sections that need embedding
        section_ids = [self._section_id(s) for s in self.sections]
        missing_ids = [sid for sid in section_ids if sid not in self._embeddings]

        if not missing_ids:
            return {
                "status": "ok",
                "cached": len(self._embeddings),
                "new": 0,
                "provider": self._embedding_provider.provider_name(),
            }

        # Prepare texts for missing sections
        missing_indices = [i for i, sid in enumerate(section_ids) if sid in missing_ids]
        texts = [
            f"{self.sections[i].title}\n{self.sections[i].body[:1000]}" for i in missing_indices
        ]

        try:
            vectors = self._embedding_provider.embed_texts(texts)
        except Exception as e:
            logger.error(f"Wiki RAG: ошибка эмбеддинга: {e}")
            return {"status": "error", "error": str(e)}

        # Store new embeddings
        for idx, vec in zip(missing_indices, vectors, strict=True):
            sid = section_ids[idx]
            self._embeddings[sid] = vec

        # Remove stale embeddings (sections no longer in index)
        current_ids = set(section_ids)
        stale = [k for k in self._embeddings if k not in current_ids]
        for k in stale:
            del self._embeddings[k]

        self._save_embedding_cache()

        return {
            "status": "ok",
            "cached": len(self._embeddings) - len(vectors),
            "new": len(vectors),
            "stale_removed": len(stale),
            "total": len(self._embeddings),
            "provider": self._embedding_provider.provider_name(),
        }

    def reindex_embeddings(self) -> dict:
        """Force rebuild all embeddings from scratch."""
        self._embeddings = {}
        return self.build_embeddings()

    def _embedding_search(self, query: str, top_k: int) -> list[tuple[float, WikiSection]]:
        """Semantic search via embeddings. Returns scored sections."""
        if not self._embedding_provider or not self._embeddings:
            return []

        try:
            query_vec = self._embedding_provider.embed_query(query)
        except Exception as e:
            logger.warning(f"Wiki RAG: ошибка эмбеддинга запроса: {e}")
            return []

        scored: list[tuple[float, WikiSection]] = []
        for section in self.sections:
            sid = self._section_id(section)
            if sid not in self._embeddings:
                continue
            sim = self._cosine_similarity(query_vec, self._embeddings[sid])
            if sim > 0.3:  # minimum similarity threshold
                scored.append((sim, section))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]

    @property
    def embeddings_available(self) -> bool:
        """True if we have both a provider and cached embeddings."""
        return bool(self._embedding_provider and self._embeddings)

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        max_chars: int = 2500,
        collection_id: Optional[int] = None,
    ) -> str:
        """
        Find top_k relevant sections for query.

        When collection_id is given and loaded, searches that collection's index.
        Otherwise searches the global index (backward compatible).

        Tries embedding search first, falls back to BM25.
        Returns formatted markdown context string, or empty string if no match.
        """
        # Determine which sections/index to search
        if collection_id is not None and collection_id in self._collection_indexes:
            cidx = self._collection_indexes[collection_id]
            sections = cidx.sections
            doc_freqs = cidx.doc_freqs
            total_docs = cidx.total_docs
            avg_dl = cidx.avg_dl
        else:
            sections = self.sections
            doc_freqs = self.doc_freqs
            total_docs = self.total_docs
            avg_dl = self.avg_dl

        if not sections or not query.strip():
            return ""

        # Try embedding search first (global index only — collection embeddings not implemented)
        top_sections: list[tuple[float, WikiSection]] = []
        if collection_id is None and self.embeddings_available:
            top_sections = self._embedding_search(query, top_k)

        # Fallback to BM25
        if not top_sections:
            query_tokens = self._tokenize(query)
            if not query_tokens:
                return ""

            scored: list[tuple[float, WikiSection]] = []
            for section in sections:
                score = self._bm25_score_with_index(
                    query_tokens, section, doc_freqs, total_docs, avg_dl
                )
                if score >= MIN_SCORE:
                    scored.append((score, section))

            if not scored:
                return ""

            scored.sort(key=lambda x: x[0], reverse=True)
            top_sections = scored[:top_k]

        # Format context, respect max_chars
        parts: list[str] = ["[Документация по теме:]"]
        total_chars = len(parts[0])

        for _score, section in top_sections:
            header_line = f"\n\n## {section.title} ({section.source_file})"
            body = section.body
            # Truncate individual section if needed
            available = max_chars - total_chars - len(header_line) - 4
            if available <= 0:
                break
            if len(body) > available:
                body = body[:available] + "..."

            part = f"{header_line}\n{body}"
            parts.append(part)
            total_chars += len(part)

            if total_chars >= max_chars:
                break

        return "".join(parts) if len(parts) > 1 else ""

    def retrieve_multi(
        self,
        query: str,
        collection_ids: list[int],
        top_k: int = 3,
        max_chars: int = 3000,
    ) -> str:
        """Search multiple collections, merge and rank results.

        Returns formatted markdown context string (same format as retrieve()).
        """
        if not collection_ids or not query.strip():
            return ""

        # Gather scored sections from each collection
        all_scored: list[tuple[float, WikiSection]] = []
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return ""

        for cid in collection_ids:
            if cid not in self._collection_indexes:
                continue
            cidx = self._collection_indexes[cid]
            if not cidx.sections:
                continue
            for section in cidx.sections:
                score = self._bm25_score_with_index(
                    query_tokens, section, cidx.doc_freqs, cidx.total_docs, cidx.avg_dl
                )
                if score >= MIN_SCORE:
                    all_scored.append((score, section))

        if not all_scored:
            return ""

        all_scored.sort(key=lambda x: x[0], reverse=True)
        top_sections = all_scored[:top_k]

        # Format context (same logic as retrieve)
        parts: list[str] = ["[Документация по теме:]"]
        total_chars = len(parts[0])

        for _score, section in top_sections:
            header_line = f"\n\n## {section.title} ({section.source_file})"
            body = section.body
            available = max_chars - total_chars - len(header_line) - 4
            if available <= 0:
                break
            if len(body) > available:
                body = body[:available] + "..."

            part = f"{header_line}\n{body}"
            parts.append(part)
            total_chars += len(part)

            if total_chars >= max_chars:
                break

        return "".join(parts) if len(parts) > 1 else ""

    def reload(self, wiki_dir: Path) -> dict:
        """Re-index wiki from disk. Also rebuilds embeddings if provider is set."""
        old_count = len(self.sections)
        self._load_and_index(wiki_dir)
        result = {
            "previous_sections": old_count,
            "current_sections": len(self.sections),
            "files_indexed": self._files_indexed,
        }
        # Rebuild embeddings for new/changed sections
        if self._embedding_provider:
            emb_result = self.build_embeddings()
            result["embeddings"] = emb_result
        return result

    def search(self, query: str, top_k: int = 3, collection_id: Optional[int] = None) -> list[dict]:
        """Structured search results with scores (for API/UI).

        When collection_id is given and loaded, searches that collection's index.
        Tries embedding search first, falls back to BM25.
        """
        # Determine which sections/index to search
        if collection_id is not None and collection_id in self._collection_indexes:
            cidx = self._collection_indexes[collection_id]
            sections = cidx.sections
            doc_freqs = cidx.doc_freqs
            total_docs = cidx.total_docs
            avg_dl = cidx.avg_dl
        else:
            sections = self.sections
            doc_freqs = self.doc_freqs
            total_docs = self.total_docs
            avg_dl = self.avg_dl

        if not sections or not query.strip():
            return []

        # Try embedding search first (global index only)
        scored: list[tuple[float, WikiSection]] = []
        if collection_id is None and self.embeddings_available:
            scored = self._embedding_search(query, top_k)
        search_engine = "embeddings" if scored else "bm25"

        # Fallback to BM25
        if not scored:
            query_tokens = self._tokenize(query)
            if not query_tokens:
                return []

            for section in sections:
                score = self._bm25_score_with_index(
                    query_tokens, section, doc_freqs, total_docs, avg_dl
                )
                if score >= MIN_SCORE:
                    scored.append((score, section))

            if not scored:
                return []

            scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, section in scored[:top_k]:
            results.append(
                {
                    "title": section.title,
                    "body": section.body[:500],
                    "source_file": section.source_file,
                    "score": round(score, 3),
                    "engine": search_engine,
                }
            )
        return results

    # ---- Vector Search integration ----

    def set_vector_search_client(self, client: VectorSearchClient) -> None:
        """Set the Vector Search microservice client."""
        self._vector_search_client = client

    @property
    def vector_search_available(self) -> bool:
        """True if vector search client is configured."""
        return self._vector_search_client is not None

    async def _vector_search_async(
        self, query: str, top_k: int, collection_slug: str = "default"
    ) -> list[dict]:
        """Search via Vector Search microservice. Returns results in standard format."""
        if not self._vector_search_client:
            return []

        try:
            results = await self._vector_search_client.search(
                text=query, group=collection_slug, limit=top_k, min_similarity=0.3
            )
        except Exception as e:
            logger.warning("Vector Search query failed: %s", e)
            return []

        output = []
        for r in results:
            meta = r.get("metadata", {})
            output.append(
                {
                    "title": meta.get("title", ""),
                    "body": r.get("text", "")[:500],
                    "source_file": meta.get("doc_id", meta.get("source_file", "")),
                    "score": r.get("similarity", 0.0),
                    "engine": "vector_search",
                }
            )
        return output

    async def search_async(
        self, query: str, top_k: int = 3, collection_id: Optional[int] = None
    ) -> list[dict]:
        """Parallel search across all engines: BM25 + embeddings + vector search.

        Returns deduplicated, merged results sorted by best score.
        """
        import asyncio

        # BM25 + embeddings (sync, run in thread)
        local_results = await asyncio.to_thread(self.search, query, top_k, collection_id)

        # Vector Search (async)
        collection_slug = "default"
        if collection_id is not None and collection_id in self._collection_indexes:
            # Use collection_id as group name
            collection_slug = str(collection_id)

        vs_results = await self._vector_search_async(query, top_k, collection_slug)

        # Merge and deduplicate
        return self._merge_results(local_results, vs_results, top_k)

    async def retrieve_async(
        self,
        query: str,
        top_k: int = 3,
        max_chars: int = 2500,
        collection_id: Optional[int] = None,
    ) -> str:
        """Like retrieve() but includes vector search results.

        Returns formatted markdown context string.
        """
        results = await self.search_async(query, top_k, collection_id)
        if not results:
            return ""

        return self._format_results(results, max_chars)

    async def retrieve_multi_async(
        self,
        query: str,
        collection_ids: list[int],
        top_k: int = 3,
        max_chars: int = 3000,
    ) -> str:
        """Like retrieve_multi() but includes vector search results."""
        import asyncio

        if not collection_ids or not query.strip():
            return ""

        # BM25 multi-collection (sync)
        local_results_raw = await asyncio.to_thread(
            self._retrieve_multi_search, query, collection_ids, top_k
        )

        # Vector Search across all collection slugs (async)
        vs_tasks = []
        for cid in collection_ids:
            vs_tasks.append(self._vector_search_async(query, top_k, str(cid)))

        vs_all = await asyncio.gather(*vs_tasks)
        vs_results = [r for batch in vs_all for r in batch]

        merged = self._merge_results(local_results_raw, vs_results, top_k)
        if not merged:
            return ""

        return self._format_results(merged, max_chars)

    def _retrieve_multi_search(
        self, query: str, collection_ids: list[int], top_k: int
    ) -> list[dict]:
        """BM25 search across multiple collections. Returns structured results."""
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        all_scored: list[tuple[float, WikiSection]] = []
        for cid in collection_ids:
            if cid not in self._collection_indexes:
                continue
            cidx = self._collection_indexes[cid]
            for section in cidx.sections:
                score = self._bm25_score_with_index(
                    query_tokens, section, cidx.doc_freqs, cidx.total_docs, cidx.avg_dl
                )
                if score >= MIN_SCORE:
                    all_scored.append((score, section))

        if not all_scored:
            return []

        all_scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, section in all_scored[:top_k]:
            results.append(
                {
                    "title": section.title,
                    "body": section.body[:500],
                    "source_file": section.source_file,
                    "score": round(score, 3),
                    "engine": "bm25",
                }
            )
        return results

    @staticmethod
    def _merge_results(local_results: list[dict], vs_results: list[dict], top_k: int) -> list[dict]:
        """Merge and deduplicate results from multiple engines.

        Deduplicates by (source_file, title), keeping the highest score.
        """
        seen: dict[tuple[str, str], dict] = {}
        for r in local_results + vs_results:
            key = (r.get("source_file", ""), r.get("title", ""))
            if key in seen:
                if r.get("score", 0) > seen[key].get("score", 0):
                    seen[key] = r
            else:
                seen[key] = r

        merged = sorted(seen.values(), key=lambda x: x.get("score", 0), reverse=True)
        return merged[:top_k]

    @staticmethod
    def _format_results(results: list[dict], max_chars: int) -> str:
        """Format search results into markdown context string."""
        parts: list[str] = ["[Документация по теме:]"]
        total_chars = len(parts[0])

        for r in results:
            header_line = f"\n\n## {r['title']} ({r['source_file']})"
            body = r.get("body", "")
            available = max_chars - total_chars - len(header_line) - 4
            if available <= 0:
                break
            if len(body) > available:
                body = body[:available] + "..."

            part = f"{header_line}\n{body}"
            parts.append(part)
            total_chars += len(part)

            if total_chars >= max_chars:
                break

        return "".join(parts) if len(parts) > 1 else ""

    def list_source_files(self) -> list[str]:
        """List unique source files in the index."""
        return sorted({s.source_file for s in self.sections})

    @property
    def stats(self) -> dict:
        """Index statistics."""
        embedding_engine = None
        if self._embedding_provider:
            embedding_engine = self._embedding_provider.provider_name()

        collection_stats = {}
        for cid, cidx in self._collection_indexes.items():
            collection_stats[str(cid)] = {
                "sections_indexed": cidx.total_docs,
                "files_indexed": cidx.files_indexed,
                "unique_tokens": len(cidx.doc_freqs),
            }

        engine_parts = []
        if self._embeddings:
            engine_parts.append("embeddings")
        engine_parts.append("bm25")
        if self._vector_search_client:
            engine_parts.append("vector_search")

        return {
            "engine": "+".join(engine_parts),
            "embedding_engine": embedding_engine,
            "embedding_sections": len(self._embeddings),
            "vector_search_available": self._vector_search_client is not None,
            "vector_search_url": (
                self._vector_search_client.base_url if self._vector_search_client else None
            ),
            "sections_indexed": len(self.sections),
            "files_indexed": self._files_indexed,
            "unique_tokens": len(self.doc_freqs),
            "avg_doc_length": round(self.avg_dl, 1),
            "available": len(self.sections) > 0,
            "collections": collection_stats,
        }
