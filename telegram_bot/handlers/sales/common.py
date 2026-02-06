"""Common / shared sales callbacks and reply keyboard handlers."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ...bot import get_action_buttons
from ...sales.database import get_sales_db
from ...sales.keyboards import (
    GITHUB_URL,
    basic_checkout_kb,
    contact_kb,
    main_reply_kb,
    menu_kb,
    submenu_reply_kb,
    welcome_kb,
)
from ...sales.states import SalesFunnel
from ...sales.texts import CONTACT_TEXT, MENU_TEXT, SKIP_TO_CHAT_TEXT, WELCOME_TEXT
from ...services.session_store import get_session_store
from ...services.social_proof import get_social_proof_data


logger = logging.getLogger(__name__)
router = Router()


# ── Helper to get keyboard with current buttons config ────────────────────


def get_main_kb() -> Message:
    """Get main reply keyboard with current action_buttons config."""
    return main_reply_kb(get_action_buttons())


def get_submenu_kb() -> Message:
    """Get submenu reply keyboard with current action_buttons config."""
    return submenu_reply_kb(get_action_buttons())


# ── Reply Keyboard Button Handlers ────────────────────────────────────


HELP_TEXT = """
ℹ️ **Помощь по боту**

Я — AI-ассистент проекта **AI Secretary**.

**Основные кнопки:**
• 📦 **Установить самостоятельно** — GitHub + инструкция
• 💳 **Оплата 5К** — установка под ключ
• 🛠️ **Техподдержка** — варианты помощи
• 📚 **Wiki** — документация + FAQ
• ❓ **Задать вопрос** — спросить у AI
• 📋 **Рассчитать заказ** — ТЗ с AI
• 🚀 **Старт** — главное меню

**Команды:**
• /start — главное меню
• /new — сбросить диалог
• /menu — меню воронки
• /tz — рассчитать заказ

**Контакты:**
• Telegram: @ShaerWare
• Сайт: shaerware.digital

━━━━━━━━━━━━━━━━━━━━━
💡 **Идеи и предложения?**
Пишите в GitHub Issues — обсудим вместе!
github.com/ShaerWare/AI_Secretary_System/issues
""".strip()

CHECKOUT_TEXT = """
💳 **Установка "под ключ" — 5,000₽**

Что входит:
✅ Подключение к вашему серверу по SSH
✅ Полная установка за 30 минут
✅ Оптимизация под ваш GPU
✅ Проверка работоспособности
✅ Краткий инструктаж

🔒 **Гарантия:** если не заработает — вернём деньги

**Требования к серверу:**
• Ubuntu 20.04+ / Debian 11+
• GPU от GTX 1660 или CPU-режим
• Docker установлен
• SSH-доступ

Для оплаты свяжитесь: @ShaerWare
""".strip()

ASK_QUESTION_TEXT = """
❓ **Задайте ваш вопрос**

Напишите любой вопрос о:
• Установке и настройке AI Secretary
• Технических требованиях
• Ценах и услугах
• Интеграциях (CRM, телефония)

Я отвечу на основе документации. Сложные вопросы передам разработчику.

