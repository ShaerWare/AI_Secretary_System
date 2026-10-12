"""Own password/profile edits must not depend on the admin-only ``settings`` module."""

import pytest
from fastapi import HTTPException

from auth_manager import User
from modules.core.router_auth import require_own_account_edit


@pytest.mark.parametrize("role", ["user", "web", "admin"])
async def test_regular_roles_may_edit_own_account(role):
    user = User(id=97, username="A", role=role)
    assert await require_own_account_edit(user) is user


async def test_guest_cannot_edit_shared_demo_account():
    with pytest.raises(HTTPException) as exc:
        await require_own_account_edit(User(id=2, username="demo", role="guest"))
    assert exc.value.status_code == 403


def test_rate_limited_auth_endpoints_take_starlette_request_as_request():
    """slowapi looks the request up by the parameter *name* ``request``.

    ``change-password`` once had its body there (``http_request`` held the real one),
    and every call that got past the permission check died with a 500.
    """
    import inspect

    from starlette.requests import Request

    from modules.core.router_auth import admin_change_password, admin_login

    for endpoint in (admin_login, admin_change_password):
        params = inspect.signature(endpoint).parameters
        assert params["request"].annotation is Request, endpoint.__name__
