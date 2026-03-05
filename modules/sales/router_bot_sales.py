# modules/sales/router_bot_sales.py
"""Sales bot router — CRUD for agent prompts, quiz, segments, followups,
testimonials, hardware specs, A/B tests, subscribers, GitHub config, events/funnel."""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth_manager import User, require_permission
from db.database import AsyncSessionLocal
from db.repositories.bot_ab_test import BotAbTestRepository
from db.repositories.bot_agent_prompt import BotAgentPromptRepository
from db.repositories.bot_discovery import BotDiscoveryRepository
from db.repositories.bot_event import BotEventRepository
from db.repositories.bot_followup import BotFollowupQueueRepository, BotFollowupRuleRepository
from db.repositories.bot_github import BotGithubRepository
from db.repositories.bot_hardware import BotHardwareRepository
from db.repositories.bot_instance import BotInstanceRepository
from db.repositories.bot_quiz import BotQuizRepository
from db.repositories.bot_segment import BotSegmentRepository
from db.repositories.bot_subscriber import BotSubscriberRepository
from db.repositories.bot_testimonial import BotTestimonialRepository
from db.repositories.bot_user_profile import BotUserProfileRepository
from modules.channels.telegram.service import bot_instance_service
from modules.monitoring.service import audit_service


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/telegram/instances/{instance_id}", tags=["bot-sales"])


# ============== Helper ==============


async def _check_instance(instance_id: str) -> None:
    """Raise 404 if instance doesn't exist."""
    exists = await bot_instance_service.instance_exists(instance_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Bot instance not found")


# ============== Agent Prompts ==============


class AgentPromptRequest(BaseModel):
    prompt_key: str
    name: str
    description: Optional[str] = None
    system_prompt: str
    temperature: float = 0.7
    max_tokens: int = 1024
    enabled: bool = True
    order: int = 0


class AgentPromptUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    enabled: Optional[bool] = None
    order: Optional[int] = None


@router.get("/prompts")
async def list_prompts(instance_id: str, user: User = Depends(require_permission("sales", "view"))):
    """List all agent prompts for bot instance."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotAgentPromptRepository(session)
        prompts = await repo.list_by_bot(instance_id)
    return {"prompts": prompts}


@router.post("/prompts")
async def create_prompt(
    instance_id: str,
    request: AgentPromptRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Create agent prompt."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotAgentPromptRepository(session)
        prompt = await repo.create_prompt(bot_id=instance_id, **request.model_dump())
        await session.commit()
    await audit_service.log(
        action="create",
        resource="bot_agent_prompt",
        resource_id=request.prompt_key,
        user_id=user.username,
    )
    return {"prompt": prompt}


@router.put("/prompts/{prompt_id}")
async def update_prompt(
    instance_id: str,
    prompt_id: int,
    request: AgentPromptUpdateRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Update agent prompt."""
    await _check_instance(instance_id)
    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}
    async with AsyncSessionLocal() as session:
        repo = BotAgentPromptRepository(session)
        prompt = await repo.update_prompt(prompt_id, **kwargs)
        await session.commit()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"prompt": prompt}


@router.delete("/prompts/{prompt_id}")
async def delete_prompt(
    instance_id: str, prompt_id: int, user: User = Depends(require_permission("sales", "edit"))
):
    """Delete agent prompt."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotAgentPromptRepository(session)
        ok = await repo.delete_prompt(prompt_id)
        await session.commit()
    if not ok:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"status": "ok"}


# ============== Quiz Questions ==============


class QuizQuestionRequest(BaseModel):
    question_key: str
    text: str
    order: int = 0
    enabled: bool = True
    options: List[dict] = []


class QuizQuestionUpdateRequest(BaseModel):
    text: Optional[str] = None
    order: Optional[int] = None
    enabled: Optional[bool] = None
    options: Optional[List[dict]] = None


@router.get("/quiz")
async def list_quiz_questions(
    instance_id: str, user: User = Depends(require_permission("sales", "view"))
):
    """List all quiz questions for bot."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotQuizRepository(session)
        questions = await repo.list_by_bot(instance_id)
    return {"questions": questions}


