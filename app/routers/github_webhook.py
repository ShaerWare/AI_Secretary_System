# app/routers/github_webhook.py
"""GitHub webhook handler — receives PR events, posts AI comments, broadcasts to subscribers."""

import hashlib
import hmac
import json
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Header, HTTPException, Request

from db.database import AsyncSessionLocal
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


async def _generate_news(system_prompt: str, pr_data: dict) -> Optional[str]:
    """Generate Telegram news message about PR."""
    return await _generate_comment(system_prompt, pr_data)


async def _broadcast_to_subscribers(
    bot_id: str,
    message: str,
    pr_url: str,
) -> int:
    """Send broadcast message to all subscribers. Returns count of user_ids retrieved."""
    async with AsyncSessionLocal() as session:
        sub_repo = BotSubscriberRepository(session)
        user_ids = await sub_repo.get_active_subscribers(bot_id)

    if not user_ids:
        logger.info(f"No subscribers for bot_id={bot_id}, skipping broadcast")
        return 0

    # Store broadcast task for the bot service to pick up
    # The actual sending happens via the Telegram bot process
    broadcast_data = {
        "bot_id": bot_id,
        "user_ids": user_ids,
        "message": message,
        "pr_url": pr_url,
    }

    # Write to a simple file-based queue that the bot service checks
    from datetime import datetime
    from pathlib import Path

    queue_dir = Path("data") / "broadcast_queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{bot_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"

    (queue_dir / filename).write_text(
        json.dumps(broadcast_data, ensure_ascii=False), encoding="utf-8"
    )

    logger.info(
        f"Queued broadcast for {len(user_ids)} subscribers: bot_id={bot_id}, file={filename}"
    )
    return len(user_ids)


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

    from db.integration import async_kanban_project_manager

    project = await async_kanban_project_manager.get_by_repo(owner, repo)
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

    logger.info(f"GitHub webhook: event={x_github_event}, action={action}, repo={repo_full_name}")

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
        if cfg_full == repo_full_name and action in cfg_events:
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

        # 2. Broadcast to Telegram subscribers
        if cfg.get("broadcast_enabled"):
            prompt = cfg.get("broadcast_prompt") or (
                "Сформируй короткую новость для Telegram-подписчиков о PR."
            )
            news = await _generate_news(prompt, pr_data)
            if news:
                pr_url = pr_data.get("html_url", "")
                count = await _broadcast_to_subscribers(bot_id, news, pr_url)
                result["broadcast"] = count

        results.append(result)

    return {"status": "processed", "results": results}