*Просто напишите ваш вопрос в чат...*
""".strip()


@router.message(F.text == "💳 Оплата 5К")
async def reply_kb_payment(message: Message, state: FSMContext) -> None:
    """Handle payment button from reply keyboard."""
    if message.from_user:
        db = await get_sales_db()
        await db.log_event(message.from_user.id, "reply_kb_payment")

    # Switch to submenu keyboard (with back button)
    await message.answer("💳", reply_markup=get_submenu_kb())
    await message.answer(
        CHECKOUT_TEXT,
        reply_markup=basic_checkout_kb(),
    )


@router.message(F.text == "📦 Установить самостоятельно")
async def reply_kb_github(message: Message, state: FSMContext) -> None:
    """Handle GitHub / self-install button from reply keyboard."""
    if message.from_user:
        db = await get_sales_db()
        await db.log_event(message.from_user.id, "reply_kb_self_install")

    await message.answer(
        f"📦 **Установить AI Secretary самостоятельно**\n\n"
        f"🔗 {GITHUB_URL}\n\n"
        f"**Лицензия MIT** — полностью бесплатно!\n\n"
        f"**Quick Start (Docker):**\n"
        f"```\n"
        f"git clone {GITHUB_URL}\n"
        f"cd AI_Secretary_System\n"
        f"cp .env.docker .env\n"
        f"docker compose up -d\n"
        f"```\n\n"
        f"**Админка:** http://localhost:8002/admin\n"
        f"**Логин:** admin / **Пароль:** admin\n\n"
        f"📚 Документация: /wiki\n"
        f"⭐ Поставьте звезду, если полезно!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 **Идеи, баги, предложения?**\n"
        f"Пишите в Issues — обсудим вместе!\n"
        f"{GITHUB_URL}/issues",
        parse_mode="Markdown",
    )


@router.message(F.text == "🛠️ Техподдержка")
async def reply_kb_support(message: Message, state: FSMContext) -> None:
    """Handle tech support button from reply keyboard."""
    if message.from_user:
        db = await get_sales_db()
        await db.log_event(message.from_user.id, "reply_kb_support")

    await message.answer(
        "🛠️ **Техподдержка AI Secretary**\n\n"
        "**Бесплатно:**\n"
        "• 📚 Wiki — 22 страницы документации\n"
        "• 💬 GitHub Issues — баги, фичи, идеи\n"
        "• 🤖 Этот бот — задавайте вопросы AI\n\n"
        "**Платные услуги:**\n"
        "• ⚡ Установка под ключ — 5,000₽\n"
        "• 🔄 Обновление — 2,000₽\n"
        "• 🛠️ Кастомная разработка — от 50,000₽\n\n"
        "**Связаться:**\n"
        "📱 Telegram: @ShaerWare\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 **Есть идея или предложение?**\n"
        "Пишите в Issues — обсудим вместе!\n"
        f"{GITHUB_URL}/issues",
    )


@router.message(F.text == "📚 Wiki")
async def reply_kb_wiki(message: Message, state: FSMContext) -> None:
    """Handle Wiki button from reply keyboard — show FAQ."""
    if message.from_user:
        db = await get_sales_db()
        await db.log_event(message.from_user.id, "reply_kb_wiki")

    from ...sales.keyboards import faq_kb
    from ...sales.texts import FAQ_WIKI_INTRO

    await message.answer(
        FAQ_WIKI_INTRO,
        reply_markup=faq_kb(),
    )


@router.callback_query(F.data.startswith("faq:"))
async def faq_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle FAQ question callbacks."""
    if not callback.data:
        await callback.answer()
        return

    action = callback.data.split(":", 1)[1]

    if callback.from_user:
        db = await get_sales_db()
        await db.log_event(callback.from_user.id, "faq_clicked", {"question": action})

    # Back to FAQ list
    if action == "back":
        from ...sales.keyboards import faq_kb
        from ...sales.texts import FAQ_WIKI_INTRO

        if callback.message:
            await callback.message.edit_text(
                FAQ_WIKI_INTRO,
                reply_markup=faq_kb(),
            )
        await callback.answer()
        return

    # Show FAQ answer
    from ...sales.keyboards import faq_back_kb
    from ...sales.texts import FAQ_ANSWERS

    answer = FAQ_ANSWERS.get(action)
    if answer and callback.message:
        await callback.message.edit_text(
            answer,
            reply_markup=faq_back_kb(),
        )

    await callback.answer()


