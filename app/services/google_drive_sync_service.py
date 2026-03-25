"""Google Drive sync service — downloads files from Drive folder, converts to markdown."""

import logging
import re
from pathlib import Path

import httpx


logger = logging.getLogger(__name__)

# Google Apps MIME types that can be exported
EXPORTABLE_TYPES = {
    "application/vnd.google-apps.document": ("text/plain", ".txt", "google_docs"),
    "application/vnd.google-apps.spreadsheet": (
        "text/csv",
        ".csv",
        "google_sheets",
    ),
    "application/vnd.google-apps.presentation": (
        "text/plain",
        ".txt",
        "google_slides",
    ),
}

# Regular file types we can read as text
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".xml",
    ".html",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".log",
    ".py",
    ".js",
    ".ts",
    ".vue",
    ".jsx",
    ".tsx",
    ".css",
    ".scss",
    ".sql",
    ".sh",
    ".bash",
    ".rb",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
}

MAX_FILE_SIZE = 512 * 1024  # 512 KB per file


async def list_drive_folder_recursive(
    access_token: str,
    folder_id: str = "root",
    max_files: int = 500,
) -> list[dict]:
    """List all files in a Drive folder recursively (up to max_files)."""
    files: list[dict] = []
    folders_to_scan = [folder_id]

    async with httpx.AsyncClient(timeout=30) as client:
        while folders_to_scan and len(files) < max_files:
            current_folder = folders_to_scan.pop(0)
            page_token = None

            while True:
                params: dict = {
                    "q": f"'{current_folder}' in parents and trashed = false",
                    "fields": "nextPageToken, files(id, name, mimeType, size, modifiedTime)",
                    "pageSize": 100,
                }
                if page_token:
                    params["pageToken"] = page_token

                resp = await client.get(
                    "https://www.googleapis.com/drive/v3/files",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

                for f in data.get("files", []):
                    if f["mimeType"] == "application/vnd.google-apps.folder":
                        folders_to_scan.append(f["id"])
                    else:
                        files.append(f)
                        if len(files) >= max_files:
                            break

                page_token = data.get("nextPageToken")
                if not page_token or len(files) >= max_files:
                    break

    return files


async def download_and_convert_file(
    access_token: str,
    file_info: dict,
) -> tuple[str, str, int] | None:
    """Download a single file and convert to text.

    Returns (title, content, size_bytes) or None if file can't be processed.
    """
    file_id = file_info["id"]
    name = file_info["name"]
    mime_type = file_info["mimeType"]
    size = int(file_info.get("size", 0))

    async with httpx.AsyncClient(timeout=60) as client:
        headers = {"Authorization": f"Bearer {access_token}"}

        # Google Apps files (Docs, Sheets, Slides) — export
        if mime_type in EXPORTABLE_TYPES:
            export_mime, _ext, _source = EXPORTABLE_TYPES[mime_type]
            resp = await client.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
                headers=headers,
                params={"mimeType": export_mime},
            )
            if resp.status_code != 200:
                logger.warning(f"Failed to export {name}: {resp.status_code}")
                return None
            content = resp.text
            return (name, content, len(content.encode("utf-8")))

        # Regular files — check size and extension
        if size > MAX_FILE_SIZE:
            logger.info(f"Skipping {name}: too large ({size} bytes)")
            return None

        ext = Path(name).suffix.lower()
        if ext not in TEXT_EXTENSIONS:
            logger.info(f"Skipping {name}: unsupported extension {ext}")
            return None

        # Download as text
        resp = await client.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            headers=headers,
            params={"alt": "media"},
        )
        if resp.status_code != 200:
            logger.warning(f"Failed to download {name}: {resp.status_code}")
            return None

        try:
            content = resp.text
        except Exception:
            return None

        return (name, content, len(content.encode("utf-8")))


def _sanitize_filename(name: str) -> str:
    """Convert file name to safe filename for disk."""
    name = re.sub(r"[^\w\s\-.]", "_", name)
    name = re.sub(r"\s+", "_", name)
    return name[:200]


async def sync_drive_folder(
    access_token: str,
    folder_id: str,
    output_dir: str,
    max_files: int = 500,
) -> list[dict]:
    """Sync entire Drive folder to disk as markdown/text files.

    Returns list of document dicts for DatasetSynced event.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Clean old files
    for old_file in Path(output_dir).glob("*.md"):
        old_file.unlink()

    # List all files
    drive_files = await list_drive_folder_recursive(access_token, folder_id, max_files)
    logger.info(f"Google Drive sync: found {len(drive_files)} files in folder {folder_id}")

    documents: list[dict] = []
    total_size = 0

    for file_info in drive_files:
        try:
            result = await download_and_convert_file(access_token, file_info)
            if not result:
                continue
            title, content, size_bytes = result
        except Exception as e:
            logger.warning(f"Error processing {file_info['name']}: {e}")
            continue

        # Determine source type
        mime_type = file_info["mimeType"]
        if mime_type in EXPORTABLE_TYPES:
            source_type = EXPORTABLE_TYPES[mime_type][2]
        else:
            source_type = "google_drive"

        # Write to disk as markdown
        safe_name = _sanitize_filename(title)
        if not safe_name.endswith(".md"):
            safe_name = (
                safe_name.rsplit(".", 1)[0] + ".md" if "." in safe_name else safe_name + ".md"
            )
        filepath = Path(output_dir) / safe_name

        # Wrap content in markdown with title
        md_content = f"# {title}\n\n{content}"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md_content)

        # Count sections
        section_count = len(re.findall(r"^#{2,3}\s+.+$", md_content, re.MULTILINE))

        documents.append(
            {
                "filename": safe_name,
                "title": title,
                "source_type": source_type,
                "file_size_bytes": size_bytes,
                "section_count": max(section_count, 1),
            }
        )
        total_size += size_bytes

    logger.info(
        f"Google Drive sync complete: {len(documents)} documents, {total_size / 1024:.1f} KB total"
    )
    return documents