@router.post("/quiz")
async def create_quiz_question(
    instance_id: str,
    request: QuizQuestionRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Create quiz question."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotQuizRepository(session)
        question = await repo.create_question(bot_id=instance_id, **request.model_dump())
        await session.commit()
    return {"question": question}


@router.put("/quiz/{question_id}")
async def update_quiz_question(
    instance_id: str,
    question_id: int,
    request: QuizQuestionUpdateRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Update quiz question."""
    await _check_instance(instance_id)
    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}
    async with AsyncSessionLocal() as session:
        repo = BotQuizRepository(session)
        question = await repo.update_question(question_id, **kwargs)
        await session.commit()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"question": question}


@router.delete("/quiz/{question_id}")
async def delete_quiz_question(
    instance_id: str, question_id: int, user: User = Depends(require_permission("sales", "edit"))
):
    """Delete quiz question."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotQuizRepository(session)
        ok = await repo.delete_question(question_id)
        await session.commit()
    if not ok:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"status": "ok"}


# ============== Segments ==============


class SegmentRequest(BaseModel):
    segment_key: str
    name: str
    description: Optional[str] = None
    path: str  # diy, basic, custom
    match_rules: dict = {}
    priority: int = 0
    agent_prompt_key: Optional[str] = None
    enabled: bool = True


class SegmentUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    path: Optional[str] = None
    match_rules: Optional[dict] = None
    priority: Optional[int] = None
    agent_prompt_key: Optional[str] = None
    enabled: Optional[bool] = None


@router.get("/segments")
async def list_segments(
    instance_id: str, user: User = Depends(require_permission("sales", "view"))
):
    """List all segments for bot."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotSegmentRepository(session)
        segments = await repo.list_by_bot(instance_id)
    return {"segments": segments}


@router.post("/segments")
async def create_segment(
    instance_id: str,
    request: SegmentRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Create segment."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotSegmentRepository(session)
        segment = await repo.create_segment(bot_id=instance_id, **request.model_dump())
        await session.commit()
    return {"segment": segment}


@router.put("/segments/{segment_id}")
async def update_segment(
    instance_id: str,
    segment_id: int,
    request: SegmentUpdateRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Update segment."""
    await _check_instance(instance_id)
    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}
    async with AsyncSessionLocal() as session:
        repo = BotSegmentRepository(session)
        segment = await repo.update_segment(segment_id, **kwargs)
        await session.commit()
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")
    return {"segment": segment}


@router.delete("/segments/{segment_id}")
async def delete_segment(
    instance_id: str, segment_id: int, user: User = Depends(require_permission("sales", "edit"))
):
    """Delete segment."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotSegmentRepository(session)
        ok = await repo.delete_segment(segment_id)
        await session.commit()
    if not ok:
        raise HTTPException(status_code=404, detail="Segment not found")
    return {"status": "ok"}


# ============== Follow-up Rules ==============


class FollowupRuleRequest(BaseModel):
    name: str
    trigger: str
    delay_hours: int = 24
    segment_filter: Optional[str] = None
    message_template: str
    buttons: List[dict] = []
    max_sends: int = 2
    enabled: bool = True
    order: int = 0


class FollowupRuleUpdateRequest(BaseModel):
    name: Optional[str] = None
    trigger: Optional[str] = None
    delay_hours: Optional[int] = None
    segment_filter: Optional[str] = None
    message_template: Optional[str] = None
    buttons: Optional[List[dict]] = None
    max_sends: Optional[int] = None
    enabled: Optional[bool] = None
    order: Optional[int] = None


@router.get("/followups")
async def list_followup_rules(
    instance_id: str, user: User = Depends(require_permission("sales", "view"))
):
    """List all follow-up rules for bot."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotFollowupRuleRepository(session)
        rules = await repo.list_rules_by_bot(instance_id)
    return {"rules": rules}


