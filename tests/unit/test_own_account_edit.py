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
