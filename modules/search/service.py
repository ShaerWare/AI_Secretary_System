"""Web search service using DuckDuckGo."""

import logging


logger = logging.getLogger(__name__)

try:
    from duckduckgo_search import DDGS

    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False
    logger.warning("duckduckgo-search not installed, web search unavailable")


class WebSearchService:
    """Performs web searches via DuckDuckGo."""

    def __init__(self) -> None:
        self.available = DDGS_AVAILABLE

    def search(
        self,
        query: str,
        max_results: int = 5,
        region: str = "ru-ru",
    ) -> str:
        """Search the web and return formatted results.

        Returns a text block suitable for injection into LLM context.
        """
        if not self.available:
            return "Web search is not available (duckduckgo-search not installed)."

        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, region=region, max_results=max_results))

            if not results:
                return f"No web results found for: {query}"

            parts: list[str] = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "")
                body = r.get("body", "")
                href = r.get("href", "")
                parts.append(f"{i}. **{title}**\n   {body}\n   URL: {href}")

            return "\n\n".join(parts)

        except Exception as e:
            logger.error(f"Web search error: {e}")
            return f"Web search failed: {e}"

    def search_news(
        self,
        query: str,
        max_results: int = 5,
        region: str = "ru-ru",
    ) -> str:
        """Search news articles."""
        if not self.available:
            return "Web search is not available."

        try:
            with DDGS() as ddgs:
                results = list(ddgs.news(query, region=region, max_results=max_results))

            if not results:
                return f"No news found for: {query}"

            parts: list[str] = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "")
                body = r.get("body", "")
                source = r.get("source", "")
                date = r.get("date", "")
                url = r.get("url", "")
                parts.append(f"{i}. **{title}** ({source}, {date})\n   {body}\n   URL: {url}")

            return "\n\n".join(parts)

        except Exception as e:
            logger.error(f"News search error: {e}")
            return f"News search failed: {e}"


# Singleton
web_search_service = WebSearchService()