@router.message(F.text == "❓ Задать вопрос")
async def reply_kb_ask_question(message: Message, state: FSMContext) -> None:
    """Handle ask question button — enter AI chat mode."""
    if message.from_user:
        db = await get_sales_db()
        await db.log_event(message.from_user.id, "reply_kb_ask_question")

        store = get_session_store()
        store.get_or_create(message.from_user.id)

    # Clear FSM state to enable AI chat
    await state.clear()

    # Switch to submenu keyboard (with back button)
    await message.answer(
        ASK_QUESTION_TEXT,
        reply_markup=get_submenu_kb(),
        parse_mode="Markdown",
    )


@router.message(F.text == "🚀 Старт")
async def reply_kb_start(message: Message, state: FSMContext) -> None:
    """Handle start button — return to welcome screen with main keyboard."""
    if not message.from_user:
        return

    db = await get_sales_db()
    await db.log_event(message.from_user.id, "reply_kb_start")

    # Get user's first name for personalization
    first_name = message.from_user.first_name or "друг"

    # Show main keyboard (with manager button, no back)
    await message.answer("🚀", reply_markup=get_main_kb())

    # Get dynamic social proof
    social = await get_social_proof_data(name=first_name)
    await message.answer(
        WELCOME_TEXT.format(**social),
        reply_markup=welcome_kb(),
    )
    await state.set_state(SalesFunnel.welcome)


@router.message(F.text == "ℹ️ Помощь")
async def reply_kb_help(message: Message, state: FSMContext) -> None:
    """Handle help button from reply keyboard."""
    if message.from_user:
        db = await get_sales_db()
        await db.log_event(message.from_user.id, "reply_kb_help")

    await message.answer(HELP_TEXT, parse_mode="Markdown")


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    """Handle /help command."""
    await message.answer(HELP_TEXT, parse_mode="Markdown")


@router.message(F.text == "← Назад")
async def reply_kb_back(message: Message, state: FSMContext) -> None:
    """Handle back button — return to welcome/main menu."""
    if not message.from_user:
        return

    db = await get_sales_db()
    await db.log_event(message.from_user.id, "reply_kb_back")

    # Get user's first name for personalization
    first_name = message.from_user.first_name or "друг"

    # Return to welcome screen (main menu) with main keyboard (no back button)
    await message.answer(
        f"👋 {first_name}, возвращаемся в главное меню!",
        reply_markup=get_main_kb(),
    )

    # Get dynamic social proof
    social = await get_social_proof_data(name=first_name)
    await message.answer(
        WELCOME_TEXT.format(**social),
        reply_markup=welcome_kb(),
    )
    await state.set_state(SalesFunnel.welcome)


MANAGER_TEXT = """
👨‍💼 **Менеджер по продажам AI Secretary**

Привет! Я помогу вам:
• Подобрать оптимальный вариант установки
• Рассчитать стоимость кастомного проекта
• Ответить на вопросы о продукте
• Оформить заказ на установку

**Просто напишите ваш вопрос** — я отвечу как живой менеджер, только быстрее 😉

Или выберите готовый сценарий:
""".strip()


def manager_kb() -> InlineKeyboardMarkup:
    """Manager assistant keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💰 Узнать цены",
                    callback_data="sales:manager_prices",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎯 Подобрать вариант",
                    callback_data="sales:start_quiz",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏢 Кастомный проект",
                    callback_data="sales:manager_custom",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❓ Свой вопрос",
                    callback_data="sales:manager_question",
                )
            ],
        ]
    )


@router.message(F.text == "👨‍💼 Менеджер")
async def reply_kb_manager(message: Message, state: FSMContext) -> None:
    """Handle manager button — show sales assistant menu."""
    if not message.from_user:
        return

    db = await get_sales_db()
    await db.log_event(message.from_user.id, "reply_kb_manager")

    # Show submenu keyboard (with back button)
    await message.answer(
        MANAGER_TEXT,
        reply_markup=manager_kb(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "sales:manager_prices")
async def manager_prices(callback: CallbackQuery, state: FSMContext) -> None:
    """Show pricing info."""
    prices_text = """
💰 **Цены на AI Secretary**

