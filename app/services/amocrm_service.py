# app/services/amocrm_service.py
"""amoCRM v4 API client — pure async functions (no DB access).

OAuth 2.0 flow:
1. Admin enters subdomain + client_id + client_secret in UI
2. Admin clicks "Connect" → redirect to amoCRM consent page
3. amoCRM redirects back with auth code → exchange for access_token + refresh_token
4. Tokens auto-refresh on 401 via router helper `_ensure_valid_token()`

API reference: https://www.amocrm.ru/developers/content/crm_platform/platform-abilities
"""

import asyncio
import logging
import os
from typing import Any, Optional

import httpx


logger = logging.getLogger(__name__)

AMOCRM_API_VERSION = "v4"
MAX_429_RETRIES = 3
RETRY_DELAY_SECONDS = 1.5

# Optional HTTP CONNECT proxy for Docker environments where amoCRM is unreachable.
# Set AMOCRM_PROXY=http://host.docker.internal:8899 in docker-compose.yml.
AMOCRM_PROXY = os.getenv("AMOCRM_PROXY") or None


def _http_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """Create httpx client with optional proxy for amoCRM requests."""
    kwargs: dict[str, Any] = {"timeout": timeout}
    if AMOCRM_PROXY:
        kwargs["proxy"] = AMOCRM_PROXY
    return httpx.AsyncClient(**kwargs)


# ============== Exceptions ==============