@router.post("/followups")
async def create_followup_rule(
    instance_id: str,
    request: FollowupRuleRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Create follow-up rule."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotFollowupRuleRepository(session)
        rule = await repo.create_rule(bot_id=instance_id, **request.model_dump())
        await session.commit()
    return {"rule": rule}


@router.put("/followups/{rule_id}")
async def update_followup_rule(
    instance_id: str,
    rule_id: int,
    request: FollowupRuleUpdateRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Update follow-up rule."""
    await _check_instance(instance_id)
    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}
    async with AsyncSessionLocal() as session:
        repo = BotFollowupRuleRepository(session)
        rule = await repo.update_rule(rule_id, **kwargs)
        await session.commit()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"rule": rule}


@router.delete("/followups/{rule_id}")
async def delete_followup_rule(
    instance_id: str, rule_id: int, user: User = Depends(require_permission("sales", "edit"))
):
    """Delete follow-up rule."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotFollowupRuleRepository(session)
        ok = await repo.delete_rule(rule_id)
        await session.commit()
    if not ok:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"status": "ok"}


@router.get("/followups/queue")
async def get_followup_queue(
    instance_id: str,
    status: str = "pending",
    user: User = Depends(require_permission("sales", "view")),
):
    """Get follow-up queue for bot."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotFollowupQueueRepository(session)
        queue = await repo.get_queue_by_bot(instance_id, status=status)
    return {"queue": queue}


# ============== Testimonials ==============


class TestimonialRequest(BaseModel):
    text: str
    author: str = "***"
    rating: int = 5
    enabled: bool = True
    order: int = 0


class TestimonialUpdateRequest(BaseModel):
    text: Optional[str] = None
    author: Optional[str] = None
    rating: Optional[int] = None
    enabled: Optional[bool] = None
    order: Optional[int] = None


@router.get("/testimonials")
async def list_testimonials(
    instance_id: str, user: User = Depends(require_permission("sales", "view"))
):
    """List all testimonials for bot."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotTestimonialRepository(session)
        testimonials = await repo.list_by_bot(instance_id)
    return {"testimonials": testimonials}


@router.post("/testimonials")
async def create_testimonial(
    instance_id: str,
    request: TestimonialRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Create testimonial."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotTestimonialRepository(session)
        testimonial = await repo.create_testimonial(bot_id=instance_id, **request.model_dump())
        await session.commit()
    return {"testimonial": testimonial}


@router.put("/testimonials/{testimonial_id}")
async def update_testimonial(
    instance_id: str,
    testimonial_id: int,
    request: TestimonialUpdateRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Update testimonial."""
    await _check_instance(instance_id)
    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}
    async with AsyncSessionLocal() as session:
        repo = BotTestimonialRepository(session)
        testimonial = await repo.update_testimonial(testimonial_id, **kwargs)
        await session.commit()
    if not testimonial:
        raise HTTPException(status_code=404, detail="Testimonial not found")
    return {"testimonial": testimonial}


@router.delete("/testimonials/{testimonial_id}")
async def delete_testimonial(
    instance_id: str, testimonial_id: int, user: User = Depends(require_permission("sales", "edit"))
):
    """Delete testimonial."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotTestimonialRepository(session)
        ok = await repo.delete_testimonial(testimonial_id)
        await session.commit()
    if not ok:
        raise HTTPException(status_code=404, detail="Testimonial not found")
    return {"status": "ok"}


# ============== Hardware Specs ==============


class HardwareSpecRequest(BaseModel):
    gpu_name: str
    gpu_vram_gb: int
    gpu_family: str
    recommended_llm: str
    recommended_tts: str = "xtts"
    recommended_stt: str = "whisper"
    quality_stars: int = 3
    speed_note: Optional[str] = None
    notes: Optional[str] = None
    enabled: bool = True
    order: int = 0


class HardwareSpecUpdateRequest(BaseModel):
    gpu_name: Optional[str] = None
    gpu_vram_gb: Optional[int] = None
    gpu_family: Optional[str] = None
    recommended_llm: Optional[str] = None
    recommended_tts: Optional[str] = None
    recommended_stt: Optional[str] = None
    quality_stars: Optional[int] = None
    speed_note: Optional[str] = None
    notes: Optional[str] = None
    enabled: Optional[bool] = None
    order: Optional[int] = None


@router.get("/hardware")
async def list_hardware_specs(
    instance_id: str, user: User = Depends(require_permission("sales", "view"))
):
    """List all hardware specs for bot."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotHardwareRepository(session)
        specs = await repo.list_by_bot(instance_id)
    return {"specs": specs}


@router.post("/hardware")
async def create_hardware_spec(
    instance_id: str,
    request: HardwareSpecRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Create hardware spec."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotHardwareRepository(session)
        spec = await repo.create_spec(bot_id=instance_id, **request.model_dump())
        await session.commit()
    return {"spec": spec}


@router.put("/hardware/{spec_id}")
async def update_hardware_spec(
    instance_id: str,
    spec_id: int,
    request: HardwareSpecUpdateRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Update hardware spec."""
    await _check_instance(instance_id)
    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}
    async with AsyncSessionLocal() as session:
        repo = BotHardwareRepository(session)
        spec = await repo.update_spec(spec_id, **kwargs)
        await session.commit()
    if not spec:
        raise HTTPException(status_code=404, detail="Hardware spec not found")
    return {"spec": spec}


@router.delete("/hardware/{spec_id}")
async def delete_hardware_spec(
    instance_id: str, spec_id: int, user: User = Depends(require_permission("sales", "edit"))
):
    """Delete hardware spec."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotHardwareRepository(session)
        ok = await repo.delete_spec(spec_id)
        await session.commit()
    if not ok:
        raise HTTPException(status_code=404, detail="Hardware spec not found")
    return {"status": "ok"}


@router.get("/hardware/audit")
async def audit_hardware(
    instance_id: str, gpu: str, user: User = Depends(require_permission("sales", "view"))
):
    """Find hardware spec by GPU name (fuzzy match)."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotHardwareRepository(session)
        specs = await repo.find_by_gpu(instance_id, gpu)
    return {"specs": specs}


# ============== A/B Tests ==============


class AbTestRequest(BaseModel):
    name: str
    test_key: str
    variants: dict = {}
    metric: str = ""
    min_sample: int = 100
    active: bool = True


class AbTestUpdateRequest(BaseModel):
    name: Optional[str] = None
    variants: Optional[dict] = None
    metric: Optional[str] = None
    min_sample: Optional[int] = None
    active: Optional[bool] = None
    results: Optional[dict] = None


@router.get("/abtests")
async def list_ab_tests(
    instance_id: str, user: User = Depends(require_permission("sales", "view"))
):
    """List all A/B tests for bot."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotAbTestRepository(session)
        tests = await repo.list_by_bot(instance_id)
    return {"tests": tests}


@router.post("/abtests")
async def create_ab_test(
    instance_id: str,
    request: AbTestRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Create A/B test."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotAbTestRepository(session)
        test = await repo.create_test(bot_id=instance_id, **request.model_dump())
        await session.commit()
    return {"test": test}


@router.put("/abtests/{test_id}")
async def update_ab_test(
    instance_id: str,
    test_id: int,
    request: AbTestUpdateRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Update A/B test."""
    await _check_instance(instance_id)
    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}
    async with AsyncSessionLocal() as session:
        repo = BotAbTestRepository(session)
        test = await repo.update_test(test_id, **kwargs)
        await session.commit()
    if not test:
        raise HTTPException(status_code=404, detail="A/B test not found")
    return {"test": test}


@router.delete("/abtests/{test_id}")
async def delete_ab_test(
    instance_id: str, test_id: int, user: User = Depends(require_permission("sales", "edit"))
):
    """Delete A/B test."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotAbTestRepository(session)
        ok = await repo.delete_test(test_id)
        await session.commit()
    if not ok:
        raise HTTPException(status_code=404, detail="A/B test not found")
    return {"status": "ok"}


# ============== Subscribers ==============


class RegisterUserRequest(BaseModel):
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


@router.post("/register-user")
async def register_user(
    instance_id: str,
    request: RegisterUserRequest,
    user: User = Depends(require_permission("telegram", "edit")),
):
    """Register a Telegram user as subscriber and create a session link.

    Called by bot subprocesses via BOT_INTERNAL_TOKEN to sync users to central DB.
    Idempotent: re-subscribes and updates profile if user already exists.
    """
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        # Upsert bot_subscribers
        sub_repo = BotSubscriberRepository(session)
        subscriber = await sub_repo.subscribe(
            bot_id=instance_id,
            user_id=request.user_id,
            username=request.username,
            first_name=request.first_name,
        )
        # Upsert telegram_sessions (link user to bot, no chat session yet)
        from db.repositories.telegram import TelegramRepository

        tg_repo = TelegramRepository(session, bot_id=instance_id)
        existing_session = await tg_repo.get_session(request.user_id)
        if not existing_session:
            # Create a placeholder session — will be updated when user chats
            import uuid

            placeholder_id = f"tg_{instance_id}_{request.user_id}_{uuid.uuid4().hex[:8]}"
            await tg_repo.set_session(
                user_id=request.user_id,
                chat_session_id=placeholder_id,
                username=request.username,
                first_name=request.first_name,
                last_name=request.last_name,
            )
        else:
            # Update profile info on existing session
            await tg_repo.set_session(
                user_id=request.user_id,
                chat_session_id=existing_session,
                username=request.username,
                first_name=request.first_name,
                last_name=request.last_name,
            )
        await session.commit()
    return {"status": "ok", "subscriber": subscriber}


@router.get("/subscribers")
async def list_subscribers(
    instance_id: str, user: User = Depends(require_permission("sales", "view"))
):
    """List all subscribers for bot."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotSubscriberRepository(session)
        subscribers = await repo.list_by_bot(instance_id)
    return {"subscribers": subscribers}


@router.get("/subscribers/stats")
async def get_subscriber_stats(
    instance_id: str, user: User = Depends(require_permission("sales", "view"))
):
    """Get subscriber stats."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotSubscriberRepository(session)
        count = await repo.count_subscribers(instance_id)
    return {"stats": {"total_active": count}}


class BroadcastRequest(BaseModel):
    message: str
    user_ids: List[int] = []
    parse_mode: str = "HTML"


@router.post("/broadcast")
async def broadcast_message(
    instance_id: str,
    request: BroadcastRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Send a message to selected subscribers (or all active if user_ids is empty)."""
    await _check_instance(instance_id)

    # Get bot token
    async with AsyncSessionLocal() as session:
        inst_repo = BotInstanceRepository(session)
        instance_data = await inst_repo.get_instance_with_token(instance_id)
    if not instance_data or not instance_data.get("bot_token"):
        raise HTTPException(status_code=400, detail="Bot token not configured")
    bot_token = instance_data["bot_token"]

    # Determine target user IDs
    if request.user_ids:
        target_ids = request.user_ids
    else:
        async with AsyncSessionLocal() as session:
            repo = BotSubscriberRepository(session)
            target_ids = await repo.get_active_subscribers(instance_id)

    if not target_ids:
        return {"status": "ok", "sent_count": 0, "failed_count": 0, "errors": []}

    sent_count = 0
    failed_count = 0
    errors: List[dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for uid in target_ids:
            try:
                resp = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": uid,
                        "text": request.message,
                        "parse_mode": request.parse_mode,
                    },
                )
                data = resp.json()
                if data.get("ok"):
                    sent_count += 1
                else:
                    failed_count += 1
                    errors.append({"user_id": uid, "error": data.get("description", "Unknown")})
            except Exception as e:
                failed_count += 1
                errors.append({"user_id": uid, "error": str(e)})

    logger.info(
        f"Broadcast to {instance_id}: sent={sent_count}, failed={failed_count}, "
        f"by user={user.username}"
    )
    await audit_service.log(
        user.username, "broadcast", f"Sent broadcast to {sent_count}/{len(target_ids)} subscribers"
    )

    return {
        "status": "ok",
        "sent_count": sent_count,
        "failed_count": failed_count,
        "errors": errors[:20],
    }


