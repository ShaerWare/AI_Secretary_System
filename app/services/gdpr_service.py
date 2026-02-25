"""GDPR data deletion service — cascade delete + anonymization."""

import logging
from typing import Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)

GDPR_ANON = "gdpr-deleted"
GDPR_IP = "0.0.0.0"


async def delete_admin_user_data(session: AsyncSession, user_id: int) -> Dict[str, int]:
    """Delete all data for an admin user (users.id).

    - DELETE: sessions, chats, claude code sessions, consents
    - SET NULL: resource ownership (bots, widgets, providers, kanban tasks)
    - ANONYMIZE: audit_log, usage_log, payment_log
    """
    report: Dict[str, int] = {}
    uid = str(user_id)

    # 1. User sessions (login tokens)
    r = await session.execute(
        text("DELETE FROM user_sessions WHERE user_id = :uid"), {"uid": user_id}
    )
    report["user_sessions"] = r.rowcount

    # 2. Chat sessions (owner_id) — messages cascade via FK
    r = await session.execute(
        text("DELETE FROM chat_sessions WHERE owner_id = :uid"), {"uid": user_id}
    )
    report["chat_sessions"] = r.rowcount

    # 3. Claude Code sessions
    r = await session.execute(
        text("DELETE FROM claude_code_sessions WHERE owner_id = :uid"), {"uid": user_id}
    )
    report["claude_code_sessions"] = r.rowcount

    # 4. User consents (user_id is string — admin users stored as str(id))
    r = await session.execute(text("DELETE FROM user_consents WHERE user_id = :uid"), {"uid": uid})
    report["user_consents"] = r.rowcount

    # 5. SET NULL on resource ownership (keep configs, remove owner)
    for table in [
        "bot_instances",
        "widget_instances",
        "whatsapp_instances",
        "cloud_llm_providers",
        "tts_presets",
        "knowledge_documents",
    ]:
        r = await session.execute(
            text(f"UPDATE {table} SET owner_id = NULL WHERE owner_id = :uid"),
            {"uid": user_id},
        )
        if r.rowcount:
            report[f"{table}_nullified"] = r.rowcount

    # 6. Kanban tasks — SET NULL owner_id, keep created_by for audit
    r = await session.execute(
        text("UPDATE kanban_tasks SET owner_id = NULL WHERE owner_id = :uid"),
        {"uid": user_id},
    )
    if r.rowcount:
        report["kanban_tasks_nullified"] = r.rowcount

    # 7. Workspace invites — SET NULL created_by / used_by
    r = await session.execute(
        text("UPDATE workspace_invites SET created_by = NULL WHERE created_by = :uid"),
        {"uid": user_id},
    )
    if r.rowcount:
        report["workspace_invites_created_nullified"] = r.rowcount
    r = await session.execute(
        text("UPDATE workspace_invites SET used_by = NULL WHERE used_by = :uid"),
        {"uid": user_id},
    )
    if r.rowcount:
        report["workspace_invites_used_nullified"] = r.rowcount

    # 8. Anonymize audit_log (keep records, remove PII)
    r = await session.execute(
        text("UPDATE audit_log SET user_id = :anon, user_ip = :ip WHERE user_id = :uid"),
        {"anon": GDPR_ANON, "ip": GDPR_IP, "uid": uid},
    )
    if r.rowcount:
        report["audit_log_anonymized"] = r.rowcount

    # Also anonymize by username (audit_log stores username, not int id)
    # Fetch username first
    row = await session.execute(
        text("SELECT username FROM users WHERE id = :uid"), {"uid": user_id}
    )
    username_row = row.first()
    if username_row and username_row[0]:
        username = username_row[0]
        r = await session.execute(
            text("UPDATE audit_log SET user_id = :anon, user_ip = :ip WHERE user_id = :uname"),
            {"anon": GDPR_ANON, "ip": GDPR_IP, "uname": username},
        )
        if r.rowcount:
            report["audit_log_anonymized"] = report.get("audit_log_anonymized", 0) + r.rowcount

    # 9. Anonymize usage_log
    r = await session.execute(
        text("UPDATE usage_log SET source_id = :anon WHERE source_id = :uid"),
        {"anon": GDPR_ANON, "uid": uid},
    )
    if r.rowcount:
        report["usage_log_anonymized"] = r.rowcount

    await session.commit()
    return report


