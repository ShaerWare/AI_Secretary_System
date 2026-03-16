"""Chat image service: upload, OCR, storage, cleanup."""

import hashlib
import logging
import shutil
import time
from pathlib import Path
from typing import Optional

from PIL import Image


try:
    import pytesseract

    PYTESSERACT_AVAILABLE = True
except ImportError:
    pytesseract = None  # type: ignore[assignment]
    PYTESSERACT_AVAILABLE = False

logger = logging.getLogger(__name__)

IMAGES_DIR = Path("data/chat_images")
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
THUMB_MAX_WIDTH = 400


def _generate_image_id() -> str:
    ts = str(time.time())
    return f"img_{int(time.time() * 1000)}_{hashlib.md5(ts.encode()).hexdigest()[:6]}"


def _session_dir(session_id: str) -> Path:
    """Get/create directory for session images."""
    d = IMAGES_DIR / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_extension(content_type: str) -> str:
    return {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/gif": "gif",
    }.get(content_type, "jpg")


async def upload_image(
    session_id: str,
    file_data: bytes,
    content_type: str,
    original_name: str,
) -> dict:
    """Save image, generate thumbnail, run OCR. Returns metadata dict."""
    if len(file_data) > MAX_FILE_SIZE:
        raise ValueError(f"File too large: {len(file_data)} > {MAX_FILE_SIZE}")

    if content_type not in ALLOWED_MIME_TYPES:
        raise ValueError(f"Unsupported type: {content_type}")

    image_id = _generate_image_id()
    ext = _get_extension(content_type)
    session_dir = _session_dir(session_id)

    # Save original
    original_path = session_dir / f"{image_id}.{ext}"
    original_path.write_bytes(file_data)

    # Open with Pillow for dimensions + thumbnail + OCR
    img = Image.open(original_path)
    width, height = img.size

    # Generate thumbnail
    thumb_path = session_dir / f"{image_id}_thumb.jpg"
    thumb = img.copy()
    if width > THUMB_MAX_WIDTH:
        ratio = THUMB_MAX_WIDTH / width
        thumb = thumb.resize((THUMB_MAX_WIDTH, int(height * ratio)), Image.LANCZOS)
    if thumb.mode in ("RGBA", "P"):
        thumb = thumb.convert("RGB")
    thumb.save(thumb_path, "JPEG", quality=80)

    # OCR
    ocr_text: Optional[str] = None
    if PYTESSERACT_AVAILABLE:
        try:
            # Use Russian + English
            ocr_img = img.convert("RGB") if img.mode != "RGB" else img
            raw = pytesseract.image_to_string(ocr_img, lang="rus+eng", timeout=15)
            ocr_text = raw.strip() if raw and raw.strip() else None
        except Exception as e:
            logger.warning(f"OCR failed for {original_name}: {e}")

    return {
        "id": image_id,
        "filename": f"{image_id}.{ext}",
        "original_name": original_name,
        "size": len(file_data),
        "width": width,
        "height": height,
        "ocr_text": ocr_text,
        "mime_type": content_type,
    }


def get_image_path(session_id: str, filename: str) -> Optional[Path]:
    """Get full path to an image file, or None if not found."""
    path = IMAGES_DIR / session_id / filename
    if path.exists() and path.is_file():
        # Security: ensure path is within IMAGES_DIR
        try:
            path.resolve().relative_to(IMAGES_DIR.resolve())
            return path
        except ValueError:
            return None
    return None


def delete_session_images(session_id: str) -> int:
    """Delete all images for a session. Returns number of files deleted."""
    session_dir = IMAGES_DIR / session_id
    if not session_dir.exists():
        return 0
    count = sum(1 for f in session_dir.iterdir() if f.is_file())
    shutil.rmtree(session_dir, ignore_errors=True)
    logger.info(f"Deleted {count} images for session {session_id}")
    return count


def delete_images_by_metadata(session_id: str, metadata: dict) -> int:
    """Delete specific images referenced in message metadata."""
    images = metadata.get("images", [])
    if not images:
        return 0
    count = 0
    session_dir = IMAGES_DIR / session_id
    for img in images:
        filename = img.get("filename", "")
        image_id = img.get("id", "")
        for f in [session_dir / filename, session_dir / f"{image_id}_thumb.jpg"]:
            if f.exists():
                f.unlink(missing_ok=True)
                count += 1
    return count
