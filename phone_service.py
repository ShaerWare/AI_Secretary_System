#!/usr/bin/env python3
"""
Сервис телефонной интеграции через Twilio
Принимает входящие звонки и обрабатывает их через оркестратор
"""

import logging
import os

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from twilio.rest import Client
from twilio.twiml.voice_response import Gather, VoiceResponse


load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Phone Service")

# Twilio настройки
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# URL оркестратора
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8000")

# Инициализация Twilio клиента
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    logger.info("✅ Twilio клиент инициализирован")
else:
    twilio_client = None
    logger.warning("⚠️  Twilio credentials не найдены. Только локальное тестирование.")


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "Phone Service (Twilio Integration)",
        "endpoints": {
            "incoming_call": "/incoming_call (POST)",
            "handle_speech": "/handle_speech (POST)",
            "status": "/status (GET)",
        },
    }


@app.get("/status")
async def status():
    """Статус телефонного сервиса"""
    return {
        "twilio_configured": twilio_client is not None,
        "orchestrator_url": ORCHESTRATOR_URL,
        "phone_number": TWILIO_PHONE_NUMBER if TWILIO_PHONE_NUMBER else "not_configured",
    }


@app.post("/incoming_call")
async def incoming_call(request: Request):
    """
    Обработка входящего звонка от Twilio
    Twilio отправляет POST запрос когда поступает звонок
    """
    form_data = await request.form()
    caller = form_data.get("From", "Unknown")
    call_sid = form_data.get("CallSid", "Unknown")

    logger.info(f"📞 Входящий звонок от {caller}, CallSid: {call_sid}")

    # Создаем TwiML ответ
    response = VoiceResponse()

    # Приветствие
    response.say(
        "Здравствуйте! Это виртуальный секретарь. Пожалуйста, говорите после сигнала.",
        language="ru-RU",
        voice="alice",  # Голос Яндекса для русского языка
    )

    # Записываем речь абонента
    response.record(
        action="/handle_speech",
        method="POST",
        max_length=30,  # Максимум 30 секунд
        play_beep=True,
        transcribe=False,  # Мы сами распознаем через Whisper
        recording_status_callback="/recording_status",
    )

    return Response(content=str(response), media_type="application/xml")


@app.post("/handle_speech")
async def handle_speech(request: Request):
    """
    Обработка записанной речи
    Twilio передает URL записи
    """
    form_data = await request.form()
    recording_url = form_data.get("RecordingUrl")
    call_sid = form_data.get("CallSid", "Unknown")

    logger.info(f"🎙️  Обработка записи для звонка {call_sid}")
    logger.info(f"📎 Recording URL: {recording_url}")

    try:
        # Скачиваем аудио запись от Twilio
        audio_response = requests.get(
            recording_url + ".wav", auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        )

        if audio_response.status_code != 200:
            logger.error(f"❌ Не удалось скачать запись: {audio_response.status_code}")
            return _error_response()

        # Отправляем на обработку в оркестратор
        files = {"audio": ("recording.wav", audio_response.content, "audio/wav")}
        orchestrator_response = requests.post(
            f"{ORCHESTRATOR_URL}/process_call",
            files=files,
            timeout=60,  # Даем 60 секунд на обработку
        )

        if orchestrator_response.status_code != 200:
            logger.error(f"❌ Ошибка от оркестратора: {orchestrator_response.status_code}")
            return _error_response()

        # Получаем аудио ответ
        _response_audio = orchestrator_response.content
        response_text = orchestrator_response.headers.get("X-Response-Text", "")

        logger.info(f"✅ Ответ от секретаря: {response_text}")

        # Сохраняем аудио ответ и возвращаем URL для Twilio
        # В продакшене нужно загрузить в облако (S3, etc)
        # Для упрощения возвращаем текстовый ответ через say()

        twiml_response = VoiceResponse()
        twiml_response.say(response_text, language="ru-RU", voice="alice")

        # Спрашиваем, нужно ли что-то еще
        twiml_response.say(
            "Могу ли я еще чем-то помочь? Нажмите 1 чтобы продолжить или повесьте трубку.",
            language="ru-RU",
            voice="alice",
        )

        gather = Gather(num_digits=1, action="/continue_or_end", method="POST", timeout=5)
        twiml_response.append(gather)

        # Если не нажали - завершаем
        twiml_response.say("Спасибо за звонок. До свидания!", language="ru-RU", voice="alice")
        twiml_response.hangup()

        return Response(content=str(twiml_response), media_type="application/xml")

    except Exception as e:
        logger.error(f"❌ Ошибка обработки речи: {e}")
        return _error_response()


@app.post("/continue_or_end")
async def continue_or_end(request: Request):
    """Продолжить диалог или завершить"""
    form_data = await request.form()
    digits = form_data.get("Digits", "")

    response = VoiceResponse()

    if digits == "1":
        # Продолжаем диалог
        response.say("Пожалуйста, говорите после сигнала.", language="ru-RU", voice="alice")
        response.record(
            action="/handle_speech", method="POST", max_length=30, play_beep=True, transcribe=False
        )
    else:
        # Завершаем
        response.say("Спасибо за звонок. До свидания!", language="ru-RU", voice="alice")
        response.hangup()

    return Response(content=str(response), media_type="application/xml")


@app.post("/recording_status")
async def recording_status(request: Request):
    """Callback для статуса записи"""
    form_data = await request.form()
    recording_status = form_data.get("RecordingStatus", "unknown")
    call_sid = form_data.get("CallSid", "Unknown")

    logger.info(f"📊 Статус записи для {call_sid}: {recording_status}")

    return {"status": "ok"}


def _error_response() -> Response:
    """Ответ при ошибке"""
    response = VoiceResponse()
    response.say(
        "Извините, произошла техническая ошибка. Пожалуйста, перезвоните позже.",
        language="ru-RU",
        voice="alice",
    )
    response.hangup()
    return Response(content=str(response), media_type="application/xml")


if __name__ == "__main__":
    import uvicorn

    logger.info("📞 Запуск Phone Service на порту 8001")
    uvicorn.run("phone_service:app", host="0.0.0.0", port=8001, reload=False, log_level="info")
