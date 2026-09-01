"""PSD-файлы клиента должны загружаться в чат.

Клиент присылает макеты в .psd; раньше загрузка падала с «Unsupported type»,
потому что тип не был в белом списке, а браузер для .psd часто вообще шлёт
application/octet-stream.
"""

import struct

import pytest

from modules.chat.image_service import (
    ALLOWED_MIME_TYPES,
    _is_image,
    _resolve_content_type,
    upload_file,
)


def _psd_bytes(channels: int = 3, size: tuple[int, int] = (120, 80)) -> bytes:
    """Минимальный валидный PSD со сведённой копией.

    Pillow умеет PSD читать, но не писать, поэтому файл собирается вручную по
    спецификации: заголовок, три пустые секции и несжатые данные изображения.
    ``channels`` 3 → RGB, 4 → CMYK.
    """
    w, h = size
    color_mode = 3 if channels == 3 else 4
    header = (
        b"8BPS"
        + struct.pack(">H", 1)  # версия
        + bytes(6)  # резерв
        + struct.pack(">H", channels)
        + struct.pack(">II", h, w)
        + struct.pack(">H", 8)  # бит на канал
        + struct.pack(">H", color_mode)
    )
    empty_sections = struct.pack(">I", 0) * 3  # color mode data, resources, layers
    image_data = struct.pack(">H", 0) + bytes([255]) * (channels * w * h)  # 0 = без сжатия
    return header + empty_sections + image_data


@pytest.mark.parametrize(
    "content_type,name,expected",
    [
        # браузер определил тип сам
        ("image/vnd.adobe.photoshop", "layout.psd", "image/vnd.adobe.photoshop"),
        # браузер не смог — доопределяем по расширению
        ("application/octet-stream", "layout.psd", "image/vnd.adobe.photoshop"),
        ("", "layout.PSD", "image/vnd.adobe.photoshop"),
        # известный тип не трогаем
        ("application/pdf", "spec.pdf", "application/pdf"),
        # неизвестное расширение оставляем как есть — пусть отвергнет валидация
        ("application/octet-stream", "archive.7z", "application/octet-stream"),
    ],
)
def test_content_type_resolution(content_type, name, expected):
    assert _resolve_content_type(content_type, name) == expected


def test_psd_is_allowed_and_treated_as_image():
    assert "image/vnd.adobe.photoshop" in ALLOWED_MIME_TYPES
    assert _is_image("image/vnd.adobe.photoshop")


async def test_psd_upload_produces_a_preview(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.chat.image_service.IMAGES_DIR", tmp_path)
    meta = await upload_file("sess1", _psd_bytes(), "application/octet-stream", "макет.psd")

    assert meta["is_image"] is True
    assert meta["filename"].endswith(".psd")
    assert (meta["width"], meta["height"]) == (120, 80)
    assert (tmp_path / "sess1" / f"{meta['id']}_thumb.jpg").exists()


async def test_cmyk_psd_still_thumbnails(tmp_path, monkeypatch):
    """JPEG не принимает CMYK — превью должно конвертироваться, а не падать."""
    monkeypatch.setattr("modules.chat.image_service.IMAGES_DIR", tmp_path)
    meta = await upload_file("sess2", _psd_bytes(channels=4), "image/vnd.adobe.photoshop", "c.psd")
    assert (tmp_path / "sess2" / f"{meta['id']}_thumb.jpg").exists()


async def test_unreadable_psd_still_uploads(tmp_path, monkeypatch):
    """PSD без сведённой копии Pillow не откроет — файл всё равно сохраняем."""
    monkeypatch.setattr("modules.chat.image_service.IMAGES_DIR", tmp_path)
    meta = await upload_file("sess3", b"8BPS\x00\x01broken", "image/vnd.adobe.photoshop", "b.psd")

    assert meta["is_image"] is True
    assert meta["width"] == 0
    assert (tmp_path / "sess3" / meta["filename"]).exists()


async def test_unknown_binary_is_still_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.chat.image_service.IMAGES_DIR", tmp_path)
    with pytest.raises(ValueError, match="Unsupported type"):
        await upload_file("sess4", b"\x00\x01\x02", "application/octet-stream", "archive.7z")
