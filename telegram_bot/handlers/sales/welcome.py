"""Welcome / /start handler for the sales funnel."""

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...bot import get_action_buttons
from ...sales.database import get_sales_db
from ...sales.keyboards import main_reply_kb, welcome_kb, what_is_kb
from ...sales.states import SalesFunnel
from ...sales.texts import WELCOME_TEXT, WHAT_IS_TEXT
from ...services.session_store import get_session_store
from ...services.social_proof import get_social_proof_data


logger = logging.getLogger(__name__)
router = Router()


def _get_keyboard():
    """Get main keyboard with current action buttons."""
    return main_reply_kb(get_action_buttons())


async def _get_social_proof(name: str = "друг") -> dict:
    """Return dynamic social proof data with personalized name."""
    return await get_social_proof_data(name=name)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Handle /start — enter the sales funnel."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    db = await get_sales_db()

    # Upsert user record
    await db.upsert_user(
        user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    await db.log_event(user_id, "start")

    # Ensure AI-chat session also exists
    store = get_session_store()
    store.get_or_create(user_id)

    # Get user's first name for personalization
    first_name = message.from_user.first_name or "друг"

    # Send persistent reply keyboard (always visible at bottom)
    await message.answer(
        f"👋 Добро пожаловать, {first_name}! Используйте кнопки ниже для быстрого доступа.",
        reply_markup=_get_keyboard(),
    )

    # Send welcome message with inline keyboard
    social = await _get_social_proof(name=first_name)
    await message.answer(
        WELCOME_TEXT.format(**social),
        reply_markup=welcome_kb(),
    )
    await state.set_state(SalesFunnel.welcome)


@router.callback_query(F.data == "sales:back_welcome")
async def back_to_welcome(callback: CallbackQuery, state: FSMContext) -> None:
    """Return to the welcome screen."""
    # Get user's first name for personalization
    first_name = "друг"
    if callback.from_user:
        first_name = callback.from_user.first_name or "друг"

    social = await _get_social_proof(name=first_name)
    if callback.message:
        await callback.message.edit_text(
            WELCOME_TEXT.format(**social),
            reply_markup=welcome_kb(),
        )
    await state.set_state(SalesFunnel.welcome)
    await callback.answer()


@router.callback_query(F.data == "sales:what_is")
async def what_is(callback: CallbackQuery, state: FSMContext) -> None:
    """Show 'What is AI Secretary?' info."""
    if callback.message:
        await callback.message.edit_text(
            WHAT_IS_TEXT,
            reply_markup=what_is_kb(),
        )
    await callback.answer()