async def delete_contact_data(
    session: AsyncSession, provider: str, provider_uid: str
) -> Dict[str, int]:
    """Delete all data for an external contact (Telegram/WhatsApp/Widget).

    Identified by (provider, provider_uid). Telegram user_id in bot tables
    is the Telegram chat_id (= provider_uid for telegram provider).

    - DELETE: bot profiles, subscribers, events, discovery, followups, sessions, consents
    - ANONYMIZE: payment_log, audit_log
    """
    report: Dict[str, int] = {}

    # Resolve the internal user.id from user_identities (if exists)
    row = await session.execute(
        text("SELECT user_id FROM user_identities WHERE provider = :p AND provider_uid = :uid"),
        {"p": provider, "uid": provider_uid},
    )
    identity_row = row.first()
    internal_user_id: Optional[int] = identity_row[0] if identity_row else None

    # For Telegram/WhatsApp, the bot tables use provider_uid as user_id (int)
    try:
        ext_user_id = int(provider_uid)
    except (ValueError, TypeError):
        ext_user_id = None

    # 1. Bot user profiles (HIGHLY SENSITIVE — quiz answers, discovery data)
    if ext_user_id is not None:
        r = await session.execute(
            text("DELETE FROM bot_user_profiles WHERE user_id = :uid"),
            {"uid": ext_user_id},
        )
        report["bot_user_profiles"] = r.rowcount

        # 2. Bot subscribers
        r = await session.execute(
            text("DELETE FROM bot_subscribers WHERE user_id = :uid"),
            {"uid": ext_user_id},
        )
        report["bot_subscribers"] = r.rowcount

        # 3. Bot discovery responses
        r = await session.execute(
            text("DELETE FROM bot_discovery_responses WHERE user_id = :uid"),
            {"uid": ext_user_id},
        )
        report["bot_discovery_responses"] = r.rowcount

        # 4. Bot followup queue
        r = await session.execute(
            text("DELETE FROM bot_followup_queue WHERE user_id = :uid"),
            {"uid": ext_user_id},
        )
        report["bot_followup_queue"] = r.rowcount

        # 5. Bot events
        r = await session.execute(
            text("DELETE FROM bot_events WHERE user_id = :uid"),
            {"uid": ext_user_id},
        )
        report["bot_events"] = r.rowcount

        # 6. Telegram sessions — also deletes linked chat_sessions via cascade
        r = await session.execute(
            text("DELETE FROM telegram_sessions WHERE user_id = :uid"),
            {"uid": ext_user_id},
        )
        report["telegram_sessions"] = r.rowcount

        # 7. Anonymize payment_log (keep financial records, remove PII)
        r = await session.execute(
            text("UPDATE payment_log SET username = :anon WHERE user_id = :uid"),
            {"anon": GDPR_ANON, "uid": ext_user_id},
        )
        if r.rowcount:
            report["payment_log_anonymized"] = r.rowcount

    # 8. User consents (user_id format varies: "telegram:123", plain "123", etc.)
    consent_ids = [provider_uid, f"{provider}:{provider_uid}"]
    if ext_user_id is not None:
        consent_ids.append(str(ext_user_id))
    for cid in consent_ids:
        r = await session.execute(
            text("DELETE FROM user_consents WHERE user_id = :uid"), {"uid": cid}
        )
        if r.rowcount:
            report["user_consents"] = report.get("user_consents", 0) + r.rowcount

    # 9. Chat sessions owned by this contact (via internal user_id)
    if internal_user_id:
        r = await session.execute(
            text("DELETE FROM chat_sessions WHERE owner_id = :uid"),
            {"uid": internal_user_id},
        )
        if r.rowcount:
            report["chat_sessions"] = r.rowcount

        # User sessions
        r = await session.execute(
            text("DELETE FROM user_sessions WHERE user_id = :uid"),
            {"uid": internal_user_id},
        )
        if r.rowcount:
            report["user_sessions"] = r.rowcount

        # Delete user_identities record
        r = await session.execute(
            text("DELETE FROM user_identities WHERE provider = :p AND provider_uid = :uid"),
            {"p": provider, "uid": provider_uid},
        )
        report["user_identities"] = r.rowcount

        # Delete the contact user record itself (role='contact', no login)
        r = await session.execute(
            text("DELETE FROM users WHERE id = :uid AND role = 'contact'"),
            {"uid": internal_user_id},
        )
        if r.rowcount:
            report["users"] = r.rowcount

    # 10. Anonymize audit_log entries for this contact
    for uid_variant in [provider_uid, f"{provider}:{provider_uid}"]:
        r = await session.execute(
            text("UPDATE audit_log SET user_id = :anon, user_ip = :ip WHERE user_id = :uid"),
            {"anon": GDPR_ANON, "ip": GDPR_IP, "uid": uid_variant},
        )
        if r.rowcount:
            report["audit_log_anonymized"] = report.get("audit_log_anonymized", 0) + r.rowcount

    await session.commit()
    return report
