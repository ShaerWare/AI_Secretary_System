"""
Vector Search microservice — semantic search engine using ChromaDB + sentence-transformers.

Model: paraphrase-multilingual-mpnet-base-v2 (768 dims)
Storage: ChromaDB persistent (./data/)
Auth: Bearer token via VECTOR_SEARCH_TOKEN env var
"""

import hashlib
import logging
import os
from typing import Optional

import chromadb
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---- Configuration ----

MODEL_NAME = os.environ.get("VECTOR_SEARCH_MODEL", "paraphrase-multilingual-mpnet-base-v2")
DATA_DIR = os.environ.get("VECTOR_SEARCH_DATA_DIR", "./data")
AUTH_TOKEN = os.environ.get("VECTOR_SEARCH_TOKEN", "")
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50

# ---- App init ----

app = FastAPI(title="Vector Search", version="1.0.0")

# Load model
logger.info("Loading model: %s", MODEL_NAME)
model = SentenceTransformer(MODEL_NAME)
logger.info("Model loaded, dims=%d", model.get_sentence_embedding_dimension())

# ChromaDB persistent client
chroma_client = chromadb.PersistentClient(path=DATA_DIR)

# ---- Auth ----

security = HTTPBearer(auto_error=False)


async def verify_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Verify Bearer token if VECTOR_SEARCH_TOKEN is configured."""
    if not AUTH_TOKEN:
        return  # No auth configured
    if not credentials or credentials.credentials != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing token")


# ---- Pydantic models ----


class UpsertRequest(BaseModel):
    text: str
    doc_id: str = ""
    group: str = "default"
    chunk_size: Optional[int] = Field(default=DEFAULT_CHUNK_SIZE, ge=50)
    chunk_overlap: Optional[int] = Field(default=DEFAULT_CHUNK_OVERLAP, ge=0)
    metadata: dict = Field(default_factory=dict)


class SearchRequest(BaseModel):
    text: str
    group: str = "default"
    doc_id: str = ""
    min_similarity: float = Field(default=0.3, ge=0.0, le=1.0)
    limit: int = Field(default=5, ge=1, le=100)


class CompareRequest(BaseModel):
    text: str
    record_id: str


class DeleteRecordRequest(BaseModel):
    record_id: str


class DeleteDocumentRequest(BaseModel):
    doc_id: str
    group: str = "default"


class DeleteGroupRequest(BaseModel):
    group: str


# ---- Helpers ----


def _get_collection(group: str):
    """Get or create a ChromaDB collection for the given group."""
    safe_name = group.replace("/", "_").replace("\\", "_")[:63]
    if not safe_name:
        safe_name = "default"
    return chroma_client.get_or_create_collection(
        name=safe_name,
        metadata={"hnsw:space": "cosine"},
    )


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into chunks with overlap."""
    if chunk_size <= 0 or len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
        if start >= len(text):
            break
    return chunks


def _record_id(doc_id: str, chunk_idx: int, text: str) -> str:
    """Generate a stable record ID."""
    raw = f"{doc_id}::{chunk_idx}::{hashlib.md5(text.encode()).hexdigest()[:8]}"
    return hashlib.md5(raw.encode()).hexdigest()


# ---- Endpoints ----


@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "dims": model.get_sentence_embedding_dimension(),
        "collections": len(chroma_client.list_collections()),
    }


@app.post("/upsert", dependencies=[Depends(verify_token)])
async def upsert(request: UpsertRequest):
    """Upsert text into vector store. Chunks text if chunk_size is set."""
    collection = _get_collection(request.group)

    chunks = _chunk_text(
        request.text,
        request.chunk_size or len(request.text) + 1,
        request.chunk_overlap or 0,
    )

    ids = []
    documents = []
    embeddings = []
    metadatas = []

    for i, chunk in enumerate(chunks):
        chunk = chunk.strip()
        if not chunk:
            continue

        rid = _record_id(request.doc_id, i, chunk)
        ids.append(rid)
        documents.append(chunk)
        embeddings.append(model.encode(chunk).tolist())
        metadatas.append(
            {
                "doc_id": request.doc_id,
                "chunk_index": i,
                "chunk_count": len(chunks),
                **request.metadata,
            }
        )

    if ids:
        collection.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)

    return {"status": "ok", "record_ids": ids, "chunks": len(ids)}