# ============== GitHub Config ==============


class GithubConfigRequest(BaseModel):
    repo_owner: str = "ShaerWare"
    repo_name: str = "AI_Secretary_System"
    github_token: Optional[str] = None
    webhook_secret: Optional[str] = None
    comment_enabled: bool = True
    broadcast_enabled: bool = True
    comment_prompt: Optional[str] = None
    broadcast_prompt: Optional[str] = None
    events: List[str] = ["opened", "merged"]


@router.get("/github-config")
async def get_github_config(
    instance_id: str, user: User = Depends(require_permission("sales", "view"))
):
    """Get GitHub config for bot."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotGithubRepository(session)
        config = await repo.get_config(instance_id)
    return {"config": config}


@router.put("/github-config")
async def save_github_config(
    instance_id: str,
    request: GithubConfigRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Save GitHub config for bot."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotGithubRepository(session)
        config = await repo.save_config(bot_id=instance_id, **request.model_dump())
        await session.commit()
    await audit_service.log(
        action="update",
        resource="bot_github_config",
        resource_id=instance_id,
        user_id=user.username,
    )
    return {"config": config}


# ============== User Profiles ==============


@router.get("/users")
async def list_user_profiles(
    instance_id: str,
    segment: Optional[str] = None,
    state: Optional[str] = None,
    user: User = Depends(require_permission("sales", "view")),
):
    """List user profiles for bot, optionally filtered."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotUserProfileRepository(session)
        profiles = await repo.list_by_bot(instance_id, segment=segment, state=state)
    return {"users": profiles}


