"""Deliver an approved reply to the client from the orchestrator side.

The bot subprocess owns incoming traffic, but an approval happens in the admin
panel — long after the bot's request is gone. The orchestrator therefore builds
its own client from the instance row, the same way the linking flow does.
"""

import logging

from modules.channels.whatsapp.bridge import get_bridge_client, is_bridge_instance
from modules.channels.whatsapp.service import whatsapp_instance_service
from whatsapp_bot.services.whatsapp_client import WhatsAppClient, split_text


logger = logging.getLogger(__name__)


class DeliveryError(Exception):
    """The reply could not be handed to the channel."""


async def send_whatsapp(instance_id: str, target: str, text: str) -> None:
    instance = await whatsapp_instance_service.get_instance_with_token(instance_id)
    if not instance:
        raise DeliveryError(f"WhatsApp-инстанс {instance_id} не найден")

    if is_bridge_instance(instance):
        client = get_bridge_client(instance)
    else:
        if not instance.get("access_token"):
            raise DeliveryError("У инстанса нет access_token для Cloud API")
        client = WhatsAppClient(
            phone_number_id=instance.get("phone_number_id") or "",
            access_token=instance["access_token"],
            app_secret=instance.get("app_secret") or "",
        )
    try:
        for chunk in split_text(text):
            await client.send_text(to=target, text=chunk)
    except Exception as e:  # httpx errors, bridge 4xx/5xx
        raise DeliveryError(str(e) or type(e).__name__) from e
    finally:
        await client.close()


async def deliver(channel: str, instance_id: str, target: str, text: str) -> None:
    if channel == "whatsapp":
        await send_whatsapp(instance_id, target, text)
        return
    raise DeliveryError(f"Канал {channel} не поддерживает отправку из очереди")
