"""Tests for LLMService facade.

Verifies that:
- LLMServiceImpl satisfies the Protocol structurally
- All Protocol methods exist with correct signatures
- Converter helpers produce correct TypedDict shapes
"""

import inspect

from modules.llm.facade import (
    LLMServiceImpl,
    _to_provider_info,
    _to_stream_chunk,
)
from modules.llm.protocols import LLMService as LLMServiceProtocol


class TestLLMServiceProtocolCompliance:
    """Verify LLMServiceImpl matches the Protocol."""

    def test_has_all_protocol_methods(self):
        """LLMServiceImpl must implement every method from the Protocol."""
        protocol_methods = {
            name
            for name, _ in inspect.getmembers(LLMServiceProtocol, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        impl_methods = {
            name
            for name in dir(LLMServiceImpl)
            if not name.startswith("_") and callable(getattr(LLMServiceImpl, name))
        }
        missing = protocol_methods - impl_methods
        assert not missing, f"LLMServiceImpl missing Protocol methods: {missing}"

    def test_generate_signature(self):
        sig = inspect.signature(LLMServiceImpl.generate)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "messages" in params
        assert "config" in params

    def test_stream_signature(self):
        sig = inspect.signature(LLMServiceImpl.stream)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "messages" in params
        assert "config" in params

    def test_resolve_backend_signature(self):
        sig = inspect.signature(LLMServiceImpl.resolve_backend)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "backend_id" in params

    def test_list_providers_signature(self):
        sig = inspect.signature(LLMServiceImpl.list_providers)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "enabled_only" in params
        assert "workspace_id" in params


class TestConverters:
    """Test TypedDict converter helpers."""

    def test_to_provider_info(self):
        data = {
            "id": "gemini-default",
            "name": "Gemini Pro",
            "provider_type": "gemini",
            "model_name": "gemini-2.0-flash",
            "enabled": True,
            "is_default": True,
            "base_url": None,
            "description": "Default Gemini provider",
            "config": {
                "temperature": 0.7,
                "max_tokens": 2048,
                "top_p": 0.9,
            },
            "created": "2026-01-01T00:00:00",
            "updated": "2026-01-02T00:00:00",
        }
        info = _to_provider_info(data)
        assert info["id"] == "gemini-default"
        assert info["name"] == "Gemini Pro"
        assert info["provider_type"] == "gemini"
        assert info["model_name"] == "gemini-2.0-flash"
        assert info["enabled"] is True
        assert info["is_default"] is True
        assert info["config"]["temperature"] == 0.7
        assert info["config"]["max_tokens"] == 2048

    def test_to_provider_info_defaults(self):
        data = {"id": "test", "name": "Test"}
        info = _to_provider_info(data)
        assert info["provider_type"] == "custom"
        assert info["model_name"] == ""
        assert info["enabled"] is True
        assert info["is_default"] is False
        assert info["base_url"] is None
        assert info["description"] is None
        assert info["config"]["temperature"] == 0.7
        assert info["config"]["max_tokens"] == 1024

    def test_to_provider_info_none_config(self):
        data = {"id": "x", "name": "X", "config": None}
        info = _to_provider_info(data)
        assert info["config"]["temperature"] == 0.7

    def test_to_stream_chunk_from_string(self):
        chunk = _to_stream_chunk("Hello")
        assert chunk["type"] == "content"
        assert chunk["content"] == "Hello"

    def test_to_stream_chunk_from_content_dict(self):
        chunk = _to_stream_chunk({"type": "content", "content": "world"})
        assert chunk["type"] == "content"
        assert chunk["content"] == "world"

    def test_to_stream_chunk_from_tool_calls_dict(self):
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "search", "arguments": '{"q": "test"}'},
            }
        ]
        chunk = _to_stream_chunk({"type": "tool_calls", "tool_calls": tool_calls})
        assert chunk["type"] == "tool_calls"
        assert len(chunk["tool_calls"]) == 1
        assert chunk["tool_calls"][0]["function"]["name"] == "search"

    def test_to_stream_chunk_from_empty_dict(self):
        chunk = _to_stream_chunk({})
        assert chunk["type"] == "content"
        assert chunk["content"] == ""


class TestModuleSingleton:
    """Verify module-level singleton behavior."""

    def test_singleton_initially_none(self):
        from modules.llm.facade import llm_service_facade

        assert llm_service_facade is None or isinstance(llm_service_facade, LLMServiceImpl)
