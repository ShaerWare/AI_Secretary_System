"""News handlers — /news command shows SMM-generated news posts."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ..bot import get_action_buttons
from ..config import get_telegram_settings
from ..sales.database import get_sales_db
from ..sales.keyboards import submenu_reply_kb
from ..services.github_news import (
    check_and_broadcast_news,
    fetch_merged_prs,
    generate_news_post,
)


logger = logging.getLogger(__name__)
router = Router()

GITHUB_URL = "https://github.com/ShaerWare/AI_Secretary_System"


def news_upsell_kb() -> InlineKeyboardMarkup:
    """Keyboard with upsell buttons for news posts."""
    buttons: list[list[InlineKeyboardButton]] = []

    # Free option
    buttons.append(
        [
            InlineKeyboardButton(
                text="📦 Обновить самостоятельно",
                url=GITHUB_URL,
            )
        ]
    )

    # Paid options
    buttons.append(
        [
            InlineKeyboardButton(
                text="⚡ Обновить за 2,000₽",
                callback_data="news:upsell_update",
            ),
            InlineKeyboardButton(
                text="🚀 Установить за 5,000₽",
                callback_data="news:upsell_install",
            ),
        ]
    )

    # Back to main menu
    buttons.append(
        [
            InlineKeyboardButton(
                text="← Главное меню",
                callback_data="sales:back_welcome",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("news"))
async def cmd_news(message: Message, state: FSMContext) -> None:
    """Handle /news — show SMM news posts for all recent PRs.

    Posts are cached in database — generated only once per PR.
    """
    if not message.from_user:
        return

    db = await get_sales_db()
    await db.log_event(message.from_user.id, "news_command")

    # Switch to submenu keyboard
    await message.answer("📰", reply_markup=submenu_reply_kb(get_action_buttons()))

    # Send loading message
    loading_msg = await message.answer("📰 Загружаю новости...")

    try:
        # Fetch PRs (last 60 days, up to 10)
        prs = await fetch_merged_prs(days=60, limit=10)

        if not prs:
            await loading_msg.edit_text(
                f"📰 **Новости AI Secretary**\n\nПока нет новых обновлений.\n\n🔗 {GITHUB_URL}"
            )
            return

        # Get all cached posts in one query
        pr_numbers = [pr["number"] for pr in prs]
        cached_posts = await db.get_all_cached_news(pr_numbers)

        # Find which PRs need generation
        uncached_prs = [pr for pr in prs if pr["number"] not in cached_posts]

        if uncached_prs:
            await loading_msg.edit_text(
                f"📰 Генерирую {len(uncached_prs)} новых постов...\n\n"
                "⏳ Это может занять некоторое время"
            )

            # Generate posts for uncached PRs
            for pr in uncached_prs:
                try:
                    post_text = await generate_news_post(pr)
                    await db.save_news_cache(pr["number"], pr["title"], post_text)
                    cached_posts[pr["number"]] = post_text
                except Exception as e:
                    logger.error(f"Failed to generate post for PR #{pr['number']}: {e}")

        # Delete loading message
        await loading_msg.delete()

        # Send posts for each PR (in order)
        sent_count = 0
        for i, pr in enumerate(prs):
            pr_number = pr["number"]

            if pr_number not in cached_posts:
                continue  # Skip if generation failed

            post_text = cached_posts[pr_number]
            is_last = i == len(prs) - 1

            try:
                await message.answer(
                    post_text,
                    reply_markup=news_upsell_kb() if is_last else None,
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send news post: {e}")

        # Log completion
        await db.log_event(
            message.from_user.id,
            "news_viewed",
            {"count": sent_count, "generated": len(uncached_prs)},
        )

    except Exception as e:
        logger.error(f"Failed to fetch news: {e}")
        await loading_msg.edit_text("❌ Не удалось загрузить новости. Попробуйте позже.")


@router.message(F.text == "📰 Новости")
async def reply_kb_news(message: Message, state: FSMContext) -> None:
    """Handle news button from reply keyboard."""
    await cmd_news(message, state)


# ── Upsell handlers ────────────────────────────────────────────


@router.callback_query(F.data == "news:upsell_update")
async def news_upsell_update(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle update service upsell — 2,000₽."""
    if callback.from_user:
        db = await get_sales_db()
        await db.log_event(callback.from_user.id, "upsell_update_clicked")

    await callback.answer()

    if callback.message:
        await callback.message.answer(
            "⚡ **Услуга обновления — 2,000₽**\n\n"
            "Что входит:\n"
            "✅ Подключение к вашему серверу\n"
            "✅ Обновление до последней версии\n"
            "✅ Проверка работоспособности\n"
            "✅ Миграция данных (если нужно)\n\n"
            "⏱️ Время: ~15 минут\n\n"
            "📱 Для заказа напишите: @ShaerWare\n"
            "Или нажмите кнопку ниже 👇",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Оплатить 2,000₽",
                            callback_data="news:pay_update",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="📞 Связаться с менеджером",
                            url="https://t.me/ShaerWare",
                        )
                    ],
                ]
            ),
        )


