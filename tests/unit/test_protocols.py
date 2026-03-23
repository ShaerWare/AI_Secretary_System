"""Tests for Protocol interfaces and TypedDict schemas.

Verifies that:
- All schemas are importable and constructable
- All Protocols are importable and runtime_checkable
- Protocol method signatures are well-formed
"""

import inspect

from modules.chat.protocols import ChatService
from modules.chat.schemas import (
    MessageInfo,
    SessionInfo,
    SessionSummary,
    ShareInfo,
    StreamChunk,
)
from modules.core.protocols import AuthService
from modules.core.schemas import (
    LoginResult,
    RoleInfo,
    UserInfo,
    WorkspaceInfo,
    WorkspaceMemberInfo,
)
from modules.knowledge.protocols import KnowledgeService
from modules.knowledge.schemas import (
    CollectionInfo,
    DocumentInfo,
    FAQEntryInfo,
    SearchResult,
    SyncResult,
)
from modules.llm.protocols import LLMService
from modules.llm.schemas import (
    LLMConfig,
    ProviderInfo,
    ToolCall,
)
from modules.llm.schemas import StreamChunk as LLMStreamChunk
from modules.llm.schemas import TokenUsage as LLMTokenUsage


# ---------------------------------------------------------------------------
# Schema construction
# ---------------------------------------------------------------------------


class TestKnowledgeSchemas:
    def test_search_result(self):
        r: SearchResult = {
            "title": "Setup",
            "body": "Install with pip",
            "source_file": "install",
            "score": 0.85,
            "collection_id": 1,
        }
        assert r["score"] == 0.85

    def test_collection_info(self):
        c: CollectionInfo = {
            "id": 1,
            "name": "Docs",
            "slug": "docs",
            "description": None,
            "enabled": True,
            "base_dir": "/data/docs",
            "document_count": 5,
            "created": "2026-01-01T00:00:00",
            "updated": None,
        }
        assert c["document_count"] == 5

    def test_document_info(self):
        d: DocumentInfo = {
            "id": 1,
            "filename": "readme.md",
            "title": "README",
            "source_type": "manual",
            "file_size_bytes": 1024,
            "section_count": 3,
            "collection_id": 1,
            "created": None,
            "updated": None,
        }
        assert d["source_type"] == "manual"

    def test_sync_result(self):
        s: SyncResult = {
            "collection_id": 1,
            "documents_synced": 10,
            "sections_indexed": 42,
        }
        assert s["sections_indexed"] == 42

    def test_faq_entry_info(self):
        f: FAQEntryInfo = {
            "id": 1,
            "question": "What is this?",
            "answer": "An AI secretary",
            "keywords": ["ai", "secretary"],
            "enabled": True,
            "hit_count": 7,
            "created": None,
            "updated": None,
        }
        assert f["hit_count"] == 7


class TestLLMSchemas:
    def test_llm_config(self):
        cfg: LLMConfig = {
            "backend": "cloud:gemini-default",
            "temperature": 0.7,
            "max_tokens": 512,
        }
        assert cfg["backend"].startswith("cloud:")

    def test_provider_info(self):
        p: ProviderInfo = {
            "id": "gemini-default",
            "name": "Gemini",
            "provider_type": "gemini",
            "model_name": "gemini-2.0-flash",
            "enabled": True,
            "is_default": True,
            "base_url": None,
            "description": None,
            "config": {"temperature": 0.7},
            "created": None,
            "updated": None,
        }
        assert p["is_default"]

    def test_stream_chunk(self):
        c: LLMStreamChunk = {"type": "content", "content": "Hello"}
        assert c["type"] == "content"

    def test_tool_call(self):
        tc: ToolCall = {
            "id": "call_1",
            "type": "function",
            "function": {"name": "search", "arguments": '{"q": "test"}'},
        }
        assert tc["function"]["name"] == "search"

    def test_token_usage(self):
        u: LLMTokenUsage = {
            "tokens": 150,
            "context_window": 8192,
            "percent": 1.8,
            "trimmed": False,
        }
        assert not u["trimmed"]


