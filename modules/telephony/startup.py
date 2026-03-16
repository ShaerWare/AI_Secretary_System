"""Telephony domain startup: GSM service + voice calls."""

import logging


logger = logging.getLogger(__name__)


async def init_gsm_services(container, deployment_mode: str) -> None:
    """Initialize GSM telephony service and voice call handler (GPU/full mode only)."""
    if deployment_mode == "cloud":
        return

    try:
        from app.services.gsm_service import GSMService

        gsm_service = GSMService()
        await gsm_service.initialize()
        container.gsm_service = gsm_service
        mode = "mock" if gsm_service.mock_mode else "hardware"
        logger.info(f"✅ GSM service initialized ({mode} mode)")

        # Start voice call service (auto-answer with AI assistant)
        try:
            from app.services.gsm_voice_call import GSMVoiceCallService

            voice_call = GSMVoiceCallService(
                gsm_service=gsm_service,
                stt_service=getattr(container, "stt_service", None),
                tts_service=container.anna_voice_service or container.voice_service,
                piper_service=container.piper_service,
                tts_voice="xtts",  # or "piper" for CPU
                piper_voice="irina",  # irina / dmitri
                rag_mode="all",  # use all knowledge collections
            )
            await voice_call.start()
            container.gsm_voice_call = voice_call
            logger.info("✅ GSM Voice Call service started (auto-answer)")
        except Exception as vc_err:
            logger.warning(f"⚠️ GSM Voice Call not available: {vc_err}")
    except Exception as gsm_err:
        logger.warning(f"⚠️ GSM service not available: {gsm_err}")
