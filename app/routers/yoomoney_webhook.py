# app/routers/yoomoney_webhook.py
"""YooMoney HTTP notification webhook — receives payment confirmations."""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Request

from app.services.yoomoney_service import verify_notification
from db.database import AsyncSessionLocal
from db.integration import async_payment_manager
from db.repositories.bot_instance import BotInstanceRepository


logger = logging.getLogger(__name__)

router = APIRouter(tags=["yoomoney-webhook"])


@router.post("/webhooks/yoomoney")
async def handle_yoomoney_notification(request: Request):
    """Handle YooMoney HTTP payment notification.

    This endpoint is public (no JWT) — verified via SHA-1 signature.
    YooMoney sends POST with application/x-www-form-urlencoded data.
    """
    form = await request.form()
    data = dict(form)

    operation_id = data.get("operation_id", "")
    amount = data.get("amount", "0")
    label = data.get("label", "")
    sender = data.get("sender", "")
    withdraw_amount = data.get("withdraw_amount", amount)

    logger.info(
        f"YooMoney notification: operation_id={operation_id}, "
        f"amount={amount}, label={label}, sender={sender}"
    )

    # Parse label: "bot_id_product_id_user_id"
    parts = label.split("_", 2) if label else []
    bot_id = parts[0] if parts else ""
    rest = parts[1] if len(parts) > 1 else ""
    # rest = "product_id_user_id"
    rest_parts = rest.rsplit("_", 1) if rest else []
    product_id = rest_parts[0] if rest_parts else "unknown"
    user_id_str = parts[2] if len(parts) > 2 else "0"

    try:
        user_id = int(user_id_str)
    except ValueError:
        user_id = 0

    if not bot_id:
        logger.warning("YooMoney notification without label, cannot route")
        return {"status": "ok"}

    # Verify signature using notification_secret (= client_secret)
    async with AsyncSessionLocal() as session:
        bot_repo = BotInstanceRepository(session)
        instance = await bot_repo.get_by_id(bot_id)

    if not instance:
        logger.warning(f"YooMoney notification for unknown bot_id={bot_id}")
        return {"status": "ok"}

    notification_secret = None
    # Try to get client_secret for signature verification
    async with AsyncSessionLocal() as session:
        bot_repo = BotInstanceRepository(session)
        raw = await bot_repo.get_by_id(bot_id)
        if raw and hasattr(raw, "yoomoney_client_secret"):
            notification_secret = raw.yoomoney_client_secret

    if notification_secret:
        if not verify_notification(notification_secret, data):
            logger.warning(f"YooMoney invalid signature for bot_id={bot_id}")
            return {"status": "ok"}
        logger.info("YooMoney notification signature verified")
    else:
        logger.warning("No notification_secret configured, skipping verification")

    # Log payment (uses retry_on_busy via manager)
    await async_payment_manager.log_payment(
        bot_id=bot_id,
        user_id=user_id,
        username=sender,
        payment_type="yoomoney",
        product_id=product_id,
        amount=int(float(withdraw_amount) * 100),  # store in kopecks
        currency="RUB",
        telegram_payment_id="",
        provider_payment_id=operation_id,
    )

    # Notify bot about payment (write to file queue for bot to pick up)
    queue_dir = Path("data") / "payment_notifications"
    queue_dir.mkdir(parents=True, exist_ok=True)
    notification = {
        "bot_id": bot_id,
        "user_id": user_id,
        "amount": amount,
        "product_id": product_id,
        "operation_id": operation_id,
    }
    filename = f"{bot_id}_{operation_id}.json"
    (queue_dir / filename).write_text(
        json.dumps(notification, ensure_ascii=False), encoding="utf-8"
    )

    logger.info(
        f"YooMoney payment logged: bot_id={bot_id}, user_id={user_id}, "
        f"amount={amount}, operation_id={operation_id}"
    )

    return {"status": "ok"}