**🆓 DIY (бесплатно)**
Самостоятельная установка с GitHub + документация

**⚡ Basic — 5,000₽** (разово)
• Установка под ключ за 30 минут
• Оптимизация под ваш GPU
• Гарантия возврата

**🏢 Custom — от 50,000₽**
• Кастомная разработка
• Интеграция с CRM
• Телефония и fine-tuning

━━━━━━━━━━━━━━━━━━━━━

💡 **Экономия vs SaaS:**
SaaS-бот: 15,000₽/мес × 36 мес = 540,000₽
AI Secretary: 5,000₽ один раз

**Экономия за 3 года: 535,000₽**
""".strip()

    if callback.message:
        await callback.message.answer(prices_text, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "sales:manager_custom")
async def manager_custom(callback: CallbackQuery, state: FSMContext) -> None:
    """Start custom project inquiry."""
    custom_text = """
🏢 **Кастомный проект**

Расскажите о вашей задаче, и я подготовлю расчёт:

• Какую проблему хотите решить?
• Нужны ли интеграции (CRM, телефония)?
• Какой примерный бюджет?

**Просто напишите в свободной форме** — я задам уточняющие вопросы.
""".strip()

    if callback.message:
        await callback.message.answer(
            custom_text,
            reply_markup=get_submenu_kb(),
            parse_mode="Markdown",
        )

    # Clear state to enable AI chat
    await state.clear()

    store = get_session_store()
    if callback.from_user:
        store.get_or_create(callback.from_user.id)

    await callback.answer()


@router.callback_query(F.data == "sales:manager_question")
async def manager_question(callback: CallbackQuery, state: FSMContext) -> None:
    """Enable free-form question mode."""
    question_text = """
❓ **Задайте ваш вопрос**

Напишите что угодно о:
• Установке и настройке
• Технических требованиях
• Ценах и услугах
• Интеграциях

Я отвечу как менеджер-консультант.
""".strip()

    if callback.message:
        await callback.message.answer(
            question_text,
            reply_markup=get_submenu_kb(),
            parse_mode="Markdown",
        )

    # Clear state to enable AI chat
    await state.clear()

    store = get_session_store()
    if callback.from_user:
        store.get_or_create(callback.from_user.id)

    await callback.answer()


@router.callback_query(F.data == "sales:skip_to_chat")
async def skip_to_chat(callback: CallbackQuery, state: FSMContext) -> None:
    """Exit the sales funnel and enter AI chat mode."""
    if callback.from_user:
        db = await get_sales_db()
        await db.log_event(callback.from_user.id, "skip_to_chat")

        # Ensure AI chat session exists
        store = get_session_store()
        store.get_or_create(callback.from_user.id)

    # Clear FSM state so messages_router catch-all works
    await state.clear()

    if callback.message:
        await callback.message.edit_text(SKIP_TO_CHAT_TEXT)
    await callback.answer()


@router.message(Command("chat"))
async def cmd_chat(message: Message, state: FSMContext) -> None:
    """Command to exit sales funnel and enter AI chat mode."""
    if not message.from_user:
        return

    store = get_session_store()
    store.get_or_create(message.from_user.id)

    await state.clear()
    await message.answer(SKIP_TO_CHAT_TEXT)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    """Command to return to the sales funnel menu."""
    if not message.from_user:
        return

    db = await get_sales_db()
    await db.log_event(message.from_user.id, "menu_opened")

    await message.answer(MENU_TEXT, reply_markup=menu_kb())
    await state.set_state(SalesFunnel.welcome)


@router.callback_query(F.data == "sales:contact")
async def contact(callback: CallbackQuery, state: FSMContext) -> None:
    """Show contact information."""
    if callback.from_user:
        db = await get_sales_db()
        await db.log_event(callback.from_user.id, "contact_clicked")

    if callback.message:
        await callback.message.edit_text(CONTACT_TEXT, reply_markup=contact_kb())
    await callback.answer()