class AmoCRMAPIError(Exception):
    """Generic amoCRM API error."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"amoCRM API error {status_code}: {detail}")


class AmoCRMTokenExpired(AmoCRMAPIError):
    """Access token is expired or invalid (401)."""

    def __init__(self, detail: str = "Token expired"):
        super().__init__(status_code=401, detail=detail)


# ============== OAuth ==============


def build_auth_url(
    subdomain: str,
    client_id: str,
    redirect_uri: str,
) -> str:
    """Build amoCRM OAuth 2.0 authorization URL."""
    from urllib.parse import urlencode

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
    }
    return f"https://{subdomain}.amocrm.ru/oauth?{urlencode(params)}"


async def exchange_code_for_token(
    subdomain: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> dict:
    """Exchange authorization code for access + refresh tokens.

    Returns dict with access_token, refresh_token, expires_in on success.
    Raises AmoCRMAPIError on failure.
    """
    url = f"https://{subdomain}.amocrm.ru/oauth2/access_token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }

    async with _http_client() as client:
        resp = await client.post(url, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            logger.info("amoCRM tokens obtained successfully")
            return data
        logger.error(f"amoCRM token exchange failed: {resp.status_code} {resp.text}")
        raise AmoCRMAPIError(resp.status_code, resp.text)


async def refresh_access_token(
    subdomain: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    redirect_uri: str,
) -> dict:
    """Refresh access token using refresh_token.

    Returns dict with new access_token, refresh_token, expires_in.
    Raises AmoCRMAPIError on failure.
    """
    url = f"https://{subdomain}.amocrm.ru/oauth2/access_token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "redirect_uri": redirect_uri,
    }

    async with _http_client() as client:
        resp = await client.post(url, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            logger.info("amoCRM tokens refreshed successfully")
            return data
        logger.error(f"amoCRM token refresh failed: {resp.status_code} {resp.text}")
        raise AmoCRMAPIError(resp.status_code, resp.text)


# ============== Generic API request ==============


async def _api_request(
    subdomain: str,
    access_token: str,
    method: str,
    path: str,
    params: Optional[dict] = None,
    json_data: Optional[Any] = None,
) -> Any:
    """Make a request to amoCRM v4 API with 429 retry.

    Raises AmoCRMTokenExpired on 401, AmoCRMAPIError on other errors.
    Returns parsed JSON response (or None for 204).
    """
    url = f"https://{subdomain}.amocrm.ru/api/{AMOCRM_API_VERSION}/{path}"
    headers = {"Authorization": f"Bearer {access_token}"}

    for attempt in range(MAX_429_RETRIES + 1):
        async with _http_client() as client:
            resp = await client.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_data,
            )

        if resp.status_code == 204:
            return None

        if resp.status_code == 401:
            raise AmoCRMTokenExpired()

        if resp.status_code == 429:
            if attempt < MAX_429_RETRIES:
                delay = RETRY_DELAY_SECONDS * (attempt + 1)
                logger.warning(f"amoCRM rate limit hit, retrying in {delay}s...")
                await asyncio.sleep(delay)
                continue
            raise AmoCRMAPIError(429, "Rate limit exceeded after retries")

        if resp.status_code >= 400:
            raise AmoCRMAPIError(resp.status_code, resp.text)

        return resp.json()

    raise AmoCRMAPIError(429, "Rate limit exceeded after retries")


# ============== Account ==============


async def get_account_info(subdomain: str, access_token: str) -> dict:
    """Get amoCRM account info (name, subdomain, current_user, etc.)."""
    return await _api_request(subdomain, access_token, "GET", "account")


# ============== Contacts ==============


async def get_contacts(
    subdomain: str,
    access_token: str,
    page: int = 1,
    limit: int = 50,
    query: Optional[str] = None,
) -> dict:
    """Get contacts list. Returns _embedded.contacts array."""
    params: dict[str, Any] = {"page": page, "limit": limit}
    if query:
        params["query"] = query
    return await _api_request(subdomain, access_token, "GET", "contacts", params=params)


async def create_contact(
    subdomain: str,
    access_token: str,
    name: str,
    custom_fields: Optional[list] = None,
) -> dict:
    """Create a new contact."""
    contact: dict[str, Any] = {"name": name}
    if custom_fields:
        contact["custom_fields_values"] = custom_fields
    return await _api_request(subdomain, access_token, "POST", "contacts", json_data=[contact])


# ============== Leads ==============


async def get_leads(
    subdomain: str,
    access_token: str,
    page: int = 1,
    limit: int = 50,
    query: Optional[str] = None,
) -> dict:
    """Get leads list. Returns _embedded.leads array."""
    params: dict[str, Any] = {"page": page, "limit": limit}
    if query:
        params["query"] = query
    return await _api_request(subdomain, access_token, "GET", "leads", params=params)


async def create_lead(
    subdomain: str,
    access_token: str,
    name: str,
    pipeline_id: Optional[int] = None,
    status_id: Optional[int] = None,
    contact_id: Optional[int] = None,
) -> dict:
    """Create a new lead, optionally linked to a contact."""
    lead: dict[str, Any] = {"name": name}
    if pipeline_id:
        lead["pipeline_id"] = pipeline_id
    if status_id:
        lead["status_id"] = status_id
    if contact_id:
        lead["_embedded"] = {"contacts": [{"id": contact_id}]}
    return await _api_request(subdomain, access_token, "POST", "leads", json_data=[lead])


async def add_note_to_lead(
    subdomain: str,
    access_token: str,
    lead_id: int,
    text: str,
) -> dict:
    """Add a text note to a lead."""
    note = {
        "note_type": "common",
        "params": {"text": text},
    }
    return await _api_request(
        subdomain,
        access_token,
        "POST",
        f"leads/{lead_id}/notes",
        json_data=[note],
    )


# ============== Pipelines ==============


async def get_pipelines(subdomain: str, access_token: str) -> dict:
    """Get sales pipelines with their statuses."""
    return await _api_request(subdomain, access_token, "GET", "leads/pipelines")


async def get_lead(
    subdomain: str,
    access_token: str,
    lead_id: int,
    with_contacts: bool = False,
) -> dict:
    """Get single lead detail, optionally with embedded contacts."""
    params: dict[str, Any] = {}
    if with_contacts:
        params["with"] = "contacts"
    return await _api_request(
        subdomain, access_token, "GET", f"leads/{lead_id}", params=params or None
    )


async def update_lead(
    subdomain: str,
    access_token: str,
    lead_id: int,
    data: dict,
) -> dict:
    """Update a lead (status_id, pipeline_id, name, price, etc.)."""
    return await _api_request(subdomain, access_token, "PATCH", f"leads/{lead_id}", json_data=data)


async def get_leads_by_pipeline(
    subdomain: str,
    access_token: str,
    pipeline_id: int,
) -> dict:
    """Get ALL leads in a specific pipeline (paginated, for kanban board)."""
    all_leads: list[dict] = []
    page = 1
    limit = 250

    while True:
        params: dict[str, Any] = {
            "filter[pipeline_id][]": pipeline_id,
            "limit": limit,
            "page": page,
            "with": "contacts",
        }
        data = await _api_request(subdomain, access_token, "GET", "leads", params=params)
        if not data or "_embedded" not in data:
            break
        leads = data["_embedded"].get("leads", [])
        if not leads:
            break
        all_leads.extend(leads)
        if len(leads) < limit:
            break
        page += 1

    return {"_embedded": {"leads": all_leads}}


async def get_unsorted_leads(
    subdomain: str,
    access_token: str,
    page: int = 1,
    limit: int = 250,
) -> dict:
    """Get unsorted (incoming) leads for one page.

    amoCRM unsorted API returns wrapper items whose embedded leads are stubs
    (only id + _links).  We build proper lead-like objects from the wrapper
    metadata (source_name, category, contacts) so the frontend can render them.

    Returns ``{_embedded: {leads: [...]}, has_next: bool}``.
    """
    empty: dict[str, Any] = {"_embedded": {"leads": []}, "has_next": False}
    params: dict[str, Any] = {"limit": limit, "page": page}
    try:
        data = await _api_request(subdomain, access_token, "GET", "leads/unsorted", params=params)
    except AmoCRMAPIError as e:
        if e.status_code == 204:
            return empty
        raise
    if not data or "_embedded" not in data:
        return empty

    has_next = bool(data.get("_links", {}).get("next"))
    unsorted_items = data["_embedded"].get("unsorted", [])
    all_leads: list[dict] = []

    for item in unsorted_items:
        embedded = item.get("_embedded", {})
        stub_leads = embedded.get("leads", [])
        contacts = embedded.get("contacts", [])
        category = item.get("category", "")
        source_name = item.get("source_name", "")
        contact_name = contacts[0]["name"] if contacts else ""

        lead_id = stub_leads[0]["id"] if stub_leads else item.get("uid")
        name = contact_name or source_name or category or "Неразобранное"

        lead: dict[str, Any] = {
            "id": lead_id,
            "name": name,
            "price": 0,
            "pipeline_id": item.get("pipeline_id"),
            "status_id": None,
            "created_at": item.get("created_at"),
            "_is_unsorted": True,
            "_unsorted_uid": item.get("uid"),
            "_unsorted_category": category,
            "_unsorted_source": source_name,
        }
        if contacts:
            lead["_embedded"] = {"contacts": contacts}
        all_leads.append(lead)

    return {"_embedded": {"leads": all_leads}, "has_next": has_next}


async def get_events(
    subdomain: str,
    access_token: str,
    page: int = 1,
    limit: int = 50,
    event_types: Optional[str] = None,
) -> dict:
    """Get events feed (chat messages, lead changes, etc.)."""
    params: dict[str, Any] = {"page": page, "limit": limit}
    if event_types:
        params["filter[type]"] = event_types
    return await _api_request(subdomain, access_token, "GET", "events", params=params)


async def get_contact_chats(
    subdomain: str,
    access_token: str,
    contact_id: int,
) -> dict:
    """Get chats linked to a contact."""
    return await _api_request(subdomain, access_token, "GET", f"contacts/{contact_id}/chats")


# ============== Amojo (Chat Messaging) API ==============


def _amojo_sign(
    method: str,
    content_type: str,
    content_md5: str,
    date_str: str,
    path: str,
    secret: str,
) -> str:
    """Create HMAC-SHA1 signature for amojo API requests."""
    import hashlib
    import hmac

    string_to_sign = "\n".join([method.upper(), content_type, content_md5, date_str, path])
    signature = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).hexdigest()
    return signature


async def _amojo_request(
    amojo_base_url: str,
    scope_id: str,
    channel_secret: str,
    method: str,
    path: str,
    json_data: Optional[Any] = None,
    params: Optional[dict] = None,
) -> Any:
    """Make a signed request to amojo API."""
    import hashlib
    import json
    from email.utils import formatdate

    url = f"{amojo_base_url.rstrip('/')}{path}"
    date_str = formatdate(usegmt=True)

    body_bytes = b""
    content_type = ""
    if json_data is not None:
        body_bytes = json.dumps(json_data).encode("utf-8")
        content_type = "application/json"

    content_md5 = hashlib.md5(body_bytes).hexdigest() if body_bytes else ""

    signature = _amojo_sign(
        method.upper(), content_type, content_md5, date_str, path, channel_secret
    )

    headers = {
        "Date": date_str,
        "Content-Type": content_type or "application/json",
        "X-Signature": signature,
    }
    if content_md5:
        headers["Content-MD5"] = content_md5

    async with _http_client(timeout=30.0) as client:
        resp = await client.request(
            method,
            url,
            headers=headers,
            content=body_bytes if body_bytes else None,
            params=params,
        )

    if resp.status_code >= 400:
        logger.error(f"Amojo API error: {resp.status_code} {resp.text}")
        raise AmoCRMAPIError(resp.status_code, resp.text)

    if resp.status_code == 204:
        return None

    return resp.json()


async def get_chat_history(
    amojo_base_url: str,
    scope_id: str,
    channel_secret: str,
    chat_id: str,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Get chat message history via amojo API."""
    path = f"/v2/origin/custom/{scope_id}/chats/{chat_id}/history"
    params = {"limit": limit, "offset": offset}
    return await _amojo_request(
        amojo_base_url, scope_id, channel_secret, "GET", path, params=params
    )


async def send_chat_message(
    amojo_base_url: str,
    scope_id: str,
    channel_secret: str,
    chat_id: str,
    sender_id: str,
    sender_name: str,
    text: str,
) -> dict:
    """Send a chat message via amojo API."""
    import time
    import uuid

    path = f"/v2/origin/custom/{scope_id}"
    payload = {
        "event_type": "new_message",
        "payload": {
            "timestamp": int(time.time()),
            "msgid": str(uuid.uuid4()),
            "conversation_id": chat_id,
            "sender": {
                "id": sender_id,
                "name": sender_name,
            },
            "message": {
                "type": "text",
                "text": text,
            },
        },
    }
    return await _amojo_request(
        amojo_base_url, scope_id, channel_secret, "POST", path, json_data=payload
    )
