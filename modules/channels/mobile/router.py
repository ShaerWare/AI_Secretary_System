"""Mobile app router — instances CRUD + user assignment + public config."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth_manager import User, require_permission, user_has_level, workspace_context
from modules.admin.service import resource_share_service
from modules.channels.mobile.push_service import fcm_push_service
from modules.channels.mobile.service import mobile_app_instance_service
from modules.chat.service import chat_service
from modules.monitoring.service import audit_service


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/mobile", tags=["mobile"])


# ============== Pydantic Models ==============


class MobileAppInstanceCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    enabled: bool = True
    llm_backend: str = "vllm"
    llm_persona: str = "anna"
    system_prompt: Optional[str] = None
    llm_params: Optional[dict] = None
    tts_engine: str = "xtts"
    tts_voice: str = "anna"
    tts_preset: Optional[str] = None
    rag_mode: str = "all"
    knowledge_collection_ids: Optional[List[int]] = None
    rate_limit_count: Optional[int] = None
    rate_limit_hours: Optional[int] = None


class MobileAppInstanceUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    llm_backend: Optional[str] = None
    llm_persona: Optional[str] = None
    system_prompt: Optional[str] = None
    llm_params: Optional[dict] = None
    tts_engine: Optional[str] = None
    tts_voice: Optional[str] = None
    tts_preset: Optional[str] = None
    rag_mode: Optional[str] = None
    knowledge_collection_ids: Optional[List[int]] = None
    rate_limit_count: Optional[int] = None
    rate_limit_hours: Optional[int] = None


class MobileShareRequest(BaseModel):
    user_id: int
    permission: str = "edit"


class MobileUpdateShareRequest(BaseModel):
    permission: str


RESOURCE_TYPE = "mobile_app_instance"


async def _check_owner_or_admin(instance_id: str, user: User) -> dict:
    """Verify user is owner or admin of the instance."""
    owner_id, ws_id = workspace_context(user, "channels")
    instance = await mobile_app_instance_service.get_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Mobile app instance not found")
    is_admin = user_has_level(user, "channels", "manage")
    is_owner = instance.get("owner_id") == user.id
    if not is_admin and not is_owner:
        raise HTTPException(status_code=403, detail="Only owner or admin can manage shares")
    return instance


async def _check_share_edit_permission(instance_id: str, user: User) -> None:
    """Check if shared user has edit permission."""
    is_admin = user_has_level(user, "channels", "manage")
    if is_admin:
        return
    perm = await resource_share_service.get_user_permission(RESOURCE_TYPE, instance_id, user.id)
    if perm == "view":
        raise HTTPException(status_code=403, detail="View-only access — editing not allowed")


# ============== Instance CRUD ==============


@router.get("/instances")
async def admin_list_mobile_instances(
    enabled_only: bool = False, user: User = Depends(require_permission("channels", "view"))
):
    """List all mobile app instances"""
    owner_id, ws_id = workspace_context(user, "channels")
    instances = await mobile_app_instance_service.list_instances(
        enabled_only=enabled_only, owner_id=owner_id, workspace_id=ws_id
    )

    # Enrich with share info
    instance_ids = [i["id"] for i in instances]
    share_counts = await resource_share_service.get_share_counts(RESOURCE_TYPE, instance_ids)
    shared_with_me = {}
    if owner_id is not None:
        shared_with_me = await resource_share_service.get_shared_resources_with_permissions(
            RESOURCE_TYPE, owner_id
        )
    for instance in instances:
        iid = instance["id"]
        instance["share_count"] = share_counts.get(iid, 0)
        instance["is_shared_with_me"] = iid in shared_with_me
        instance["share_permission"] = shared_with_me.get(iid)

    return {"instances": instances}


@router.post("/instances")
async def admin_create_mobile_instance(
    request: MobileAppInstanceCreateRequest,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Create a new mobile app instance"""
    owner_id, ws_id = workspace_context(user, "channels")
    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}
    kwargs["owner_id"] = owner_id
    kwargs["workspace_id"] = ws_id

    instance = await mobile_app_instance_service.create_instance(**kwargs)

    await audit_service.log(
        action="create",
        resource="mobile_app_instance",
        resource_id=instance["id"],
        user_id=user.username,
        details={"name": instance["name"]},
    )

    return {"instance": instance}


@router.get("/instances/{instance_id}")
async def admin_get_mobile_instance(
    instance_id: str, user: User = Depends(require_permission("channels", "view"))
):
    """Get a specific mobile app instance"""
    owner_id, ws_id = workspace_context(user, "channels")
    instance = await mobile_app_instance_service.get_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Mobile app instance not found")

    return {"instance": instance}


