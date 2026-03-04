"""File and photo handler — text extraction for documents."""

import logging

from aiogram import F, Router
from aiogram.types import Message

from ..services.file_extractor import extract_text
from .messages import _get_lock, _handle_user_message


router = Router()
logger = logging.getLogger(__name__)

# 20 MB limit (Telegram Bot API file download limit)
MAX_FILE_SIZE = 20 * 1024 * 1024

PHOTO_NOT_SUPPORTED_MSG = (
    "Распознавание изображений пока не поддерживается.\n\n"
    "Отправьте текстовый файл (.txt, .md, .csv, .py, .json и др.) или PDF."
)

DEFAULT_PROMPT = "Проанализируй этот файл"


@router.message(F.document)
async def on_document(message: Message) -> None:
    """Handle document uploads — extract text and send to LLM."""
    if not message.from_user or not message.document:
        return

    user_id = message.from_user.id
    doc = message.document

    # --- size check ---
    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        await message.answer(
            f"Файл слишком большой ({doc.file_size // (1024 * 1024)} МБ).\n"
            f"Максимальный размер — {MAX_FILE_SIZE // (1024 * 1024)} МБ."
        )
        return

    # --- download ---
    try:
        file_obj = await message.bot.get_file(doc.file_id)
        bio = await message.bot.download_file(file_obj.file_path)
        data = bio.read()
    except Exception:
        logger.exception("Failed to download file from user %s", user_id)
        await message.answer("Не удалось скачать файл. Попробуйте ещё раз.")
        return

    # --- extract text ---
    filename = doc.file_name or "file"
    mime = doc.mime_type or ""
    try:
        text = extract_text(data, filename, mime)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    except Exception:
        logger.exception("Text extraction failed for %s from user %s", filename, user_id)
        await message.answer("Не удалось извлечь текст из файла.")
        return

    # --- build message for LLM ---
    caption = message.caption or DEFAULT_PROMPT
    user_text = f"\U0001f4ce {filename}\n\n{text}\n\n{caption}"

    lock = _get_lock(user_id)
    async with lock:
        await _handle_user_message(message, user_id, user_text)


@router.message(F.photo)
async def on_photo(message: Message) -> None:
    """Handle photo uploads — not supported yet."""
    if not message.from_user or not message.photo:
        return

    await message.answer(PHOTO_NOT_SUPPORTED_MSG)
    logger.info("Photo upload attempted by user %s", message.from_user.id)