@router.callback_query(F.data == "news:upsell_install")
async def news_upsell_install(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle install service upsell — redirect to basic checkout."""
    if callback.from_user:
        db = await get_sales_db()
        await db.log_event(callback.from_user.id, "upsell_install_clicked")

    await callback.answer()

    # Redirect to basic checkout
    if callback.message:
        from ..sales.keyboards import basic_checkout_kb
        from ..sales.texts import BASIC_CHECKOUT_TEXT

        await callback.message.answer(
            BASIC_CHECKOUT_TEXT,
            reply_markup=basic_checkout_kb(),
        )


@router.callback_query(F.data == "news:pay_update")
async def news_pay_update(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle payment for update service."""
    if callback.from_user:
        db = await get_sales_db()
        await db.log_event(callback.from_user.id, "pay_update_initiated")

    await callback.answer()

    # Try to send invoice for update service
    from aiogram.types import LabeledPrice

    from ..config import get_telegram_settings

    settings = get_telegram_settings()

    if settings.payment_provider_token and callback.message:
        try:
            await callback.message.answer_invoice(
                title="AI Secretary — Обновление",
                description=(
                    "Обновление AI Secretary до последней версии:\n"
                    "✅ Подключение по SSH\n"
                    "✅ Обновление за 15 минут\n"
                    "✅ Проверка работоспособности\n"
                    "✅ Миграция данных"
                ),
                payload=f"update_{callback.from_user.id}",
                provider_token=settings.payment_provider_token,
                currency=settings.payment_currency,
                prices=[LabeledPrice(label="Обновление", amount=200000)],  # 2000₽
                need_name=True,
                need_phone_number=True,
                need_email=True,
            )
            return
        except Exception as e:
            logger.error(f"Failed to send update invoice: {e}")

    # Fallback to contact
    if callback.message:
        await callback.message.answer(
            "💳 **Оплата обновления — 2,000₽**\n\n"
            "Для оплаты свяжитесь с нами:\n\n"
            "📱 Telegram: @ShaerWare\n\n"
            "После оплаты согласуем время обновления.",
        )


@router.callback_query(F.data == "news:subscribe")
async def news_subscribe(callback: CallbackQuery, state: FSMContext) -> None:
    """Subscribe to news updates."""
    if callback.from_user:
        db = await get_sales_db()
        await db.update_user(callback.from_user.id, subscribed=True)
        await db.log_event(callback.from_user.id, "news_subscribed")

    await callback.answer("✅ Вы подписаны на обновления!")

    if callback.message:
        await callback.message.answer(
            "🔔 Вы подписаны на новости AI Secretary!\n\n"
            "Буду присылать уведомления о важных обновлениях."
        )


@router.callback_query(F.data == "news:unsubscribe")
async def news_unsubscribe(callback: CallbackQuery, state: FSMContext) -> None:
    """Unsubscribe from news updates."""
    if callback.from_user:
        db = await get_sales_db()
        await db.update_user(callback.from_user.id, subscribed=False)
        await db.log_event(callback.from_user.id, "news_unsubscribed")

    await callback.answer("Вы отписаны от обновлений")

    if callback.message:
        await callback.message.answer(
            "🔕 Вы отписаны от новостей.\n\nЧтобы подписаться снова, используйте /news"
        )


# ── Admin commands ────────────────────────────────────────────


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext) -> None:
    """Admin command to manually trigger news broadcast.

    Usage:
        /broadcast - check and send only new PRs
        /broadcast force - send all recent PRs (ignore already sent)
    """
    if not message.from_user:
        return

    # Check if user is admin
    settings = get_telegram_settings()
    admin_ids = settings.get_admin_ids()

    if message.from_user.id not in admin_ids:
        await message.answer("⛔ Эта команда только для администраторов")
        return

    db = await get_sales_db()
    await db.log_event(message.from_user.id, "broadcast_manual")

    # Check for "force" argument
    args = message.text.split() if message.text else []
    force_mode = len(args) > 1 and args[1].lower() == "force"

    status_msg = await message.answer(
        "📡 Принудительная рассылка..." if force_mode else "📡 Проверяю новые PR..."
    )

    try:
        # skip_initial=False means it will broadcast even on first run
        await check_and_broadcast_news(message.bot, skip_initial=not force_mode)

        # Get stats
        subscribers_count = await db.get_subscribers_count()

        await status_msg.edit_text(f"✅ Рассылка завершена!\n\n📊 Подписчиков: {subscribers_count}")
    except Exception as e:
        logger.error(f"Manual broadcast failed: {e}")
        await status_msg.edit_text(f"❌ Ошибка рассылки: {e}")