@router.put("/instances/{instance_id}")
async def admin_update_mobile_instance(
    instance_id: str,
    request: MobileAppInstanceUpdateRequest,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Update a mobile app instance"""
    owner_id, ws_id = workspace_context(user, "channels")
    existing = await mobile_app_instance_service.get_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Mobile app instance not found")

    await _check_share_edit_permission(instance_id, user)

    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}
    instance = await mobile_app_instance_service.update_instance(instance_id, **kwargs)

    await audit_service.log(
        action="update",
        resource="mobile_app_instance",
        resource_id=instance_id,
        user_id=user.username,
        details={"name": instance.get("name") if instance else None},
    )

    return {"instance": instance}


@router.delete("/instances/{instance_id}")
async def admin_delete_mobile_instance(
    instance_id: str, user: User = Depends(require_permission("channels", "edit"))
):
    """Delete a mobile app instance"""
    owner_id, ws_id = workspace_context(user, "channels")
    success = await mobile_app_instance_service.delete_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Mobile app instance not found")

    await resource_share_service.remove_all_shares(RESOURCE_TYPE, instance_id)

    await audit_service.log(
        action="delete",
        resource="mobile_app_instance",
        resource_id=instance_id,
        user_id=user.username,
    )

    return {"status": "ok", "message": f"Mobile app instance {instance_id} deleted"}


# ============== Public Config Endpoint (for mobile app) ==============


@router.get("/my-config")
async def get_my_mobile_config(user: User = Depends(require_permission("chat", "view"))):
    """Get current user's assigned mobile app instance config.
    Called by the mobile app after login.
    """
    instance = await mobile_app_instance_service.get_user_instance(user.id)
    if not instance:
        return {"instance": None}
    return {"instance": instance}


@router.get("/my-instances")
async def get_my_mobile_instances(user: User = Depends(require_permission("chat", "view"))):
    """List all mobile app instances assigned to current user.

    Used by the assistant switcher in admin web + mobile app: each instance
    is a separate persona (system_prompt + RAG collections). Frontend
    find-or-creates a per-user ChatSession with source="mobile" +
    source_id=<instance_id> for each.
    """
    instances = await mobile_app_instance_service.list_user_instances(user.id)
    return {"instances": instances}


@router.get("/instances/{instance_id}/my-session")
async def get_my_instance_session(
    instance_id: str, user: User = Depends(require_permission("chat", "view"))
):
    """Find-or-create the calling user's PRIVATE session for an assistant.

    Each user gets their own conversation per assistant instance (owner_id=user,
    source="mobile", source_id=instance_id) while the instance's prompt + RAG
    collections stay shared. Idempotent: repeated calls return the same session.
    """
    is_admin = user_has_level(user, "channels", "manage")
    if not is_admin:
        perm = await resource_share_service.get_user_permission(
            RESOURCE_TYPE, instance_id, user.id
        )
        if not perm:
            raise HTTPException(status_code=403, detail="Assistant not assigned to you")

    instance = await mobile_app_instance_service.get_instance(instance_id)
    if not instance or not instance.get("enabled", True):
        raise HTTPException(status_code=404, detail="Assistant not found")

    _, ws_id = workspace_context(user, "chat")

    # This is explicitly the caller's OWN private chat, so it is always owned by
    # the user (even admins) — not the workspace. Guarantees find-or-create is
    # idempotent regardless of the user's permission level.
    existing_id = await chat_service.find_user_instance_session(
        user.id, "mobile", instance_id
    )
    if existing_id:
        return {"session_id": existing_id, "created": False}

    # Create a new one, inheriting the assistant's persona + RAG config.
    session = await chat_service.create_session(
        instance.get("name"),
        instance.get("system_prompt"),
        "mobile",
        instance_id,
        owner_id=user.id,
        rag_mode=instance.get("rag_mode"),
        workspace_id=ws_id,
    )
    collection_ids = instance.get("knowledge_collection_ids")
    if collection_ids:
        updated = await chat_service.update_session(
            session["id"], knowledge_collection_ids=collection_ids
        )
        if updated:
            session = updated

    return {"session_id": session["id"], "created": True}


# ============== Version check ==============


class VersionInfoResponse(BaseModel):
    version_name: str
    version_code: int
    apk_url: str
    release_notes: Optional[str] = None


@router.get("/version", response_model=VersionInfoResponse)
async def get_latest_version():
    """Return the latest known mobile app version.

    The mobile app calls this on startup, compares with its own versionCode,
    and shows an update banner if a newer build is available.

    Values are read from env (updated on deploy), not hardcoded in code so
    production can bump version without a release.
    """
    import os

    return VersionInfoResponse(
        version_name=os.getenv("MOBILE_LATEST_VERSION_NAME", "1.6"),
        version_code=int(os.getenv("MOBILE_LATEST_VERSION_CODE", "9")),
        apk_url=os.getenv(
            "MOBILE_LATEST_APK_URL",
            "https://github.com/ShaerWare/AI_Secretary_System/releases/latest",
        ),
        release_notes=os.getenv("MOBILE_LATEST_RELEASE_NOTES"),
    )


# ============== Push notifications ==============


class PushRegisterRequest(BaseModel):
    token: str
    platform: str = "android"
    app_version: Optional[str] = None
    build_number: Optional[str] = None


@router.post("/push/register")
async def register_push_token(
    request: PushRegisterRequest,
    user: User = Depends(require_permission("chat", "view")),
):
    """Register FCM device token for the current user.

    Called by the mobile app after successful login / on app start with fresh token.
    Same token across re-logins updates ownership and timestamps.
    """
    if not request.token or len(request.token) < 20:
        raise HTTPException(status_code=400, detail="Invalid token")
    await fcm_push_service.register_token(
        user_id=user.id,
        token=request.token,
        platform=request.platform,
        app_version=request.app_version,
        build_number=request.build_number,
    )
    return {"status": "ok"}


@router.post("/push/unregister")
async def unregister_push_tokens(
    user: User = Depends(require_permission("chat", "view")),
):
    """Delete all FCM tokens for the current user. Called on logout."""
    await fcm_push_service.unregister_user(user.id)
    return {"status": "ok"}


class PushTestRequest(BaseModel):
    title: str = "Test push"
    body: str = "Hello from AI-Секретарь"
    to_all: bool = False
    user_id: Optional[int] = None


@router.post("/push/test")
async def send_test_push(
    request: PushTestRequest,
    user: User = Depends(require_permission("channels", "manage")),
):
    """Send a test push notification.

    Admin-only. If `to_all=true` — broadcast to every registered device.
    If `user_id` is given — send only to that user's devices.
    Otherwise — send to the requesting admin's devices.
    """
    if not fcm_push_service.enabled:
        raise HTTPException(
            status_code=503,
            detail="FCM not configured (FCM_PROJECT_ID + FCM_SERVICE_ACCOUNT_FILE env vars)",
        )
    target_user_id = request.user_id if request.user_id else user.id
    if request.to_all:
        delivered = await fcm_push_service.send_to_all(
            title=request.title,
            body=request.body,
            data={"type": "test"},
        )
    else:
        delivered = await fcm_push_service.send_to_user(
            user_id=target_user_id,
            title=request.title,
            body=request.body,
            data={"type": "test"},
        )
    return {"status": "ok", "delivered": delivered, "fcm_enabled": fcm_push_service.enabled}


@router.get("/push/status")
async def get_push_status(
    user: User = Depends(require_permission("channels", "manage")),
):
    """Check FCM configuration status. Admin-only."""
    from sqlalchemy import func, select

    from db.database import get_async_session
    from modules.channels.mobile.models import MobilePushToken

    total = 0
    async for session in get_async_session():
        result = await session.execute(select(func.count()).select_from(MobilePushToken))
        total = result.scalar() or 0

    return {
        "fcm_enabled": fcm_push_service.enabled,
        "project_id": fcm_push_service.project_id,
        "service_account_file": fcm_push_service.service_account_file,
        "total_tokens": total,
    }


# ============== Resource Sharing (user assignment) ==============


@router.get("/instances/{instance_id}/shares")
async def get_mobile_shares(
    instance_id: str, user: User = Depends(require_permission("channels", "view"))
):
    """List users assigned to a mobile app instance."""
    await _check_owner_or_admin(instance_id, user)
    shares = await resource_share_service.get_shares(RESOURCE_TYPE, instance_id)
    return {"shares": shares}


@router.post("/instances/{instance_id}/shares")
async def add_mobile_share(
    instance_id: str,
    request: MobileShareRequest,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Assign a user to a mobile app instance."""
    await _check_owner_or_admin(instance_id, user)

    if request.permission not in ("view", "edit"):
        raise HTTPException(status_code=400, detail="Permission must be 'view' or 'edit'")
    if request.user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot share with yourself")

    share = await resource_share_service.add_share(
        RESOURCE_TYPE,
        instance_id,
        request.user_id,
        request.permission,
        shared_by=user.id,
    )

    await audit_service.log(
        action="share",
        resource="mobile_app_instance",
        resource_id=instance_id,
        user_id=user.username,
        details={"shared_with": request.user_id, "permission": request.permission},
    )

    return {"share": share}


@router.put("/instances/{instance_id}/shares/{target_user_id}")
async def update_mobile_share(
    instance_id: str,
    target_user_id: int,
    request: MobileUpdateShareRequest,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Update user permission for a mobile app instance."""
    await _check_owner_or_admin(instance_id, user)

    if request.permission not in ("view", "edit"):
        raise HTTPException(status_code=400, detail="Permission must be 'view' or 'edit'")

    success = await resource_share_service.update_permission(
        RESOURCE_TYPE, instance_id, target_user_id, request.permission
    )
    if not success:
        raise HTTPException(status_code=404, detail="Share not found")

    return {"status": "ok"}


@router.delete("/instances/{instance_id}/shares/{target_user_id}")
async def remove_mobile_share(
    instance_id: str,
    target_user_id: int,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Remove user from a mobile app instance."""
    await _check_owner_or_admin(instance_id, user)

    success = await resource_share_service.remove_share(RESOURCE_TYPE, instance_id, target_user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Share not found")

    await audit_service.log(
        action="unshare",
        resource="mobile_app_instance",
        resource_id=instance_id,
        user_id=user.username,
        details={"removed_user": target_user_id},
    )

    return {"status": "ok"}
