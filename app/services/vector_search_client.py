"""
Async HTTP client for Vector Search microservice.

Graceful degradation: if the service is unavailable, methods log warnings
and return empty results instead of raising exceptions.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx


logger = logging.getLogger(__name__)

# Retry config
MAX_RETRIES = 2
RETRY_BACKOFF = 0.5  # seconds


class VectorSearchClient:
    """Async client for the Vector Search microservice."""

    def __init__(self, base_url: str, token: str = "", timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._available = False

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request with retry and graceful error handling."""
        import asyncio

        url = f"{self._base_url}{path}"
        last_error = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.request(
                        method, url, json=json, params=params, headers=self._headers()
                    )
                    resp.raise_for_status()
                    self._available = True
                    return resp.json()
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                last_error = e
                self._available = False
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
            except httpx.HTTPStatusError as e:
                logger.warning("Vector Search %s %s: HTTP %s", method, path, e.response.status_code)
                self._available = True
                raise
            except Exception as e:
                last_error = e
                self._available = False
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))

        logger.warning("Vector Search unavailable (%s %s): %s", method, path, last_error)
        return {}

    @property
    def available(self) -> bool:
        """Whether the last request succeeded."""
        return self._available

    @property
    def base_url(self) -> str:
        return self._base_url

    async def health(self) -> dict[str, Any]:
        """Check service health."""
        return await self._request("GET", "/health")

    async def upsert(
        self,
        text: str,
        doc_id: str = "",
        group: str = "default",
        chunk_size: int | None = 500,
        chunk_overlap: int | None = 50,
        metadata: dict | None = None,
    ) -> list[str]:
        """Upsert text into vector store. Returns list of record IDs."""
        body: dict[str, Any] = {
            "text": text,
            "doc_id": doc_id,
            "group": group,
        }
        if chunk_size is not None:
            body["chunk_size"] = chunk_size
        if chunk_overlap is not None:
            body["chunk_overlap"] = chunk_overlap
        if metadata:
            body["metadata"] = metadata

        result = await self._request("POST", "/upsert", json=body)
        return result.get("record_ids", [])

    async def search(
        self,
        text: str,
        group: str = "default",
        doc_id: str = "",
        min_similarity: float = 0.3,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Semantic search. Returns list of {record_id, text, similarity, metadata}."""
        body = {
            "text": text,
            "group": group,
            "min_similarity": min_similarity,
            "limit": limit,
        }
        if doc_id:
            body["doc_id"] = doc_id

        result = await self._request("POST", "/search", json=body)
        return result.get("results", [])

    async def compare(self, text: str, record_id: str) -> float:
        """Compare text with a stored record. Returns similarity score."""
        result = await self._request(
            "POST",
            "/compare",
            json={
                "text": text,
                "record_id": record_id,
            },
        )
        return result.get("similarity", 0.0)

    async def count(self, group: str = "default") -> int:
        """Count records in a group."""
        result = await self._request("GET", "/count", params={"group": group})
        return result.get("count", 0)

    async def get_ids(self, group: str = "default", doc_id: str = "") -> list[str]:
        """Get record IDs in a group."""
        params: dict[str, str] = {"group": group}
        if doc_id:
            params["doc_id"] = doc_id
        result = await self._request("GET", "/ids", params=params)
        return result.get("ids", [])

    async def delete_record(self, record_id: str) -> bool:
        """Delete a single record."""
        try:
            result = await self._request("POST", "/delete/record", json={"record_id": record_id})
            return result.get("status") == "ok"
        except Exception:
            return False

    async def delete_document(self, doc_id: str, group: str = "default") -> bool:
        """Delete all records for a document."""
        try:
            result = await self._request(
                "POST", "/delete/document", json={"doc_id": doc_id, "group": group}
            )
            return result.get("status") == "ok"
        except Exception:
            return False

    async def delete_group(self, group: str) -> bool:
        """Delete an entire group (collection)."""
        try:
            result = await self._request("POST", "/delete/group", json={"group": group})
            return result.get("status") == "ok"
        except Exception:
            return False