@app.post("/search", dependencies=[Depends(verify_token)])
async def search(request: SearchRequest):
    """Semantic search within a group (collection)."""
    collection = _get_collection(request.group)

    if collection.count() == 0:
        return {"results": [], "total": 0}

    query_embedding = model.encode(request.text).tolist()

    where_filter = None
    if request.doc_id:
        where_filter = {"doc_id": request.doc_id}

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(request.limit, collection.count()),
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )

    output = []
    if results and results["ids"] and results["ids"][0]:
        for i, rid in enumerate(results["ids"][0]):
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            # Convert to similarity: 1 - (distance / 2)
            distance = results["distances"][0][i]
            similarity = 1.0 - (distance / 2.0)

            if similarity < request.min_similarity:
                continue

            output.append(
                {
                    "record_id": rid,
                    "text": results["documents"][0][i],
                    "similarity": round(similarity, 4),
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                }
            )

    return {"results": output, "total": len(output)}


@app.post("/compare", dependencies=[Depends(verify_token)])
async def compare(request: CompareRequest):
    """Compare text similarity with a specific record."""
    # Search all collections for the record
    for col_info in chroma_client.list_collections():
        col = chroma_client.get_collection(col_info.name)
        try:
            record = col.get(ids=[request.record_id], include=["embeddings"])
            if record and record["ids"]:
                query_embedding = model.encode(request.text).tolist()
                stored_embedding = record["embeddings"][0]

                # Cosine similarity
                dot = sum(a * b for a, b in zip(query_embedding, stored_embedding, strict=False))
                norm_q = sum(a * a for a in query_embedding) ** 0.5
                norm_s = sum(a * a for a in stored_embedding) ** 0.5
                similarity = dot / (norm_q * norm_s) if norm_q and norm_s else 0.0

                return {"similarity": round(similarity, 4), "record_id": request.record_id}
        except Exception:
            continue

    raise HTTPException(status_code=404, detail=f"Record {request.record_id} not found")


@app.get("/count", dependencies=[Depends(verify_token)])
async def count(group: str = "default"):
    """Count records in a group."""
    collection = _get_collection(group)
    return {"count": collection.count(), "group": group}


@app.get("/ids", dependencies=[Depends(verify_token)])
async def get_ids(group: str = "default", doc_id: str = ""):
    """Get record IDs in a group, optionally filtered by doc_id."""
    collection = _get_collection(group)

    where_filter = None
    if doc_id:
        where_filter = {"doc_id": doc_id}

    result = collection.get(where=where_filter, include=[])
    return {"ids": result["ids"], "total": len(result["ids"])}


@app.get("/records", dependencies=[Depends(verify_token)])
async def get_records(group: str = "default", doc_id: str = "", limit: int = 100):
    """Get records with text and metadata."""
    collection = _get_collection(group)

    where_filter = None
    if doc_id:
        where_filter = {"doc_id": doc_id}

    result = collection.get(
        where=where_filter,
        include=["documents", "metadatas"],
        limit=limit,
    )

    records = []
    for i, rid in enumerate(result["ids"]):
        records.append(
            {
                "record_id": rid,
                "text": result["documents"][i] if result["documents"] else "",
                "metadata": result["metadatas"][i] if result["metadatas"] else {},
            }
        )

    return {"records": records, "total": len(records)}


@app.post("/delete/record", dependencies=[Depends(verify_token)])
async def delete_record(request: DeleteRecordRequest):
    """Delete a single record by ID (searches all collections)."""
    for col_info in chroma_client.list_collections():
        col = chroma_client.get_collection(col_info.name)
        try:
            existing = col.get(ids=[request.record_id], include=[])
            if existing and existing["ids"]:
                col.delete(ids=[request.record_id])
                return {"status": "ok", "deleted": request.record_id}
        except Exception:
            continue

    raise HTTPException(status_code=404, detail=f"Record {request.record_id} not found")


@app.post("/delete/document", dependencies=[Depends(verify_token)])
async def delete_document(request: DeleteDocumentRequest):
    """Delete all records for a doc_id within a group."""
    collection = _get_collection(request.group)

    result = collection.get(where={"doc_id": request.doc_id}, include=[])
    ids = result["ids"]

    if ids:
        collection.delete(ids=ids)

    return {"status": "ok", "deleted_count": len(ids), "doc_id": request.doc_id}


@app.post("/delete/group", dependencies=[Depends(verify_token)])
async def delete_group(request: DeleteGroupRequest):
    """Delete an entire group (collection)."""
    safe_name = request.group.replace("/", "_").replace("\\", "_")[:63]
    if not safe_name:
        safe_name = "default"

    try:
        chroma_client.delete_collection(safe_name)
        return {"status": "ok", "deleted_group": request.group}
    except Exception:
        return {"status": "ok", "deleted_group": request.group, "note": "collection did not exist"}


@app.post("/clear", dependencies=[Depends(verify_token)])
async def clear():
    """Delete all collections."""
    collections = chroma_client.list_collections()
    count = len(collections)
    for col_info in collections:
        chroma_client.delete_collection(col_info.name)
    return {"status": "ok", "deleted_collections": count}
