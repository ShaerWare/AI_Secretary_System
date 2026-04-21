# modules/admin/router_github_webhook.py
"""GitHub webhook handler — receives PR events, posts AI comments, broadcasts to subscribers."""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
from typing import Optional

import httpx
from fastapi import APIRouter, Header, HTTPException, Request

from db.database import AsyncSessionLocal
from db.models import BotInstance
from db.repositories.bot_github import BotGithubRepository
from db.repositories.bot_subscriber import BotSubscriberRepository


logger = logging.getLogger(__name__)

router = APIRouter(tags=["github-webhook"])


async def _verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _generate_comment(system_prompt: str, pr_data: dict) -> Optional[str]:
    """Generate AI comment for PR using local vLLM."""
    from app.dependencies import service_container

    vllm_url = getattr(service_container, "vllm_api_url", None)
    if not vllm_url:
        vllm_url = "http://localhost:11434"

    user_content = (
        f"PR #{pr_data['number']}: {pr_data['title']}\n\n"
        f"Author: {pr_data.get('user', {}).get('login', 'unknown')}\n"
        f"Branch: {pr_data.get('head', {}).get('ref', '?')} -> {pr_data.get('base', {}).get('ref', '?')}\n\n"
        f"Description:\n{pr_data.get('body', 'No description') or 'No description'}\n\n"
        f"Changed files: {pr_data.get('changed_files', '?')}, "
        f"Additions: +{pr_data.get('additions', '?')}, "
        f"Deletions: -{pr_data.get('deletions', '?')}"
    )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{vllm_url}/v1/chat/completions",
                json={
                    "model": "default",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1024,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Failed to generate AI comment: {e}")
        return None


async def _post_github_comment(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    comment_body: str,
    github_token: str,
) -> bool:
    """Post a comment on a GitHub PR."""
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues/{pr_number}/comments"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json={"body": comment_body},
                headers={
                    "Authorization": f"token {github_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            resp.raise_for_status()
            logger.info(f"Posted comment on PR #{pr_number} in {repo_owner}/{repo_name}")
            return True
    except Exception as e:
        logger.error(f"Failed to post GitHub comment: {e}")
        return False


_NEWS_PATTERN = re.compile(
    r"##\s*(?:\U0001f4e2\s*)?NEWS\s*\n(.*?)(?=\n##|\Z)", re.IGNORECASE | re.DOTALL
)


def _parse_news_from_pr(pr_body: str) -> Optional[str]:
    """Extract ## NEWS section from PR body and clean it up."""
    if not pr_body:
        return None
    match = _NEWS_PATTERN.search(pr_body)
    if not match:
        return None
    lines = []
    for line in match.group(1).strip().splitlines():
        if "Generated with" in line and "Claude" in line:
            continue
        if "Co-Authored-By:" in line:
            continue
        lines.append(line)
    text = "\n".join(lines).rstrip()
    if not text:
        return None
    if "ai-sekretar24.ru" not in text:
        text += "\n\n\U0001f5a5 Демо: https://ai-sekretar24.ru"
    if "@shaerware" not in text.lower():
        text += "\n\n\U0001f517 @shaerware"
    return text


async def _broadcast_to_subscribers(
    bot_id: str,
    message: str,
) -> int:
    """Send message to all subscribers via Telegram Bot API (direct HTTP).

    Fetches bot_token from BotInstance, then sends to each subscriber.
    Returns number of successfully sent messages.
    """
    from sqlalchemy import select

    # Get bot token and subscriber list
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BotInstance.bot_token).where(BotInstance.id == bot_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            logger.warning(f"No bot_token for bot_id={bot_id}, cannot broadcast")
            return 0
        bot_token = row

        sub_repo = BotSubscriberRepository(session)
        user_ids = await sub_repo.get_active_subscribers(bot_id)

    if not user_ids:
        logger.info(f"No subscribers for bot_id={bot_id}, skipping broadcast")
        return 0

    sent = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        for user_id in user_ids:
            try:
                resp = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": user_id, "text": message},
                )
                if resp.status_code == 200:
                    sent += 1
                else:
                    logger.warning(f"Telegram send failed for user {user_id}: {resp.status_code}")
            except Exception as e:
                logger.warning(f"Failed to send news to user {user_id}: {e}")
            await asyncio.sleep(0.05)

    logger.info(f"Broadcast sent to {sent}/{len(user_ids)} subscribers (bot_id={bot_id})")
    return sent


async def _handle_issue_event(payload: bytes, signature: Optional[str]) -> dict:
    """Handle GitHub issues webhook events for kanban sync."""
    try:
        event_data = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    repo_data = event_data.get("repository", {})
    full_name = repo_data.get("full_name", "")
    if "/" not in full_name:
        return {"status": "ignored", "reason": "no repo"}

    owner, repo = full_name.split("/", 1)

    from modules.kanban.service import kanban_project_service

    project = await kanban_project_service.get_by_repo(owner, repo)
    if not project:
        return {"status": "ignored", "reason": "no matching kanban project"}

    if not project.get("sync_enabled", True):
        return {"status": "ignored", "reason": "sync disabled"}

    # Verify HMAC if webhook_secret is set
    if project.get("webhook_secret") and signature:
        if not await _verify_signature(payload, signature, project["webhook_secret"]):
            logger.warning(f"Invalid signature for kanban project {project['id']}")
            raise HTTPException(status_code=401, detail="Invalid signature")

    from app.services.github_kanban_sync import handle_issue_webhook

    result = await handle_issue_webhook(event_data, project)
    if result:
        return {"status": "processed", "task_id": result.get("id")}
    return {"status": "ignored", "reason": "unsupported action"}


@router.post("/webhooks/github")
async def handle_github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
):
    """Handle GitHub webhook events (PR opened/merged -> AI comment + subscriber broadcast).

    This endpoint is public (no JWT) but verified via webhook secret signature.
    """
    payload = await request.body()

    if not x_github_event:
        raise HTTPException(status_code=400, detail="Missing X-GitHub-Event header")

    # Handle issues events for kanban sync
    if x_github_event == "issues":
        return await _handle_issue_event(payload, x_hub_signature_256)

    # Only process pull_request events below
    if x_github_event != "pull_request":
        return {"status": "ignored", "event": x_github_event}

    try:
        event_data = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    action = event_data.get("action", "")
    pr_data = event_data.get("pull_request", {})
    repo = event_data.get("repository", {})
    repo_full_name = repo.get("full_name", "")  # e.g. "ShaerWare/AI_Secretary_System"

    # GitHub sends action=closed with merged=true for merged PRs.
    # Normalize to "merged" for config matching (configs use "merged" in events list).
    effective_action = action
    if action == "closed" and pr_data.get("merged"):
        effective_action = "merged"

    logger.info(
        f"GitHub webhook: event={x_github_event}, action={action}"
        f" (effective={effective_action}), repo={repo_full_name}"
    )

    # Find all bot configs that match this repo
    async with AsyncSessionLocal() as session:
        github_repo = BotGithubRepository(session)
        all_configs = await github_repo.get_all_configs()

    matching_configs = []
    for cfg in all_configs:
        cfg_full = f"{cfg.get('repo_owner', '')}/{cfg.get('repo_name', '')}"
        cfg_events = cfg.get("events", [])
        if isinstance(cfg_events, str):
            try:
                cfg_events = json.loads(cfg_events)
            except (json.JSONDecodeError, TypeError):
                cfg_events = []
        if cfg_full == repo_full_name and effective_action in cfg_events:
            # Verify signature if webhook_secret is configured
            secret = cfg.get("webhook_secret")
            if secret and x_hub_signature_256:
                if not await _verify_signature(payload, x_hub_signature_256, secret):
                    logger.warning(f"Invalid signature for bot_id={cfg['bot_id']}")
                    continue
            matching_configs.append(cfg)

    if not matching_configs:
        return {"status": "no_matching_config", "repo": repo_full_name, "action": action}

    results = []
    for cfg in matching_configs:
        bot_id = cfg["bot_id"]
        result = {"bot_id": bot_id, "comment": False, "broadcast": 0}

        # 1. Post AI comment on PR
        if cfg.get("comment_enabled") and cfg.get("github_token"):
            prompt = cfg.get("comment_prompt") or (
                "Напиши краткий информативный комментарий к Pull Request на русском."
            )
            comment = await _generate_comment(prompt, pr_data)
            if comment:
                posted = await _post_github_comment(
                    cfg["repo_owner"],
                    cfg["repo_name"],
                    pr_data["number"],
                    comment,
                    cfg["github_token"],
                )
                result["comment"] = posted

        # 2. Broadcast ## NEWS to Telegram subscribers + mobile push (on merged PRs)
        if cfg.get("broadcast_enabled") and pr_data.get("merged"):
            news_text = _parse_news_from_pr(pr_data.get("body") or "")
            if news_text:
                count = await _broadcast_to_subscribers(bot_id, news_text)
                result["broadcast"] = count
                # Mobile push (best-effort, non-blocking on failure)
                try:
                    from modules.channels.mobile.push_service import fcm_push_service

                    push_title = "AI-Секретарь"
                    # Preserve first line as title if looks like a heading
                    lines = news_text.strip().split("\n", 1)
                    push_body = news_text if len(lines) == 1 else lines[1].strip()
                    # FCM body is limited — truncate safely
                    if len(push_body) > 240:
                        push_body = push_body[:237] + "..."
                    mobile_count = await fcm_push_service.send_to_all(
                        title=push_title,
                        body=push_body,
                        data={"type": "news", "pr": str(pr_data.get("number", ""))},
                    )
                    result["mobile_push"] = mobile_count
                except Exception as e:
                    logger.error(f"Mobile push broadcast failed: {e}")
            else:
                logger.info(f"PR #{pr_data.get('number')} has no NEWS section, skip broadcast")

        results.append(result)

    return {"status": "processed", "results": results}