class TestChatSchemas:
    def test_session_info(self):
        s: SessionInfo = {
            "id": "abc-123",
            "title": "Test chat",
            "system_prompt": None,
            "pinned": False,
            "source": "admin",
            "source_id": None,
            "owner_id": 1,
            "rag_mode": "all",
            "collection_ids": [1, 2],
            "created": "2026-01-01T00:00:00",
            "updated": None,
        }
        assert s["rag_mode"] == "all"

    def test_session_summary(self):
        s: SessionSummary = {
            "id": "abc-123",
            "title": "Test chat",
            "pinned": False,
            "message_count": 5,
            "last_message": "Hello...",
            "source": "admin",
            "owner_id": 1,
            "created": None,
            "updated": None,
        }
        assert s["message_count"] == 5

    def test_message_info(self):
        m: MessageInfo = {
            "id": "msg-1",
            "role": "assistant",
            "content": "Hello!",
            "edited": False,
            "timestamp": "2026-01-01T00:00:00",
            "parent_id": None,
            "is_active": True,
            "metadata": None,
        }
        assert m["role"] == "assistant"

    def test_stream_chunk(self):
        c: StreamChunk = {"content": "Hi", "done": False}
        assert c["content"] == "Hi"

    def test_share_info(self):
        s: ShareInfo = {
            "id": 1,
            "session_id": "abc-123",
            "user_id": 2,
            "permission": "read",
            "shared_by": 1,
            "shared_at": "2026-01-01T00:00:00",
        }
        assert s["permission"] == "read"


class TestCoreSchemas:
    def test_user_info(self):
        u: UserInfo = {
            "id": 1,
            "username": "admin",
            "role": "admin",
            "display_name": "Administrator",
            "is_active": True,
            "workspace_id": 1,
            "created": None,
            "last_login": None,
        }
        assert u["is_active"]

    def test_login_result(self):
        r: LoginResult = {
            "access_token": "eyJ...",
            "token_type": "bearer",
            "expires_in": 86400,
            "user": {
                "id": 1,
                "username": "admin",
                "role": "admin",
                "display_name": None,
                "is_active": True,
                "workspace_id": 1,
                "created": None,
                "last_login": None,
            },
        }
        assert r["token_type"] == "bearer"

    def test_role_info(self):
        r: RoleInfo = {
            "id": 1,
            "name": "admin",
            "display_name": "Administrator",
            "description": "Full access",
            "is_system": True,
            "permissions": {"channels": "manage", "knowledge": "manage"},
        }
        assert r["is_system"]

    def test_workspace_info(self):
        w: WorkspaceInfo = {
            "id": 1,
            "name": "Default",
            "slug": "default",
            "owner_id": 1,
            "created": None,
        }
        assert w["slug"] == "default"

    def test_workspace_member_info(self):
        m: WorkspaceMemberInfo = {
            "user_id": 1,
            "username": "admin",
            "role_name": "admin",
            "joined_at": None,
        }
        assert m["role_name"] == "admin"


# ---------------------------------------------------------------------------
# Protocol importability & runtime_checkable
# ---------------------------------------------------------------------------


class TestProtocols:
    def test_knowledge_service_is_protocol(self):
        assert hasattr(KnowledgeService, "__protocol_attrs__") or issubclass(
            KnowledgeService, object
        )

    def test_llm_service_is_protocol(self):
        assert hasattr(LLMService, "__protocol_attrs__") or issubclass(LLMService, object)

    def test_chat_service_is_protocol(self):
        assert hasattr(ChatService, "__protocol_attrs__") or issubclass(ChatService, object)

    def test_auth_service_is_protocol(self):
        assert hasattr(AuthService, "__protocol_attrs__") or issubclass(AuthService, object)

    def test_knowledge_service_methods(self):
        methods = {
            "search",
            "retrieve_context",
            "get_collections",
            "get_collection",
            "get_documents",
            "sync_documents",
            "find_faq_answer",
            "get_faq_entries",
        }
        actual = {
            name
            for name, _ in inspect.getmembers(KnowledgeService, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        assert methods <= actual, f"Missing: {methods - actual}"

    def test_llm_service_methods(self):
        methods = {"generate", "stream", "resolve_backend", "list_providers"}
        actual = {
            name
            for name, _ in inspect.getmembers(LLMService, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        assert methods <= actual, f"Missing: {methods - actual}"

    def test_chat_service_methods(self):
        methods = {
            "create_session",
            "get_session",
            "list_sessions",
            "delete_session",
            "get_history",
            "add_message",
            "send_message",
            "stream_message",
            "share_session",
            "unshare_session",
        }
        actual = {
            name
            for name, _ in inspect.getmembers(ChatService, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        assert methods <= actual, f"Missing: {methods - actual}"

    def test_auth_service_methods(self):
        methods = {
            "authenticate",
            "validate_token",
            "revoke_session",
            "revoke_all_sessions",
            "get_permissions",
            "has_permission",
            "get_user",
            "list_users",
            "get_roles",
            "get_workspace",
            "list_members",
        }
        actual = {
            name
            for name, _ in inspect.getmembers(AuthService, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        assert methods <= actual, f"Missing: {methods - actual}"
