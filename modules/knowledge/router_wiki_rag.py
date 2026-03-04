"""Wiki RAG management router — stats, search, knowledge base CRUD, collections."""

import logging
import re
import unicodedata
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.dependencies import get_container
from auth_manager import User, require_permission, workspace_context
from modules.knowledge.service import knowledge_collection_service, knowledge_doc_service
from modules.monitoring.service import audit_service


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/wiki-rag", tags=["wiki-rag"])

WIKI_DIR = Path("wiki-pages")


# ---- Pydantic models ----


class WikiSearchRequest(BaseModel):
    query: str
    top_k: int = 3
    max_chars: int = 1500
    collection_id: int | None = None


class DocumentUpdateRequest(BaseModel):
    title: str | None = None
    content: str | None = None


class CollectionCreateRequest(BaseModel):
    name: str
    slug: str | None = None
    description: str | None = None
    enabled: bool = True


class CollectionUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None


# ---- Helpers ----


def _slugify(text: str) -> str:
    """Generate a URL-safe slug from text."""
    # Transliterate Cyrillic
    translit_map = {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "yo",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "kh",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "shch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
    text = text.lower()
    result = []
    for ch in text:
        if ch in translit_map:
            result.append(translit_map[ch])
        else:
            result.append(ch)
    text = "".join(result)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text or "collection"


async def _get_default_collection_id() -> Optional[int]:
    """Get the default collection ID, creating it if needed."""
    default = await knowledge_collection_service.ensure_default_exists()
    return default["id"]


async def _sync_disk_to_db() -> int:
    """Sync wiki-pages/*.md files to knowledge_documents DB table.

    Creates records for files on disk that don't have DB entries yet.
    Assigns synced docs to the default collection.
    Returns number of newly synced records.
    """
    if not WIKI_DIR.exists():
        return 0

    default_collection_id = await _get_default_collection_id()

    synced = 0
    for md_file in sorted(WIKI_DIR.glob("*.md")):
        if md_file.name.startswith("_"):
            continue
        existing = await knowledge_doc_service.get_by_filename(md_file.name)
        if existing:
            continue

        # Count sections (## and ### headers)
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        sections = len(re.findall(r"^#{2,3}\s+.+$", content, re.MULTILINE))
        title = md_file.stem.replace("-", " ").replace("_", " ")

        # Try to extract title from first # header
        first_header = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if first_header:
            title = first_header.group(1).strip()

        await knowledge_doc_service.create(
            filename=md_file.name,
            title=title,
            source_type="wiki",
            file_size_bytes=md_file.stat().st_size,
            section_count=sections,
            collection_id=default_collection_id,
        )
        synced += 1

    return synced


def _get_wiki_rag():
    """Get wiki RAG service from container."""
    container = get_container()
    return container.wiki_rag_service


async def _get_collection_dir(collection_id: int | None) -> Path:
    """Get the base directory for a collection's files.

    Returns the collection's base_dir if set, otherwise WIKI_DIR.
    """
    if collection_id is not None:
        col = await knowledge_collection_service.get_by_id(collection_id)
        if col and col.get("base_dir"):
            return Path(col["base_dir"])
    return WIKI_DIR


# ---- Collection Endpoints ----


@router.get("/collections")
async def list_collections(user: User = Depends(require_permission("wiki", "view"))):
    """List all knowledge collections."""
    _owner_id, ws_id = workspace_context(user, "wiki")
    collections = await knowledge_collection_service.get_all(workspace_id=ws_id)
    return {"collections": collections}


@router.post("/collections")
async def create_collection(
    request: CollectionCreateRequest,
    user: User = Depends(require_permission("wiki", "edit")),
):
    """Create a new knowledge collection."""
    _owner_id, ws_id = workspace_context(user, "wiki")
    slug = request.slug or _slugify(request.name)

    # Check for duplicate slug
    existing = await knowledge_collection_service.get_by_slug(slug)
    if existing:
        raise HTTPException(status_code=409, detail=f"Коллекция со slug '{slug}' уже существует")

    # Check for duplicate name
    existing_name = await knowledge_collection_service.get_by_slug(slug)
    if existing_name:
        raise HTTPException(
            status_code=409, detail=f"Коллекция с именем '{request.name}' уже существует"
        )

    collection = await knowledge_collection_service.create(
        name=request.name,
        slug=slug,
        description=request.description,
        enabled=request.enabled,
        workspace_id=ws_id,
    )

    await audit_service.log(
        action="create",
        resource="knowledge_collection",
        resource_id=slug,
        user_id=user.username,
        details={"name": request.name},
    )

    return {"status": "ok", "collection": collection}


@router.get("/collections/{collection_id}")
async def get_collection(
    collection_id: int, user: User = Depends(require_permission("wiki", "view"))
):
    """Get a single knowledge collection."""
    _owner_id, ws_id = workspace_context(user, "wiki")
    collection = await knowledge_collection_service.get_by_id(collection_id, workspace_id=ws_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Коллекция не найдена")
    return {"collection": collection}


@router.put("/collections/{collection_id}")
async def update_collection(
    collection_id: int,
    request: CollectionUpdateRequest,
    user: User = Depends(require_permission("wiki", "edit")),
):
    """Update a knowledge collection."""
    _owner_id, ws_id = workspace_context(user, "wiki")
    collection = await knowledge_collection_service.get_by_id(collection_id, workspace_id=ws_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Коллекция не найдена")

    updated = await knowledge_collection_service.update(
        collection_id,
        name=request.name,
        description=request.description,
        enabled=request.enabled,
    )

    await audit_service.log(
        action="update",
        resource="knowledge_collection",
        resource_id=str(collection_id),
        user_id=user.username,
    )

    return {"status": "ok", "collection": updated}


@router.delete("/collections/{collection_id}")
async def delete_collection(
    collection_id: int,
    user: User = Depends(require_permission("wiki", "edit")),
):
    """Delete a knowledge collection. Cannot delete 'default'."""
    _owner_id, ws_id = workspace_context(user, "wiki")
    collection = await knowledge_collection_service.get_by_id(collection_id, workspace_id=ws_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Коллекция не найдена")

    if collection["slug"] == "default":
        raise HTTPException(status_code=400, detail="Нельзя удалить коллекцию по умолчанию")

    # Unload collection index
    wiki_rag = _get_wiki_rag()
    if wiki_rag:
        wiki_rag.unload_collection(collection_id)

    await knowledge_collection_service.delete(collection_id)

    await audit_service.log(
        action="delete",
        resource="knowledge_collection",
        resource_id=collection["name"],
        user_id=user.username,
    )

    return {"status": "ok", "deleted": collection["name"]}


@router.post("/collections/{collection_id}/reload")
async def reload_collection_index(
    collection_id: int,
    user: User = Depends(require_permission("wiki", "manage")),
):
    """Re-index a specific collection."""
    wiki_rag = _get_wiki_rag()
    if not wiki_rag:
        raise HTTPException(status_code=503, detail="Wiki RAG сервис не инициализирован")

    _owner_id, ws_id = workspace_context(user, "wiki")
    collection = await knowledge_collection_service.get_by_id(collection_id, workspace_id=ws_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Коллекция не найдена")

    filenames = await knowledge_collection_service.get_document_filenames(collection_id)
    collection_dir = await _get_collection_dir(collection_id)
    if filenames:
        idx = wiki_rag.reload_collection(collection_id, filenames, collection_dir)
        result = {
            "sections_indexed": idx.total_docs,
            "files_indexed": idx.files_indexed,
        }
    else:
        wiki_rag.unload_collection(collection_id)
        result = {"sections_indexed": 0, "files_indexed": 0}

    await audit_service.log(
        action="reload",
        resource="knowledge_collection",
        resource_id=str(collection_id),
        user_id=user.username,
        details=result,
    )

    return {"status": "ok", **result}


# ---- Existing Endpoints (updated for collection_id) ----


@router.get("/stats")
async def wiki_rag_stats(user: User = Depends(require_permission("wiki", "view"))):
    """Get Wiki RAG index statistics and source file list."""
    wiki_rag = _get_wiki_rag()
    if not wiki_rag:
        return {
            "stats": {
                "sections_indexed": 0,
                "files_indexed": 0,
                "unique_tokens": 0,
                "available": False,
            },
            "source_files": [],
        }

    return {
        "stats": wiki_rag.stats,
        "source_files": wiki_rag.list_source_files(),
    }


@router.post("/reload")
async def wiki_rag_reload(user: User = Depends(require_permission("wiki", "manage"))):
    """Re-index wiki-pages/ directory."""
    wiki_rag = _get_wiki_rag()
    if not wiki_rag:
        raise HTTPException(status_code=503, detail="Wiki RAG сервис не инициализирован")

    result = wiki_rag.reload(WIKI_DIR)

    await audit_service.log(
        action="reload",
        resource="wiki_rag",
        user_id=user.username,
        details=result,
    )

    return {"status": "ok", **result}


@router.post("/reindex-embeddings")
async def wiki_rag_reindex_embeddings(user: User = Depends(require_permission("wiki", "manage"))):
    """Force rebuild all embedding vectors from scratch."""
    wiki_rag = _get_wiki_rag()
    if not wiki_rag:
        raise HTTPException(status_code=503, detail="Wiki RAG сервис не инициализирован")

    result = wiki_rag.reindex_embeddings()

    await audit_service.log(
        action="reindex_embeddings",
        resource="wiki_rag",
        user_id=user.username,
        details=result,
    )

    return {"status": "ok", **result}


@router.post("/search")
async def wiki_rag_search(
    request: WikiSearchRequest,
    user: User = Depends(require_permission("wiki", "view")),
):
    """Test search: query → scored results. Optionally filter by collection."""
    wiki_rag = _get_wiki_rag()
    if not wiki_rag:
        return {"results": [], "query": request.query}

    results = wiki_rag.search(
        request.query, top_k=request.top_k, collection_id=request.collection_id
    )
    return {"results": results, "query": request.query}


@router.get("/documents")
async def list_documents(
    collection_id: Optional[int] = Query(None),
    user: User = Depends(require_permission("wiki", "view")),
):
    """List knowledge base documents. Optionally filter by collection_id."""
    _owner_id, ws_id = workspace_context(user, "wiki")
    synced = await _sync_disk_to_db()

    if collection_id is not None:
        documents = await knowledge_doc_service.get_by_collection(collection_id, workspace_id=ws_id)
    else:
        documents = await knowledge_doc_service.get_all(workspace_id=ws_id)

    return {"documents": documents, "synced": synced}


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile,
    collection_id: Optional[int] = Form(None),
    user: User = Depends(require_permission("wiki", "edit")),
):
    """Upload .md or .txt file to wiki-pages/ and register in DB."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Имя файла не указано")

    # Validate extension
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".md", ".txt"):
        raise HTTPException(status_code=400, detail="Допустимые форматы: .md, .txt")

    # Ensure .md extension for storage
    filename = file.filename if suffix == ".md" else Path(file.filename).stem + ".md"

    # Check duplicate
    existing = await knowledge_doc_service.get_by_filename(filename)
    if existing:
        raise HTTPException(status_code=409, detail=f"Файл {filename} уже существует")

    # Default to default collection if not specified
    if collection_id is None:
        collection_id = await _get_default_collection_id()

    # Read content
    content_bytes = await file.read()
    content = content_bytes.decode("utf-8")

    # Write to collection directory
    upload_dir = await _get_collection_dir(collection_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / filename
    target.write_text(content, encoding="utf-8")

    # Count sections
    sections = len(re.findall(r"^#{2,3}\s+.+$", content, re.MULTILINE))

    # Extract title
    title = Path(filename).stem.replace("-", " ").replace("_", " ")
    first_header = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if first_header:
        title = first_header.group(1).strip()

    # Create DB record
    owner_id, ws_id = workspace_context(user, "wiki")
    doc = await knowledge_doc_service.create(
        filename=filename,
        title=title,
        source_type="manual",
        file_size_bytes=len(content_bytes),
        section_count=sections,
        owner_id=owner_id,
        collection_id=collection_id,
        workspace_id=ws_id,
    )

    # Re-index global + collection
    wiki_rag = _get_wiki_rag()
    if wiki_rag:
        wiki_rag.reload(WIKI_DIR)
        if collection_id:
            col_dir = await _get_collection_dir(collection_id)
            filenames = await knowledge_collection_service.get_document_filenames(collection_id)
            if filenames:
                wiki_rag.reload_collection(collection_id, filenames, col_dir)

    await audit_service.log(
        action="upload",
        resource="wiki_rag_document",
        resource_id=filename,
        user_id=user.username,
        details={"size": len(content_bytes), "sections": sections},
    )

    return {"status": "ok", "document": doc}


@router.get("/documents/{doc_id}")
async def get_document(doc_id: int, user: User = Depends(require_permission("wiki", "view"))):
    """Get document metadata + content preview."""
    _owner_id, ws_id = workspace_context(user, "wiki")
    doc = await knowledge_doc_service.get_by_id(doc_id, workspace_id=ws_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")

    # Read content preview from disk
    content_preview = ""
    doc_dir = await _get_collection_dir(doc.get("collection_id"))
    file_path = doc_dir / doc["filename"]
    if file_path.exists():
        try:
            full_content = file_path.read_text(encoding="utf-8")
            content_preview = full_content
        except Exception:
            pass

    return {"document": doc, "content_preview": content_preview}


@router.put("/documents/{doc_id}")
async def update_document(
    doc_id: int,
    request: DocumentUpdateRequest,
    user: User = Depends(require_permission("wiki", "edit")),
):
    """Update document title and/or content."""
    _owner_id, ws_id = workspace_context(user, "wiki")
    doc = await knowledge_doc_service.get_by_id(doc_id, workspace_id=ws_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")

    # Update file content if provided
    if request.content is not None:
        doc_dir = await _get_collection_dir(doc.get("collection_id"))
        file_path = doc_dir / doc["filename"]
        file_path.write_text(request.content, encoding="utf-8")

        sections = len(re.findall(r"^#{2,3}\s+.+$", request.content, re.MULTILINE))
        await knowledge_doc_service.update(
            doc_id,
            title=request.title,
            file_size_bytes=len(request.content.encode("utf-8")),
            section_count=sections,
        )

        # Re-index after content change
        wiki_rag = _get_wiki_rag()
        if wiki_rag:
            wiki_rag.reload(WIKI_DIR)
            # Reload collection index if document belongs to one
            cid = doc.get("collection_id")
            if cid:
                col_dir = await _get_collection_dir(cid)
                filenames = await knowledge_collection_service.get_document_filenames(cid)
                if filenames:
                    wiki_rag.reload_collection(cid, filenames, col_dir)
    elif request.title is not None:
        await knowledge_doc_service.update(doc_id, title=request.title)

    updated_doc = await knowledge_doc_service.get_by_id(doc_id)

    await audit_service.log(
        action="update",
        resource="wiki_rag_document",
        resource_id=str(doc_id),
        user_id=user.username,
    )

    return {"status": "ok", "document": updated_doc}


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: int, user: User = Depends(require_permission("wiki", "edit"))):
    """Delete document from disk and DB, re-index."""
    _owner_id, ws_id = workspace_context(user, "wiki")
    doc = await knowledge_doc_service.get_by_id(doc_id, workspace_id=ws_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")

    collection_id = doc.get("collection_id")
    doc_dir = await _get_collection_dir(collection_id)

    # Delete file from disk
    file_path = doc_dir / doc["filename"]
    if file_path.exists():
        file_path.unlink()

    # Delete DB record
    await knowledge_doc_service.delete(doc_id)

    # Re-index global + collection
    wiki_rag = _get_wiki_rag()
    if wiki_rag:
        wiki_rag.reload(WIKI_DIR)
        if collection_id:
            filenames = await knowledge_collection_service.get_document_filenames(collection_id)
            if filenames:
                wiki_rag.reload_collection(collection_id, filenames, doc_dir)
            else:
                wiki_rag.unload_collection(collection_id)

    await audit_service.log(
        action="delete",
        resource="wiki_rag_document",
        resource_id=doc["filename"],
        user_id=user.username,
    )

    return {"status": "ok", "deleted": doc["filename"]}