@router.post("/webhooks/github/release")
async def handle_github_release_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
):
    """Handle release events: push 'new version available' to mobile devices when
    a release tagged `mobile-v*` is published.

    Register this webhook in GitHub repo settings with event = 'Releases'.
    Signature verification uses GITHUB_WEBHOOK_SECRET env.
    """
    payload = await request.body()

    if x_github_event != "release":
        return {"status": "ignored", "event": x_github_event}

    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if secret and x_hub_signature_256:
        if not await _verify_signature(payload, x_hub_signature_256, secret):
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        event_data = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if event_data.get("action") != "published":
        return {"status": "ignored", "action": event_data.get("action")}

    release = event_data.get("release", {})
    tag = release.get("tag_name", "")
    if not tag.startswith("mobile-v"):
        return {"status": "ignored", "tag": tag, "reason": "not a mobile release"}

    version = tag[len("mobile-v") :]
    notes = (release.get("body") or "").strip()
    html_url = release.get("html_url", "")

    # Find APK asset URL
    apk_url = ""
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        if name.endswith(".apk"):
            apk_url = asset.get("browser_download_url", "")
            break

    try:
        from modules.channels.mobile.push_service import fcm_push_service

        title = f"Доступна новая версия {version}"
        body = (notes.split("\n", 1)[0] if notes else "Нажмите для скачивания").strip() or (
            "Нажмите для скачивания"
        )
        if len(body) > 240:
            body = body[:237] + "..."
        count = await fcm_push_service.send_to_all(
            title=title,
            body=body,
            data={
                "type": "update",
                "version": version,
                "apk_url": apk_url or html_url,
                "link": "/settings",
            },
        )
        return {"status": "processed", "version": version, "delivered": count}
    except Exception as e:
        logger.error(f"Mobile release push failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
