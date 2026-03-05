# modules/admin/router_legal.py
"""Legal compliance router - privacy policy, terms, consents."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from auth_manager import User, require_permission
from db.database import AsyncSessionLocal
from db.models import CONSENT_TYPES
from db.repositories.consent import ConsentRepository


logger = logging.getLogger(__name__)


router = APIRouter(tags=["legal"])


# =============================================================================
# Request/Response Models
# =============================================================================


class ConsentRequest(BaseModel):
    """Request to grant or revoke consent."""

    user_id: str = Field(..., description="User identifier (telegram_id, session_id)")
    user_type: str = Field(..., description="User type: telegram, widget, admin")
    consent_type: str = Field(..., description="Type of consent")
    consent_version: str = Field("1.0", description="Version of the consent document")


class ConsentBulkRequest(BaseModel):
    """Request to grant multiple consents at once."""

    user_id: str
    user_type: str
    consent_types: List[str]
    consent_version: str = "1.0"


class DataDeletionRequest(BaseModel):
    """Request for GDPR data deletion.

    Two modes:
    - Admin user: set user_id (int) to delete by users.id
    - External contact: set provider + provider_uid to delete by channel identity
    """

    user_id: Optional[int] = Field(None, description="Internal user ID (admin users)")
    provider: Optional[str] = Field(None, description="Channel: telegram, whatsapp, widget")
    provider_uid: Optional[str] = Field(None, description="External user ID in channel")
    confirm: bool = Field(..., description="Must be true to confirm deletion")


# =============================================================================
# Public Endpoints - Privacy Policy & Terms
# =============================================================================


@router.get("/privacy-policy", response_class=HTMLResponse)
async def get_privacy_policy(lang: str = "ru"):
    """Get privacy policy page."""
    if lang == "en":
        content = PRIVACY_POLICY_EN
    else:
        content = PRIVACY_POLICY_RU
    return HTMLResponse(content=content)


@router.get("/terms", response_class=HTMLResponse)
async def get_terms_of_service(lang: str = "ru"):
    """Get terms of service page."""
    if lang == "en":
        content = TERMS_OF_SERVICE_EN
    else:
        content = TERMS_OF_SERVICE_RU
    return HTMLResponse(content=content)


@router.get("/consent-types")
async def get_consent_types():
    """Get available consent types."""
    return {"consent_types": CONSENT_TYPES}


# =============================================================================
# Consent Management Endpoints
# =============================================================================


@router.get("/admin/legal/consents/{user_id}")
async def admin_get_user_consents(
    user_id: str,
    user: User = Depends(require_permission("settings", "manage")),
):
    """Get all consents for a user."""
    async with AsyncSessionLocal() as session:
        repo = ConsentRepository(session)
        consents = await repo.get_user_consents(user_id)
        return {"consents": consents, "user_id": user_id}


@router.post("/legal/consents/grant")
async def grant_consent(
    request: ConsentRequest,
    req: Request,
):
    """Grant a consent (public endpoint for widgets/bots)."""
    if request.consent_type not in CONSENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid consent_type. Must be one of: {list(CONSENT_TYPES.keys())}",
        )

    # Get IP and User-Agent from request
    ip_address = req.client.host if req.client else None
    forwarded = req.headers.get("X-Forwarded-For")
    if forwarded:
        ip_address = forwarded.split(",")[0].strip()
    user_agent = req.headers.get("User-Agent", "")[:500]

    async with AsyncSessionLocal() as session:
        repo = ConsentRepository(session)
        consent = await repo.grant_consent(
            user_id=request.user_id,
            user_type=request.user_type,
            consent_type=request.consent_type,
            consent_version=request.consent_version,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await session.commit()
        return {"consent": consent}


@router.post("/legal/consents/grant-bulk")
async def grant_bulk_consents(
    request: ConsentBulkRequest,
    req: Request,
):
    """Grant multiple consents at once."""
    invalid_types = [ct for ct in request.consent_types if ct not in CONSENT_TYPES]
    if invalid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid consent types: {invalid_types}",
        )

    ip_address = req.client.host if req.client else None
    forwarded = req.headers.get("X-Forwarded-For")
    if forwarded:
        ip_address = forwarded.split(",")[0].strip()
    user_agent = req.headers.get("User-Agent", "")[:500]

    async with AsyncSessionLocal() as session:
        repo = ConsentRepository(session)
        granted = []
        for consent_type in request.consent_types:
            consent = await repo.grant_consent(
                user_id=request.user_id,
                user_type=request.user_type,
                consent_type=consent_type,
                consent_version=request.consent_version,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            granted.append(consent)
        await session.commit()
        return {"consents": granted}


@router.post("/legal/consents/grant-required")
async def grant_required_consents(
    request: ConsentRequest,
    req: Request,
):
    """Grant all required consents at once."""
    ip_address = req.client.host if req.client else None
    forwarded = req.headers.get("X-Forwarded-For")
    if forwarded:
        ip_address = forwarded.split(",")[0].strip()
    user_agent = req.headers.get("User-Agent", "")[:500]

    async with AsyncSessionLocal() as session:
        repo = ConsentRepository(session)
        granted = await repo.grant_all_required(
            user_id=request.user_id,
            user_type=request.user_type,
            consent_version=request.consent_version,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await session.commit()
        return {"consents": granted}


@router.post("/admin/legal/consents/revoke")
async def admin_revoke_consent(
    user_id: str,
    consent_type: str,
    user: User = Depends(require_permission("settings", "manage")),
):
    """Revoke a consent (admin only)."""
    if consent_type not in CONSENT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid consent_type")

    async with AsyncSessionLocal() as session:
        repo = ConsentRepository(session)
        consent = await repo.revoke_consent(user_id, consent_type)
        await session.commit()
        if not consent:
            raise HTTPException(status_code=404, detail="Consent not found")
        return {"consent": consent}


@router.get("/admin/legal/consents/check/{user_id}")
async def admin_check_consents(
    user_id: str,
    user: User = Depends(require_permission("settings", "view")),
):
    """Check if user has granted all required consents (admin only)."""
    async with AsyncSessionLocal() as session:
        repo = ConsentRepository(session)
        result = await repo.check_required_consents(user_id)
        return result


@router.get("/admin/legal/stats")
async def admin_get_consent_stats(user: User = Depends(require_permission("settings", "manage"))):
    """Get consent statistics."""
    async with AsyncSessionLocal() as session:
        repo = ConsentRepository(session)
        stats = await repo.get_consent_stats()
        return {"stats": stats}


# =============================================================================
# GDPR Data Deletion
# =============================================================================


@router.post("/admin/legal/gdpr/delete")
async def admin_gdpr_delete_data(
    request: DataDeletionRequest,
    user: User = Depends(require_permission("settings", "manage")),
):
    """Delete all user data (GDPR right to erasure).

    Two modes:
    - Admin user: {"user_id": 5, "confirm": true}
    - External contact: {"provider": "telegram", "provider_uid": "123456", "confirm": true}

    Cascade-deletes PII data, anonymizes audit/payment logs.
    """
    if not request.confirm:
        raise HTTPException(
            status_code=400,
            detail="Must confirm deletion by setting confirm=true",
        )

    from app.services.gdpr_service import delete_admin_user_data, delete_contact_data
    from modules.monitoring.service import audit_service

    if request.user_id is not None:
        # Admin user deletion
        if request.user_id == user.id:
            raise HTTPException(status_code=400, detail="Cannot delete own account")

        await audit_service.log(
            action="gdpr_delete",
            resource="user",
            resource_id=str(request.user_id),
            user_id=user.username,
            details=f"GDPR cascade delete for admin user {request.user_id}",
        )

        async with AsyncSessionLocal() as session:
            report = await delete_admin_user_data(session, request.user_id)

        logger.info(
            "GDPR delete admin user %d by %s: %s",
            request.user_id,
            user.username,
            report,
        )
        return {
            "status": "deleted",
            "mode": "admin_user",
            "user_id": request.user_id,
            "report": report,
        }

    elif request.provider and request.provider_uid:
        # External contact deletion
        valid_providers = ("telegram", "whatsapp", "widget")
        if request.provider not in valid_providers:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid provider. Must be one of: {valid_providers}",
            )

        await audit_service.log(
            action="gdpr_delete",
            resource="contact",
            resource_id=f"{request.provider}:{request.provider_uid}",
            user_id=user.username,
            details=f"GDPR cascade delete for {request.provider} contact {request.provider_uid}",
        )

        async with AsyncSessionLocal() as session:
            report = await delete_contact_data(session, request.provider, request.provider_uid)

        logger.info(
            "GDPR delete contact %s:%s by %s: %s",
            request.provider,
            request.provider_uid,
            user.username,
            report,
        )
        return {
            "status": "deleted",
            "mode": "contact",
            "provider": request.provider,
            "provider_uid": request.provider_uid,
            "report": report,
        }

    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either user_id (admin user) or provider+provider_uid (external contact)",
        )


# =============================================================================
# Privacy Policy & Terms Content
# =============================================================================

PRIVACY_POLICY_RU = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Политика конфиденциальности - AI Secretary</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; }
        h1 { color: #1a1a1a; }
        h2 { color: #333; margin-top: 30px; }
        p { color: #444; }
        ul { color: #444; }
        .date { color: #666; font-size: 0.9em; }
    </style>
</head>
<body>
    <h1>Политика конфиденциальности</h1>
    <p class="date">Последнее обновление: февраль 2026</p>

    <h2>1. Общие положения</h2>
    <p>Настоящая Политика конфиденциальности описывает, как AI Secretary System
    собирает, использует и защищает информацию пользователей.</p>

    <h2>2. Какие данные мы собираем</h2>
    <ul>
        <li><strong>Текстовые сообщения:</strong> содержание переписки с ассистентом</li>
        <li><strong>Голосовые данные:</strong> записи голоса для синтеза речи (TTS) и распознавания (STT)</li>
        <li><strong>Идентификаторы:</strong> Telegram ID, IP-адрес, User-Agent</li>
        <li><strong>Технические данные:</strong> логи использования сервисов</li>
    </ul>

    <h2>3. Как мы используем данные</h2>
    <ul>
        <li>Предоставление услуг AI-ассистента</li>
        <li>Улучшение качества распознавания и синтеза речи</li>
        <li>Обучение моделей машинного обучения (с вашего согласия)</li>
        <li>Техническая поддержка и диагностика</li>
    </ul>

    <h2>4. Хранение данных</h2>
    <p>Данные хранятся на серверах владельца системы. Срок хранения:</p>
    <ul>
        <li>История чатов: до удаления пользователем или 1 год неактивности</li>
        <li>Голосовые записи: до 90 дней или до отзыва согласия</li>
        <li>Логи: до 90 дней</li>
    </ul>

    <h2>5. Защита данных</h2>
    <p>Мы применяем технические меры защиты:</p>
    <ul>
        <li>Шифрование данных при передаче (HTTPS/TLS)</li>
        <li>Ограничение доступа к данным</li>
        <li>Регулярное резервное копирование</li>
    </ul>

    <h2>6. Ваши права</h2>
    <p>В соответствии с законодательством РФ и GDPR вы имеете право:</p>
    <ul>
        <li>Получить копию своих данных</li>
        <li>Исправить неточные данные</li>
        <li>Удалить свои данные ("право быть забытым")</li>
        <li>Отозвать согласие на обработку</li>
        <li>Ограничить обработку данных</li>
    </ul>

    <h2>7. Согласия</h2>
    <p>Перед использованием сервиса вы даёте согласие на:</p>
    <ul>
        <li>Обработку персональных данных</li>
        <li>Запись и обработку голоса (опционально)</li>
        <li>Запись телефонных разговоров (для телефонии)</li>
    </ul>
    <p>Вы можете отозвать согласие в любой момент через настройки или обратившись к администратору.</p>

    <h2>8. Контакты</h2>
    <p>По вопросам обработки данных обращайтесь к администратору системы.</p>
</body>
</html>
"""