@router.get("/users/{user_id}")
async def get_user_profile(
    instance_id: str, user_id: int, user: User = Depends(require_permission("sales", "view"))
):
    """Get specific user profile."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotUserProfileRepository(session)
        profile = await repo.get_or_create(instance_id, user_id)
        await session.commit()
    return {"user": profile}


@router.delete("/users/{user_id}")
async def delete_user_profile(
    instance_id: str, user_id: int, user: User = Depends(require_permission("sales", "edit"))
):
    """Delete user profile."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotUserProfileRepository(session)
        ok = await repo.delete_by_bot_user(instance_id, user_id)
        await session.commit()
    if not ok:
        raise HTTPException(status_code=404, detail="User profile not found")
    return {"status": "ok"}


# ============== Events / Funnel Analytics ==============


@router.get("/events")
async def list_events(
    instance_id: str,
    event_type: Optional[str] = None,
    days: int = 30,
    user: User = Depends(require_permission("sales", "view")),
):
    """List events for bot."""
    await _check_instance(instance_id)
    date_from = datetime.utcnow() - timedelta(days=days)
    async with AsyncSessionLocal() as session:
        repo = BotEventRepository(session)
        events = await repo.get_events_by_bot(
            instance_id, date_from=date_from, event_type=event_type
        )
    return {"events": events}


