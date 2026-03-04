"""Extract text from uploaded files (text formats and PDF)."""

import io
import logging
from pathlib import PurePosixPath


logger = logging.getLogger(__name__)

MAX_EXTRACTED_CHARS = 50_000

# Extensions recognized as plain text
TEXT_EXTENSIONS: set[str] = {
    ".txt",
    ".md",
    ".csv",
    ".py",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".log",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".sh",
    ".bat",
    ".sql",
    ".env",
    ".rst",
    ".js",
    ".ts",
    ".css",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".r",
    ".lua",
    ".pl",
}

# MIME prefixes/types that indicate plain text
TEXT_MIME_PREFIXES: tuple[str, ...] = (
    "text/",
    "application/json",
    "application/xml",
    "application/x-yaml",
    "application/x-sh",
    "application/sql",
    "application/javascript",
    "application/typescript",
    "application/x-python",
)

PDF_MIMES: set[str] = {"application/pdf"}
PDF_EXTENSIONS: set[str] = {".pdf"}


def _is_text(mime: str, ext: str) -> bool:
    if any(mime.startswith(p) for p in TEXT_MIME_PREFIXES):
        return True
    return ext in TEXT_EXTENSIONS


def _is_pdf(mime: str, ext: str) -> bool:
    return mime in PDF_MIMES or ext in PDF_EXTENSIONS


def _extract_text_file(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _extract_pdf(data: bytes) -> str:
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    if not pages:
        raise ValueError("PDF не содержит извлекаемого текста (возможно, это скан-копия).")
    return "\n\n".join(pages)


def extract_text(data: bytes, filename: str, mime: str) -> str:
    """Extract text content from file bytes.

    Args:
        data: Raw file bytes.
        filename: Original filename (used for extension detection).
        mime: MIME type reported by Telegram.

    Returns:
        Extracted text, truncated to MAX_EXTRACTED_CHARS.

    Raises:
        ValueError: If the file format is not supported or extraction fails.
    """
    mime = (mime or "").lower()
    ext = PurePosixPath(filename).suffix.lower() if filename else ""

    if _is_pdf(mime, ext):
        text = _extract_pdf(data)
    elif _is_text(mime, ext):
        text = _extract_text_file(data)
    else:
        raise ValueError(
            f"Формат файла не поддерживается ({ext or mime}).\n"
            "Поддерживаются: текстовые файлы (.txt, .md, .csv, .py, .json и др.) и PDF."
        )

    if len(text) > MAX_EXTRACTED_CHARS:
        text = text[:MAX_EXTRACTED_CHARS] + "\n\n[... текст обрезан]"

    return text