PRIVACY_POLICY_EN = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Privacy Policy - AI Secretary</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; }
        h1 { color: #1a1a1a; }
        h2 { color: #333; margin-top: 30px; }
        p { color: #444; }
        ul { color: #444; }
        .date { color: #666; font-size: 0.9em; }
    </style>
</head>
<body>
    <h1>Privacy Policy</h1>
    <p class="date">Last updated: February 2026</p>

    <h2>1. Introduction</h2>
    <p>This Privacy Policy describes how AI Secretary System collects, uses,
    and protects user information.</p>

    <h2>2. Data We Collect</h2>
    <ul>
        <li><strong>Text messages:</strong> conversation content with the assistant</li>
        <li><strong>Voice data:</strong> voice recordings for TTS and STT</li>
        <li><strong>Identifiers:</strong> Telegram ID, IP address, User-Agent</li>
        <li><strong>Technical data:</strong> service usage logs</li>
    </ul>

    <h2>3. How We Use Data</h2>
    <ul>
        <li>Providing AI assistant services</li>
        <li>Improving speech recognition and synthesis quality</li>
        <li>Training machine learning models (with your consent)</li>
        <li>Technical support and diagnostics</li>
    </ul>

    <h2>4. Data Retention</h2>
    <p>Data is stored on the system owner's servers. Retention periods:</p>
    <ul>
        <li>Chat history: until deleted by user or 1 year of inactivity</li>
        <li>Voice recordings: up to 90 days or until consent revoked</li>
        <li>Logs: up to 90 days</li>
    </ul>

    <h2>5. Data Protection</h2>
    <p>We apply technical protection measures:</p>
    <ul>
        <li>Data encryption in transit (HTTPS/TLS)</li>
        <li>Access restrictions</li>
        <li>Regular backups</li>
    </ul>

    <h2>6. Your Rights</h2>
    <p>Under GDPR and applicable laws, you have the right to:</p>
    <ul>
        <li>Access your data</li>
        <li>Rectify inaccurate data</li>
        <li>Erase your data ("right to be forgotten")</li>
        <li>Withdraw consent</li>
        <li>Restrict processing</li>
    </ul>

    <h2>7. Consents</h2>
    <p>Before using the service, you consent to:</p>
    <ul>
        <li>Personal data processing</li>
        <li>Voice recording and processing (optional)</li>
        <li>Phone call recording (for telephony)</li>
    </ul>
    <p>You can withdraw consent at any time through settings or by contacting the administrator.</p>

    <h2>8. Contact</h2>
    <p>For data processing inquiries, contact the system administrator.</p>
</body>
</html>
"""

TERMS_OF_SERVICE_RU = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Условия использования - AI Secretary</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; }
        h1 { color: #1a1a1a; }
        h2 { color: #333; margin-top: 30px; }
        p { color: #444; }
        ul { color: #444; }
        .date { color: #666; font-size: 0.9em; }
    </style>
</head>
<body>
    <h1>Условия использования</h1>
    <p class="date">Последнее обновление: февраль 2026</p>

    <h2>1. Принятие условий</h2>
    <p>Используя AI Secretary System, вы соглашаетесь с настоящими условиями.
    Если вы не согласны, прекратите использование сервиса.</p>

    <h2>2. Описание сервиса</h2>
    <p>AI Secretary — система виртуального секретаря с поддержкой:</p>
    <ul>
        <li>Текстового и голосового общения</li>
        <li>Синтеза речи (TTS)</li>
        <li>Распознавания речи (STT)</li>
        <li>Интеграции с Telegram и веб-сайтами</li>
    </ul>

    <h2>3. Правила использования</h2>
    <p>Запрещается:</p>
    <ul>
        <li>Использовать сервис для незаконной деятельности</li>
        <li>Передавать вредоносный код</li>
        <li>Пытаться получить несанкционированный доступ</li>
        <li>Использовать голосовое клонирование для обмана</li>
        <li>Нарушать права третьих лиц</li>
    </ul>

    <h2>4. Интеллектуальная собственность</h2>
    <p>Программное обеспечение предоставляется по лицензии MIT.
    Пользовательский контент остаётся собственностью пользователей.</p>

    <h2>5. Ограничение ответственности</h2>
    <p>Сервис предоставляется "как есть". Мы не гарантируем:</p>
    <ul>
        <li>Бесперебойную работу</li>
        <li>Точность ответов AI</li>
        <li>Сохранность данных при сбоях</li>
    </ul>

    <h2>6. Изменения условий</h2>
    <p>Мы можем изменять условия. При существенных изменениях
    пользователи будут уведомлены.</p>

    <h2>7. Применимое право</h2>
    <p>Настоящие условия регулируются законодательством Российской Федерации.</p>
</body>
</html>
"""

TERMS_OF_SERVICE_EN = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Terms of Service - AI Secretary</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; }
        h1 { color: #1a1a1a; }
        h2 { color: #333; margin-top: 30px; }
        p { color: #444; }
        ul { color: #444; }
        .date { color: #666; font-size: 0.9em; }
    </style>
</head>
<body>
    <h1>Terms of Service</h1>
    <p class="date">Last updated: February 2026</p>

    <h2>1. Acceptance of Terms</h2>
    <p>By using AI Secretary System, you agree to these terms.
    If you disagree, please stop using the service.</p>

    <h2>2. Service Description</h2>
    <p>AI Secretary is a virtual secretary system supporting:</p>
    <ul>
        <li>Text and voice communication</li>
        <li>Text-to-speech (TTS)</li>
        <li>Speech-to-text (STT)</li>
        <li>Telegram and website integrations</li>
    </ul>

    <h2>3. Usage Rules</h2>
    <p>Prohibited:</p>
    <ul>
        <li>Using the service for illegal activities</li>
        <li>Transmitting malicious code</li>
        <li>Attempting unauthorized access</li>
        <li>Using voice cloning for deception</li>
        <li>Violating third-party rights</li>
    </ul>

    <h2>4. Intellectual Property</h2>
    <p>The software is provided under the MIT license.
    User content remains the property of users.</p>

    <h2>5. Limitation of Liability</h2>
    <p>The service is provided "as is". We do not guarantee:</p>
    <ul>
        <li>Uninterrupted operation</li>
        <li>AI response accuracy</li>
        <li>Data preservation during failures</li>
    </ul>

    <h2>6. Changes to Terms</h2>
    <p>We may change these terms. Users will be notified of significant changes.</p>

    <h2>7. Governing Law</h2>
    <p>These terms are governed by the laws of the Russian Federation.</p>
</body>
</html>
"""
