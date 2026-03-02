"""
Sales funnel handler for Telegram bots.

Manages the quiz flow, segment matching, user profile FSM,
event logging, and follow-up triggers. Designed to be composed
into TelegramBotService without tight coupling.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from db.database import AsyncSessionLocal
from db.repositories.bot_agent_prompt import BotAgentPromptRepository
from db.repositories.bot_event import BotEventRepository
from db.repositories.bot_quiz import BotQuizRepository
from db.repositories.bot_segment import BotSegmentRepository
from db.repositories.bot_subscriber import BotSubscriberRepository
from db.repositories.bot_testimonial import BotTestimonialRepository
from db.repositories.bot_user_profile import BotUserProfileRepository


logger = logging.getLogger(__name__)


# FSM states
STATE_NEW = "new"
STATE_QUIZ_Q1 = "quiz_q1"
STATE_QUIZ_Q2 = "quiz_q2"
STATE_SEGMENTED = "segmented"
STATE_VALUE_SHOWN = "value_shown"
STATE_FREE_CHAT = "free_chat"


class SalesFunnelHandler:
    """Handles the sales funnel flow: quiz, segmentation, events, follow-ups."""

    def __init__(self, instance_id: str):
        self.instance_id = instance_id
        # Cache quiz questions on first access
        self._quiz_cache: Optional[List[dict]] = None

    # ============== Quiz Flow ==============

    async def _get_quiz_questions(self) -> List[dict]:
        """Get quiz questions for this bot, cached."""
        if self._quiz_cache is not None:
            return self._quiz_cache
        async with AsyncSessionLocal() as session:
            repo = BotQuizRepository(session)
            questions = await repo.list_by_bot(self.instance_id)
        # Only enabled questions
        self._quiz_cache = [q for q in questions if q.get("enabled", True)]
        return self._quiz_cache

    def invalidate_cache(self) -> None:
        """Clear cached data (call when admin updates quiz questions)."""
        self._quiz_cache = None

    async def start_quiz(self, update: Update, user_id: int) -> bool:
        """Start the segmentation quiz. Returns True if quiz was started."""
        questions = await self._get_quiz_questions()
        if not questions:
            logger.warning(f"No quiz questions for bot {self.instance_id}")
            return False

        # Create/update user profile
        async with AsyncSessionLocal() as session:
            profile_repo = BotUserProfileRepository(session)
            user = update.effective_user
            await profile_repo.get_or_create(
                self.instance_id,
                user_id,
                username=user.username if user else None,
                first_name=user.first_name if user else None,
            )
            await profile_repo.update_state(self.instance_id, user_id, STATE_QUIZ_Q1)
            await session.commit()

        # Log event
        await self._log_event(user_id, "quiz_started")

        # Send first question
        await self._send_quiz_question(update, questions[0], 0)
        return True

    async def _send_quiz_question(self, update: Update, question: dict, index: int) -> None:
        """Send a quiz question with inline keyboard options."""
        options = question.get("options", [])
        if isinstance(options, str):
            try:
                options = json.loads(options)
            except (json.JSONDecodeError, TypeError):
                options = []

        buttons = []
        for opt in options:
            label = opt.get("label", "?")
            icon = opt.get("icon", "")
            display = f"{icon} {label}" if icon else label
            callback = f"quiz:{question['question_key']}:{opt.get('value', label)}"
            buttons.append([InlineKeyboardButton(display, callback_data=callback)])

        markup = InlineKeyboardMarkup(buttons)

        text = question.get("text", "")
        if update.callback_query:
            await update.callback_query.message.reply_text(text, reply_markup=markup)
        elif update.message:
            await update.message.reply_text(text, reply_markup=markup)

    async def handle_quiz_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> Optional[str]:
        """Handle quiz answer callback. Returns segment_key if quiz completed, else None."""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        data = query.data  # "quiz:{question_key}:{value}"
        parts = data.split(":", 2)
        if len(parts) != 3:
            return None

        _, question_key, answer_value = parts

        # Save answer to profile
        async with AsyncSessionLocal() as session:
            profile_repo = BotUserProfileRepository(session)
            profile = await profile_repo.get_or_create(self.instance_id, user_id)
            quiz_answers = profile.get("quiz_answers", {})
            if isinstance(quiz_answers, str):
                try:
                    quiz_answers = json.loads(quiz_answers)
                except (json.JSONDecodeError, TypeError):
                    quiz_answers = {}
            quiz_answers[question_key] = answer_value
            await profile_repo.set_quiz_answers(self.instance_id, user_id, quiz_answers)
            await session.commit()

        # Acknowledge the answer
        questions = await self._get_quiz_questions()
        current_idx = next(
            (i for i, q in enumerate(questions) if q["question_key"] == question_key),
            -1,
        )

        # Check if there are more questions
        next_idx = current_idx + 1
        if next_idx < len(questions):
            # Advance state
            state = f"quiz_q{next_idx + 1}"
            async with AsyncSessionLocal() as session:
                repo = BotUserProfileRepository(session)
                await repo.update_state(self.instance_id, user_id, state)
                await session.commit()

            # Send next question
            await self._send_quiz_question(update, questions[next_idx], next_idx)
            return None

        # Quiz completed — match segment
        segment = await self._match_and_assign_segment(user_id, quiz_answers)
        await self._log_event(user_id, "quiz_completed", {"answers": quiz_answers})

        return segment

    async def _match_and_assign_segment(self, user_id: int, quiz_answers: dict) -> Optional[str]:
        """Match answers to a segment and update user profile."""
        async with AsyncSessionLocal() as session:
            segment_repo = BotSegmentRepository(session)
            matched = await segment_repo.match_segment(self.instance_id, quiz_answers)

        if not matched:
            logger.info(f"No segment match for user {user_id}, answers={quiz_answers}")
            async with AsyncSessionLocal() as session:
                repo = BotUserProfileRepository(session)
                await repo.update_state(self.instance_id, user_id, STATE_FREE_CHAT)
                await session.commit()
            return None

        segment_key = matched["segment_key"]
        path = matched.get("path", "")

        async with AsyncSessionLocal() as session:
            repo = BotUserProfileRepository(session)
            await repo.update_segment(self.instance_id, user_id, segment_key, path)
            await repo.update_state(self.instance_id, user_id, STATE_SEGMENTED)
            await session.commit()

        logger.info(f"User {user_id} matched segment '{segment_key}' (path={path})")
        return segment_key

    # ============== Segment-Aware Prompt ==============

    async def get_prompt_for_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get the agent prompt config based on user's segment.

        Returns dict with system_prompt, temperature, max_tokens or None.
        """
        async with AsyncSessionLocal() as session:
            profile_repo = BotUserProfileRepository(session)
            profile = await profile_repo.get_or_create(self.instance_id, user_id)
            await session.commit()

        segment_key = profile.get("segment")
        if not segment_key:
            return None

        # Find segment → agent_prompt_key → prompt
        async with AsyncSessionLocal() as session:
            segment_repo = BotSegmentRepository(session)
            segment = await segment_repo.get_by_key(self.instance_id, segment_key)

        if not segment:
            return None

        prompt_key = segment.agent_prompt_key
        if not prompt_key:
            return None

        async with AsyncSessionLocal() as session:
            prompt_repo = BotAgentPromptRepository(session)
            prompt = await prompt_repo.get_by_key(self.instance_id, prompt_key)

        if not prompt or not prompt.enabled:
            return None

        return {
            "system_prompt": prompt.system_prompt,
            "temperature": prompt.temperature,
            "max_tokens": prompt.max_tokens,
        }

    async def get_user_state(self, user_id: int) -> str:
        """Get current FSM state for a user."""
        async with AsyncSessionLocal() as session:
            repo = BotUserProfileRepository(session)
            profile = await repo.get_or_create(self.instance_id, user_id)
            await session.commit()
        return profile.get("state", STATE_NEW)

    # ============== Welcome + Social Proof ==============

    async def build_welcome_message(self, user_first_name: Optional[str] = None) -> str:
        """Build a welcome message with social proof (testimonials)."""
        name_part = f", {user_first_name}" if user_first_name else ""

        # Get a random testimonial
        testimonial_text = ""
        async with AsyncSessionLocal() as session:
            repo = BotTestimonialRepository(session)
            testimonial = await repo.get_random(self.instance_id)
        if testimonial:
            stars = "\u2b50" * testimonial.get("rating", 5)
            testimonial_text = (
                f"\n\n{stars}\n\u00ab{testimonial['text']}\u00bb\n\u2014 {testimonial['author']}"
            )

        return (
            f"AI Secretary \u2014 ваш виртуальный AI-ассистент{name_part}!\n\n"
            f"\U0001f4ac Голосовой AI на вашем сервере\n"
            f"\U0001f512 Полная приватность данных (152-\u0424\u0417)\n"
            f"\U0001f3a4 \u041a\u043b\u043e\u043d\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 \u0433\u043e\u043b\u043e\u0441\u0430 (XTTS v2)\n"
            f"\U0001f4b0 \u0411\u0435\u0437 \u0430\u0431\u043e\u043d\u0435\u043d\u0442\u043a\u0438 \u2014 \u0440\u0430\u0437\u043e\u0432\u0430\u044f \u043e\u043f\u043b\u0430\u0442\u0430"
            f"{testimonial_text}\n\n"
            f"\U0001f449 \u041f\u0440\u043e\u0439\u0434\u0438\u0442\u0435 \u043a\u043e\u0440\u043e\u0442\u043a\u0438\u0439 \u043a\u0432\u0438\u0437 (2 \u0432\u043e\u043f\u0440\u043e\u0441\u0430), \u0438 \u044f \u043f\u043e\u0434\u0431\u0435\u0440\u0443 \u043b\u0443\u0447\u0448\u0438\u0439 \u0432\u0430\u0440\u0438\u0430\u043d\u0442 \u0434\u043b\u044f \u0432\u0430\u0441!"
        )

    def build_welcome_keyboard(self) -> InlineKeyboardMarkup:
        """Build welcome inline keyboard with quiz CTA and skip."""
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "\U0001f680 \u041f\u043e\u0434\u043e\u0431\u0440\u0430\u0442\u044c \u0432\u0430\u0440\u0438\u0430\u043d\u0442 (2 \u043c\u0438\u043d)",
                        callback_data="quiz:start",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "\U0001f4ac \u041f\u0440\u043e\u0441\u0442\u043e \u043f\u043e\u0433\u043e\u0432\u043e\u0440\u0438\u0442\u044c",
                        callback_data="quiz:skip",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "\u2b50 GitHub",
                        url="https://github.com/ShaerWare/AI_Secretary_System",
                    )
                ],
            ]
        )

    async def build_segment_result_message(
        self, segment_key: str
    ) -> Tuple[str, InlineKeyboardMarkup]:
        """Build message showing quiz results with path-specific CTA."""
        async with AsyncSessionLocal() as session:
            segment_repo = BotSegmentRepository(session)
            segment = await segment_repo.get_by_key(self.instance_id, segment_key)

        if not segment:
            return (
                "\u2705 \u0421\u043f\u0430\u0441\u0438\u0431\u043e! \u0422\u0435\u043f\u0435\u0440\u044c \u043c\u043e\u0436\u0435\u0442\u0435 \u0437\u0430\u0434\u0430\u0442\u044c \u043b\u044e\u0431\u043e\u0439 \u0432\u043e\u043f\u0440\u043e\u0441.",
                InlineKeyboardMarkup([]),
            )

        path = segment.path
        name = segment.name

        # Path-specific messages and buttons
        if path == "diy":
            text = (
                f"\U0001f3af \u0412\u0430\u0448 \u043f\u0440\u043e\u0444\u0438\u043b\u044c: {name}\n\n"
                "\U0001f527 \u0412\u044b \u043c\u043e\u0436\u0435\u0442\u0435 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c AI Secretary \u0441\u0430\u043c\u043e\u0441\u0442\u043e\u044f\u0442\u0435\u043b\u044c\u043d\u043e!\n\n"
                "\U0001f4cb \u0414\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430\u0446\u0438\u044f, Docker-\u043a\u043e\u043c\u0430\u043d\u0434\u044b, GPU-\u0442\u0440\u0435\u0431\u043e\u0432\u0430\u043d\u0438\u044f \u2014 \u0441\u043f\u0440\u0430\u0448\u0438\u0432\u0430\u0439\u0442\u0435!"
            )
            buttons = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "\U0001f4d6 \u0414\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430\u0446\u0438\u044f",
                            url="https://github.com/ShaerWare/AI_Secretary_System/wiki",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "\U0001f5a5 \u0410\u0443\u0434\u0438\u0442 \u043c\u043e\u0435\u0433\u043e \u0436\u0435\u043b\u0435\u0437\u0430",
                            callback_data="action:hardware_audit",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "\U0001f514 \u041f\u043e\u0434\u043f\u0438\u0441\u0430\u0442\u044c\u0441\u044f \u043d\u0430 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f",
                            callback_data="action:subscribe",
                        )
                    ],
                ]
            )
        elif path == "basic":
            text = (
                f"\U0001f3af \u0412\u0430\u0448 \u043f\u0440\u043e\u0444\u0438\u043b\u044c: {name}\n\n"
                "\U0001f4e6 \u0423\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0430 \u043f\u043e\u0434 \u043a\u043b\u044e\u0447 \u2014 5000\u20bd\n"
                "\u23f0 30 \u043c\u0438\u043d\u0443\u0442, \u0431\u0435\u0437 \u0430\u0431\u043e\u043d\u0435\u043d\u0442\u043a\u0438\n\n"
                "\U0001f4b0 \u042d\u043a\u043e\u043d\u043e\u043c\u0438\u044f vs SaaS: ~180\u041a\u20bd/\u0433\u043e\u0434"
            )
            buttons = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "\U0001f4b0 \u041f\u043e\u0441\u0447\u0438\u0442\u0430\u0442\u044c ROI",
                            callback_data="action:roi_calc",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "\U0001f6d2 \u0417\u0430\u043a\u0430\u0437\u0430\u0442\u044c \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0443",
                            callback_data="action:order_install",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "\u2753 \u0415\u0441\u0442\u044c \u0432\u043e\u043f\u0440\u043e\u0441\u044b",
                            callback_data="action:faq",
                        )
                    ],
                ]
            )
        elif path == "qualified":
            text = (
                f"\U0001f3af Ваш профиль: {name}\n\n"
                "\u2705 Ваш проект подходит под формат работы.\n\n"
                "\U0001f4cb Опишите проект подробнее, и я составлю ТЗ "
                "с разбивкой на спринты и оценкой стоимости."
            )
            buttons = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "\U0001f4cb Описать проект",
                            callback_data="action:describe_project",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "\U0001f4d1 Условия работы",
                            callback_data="action:conditions",
                        )
                    ],
                ]
            )
        elif path == "unqualified":
            text = (
                f"\U0001f3af Ваш профиль: {name}\n\n"
                "\u26a0\ufe0f Минимальный заказ — 1 спринт (50,000\u20bd / неделя).\n\n"
                "Для небольших задач рекомендуем:\n"
                "\u2022 Kwork — kwork.ru\n"
                "\u2022 FL.ru — fl.ru\n"
                "\u2022 Habr Freelance — freelance.habr.com\n\n"
                "Если проект побольше — расскажите подробнее!"
            )
            buttons = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "\U0001f4cb У меня проект побольше",
                            callback_data="action:describe_project",
                        )
                    ],
                ]
            )
        elif path == "needs_analysis":
            text = (
                f"\U0001f3af Ваш профиль: {name}\n\n"
                "\U0001f9ee Опишите проект, и я рассчитаю стоимость "
                "с разбивкой на спринты."
            )
            buttons = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "\U0001f4cb Описать проект",
                            callback_data="action:describe_project",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "\U0001f4bc Портфолио",
                            callback_data="action:portfolio",
                        )
                    ],
                ]
            )
        else:  # custom (default fallback)
            text = (
                f"\U0001f3af Ваш профиль: {name}\n\n"
                "\U0001f3e2 Кастомная интеграция под ваш бизнес\n"
                "\U0001f4de CRM, телефония, кастомные сценарии\n\n"
                "\U0001f4ac Давайте обсудим вашу задачу!"
            )
            buttons = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "\U0001f4dd Начать discovery",
                            callback_data="action:discovery_start",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "\U0001f4bc Кейсы внедрения",
                            callback_data="action:cases",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "\U0001f4b0 Предварительный расчёт",
                            callback_data="action:quote",
                        )
                    ],
                ]
            )

        return text, buttons

    # ============== Action Callbacks ==============

    async def handle_action_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> Optional[str]:
        """Handle action:* callbacks. Returns response text or None."""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        data = query.data  # "action:{action_name}"
        action = data.split(":", 1)[1] if ":" in data else data

        if action == "subscribe":
            async with AsyncSessionLocal() as session:
                repo = BotSubscriberRepository(session)
                await repo.subscribe(self.instance_id, user_id)
                await session.commit()
            await query.message.reply_text(
                "\U0001f514 \u0412\u044b \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u044b \u043d\u0430 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f! "
                "\u0412\u044b \u0431\u0443\u0434\u0435\u0442\u0435 \u043f\u043e\u043b\u0443\u0447\u0430\u0442\u044c \u043d\u043e\u0432\u043e\u0441\u0442\u0438 \u043e \u043f\u0440\u043e\u0435\u043a\u0442\u0435."
            )
            await self._log_event(user_id, "subscribed")
            return None

        if action == "unsubscribe":
            async with AsyncSessionLocal() as session:
                repo = BotSubscriberRepository(session)
                await repo.unsubscribe(self.instance_id, user_id)
                await session.commit()
            await query.message.reply_text(
                "\U0001f515 \u0412\u044b \u043e\u0442\u043f\u0438\u0441\u0430\u043d\u044b \u043e\u0442 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0439."
            )
            await self._log_event(user_id, "unsubscribed")
            return None

        if action == "hardware_audit":
            await self._log_event(user_id, "cta_clicked", {"cta": "hardware_audit"})
            return (
                "\U0001f5a5 \u041d\u0430\u043f\u0438\u0448\u0438\u0442\u0435 \u043c\u043e\u0434\u0435\u043b\u044c \u0432\u0430\u0448\u0435\u0439 \u0432\u0438\u0434\u0435\u043e\u043a\u0430\u0440\u0442\u044b "
                "(\u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440, RTX 3060) "
                "\u0438 \u044f \u043f\u043e\u0434\u0431\u0435\u0440\u0443 \u043e\u043f\u0442\u0438\u043c\u0430\u043b\u044c\u043d\u0443\u044e \u043a\u043e\u043d\u0444\u0438\u0433\u0443\u0440\u0430\u0446\u0438\u044e."
            )

        if action == "roi_calc":
            await self._log_event(user_id, "cta_clicked", {"cta": "roi_calc"})
            return (
                "\U0001f4b0 \u0420\u0430\u0441\u0441\u0447\u0438\u0442\u0430\u044e ROI!\n\n"
                "AI Secretary: 5000\u20bd \u0440\u0430\u0437\u043e\u0432\u043e\n"
                "SaaS-\u0431\u043e\u0442: ~15000\u20bd/\u043c\u0435\u0441\n\n"
                "\u042d\u043a\u043e\u043d\u043e\u043c\u0438\u044f \u0437\u0430 1 \u0433\u043e\u0434: ~175\u041a\u20bd\n"
                "\u042d\u043a\u043e\u043d\u043e\u043c\u0438\u044f \u0437\u0430 3 \u0433\u043e\u0434\u0430: ~535\u041a\u20bd\n\n"
                "\u0417\u0430\u0434\u0430\u0439\u0442\u0435 \u0432\u043e\u043f\u0440\u043e\u0441 \u0434\u043b\u044f \u0438\u043d\u0434\u0438\u0432\u0438\u0434\u0443\u0430\u043b\u044c\u043d\u043e\u0433\u043e \u0440\u0430\u0441\u0447\u0451\u0442\u0430."
            )

        if action in ("order_install", "discovery_start", "quote", "cases", "faq"):
            await self._log_event(user_id, "cta_clicked", {"cta": action})
            # These return a prompt hint; the next message will be handled by LLM
            prompts = {
                "order_install": "\U0001f6d2 \u041e\u0442\u043b\u0438\u0447\u043d\u043e! \u041d\u0430\u043f\u0438\u0448\u0438\u0442\u0435 \u043c\u043d\u0435, \u0438 \u044f \u043f\u043e\u043c\u043e\u0433\u0443 \u043e\u0444\u043e\u0440\u043c\u0438\u0442\u044c \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0443.",
                "discovery_start": "\U0001f4dd \u041d\u0430\u0447\u0438\u043d\u0430\u0435\u043c discovery! \u0420\u0430\u0441\u0441\u043a\u0430\u0436\u0438\u0442\u0435 \u043e \u0432\u0430\u0448\u0435\u0439 \u0437\u0430\u0434\u0430\u0447\u0435.",
                "quote": "\U0001f4b0 \u0420\u0430\u0441\u0441\u043a\u0430\u0436\u0438\u0442\u0435 \u043e \u043f\u0440\u043e\u0435\u043a\u0442\u0435 \u0434\u043b\u044f \u043f\u0440\u0435\u0434\u0432\u0430\u0440\u0438\u0442\u0435\u043b\u044c\u043d\u043e\u0433\u043e \u0440\u0430\u0441\u0447\u0451\u0442\u0430.",
                "cases": "\U0001f4bc \u041a\u0435\u0439\u0441\u044b: \u0430\u0432\u0442\u043e\u0441\u0430\u043b\u043e\u043d -70% \u043d\u0430\u0433\u0440\u0443\u0437\u043a\u0438, \u043a\u043b\u0438\u043d\u0438\u043a\u0430 +40% \u0437\u0430\u043f\u0438\u0441\u0435\u0439. \u0421\u043f\u0440\u043e\u0441\u0438\u0442\u0435 \u043f\u043e\u0434\u0440\u043e\u0431\u043d\u0435\u0435!",
                "faq": "\u2753 \u0417\u0430\u0434\u0430\u0439\u0442\u0435 \u043b\u044e\u0431\u043e\u0439 \u0432\u043e\u043f\u0440\u043e\u0441 \u043e \u043f\u0440\u043e\u0435\u043a\u0442\u0435.",
            }
            return prompts.get(action)

        return None

    # ============== Event Logging ==============

    async def _log_event(
        self, user_id: int, event_type: str, event_data: Optional[dict] = None
    ) -> None:
        """Log a funnel event."""
        try:
            async with AsyncSessionLocal() as session:
                repo = BotEventRepository(session)
                await repo.log_event(self.instance_id, user_id, event_type, event_data)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to log event: {e}")

    async def log_start_event(self, user_id: int) -> None:
        """Log the /start event."""
        await self._log_event(user_id, "start")

    async def log_value_shown(self, user_id: int, path: str) -> None:
        """Log that value proposition was shown."""
        await self._log_event(user_id, "value_shown", {"path": path})

    # ============== Subscription Commands ==============

    async def handle_subscribe_command(self, update: Update, user_id: int) -> str:
        """Handle /subscribe command."""
        async with AsyncSessionLocal() as session:
            repo = BotSubscriberRepository(session)
            await repo.subscribe(self.instance_id, user_id)
            await session.commit()
        await self._log_event(user_id, "subscribed")
        return "\U0001f514 \u0412\u044b \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u044b \u043d\u0430 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f \u043f\u0440\u043e\u0435\u043a\u0442\u0430!"

    async def handle_unsubscribe_command(self, update: Update, user_id: int) -> str:
        """Handle /unsubscribe command."""
        async with AsyncSessionLocal() as session:
            repo = BotSubscriberRepository(session)
            await repo.unsubscribe(self.instance_id, user_id)
            await session.commit()
        await self._log_event(user_id, "unsubscribed")
        return "\U0001f515 \u0412\u044b \u043e\u0442\u043f\u0438\u0441\u0430\u043d\u044b. \u0427\u0442\u043e\u0431\u044b \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u0442\u044c\u0441\u044f \u0441\u043d\u043e\u0432\u0430: /subscribe"
