"""GitHub news service — fetches merged PRs and parses NEWS section."""

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import httpx


if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

GITHUB_REPO = "ShaerWare/AI_Secretary_System"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}"


def _github_headers() -> dict[str, str]:
    """Build GitHub API headers, including auth token if available."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AI-Secretary-Bot",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# Regex to extract ## NEWS section from PR body
NEWS_SECTION_PATTERN = re.compile(
    r"##\s*(?:\U0001f4e2\s*)?NEWS\s*\n(.*?)(?=\n##|\Z)", re.IGNORECASE | re.DOTALL
)


async def fetch_merged_prs(
    days: int = 7,
    limit: int = 20,
    repo: str | None = None,
) -> list[dict]:
    """Fetch recently merged pull requests from GitHub.

    Args:
        days: Look back this many days
        limit: Maximum number of PRs to return
        repo: GitHub repo in 'owner/repo' format (default: GITHUB_REPO)

    Returns:
        List of PR data dicts
    """
    repo = repo or GITHUB_REPO
    since = datetime.utcnow() - timedelta(days=days)

    url = f"https://api.github.com/repos/{repo}/pulls"
    params = {
        "state": "closed",
        "sort": "updated",
        "direction": "desc",
        "per_page": 100,  # Fetch more to filter merged ones
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, params=params, headers=_github_headers())
            response.raise_for_status()
            all_prs = response.json()

            # Filter merged PRs within the date range
            merged_prs = []
            for pr in all_prs:
                if not pr.get("merged_at"):
                    continue

                merged_at = datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))
                if merged_at.replace(tzinfo=None) < since:
                    continue

                merged_prs.append(
                    {
                        "number": pr["number"],
                        "title": pr["title"],
                        "body": pr.get("body") or "",
                        "merged_at": pr["merged_at"],
                        "author": pr["user"]["login"],
                        "labels": [label["name"] for label in pr.get("labels", [])],
                        "html_url": pr["html_url"],
                    }
                )

                if len(merged_prs) >= limit:
                    break

            return merged_prs

    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch PRs from GitHub: {e}")
        return []


def _clean_news_text(text: str) -> str:
    """Remove auto-generated footers and add demo link."""
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        # Skip Claude Code / bot-generated footers
        if "Generated with" in line and "Claude" in line:
            continue
        if "Co-Authored-By:" in line:
            continue
        cleaned.append(line)
    # Strip trailing empty lines
    result = "\n".join(cleaned).rstrip()
    # Add demo link if not already present
    if "ai-sekretar24.ru" not in result:
        result += "\n\n\U0001f5a5 \u0414\u0435\u043c\u043e: https://ai-sekretar24.ru"
    return result


def parse_news_section(pr_body: str) -> str | None:
    """Parse ## NEWS section from PR body.

    Args:
        pr_body: PR body text (markdown)

    Returns:
        Extracted news text or None if no NEWS section found
    """
    if not pr_body:
        return None

    match = NEWS_SECTION_PATTERN.search(pr_body)
    if match:
        news_text = _clean_news_text(match.group(1).strip())
        if news_text:
            return news_text

    return None


async def fetch_recent_commits(
    repo: str,
    days: int = 7,
    limit: int = 20,
) -> list[dict]:
    """Fetch recent commits from a GitHub repository.

    Args:
        repo: GitHub repo in 'owner/repo' format
        days: Look back this many days
        limit: Maximum number of commits to return

    Returns:
        List of commit data dicts
    """
    since = datetime.utcnow() - timedelta(days=days)
    since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    url = f"https://api.github.com/repos/{repo}/commits"
    params = {
        "since": since_str,
        "per_page": limit,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, params=params, headers=_github_headers())
            response.raise_for_status()
            raw_commits = response.json()

            commits = []
            for c in raw_commits:
                commits.append(
                    {
                        "sha": c["sha"],
                        "message": c["commit"]["message"],
                        "author": c["commit"]["author"]["name"],
                        "date": c["commit"]["author"]["date"],
                        "html_url": c["html_url"],
                        "repo": repo,
                    }
                )

            return commits

    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch commits from GitHub ({repo}): {e}")
        return []


async def generate_commit_news_post(commit: dict) -> str | None:
    """Extract news post from a commit message's ## NEWS section.

    Args:
        commit: Commit data dict from fetch_recent_commits

    Returns:
        News post text or None if no NEWS section
    """
    message = commit.get("message", "")
    news_text = parse_news_section(message)

    if news_text:
        if "@shaerware" not in news_text.lower():
            news_text += "\n\n\U0001f517 @shaerware"
        return news_text

    logger.debug(f"Commit {commit.get('sha', '')[:8]} has no NEWS section, skipping")
    return None


async def generate_news_post(pr: dict) -> str | None:
    """Extract news post from PR body's ## NEWS section.

    Args:
        pr: PR data dict from fetch_merged_prs

    Returns:
        News post text or None if no NEWS section
    """
    pr_body = pr.get("body", "")
    news_text = parse_news_section(pr_body)

    if news_text:
        # Add author tag if not present
        if "@shaerware" not in news_text.lower():
            news_text += "\n\n\U0001f517 @shaerware"
        return news_text

    # No NEWS section — return None (PR won't be shown as news)
    logger.debug(f"PR #{pr.get('number')} has no NEWS section, skipping")
    return None


async def get_latest_news(days: int = 7, limit: int = 3) -> list[dict]:
    """Get latest news with parsed posts.

    Args:
        days: Look back this many days
        limit: Maximum number of news items

    Returns:
        List of dicts with 'pr' and 'post' keys (only PRs with NEWS section)
    """
    prs = await fetch_merged_prs(days=days, limit=limit * 2)  # Fetch more to filter

    news = []
    for pr in prs:
        post = await generate_news_post(pr)
        if post:  # Only include PRs with NEWS section
            news.append(
                {
                    "pr": pr,
                    "post": post,
                }
            )
            if len(news) >= limit:
                break

    return news


async def format_news_digest(days: int = 7) -> str:
    """Format a news digest message.

    Args:
        days: Look back this many days

    Returns:
        Formatted digest message
    """
    prs = await fetch_merged_prs(days=days, limit=5)

    if not prs:
        return (
            "\U0001f4f0 **\u041d\u043e\u0432\u043e\u0441\u0442\u0438 AI Secretary**\n\n"
            f"\u0417\u0430 \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 {days} \u0434\u043d\u0435\u0439 \u043d\u043e\u0432\u044b\u0445 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0439 \u043d\u0435 \u0431\u044b\u043b\u043e.\n\n"
            "\u0421\u043b\u0435\u0434\u0438\u0442\u0435 \u0437\u0430 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f\u043c\u0438 \u0432 \u0440\u0435\u043f\u043e\u0437\u0438\u0442\u043e\u0440\u0438\u0438:\n"
            f"\U0001f517 https://github.com/{GITHUB_REPO}"
        )

    digest = f"\U0001f4f0 **\u041d\u043e\u0432\u043e\u0441\u0442\u0438 AI Secretary** (\u0437\u0430 {days} \u0434\u043d\u0435\u0439)\n\n"

    for i, pr in enumerate(prs, 1):
        merged_date = datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00")).strftime(
            "%d.%m"
        )

        digest += f"{i}. **{pr['title']}** ({merged_date})\n"

    digest += f"\n\U0001f517 https://github.com/{GITHUB_REPO}/pulls?q=is%3Apr+is%3Amerged"

    return digest


# ── Broadcast to subscribers ────────────────────────────────────


async def broadcast_news_to_subscribers(bot: "Bot", post_text: str) -> int:
    """Send news post to all subscribed users.

    Args:
        bot: Telegram bot instance
        post_text: Generated news post text

    Returns:
        Number of successfully sent messages
    """
    from ..sales.database import get_sales_db

    db = await get_sales_db()
    subscribers = await db.get_subscribed_users()

    if not subscribers:
        logger.info("No subscribers to broadcast to")
        return 0

    sent_count = 0
    for user_id in subscribers:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=post_text,
            )
            sent_count += 1
            # Small delay to avoid hitting rate limits
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.warning(f"Failed to send news to user {user_id}: {e}")

    logger.info(f"Broadcast sent to {sent_count}/{len(subscribers)} subscribers")
    return sent_count


async def check_and_broadcast_news(bot: "Bot", skip_initial: bool = True) -> None:
    """Check for new PRs and broadcast to subscribers if any.

    This function:
    1. Fetches recent merged PRs from all configured repos
    2. Filters out already broadcast ones
    3. Generates posts for new PRs
    4. Sends to all subscribers

    Args:
        bot: Telegram bot instance
        skip_initial: If True and no broadcasts exist yet, mark all current PRs
                      as seen without sending (to avoid spam on first run)
    """
    from ..config import get_telegram_settings
    from ..sales.database import get_sales_db

    settings = get_telegram_settings()
    repos = settings.get_news_repos()

    logger.info("Checking for new PRs to broadcast from %s...", repos)

    try:
        db = await get_sales_db()

        for repo in repos:
            try:
                prs = await fetch_merged_prs(days=7, limit=10, repo=repo)

                if not prs:
                    logger.info("No recent PRs found in %s", repo)
                    continue

                # Filter to get only unbroadcast PRs
                pr_numbers = [pr["number"] for pr in prs]
                unbroadcast_numbers = await db.get_unbroadcast_pr_numbers(pr_numbers)

                if not unbroadcast_numbers:
                    logger.info("All recent PRs in %s already broadcast", repo)
                    continue

                # Check if this is truly first run (no broadcasts in DB at all).
                # Previous heuristic (all fetched PRs are new) caused false positives
                # when the bot was offline for weeks and old broadcast records fell out
                # of the current fetch window.
                if skip_initial and not await db.has_any_broadcasts():
                    logger.info(
                        "First run: marking %d existing PRs in %s as seen (no broadcast)",
                        len(pr_numbers),
                        repo,
                    )
                    for pr_num in pr_numbers:
                        await db.mark_pr_broadcast(pr_num, 0)
                    continue

                # Get PRs that need broadcasting
                new_prs = [pr for pr in prs if pr["number"] in unbroadcast_numbers]
                logger.info("Found %d new PRs in %s to broadcast", len(new_prs), repo)

                # Process each new PR
                for pr in new_prs:
                    try:
                        cached_post = await db.get_cached_news(pr["number"])

                        if cached_post:
                            post_text = cached_post
                        else:
                            logger.info(
                                "Parsing NEWS section for PR #%d (%s)",
                                pr["number"],
                                repo,
                            )
                            post_text = await generate_news_post(pr)

                            if post_text is None:
                                logger.info(
                                    "PR #%d has no NEWS section, skipping broadcast",
                                    pr["number"],
                                )
                                await db.mark_pr_broadcast(pr["number"], 0)
                                continue

                            await db.save_news_cache(pr["number"], pr["title"], post_text)

                        sent_count = await broadcast_news_to_subscribers(bot, post_text)
                        await db.mark_pr_broadcast(pr["number"], sent_count)
                        logger.info(
                            "PR #%d broadcast complete: %d recipients",
                            pr["number"],
                            sent_count,
                        )

                    except Exception as e:
                        logger.error("Failed to broadcast PR #%d: %s", pr["number"], e)

            except Exception as e:
                logger.error("Error processing PRs for %s: %s", repo, e)

    except Exception as e:
        logger.error("Error in check_and_broadcast_news: %s", e)


async def check_and_broadcast_commit_news(bot: "Bot", skip_initial: bool = True) -> None:
    """Check for new commits with NEWS sections and broadcast to subscribers.

    Args:
        bot: Telegram bot instance
        skip_initial: If True and no broadcasts exist yet, mark all current commits
                      as seen without sending (to avoid spam on first run)
    """
    from ..config import get_telegram_settings
    from ..sales.database import get_sales_db

    settings = get_telegram_settings()
    repos = settings.get_news_repos()

    if not repos:
        return

    logger.info("Checking for new commits to broadcast from %s...", repos)

    try:
        db = await get_sales_db()

        for repo in repos:
            try:
                commits = await fetch_recent_commits(repo, days=7, limit=10)

                if not commits:
                    logger.info("No recent commits found in %s", repo)
                    continue

                shas = [c["sha"] for c in commits]
                unbroadcast_shas = await db.get_unbroadcast_commit_shas(shas)

                if not unbroadcast_shas:
                    logger.info("All recent commits in %s already broadcast", repo)
                    continue

                # First run — mark all as seen without sending
                if skip_initial and not await db.has_any_commit_broadcasts():
                    logger.info(
                        "First run: marking %d existing commits in %s as seen (no broadcast)",
                        len(shas),
                        repo,
                    )
                    for sha in shas:
                        await db.mark_commit_broadcast(sha, 0)
                    continue

                new_commits = [c for c in commits if c["sha"] in unbroadcast_shas]
                logger.info("Found %d new commits in %s to broadcast", len(new_commits), repo)

                for commit in new_commits:
                    try:
                        cached_post = await db.get_cached_commit_news(commit["sha"])

                        if cached_post:
                            post_text = cached_post
                        else:
                            post_text = await generate_commit_news_post(commit)

                            if post_text is None:
                                await db.mark_commit_broadcast(commit["sha"], 0)
                                continue

                            await db.save_commit_news_cache(
                                commit["sha"], repo, commit["message"], post_text
                            )

                        sent_count = await broadcast_news_to_subscribers(bot, post_text)
                        await db.mark_commit_broadcast(commit["sha"], sent_count)
                        logger.info(
                            "Commit %s broadcast complete: %d recipients",
                            commit["sha"][:8],
                            sent_count,
                        )

                    except Exception as e:
                        logger.error("Failed to broadcast commit %s: %s", commit["sha"][:8], e)

            except Exception as e:
                logger.error("Error processing commits for %s: %s", repo, e)

    except Exception as e:
        logger.error("Error in check_and_broadcast_commit_news: %s", e)


async def news_broadcast_scheduler(bot: "Bot", interval_minutes: int = 30) -> None:
    """Background task that checks for news every N minutes.

    Args:
        bot: Telegram bot instance
        interval_minutes: Check interval in minutes (default: 30)
    """
    logger.info(f"News broadcast scheduler started (interval: {interval_minutes}m)")

    while True:
        try:
            await check_and_broadcast_news(bot)
        except Exception as e:
            logger.error(f"Scheduler error (PR news): {e}")

        # NOTE: commit-based broadcasting removed — all changes go through PRs
        # (main is protected), and PR body is the canonical source of ## NEWS.
        # Having both caused duplicate messages (same NEWS in commit + PR body).

        # Wait for next check
        await asyncio.sleep(interval_minutes * 60)
