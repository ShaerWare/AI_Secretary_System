"""WooCommerce REST API v3 async HTTP client.

Uses Basic Auth (consumer_key:consumer_secret) over HTTPS.
"""

import logging
from typing import Any

import httpx


logger = logging.getLogger(__name__)

TIMEOUT = 30.0
MAX_PER_PAGE = 100


async def _request(
    method: str,
    url: str,
    consumer_key: str,
    consumer_secret: str,
    params: dict[str, Any] | None = None,
) -> Any:
    """Make an authenticated WooCommerce API request.

    Uses query parameter auth (consumer_key/consumer_secret in URL params)
    which works universally, including on hosts that block HTTP Basic Auth
    for the WordPress REST API.
    """
    if params is None:
        params = {}
    params["consumer_key"] = consumer_key
    params["consumer_secret"] = consumer_secret
    async with httpx.AsyncClient(timeout=TIMEOUT, trust_env=False) as client:
        resp = await client.request(method, url, params=params)
        resp.raise_for_status()
        return resp.json()


def _api_url(store_url: str, endpoint: str) -> str:
    """Build WooCommerce REST API URL."""
    base = store_url.rstrip("/")
    return f"{base}/wp-json/wc/v3/{endpoint}"


async def test_connection(
    store_url: str, consumer_key: str, consumer_secret: str
) -> dict[str, Any]:
    """Test connection to WooCommerce store. Returns store info."""
    url = store_url.rstrip("/") + "/wp-json/wc/v3"
    data = await _request("GET", url, consumer_key, consumer_secret)
    return {
        "store_name": data.get("store", {}).get("name", ""),
        "description": data.get("description", ""),
        "wc_version": data.get("wc_version", ""),
        "url": store_url,
    }


async def get_products(
    store_url: str,
    consumer_key: str,
    consumer_secret: str,
    page: int = 1,
    per_page: int = MAX_PER_PAGE,
) -> list[dict[str, Any]]:
    """Fetch a page of products."""
    url = _api_url(store_url, "products")
    return await _request(
        "GET",
        url,
        consumer_key,
        consumer_secret,
        params={"page": page, "per_page": per_page},
    )


async def get_all_products(
    store_url: str, consumer_key: str, consumer_secret: str
) -> list[dict[str, Any]]:
    """Fetch all products with pagination."""
    all_products: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = await get_products(store_url, consumer_key, consumer_secret, page)
        if not batch:
            break
        all_products.extend(batch)
        logger.info(f"WooCommerce: fetched {len(all_products)} products (page {page})")
        if len(batch) < MAX_PER_PAGE:
            break
        page += 1
    return all_products


async def get_categories(
    store_url: str, consumer_key: str, consumer_secret: str
) -> list[dict[str, Any]]:
    """Fetch all product categories."""
    all_categories: list[dict[str, Any]] = []
    page = 1
    while True:
        url = _api_url(store_url, "products/categories")
        batch = await _request(
            "GET",
            url,
            consumer_key,
            consumer_secret,
            params={"page": page, "per_page": MAX_PER_PAGE},
        )
        if not batch:
            break
        all_categories.extend(batch)
        if len(batch) < MAX_PER_PAGE:
            break
        page += 1
    return all_categories


async def get_orders(
    store_url: str,
    consumer_key: str,
    consumer_secret: str,
    page: int = 1,
    per_page: int = MAX_PER_PAGE,
) -> list[dict[str, Any]]:
    """Fetch a page of orders."""
    url = _api_url(store_url, "orders")
    return await _request(
        "GET",
        url,
        consumer_key,
        consumer_secret,
        params={"page": page, "per_page": per_page},
    )


async def get_all_orders(
    store_url: str, consumer_key: str, consumer_secret: str
) -> list[dict[str, Any]]:
    """Fetch all orders with pagination."""
    all_orders: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = await get_orders(store_url, consumer_key, consumer_secret, page)
        if not batch:
            break
        all_orders.extend(batch)
        logger.info(f"WooCommerce: fetched {len(all_orders)} orders (page {page})")
        if len(batch) < MAX_PER_PAGE:
            break
        page += 1
    return all_orders
