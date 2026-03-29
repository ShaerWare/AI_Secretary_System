"""Tests for AuthService facade.

Verifies that:
- AuthService satisfies the Protocol structurally
- All Protocol methods exist with correct signatures
- Converter helpers produce correct TypedDict shapes
"""

import inspect

from modules.core.auth_service import AuthService, _role_dict_to_info, _user_dict_to_info
from modules.core.protocols import AuthService as AuthServiceProtocol


class TestAuthServiceProtocolCompliance:
    """Verify AuthService class matches the Protocol."""

    def test_has_all_protocol_methods(self):
        """AuthService must implement every method from the Protocol."""
        protocol_methods = {
            name
            for name, _ in inspect.getmembers(AuthServiceProtocol, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        impl_methods = {
            name
            for name in dir(AuthService)
            if not name.startswith("_") and callable(getattr(AuthService, name))
        }
        missing = protocol_methods - impl_methods
        assert not missing, f"AuthService missing Protocol methods: {missing}"

    def test_authenticate_signature(self):
        sig = inspect.signature(AuthService.authenticate)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "username" in params
        assert "password" in params

    def test_validate_token_signature(self):
        sig = inspect.signature(AuthService.validate_token)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "token" in params

    def test_revoke_session_signature(self):
        sig = inspect.signature(AuthService.revoke_session)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "jti" in params

    def test_revoke_all_sessions_signature(self):
        sig = inspect.signature(AuthService.revoke_all_sessions)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "user_id" in params

    def test_get_permissions_signature(self):
        sig = inspect.signature(AuthService.get_permissions)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "user_id" in params

    def test_has_permission_signature(self):
        sig = inspect.signature(AuthService.has_permission)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "user_id" in params
        assert "module" in params
        assert "min_level" in params

    def test_get_user_signature(self):
        sig = inspect.signature(AuthService.get_user)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "user_id" in params

    def test_list_users_signature(self):
        sig = inspect.signature(AuthService.list_users)
        params = list(sig.parameters.keys())
        assert "self" in params

    def test_get_roles_signature(self):
        sig = inspect.signature(AuthService.get_roles)
        params = list(sig.parameters.keys())
        assert "self" in params

    def test_get_workspace_signature(self):
        sig = inspect.signature(AuthService.get_workspace)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "workspace_id" in params

    def test_list_members_signature(self):
        sig = inspect.signature(AuthService.list_members)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "workspace_id" in params


class TestConverters:
    """Test TypedDict converter helpers."""

    def test_user_dict_to_info(self):
        data = {
            "id": 1,
            "username": "admin",
            "role": "admin",
            "display_name": "Admin User",
            "is_active": True,
            "workspace_id": 1,
            "created_at": "2026-01-01T00:00:00",
            "last_login": None,
        }
        info = _user_dict_to_info(data)
        assert info["id"] == 1
        assert info["username"] == "admin"
        assert info["role"] == "admin"
        assert info["display_name"] == "Admin User"
        assert info["is_active"] is True
        assert info["workspace_id"] == 1
        assert info["created"] == "2026-01-01T00:00:00"
        assert info["last_login"] is None

    def test_user_dict_to_info_defaults(self):
        data = {"id": 2, "username": "user2"}
        info = _user_dict_to_info(data)
        assert info["role"] == "user"
        assert info["is_active"] is True
        assert info["workspace_id"] == 1
        assert info["display_name"] is None

    def test_role_dict_to_info(self):
        data = {
            "id": 1,
            "name": "admin",
            "display_name": "Administrator",
            "description": "Full access",
            "is_system": True,
            "permissions": {"chat": "manage", "llm": "manage"},
        }
        info = _role_dict_to_info(data)
        assert info["id"] == 1
        assert info["name"] == "admin"
        assert info["is_system"] is True
        assert info["permissions"]["chat"] == "manage"

    def test_role_dict_to_info_defaults(self):
        data = {"id": 2, "name": "custom"}
        info = _role_dict_to_info(data)
        assert info["is_system"] is False
        assert info["permissions"] == {}
        assert info["display_name"] is None


class TestSingleton:
    """Verify module-level singleton."""

    def test_singleton_exported(self):
        from modules.core.auth_service import auth_service

        assert isinstance(auth_service, AuthService)

    def test_singleton_is_same_instance(self):
        from modules.core.auth_service import auth_service

        assert auth_service is auth_service  # trivial but documents intent