@router.get("/funnel")
async def get_funnel(
    instance_id: str, days: int = 30, user: User = Depends(require_permission("sales", "view"))
):
    """Get funnel analytics for bot."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotEventRepository(session)
        funnel = await repo.get_funnel(instance_id, days=days)
    return {"funnel": funnel}


@router.get("/funnel/daily")
async def get_daily_report(
    instance_id: str, user: User = Depends(require_permission("sales", "view"))
):
    """Get daily report summary."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        event_repo = BotEventRepository(session)
        subscriber_repo = BotSubscriberRepository(session)
        profile_repo = BotUserProfileRepository(session)

        funnel = await event_repo.get_funnel(instance_id, days=1)
        subscriber_count = await subscriber_repo.count_subscribers(instance_id)
        segment_counts = await profile_repo.count_by_segment(instance_id)

    return {
        "report": {
            "funnel": funnel,
            "subscribers": subscriber_count,
            "segments": segment_counts,
        }
    }


# ============== Discovery Responses ==============


@router.get("/discovery/{user_id}")
async def get_discovery_responses(
    instance_id: str, user_id: int, user: User = Depends(require_permission("sales", "view"))
):
    """Get discovery responses for a specific user."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotDiscoveryRepository(session)
        responses = await repo.get_responses(instance_id, user_id)
    return {"responses": responses}


@router.get("/discovery")
async def list_all_discovery_responses(
    instance_id: str, user: User = Depends(require_permission("sales", "view"))
):
    """List all discovery responses for bot (admin view)."""
    await _check_instance(instance_id)
    async with AsyncSessionLocal() as session:
        repo = BotDiscoveryRepository(session)
        responses = await repo.list_all_by_bot(instance_id)
    return {"responses": responses}
