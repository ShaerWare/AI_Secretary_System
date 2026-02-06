"""Inline keyboard builders for the sales funnel.

All callback_data values are prefixed with ``sales:`` to avoid
conflicts with the existing AI-chat callbacks (``model:``).
"""

from typing import Any

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


GITHUB_URL = "https://github.com/ShaerWare/AI_Secretary_System"
WIKI_URL = "https://github.com/ShaerWare/AI_Secretary_System/wiki"


# ── Default action buttons (fallback when not loaded from API) ──────────

DEFAULT_ACTION_BUTTONS: list[dict[str, Any]] = [
    {"id": "diy", "label": "Установить самостоятельно", "icon": "📦", "order": 1, "enabled": True},
    {"id": "pay_5k", "label": "Оплата 5К", "icon": "💳", "order": 2, "enabled": True},
    {"id": "support", "label": "Техподдержка", "icon": "🛠️", "order": 3, "enabled": True},
    {"id": "wiki", "label": "Wiki", "icon": "📚", "order": 4, "enabled": True},
    {"id": "ask", "label": "Задать вопрос", "icon": "❓", "order": 5, "enabled": True},
    {"id": "news", "label": "Новости", "icon": "📰", "order": 6, "enabled": True},
    {"id": "start", "label": "Старт", "icon": "🚀", "order": 7, "enabled": True},
    {"id": "tz_calc", "label": "Рассчитать заказ", "icon": "📋", "order": 8, "enabled": True},
]

# Button ID to text mapping (for handler routing)
BUTTON_ID_TO_TEXT: dict[str, str] = {}


def _update_button_mapping(buttons: list[dict[str, Any]]) -> None:
    """Update button ID to text mapping for handler routing."""
    # No global needed - we're mutating the dict, not reassigning
    BUTTON_ID_TO_TEXT.clear()
    for btn in buttons:
        if btn.get("enabled", True):
            icon = btn.get("icon", "")
            label = btn.get("label", "")
            text = f"{icon} {label}" if icon else label
            BUTTON_ID_TO_TEXT[btn["id"]] = text


def get_button_id_by_text(text: str) -> str | None:
    """Get button ID by its display text (for routing)."""
    for btn_id, btn_text in BUTTON_ID_TO_TEXT.items():
        if btn_text == text:
            return btn_id
    return None


# ── Persistent Reply Keyboard (always visible at bottom) ────────────────


def build_main_keyboard(action_buttons: list[dict[str, Any]] | None = None) -> ReplyKeyboardMarkup:
    """Build main reply keyboard from action_buttons config.

    Args:
        action_buttons: List of button configs from API. If None, uses defaults.

    Returns:
        ReplyKeyboardMarkup with buttons arranged in rows.
    """
    buttons = action_buttons or DEFAULT_ACTION_BUTTONS

    # Update button mapping for handler routing
    _update_button_mapping(buttons)

    # Filter enabled buttons and sort by order
    enabled = sorted(
        [b for b in buttons if b.get("enabled", True)],
        key=lambda x: x.get("order", 0),
    )

    if not enabled:
        # Fallback to single start button
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🚀 Старт")]],
            resize_keyboard=True,
        )

    # Build keyboard rows (layout from button config or default 2-3 per row)
    keyboard: list[list[KeyboardButton]] = []

    # Group buttons by row (using row_index if available, else auto-layout)
    rows: dict[int, list[dict[str, Any]]] = {}
    for btn in enabled:
        row_idx = btn.get("row", len(rows))
        if row_idx not in rows:
            rows[row_idx] = []
        rows[row_idx].append(btn)

    # If no row info, use default layout
    if len(rows) == 1 and 0 in rows and len(rows[0]) == len(enabled):
        # No row info provided - use default 2-3-3-1 layout
        layout = [1, 3, 3, 1]  # [diy], [pay, support, wiki], [ask, news, start], [tz]
        idx = 0
        for row_size in layout:
            row = []
            for _ in range(row_size):
                if idx < len(enabled):
                    btn = enabled[idx]
                    icon = btn.get("icon", "")
                    label = btn.get("label", "")
                    text = f"{icon} {label}" if icon else label
                    row.append(KeyboardButton(text=text))
                    idx += 1
            if row:
                keyboard.append(row)
    else:
        # Use row info from config
        for row_idx in sorted(rows.keys()):
            row = []
            for btn in rows[row_idx]:
                icon = btn.get("icon", "")
                label = btn.get("label", "")
                text = f"{icon} {label}" if icon else label
                row.append(KeyboardButton(text=text))
            if row:
                keyboard.append(row)

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Напишите сообщение или выберите действие...",
    )


def main_reply_kb(action_buttons: list[dict[str, Any]] | None = None) -> ReplyKeyboardMarkup:
    """Main keyboard for welcome screen.

    Args:
        action_buttons: Optional list of button configs from API.
                       If None, uses DEFAULT_ACTION_BUTTONS.
    """
    return build_main_keyboard(action_buttons)


def submenu_reply_kb(action_buttons: list[dict[str, Any]] | None = None) -> ReplyKeyboardMarkup:
    """Keyboard for submenus — has back button.

    Args:
        action_buttons: Optional list of button configs from API.
                       If None, uses DEFAULT_ACTION_BUTTONS.
    """
    # Build main keyboard and add back button
    kb = build_main_keyboard(action_buttons)

    # Replace last button in third row with back button if it exists
    if len(kb.keyboard) >= 3 and len(kb.keyboard[2]) >= 3:
        kb.keyboard[2][-1] = KeyboardButton(text="← Назад")

    return kb


# ── Welcome ────────────────────────────────────────────────


def welcome_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Начать (30 сек)", callback_data="sales:start_quiz")],
            [
                InlineKeyboardButton(text="📚 Сразу в GitHub", url=GITHUB_URL),
                InlineKeyboardButton(text="❓ Что это такое?", callback_data="sales:what_is"),
            ],
        ]
    )


def what_is_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Подобрать вариант", callback_data="sales:start_quiz")],
            [InlineKeyboardButton(text="📚 GitHub", url=GITHUB_URL)],
            [InlineKeyboardButton(text="← Назад", callback_data="sales:back_welcome")],
        ]
    )


# ── Quiz ───────────────────────────────────────────────────


def quiz_tech_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛠️ Люблю сам разбираться в настройках",
                    callback_data="sales:qt_diy",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🤝 Предпочитаю готовое решение",
                    callback_data="sales:qt_ready",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏢 У меня бизнес-задача, нужна интеграция",
                    callback_data="sales:qt_business",
                )
            ],
        ]
    )


def quiz_infra_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, есть сервер с GPU",
                    callback_data="sales:qi_gpu",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💻 Есть сервер, но без GPU",
                    callback_data="sales:qi_cpu",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Нет сервера",
                    callback_data="sales:qi_none",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🤷 Не знаю / Нужна консультация",
                    callback_data="sales:qi_unknown",
                )
            ],
        ]
    )


# ── DIY Path ───────────────────────────────────────────────


def diy_gpu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="GTX 1660/1070/1080 (6-8 GB)",
                    callback_data="sales:gpu_gtx_16xx",
                )
            ],
            [
                InlineKeyboardButton(
                    text="RTX 3060/3070 (8-12 GB)",
                    callback_data="sales:gpu_rtx_30xx_low",
                )
            ],
            [
                InlineKeyboardButton(
                    text="RTX 3080/3090 (10-24 GB)",
                    callback_data="sales:gpu_rtx_30xx_high",
                )
            ],
            [
                InlineKeyboardButton(
                    text="RTX 4080/4090 (16-24 GB)",
                    callback_data="sales:gpu_rtx_40xx",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Другая (напишу модель)",
                    callback_data="sales:gpu_other",
                )
            ],
        ]
    )


def diy_audit_result_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📦 Скачать с GitHub (бесплатно)",
                    callback_data="sales:diy_github",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚡ Установить за меня (5,000₽)",
                    callback_data="sales:diy_install_5k",
                )
            ],
            [
                InlineKeyboardButton(text="📚 Документация", url=GITHUB_URL),
                InlineKeyboardButton(text="❓ Есть вопросы", callback_data="sales:contact"),
            ],
        ]
    )


def diy_github_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Открыть GitHub", url=GITHUB_URL)],
            [InlineKeyboardButton(text="📚 Документация", url=GITHUB_URL + "#readme")],
            [InlineKeyboardButton(text="← Главное меню", callback_data="sales:back_welcome")],
        ]
    )


# ── Basic Path ─────────────────────────────────────────────


def basic_value_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚡ Установить за 5,000₽",
                    callback_data="sales:basic_checkout",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎬 Посмотреть демо",
                    callback_data="sales:basic_demo",
                ),
                InlineKeyboardButton(
                    text="❓ Есть вопросы",
                    callback_data="sales:contact",
                ),
            ],
        ]
    )


def basic_demo_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚡ Хочу такое!",
                    callback_data="sales:basic_checkout",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❓ Есть вопросы",
                    callback_data="sales:contact",
                ),
                InlineKeyboardButton(
                    text="← Назад",
                    callback_data="sales:basic_back_value",
                ),
            ],
        ]
    )


def basic_checkout_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Оплатить 5,000₽",
                    callback_data="sales:basic_pay",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❓ Что если нет GPU",
                    callback_data="sales:basic_no_gpu",
                ),
                InlineKeyboardButton(
                    text="📞 Задать вопрос",
                    callback_data="sales:contact",
                ),
            ],
        ]
    )


def basic_no_gpu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="1️⃣ CPU режим",
                    callback_data="sales:nogpu_cpu",
                )
            ],
            [
                InlineKeyboardButton(
                    text="2️⃣ Аренда VPS",
                    callback_data="sales:nogpu_vps",
                )
            ],
            [
                InlineKeyboardButton(
                    text="3️⃣ Свой сервер",
                    callback_data="sales:nogpu_own",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🤔 Помогите выбрать",
                    callback_data="sales:contact",
                )
            ],
        ]
    )


# ── Custom Path ────────────────────────────────────────────


def custom_intro_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎯 Да, опишу задачу",
                    callback_data="sales:custom_start",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💰 Сначала цены",
                    callback_data="sales:custom_prices",
                ),
                InlineKeyboardButton(
                    text="📞 Позвоните мне",
                    callback_data="sales:contact",
                ),
            ],
        ]
    )


def custom_step_2_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="До 50", callback_data="sales:cv_vol_low")],
            [InlineKeyboardButton(text="50-200", callback_data="sales:cv_vol_mid")],
            [InlineKeyboardButton(text="200-1000", callback_data="sales:cv_vol_high")],
            [InlineKeyboardButton(text="Больше 1000", callback_data="sales:cv_vol_enterprise")],
            [InlineKeyboardButton(text="Пока не знаю", callback_data="sales:cv_vol_unknown")],
        ]
    )


def custom_step_3_kb(selected: set[str] | None = None) -> InlineKeyboardMarkup:
    """Integration multi-select. Selected items get a checkmark."""
    selected = selected or set()
    options = [
        ("Bitrix24", "int_bitrix"),
        ("amoCRM", "int_amo"),
        ("1С", "int_1c"),
        ("Телефония", "int_phone"),
        ("Своя система (API)", "int_custom"),
        ("Не нужны", "int_none"),
    ]
    buttons = []
    for label, key in options:
        prefix = "☑ " if key in selected else "☐ "
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix}{label}",
                    callback_data=f"sales:ci_{key}",
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text="✅ Далее", callback_data="sales:ci_done")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def custom_step_4_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Срочно (1-2 недели)", callback_data="sales:ct_time_urgent"
                )
            ],
            [InlineKeyboardButton(text="В течение месяца", callback_data="sales:ct_time_month")],
            [
                InlineKeyboardButton(
                    text="В течение квартала", callback_data="sales:ct_time_quarter"
                )
            ],
            [InlineKeyboardButton(text="Пока изучаю", callback_data="sales:ct_time_research")],
        ]
    )


def custom_step_5_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="50-100K₽", callback_data="sales:cb_budget_50")],
            [InlineKeyboardButton(text="100-200K₽", callback_data="sales:cb_budget_100")],
            [InlineKeyboardButton(text="200-500K₽", callback_data="sales:cb_budget_200")],
            [InlineKeyboardButton(text="500K₽+", callback_data="sales:cb_budget_500")],
            [InlineKeyboardButton(text="Нужен расчёт", callback_data="sales:cb_budget_unknown")],
        ]
    )


def custom_quote_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📞 Обсудить детали", callback_data="sales:contact")],
            [
                InlineKeyboardButton(
                    text="🤔 Дорого, есть попроще?",
                    callback_data="sales:custom_expensive",
                ),
                InlineKeyboardButton(
                    text="✏️ Изменить запрос",
                    callback_data="sales:custom_restart",
                ),
            ],
        ]
    )


def custom_expensive_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1️⃣ MVP", callback_data="sales:ce_mvp")],
            [InlineKeyboardButton(text="2️⃣ Этапы", callback_data="sales:ce_stages")],
            [InlineKeyboardButton(text="3️⃣ DIY", callback_data="sales:ce_diy")],
        ]
    )


# ── TZ (Technical Specification) Quiz ─────────────────────────────


def tz_project_type_kb() -> InlineKeyboardMarkup:
    """Step 1: What type of project?"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🤖 AI-ассистент / Чат-бот",
                    callback_data="tz:type_chatbot",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📞 Голосовой бот / Телефония",
                    callback_data="tz:type_voice",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔗 Интеграция с CRM/1С",
                    callback_data="tz:type_integration",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🌐 Веб-приложение / SaaS",
                    callback_data="tz:type_web",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📱 Telegram-бот",
                    callback_data="tz:type_telegram",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔧 Другое (опишу)",
                    callback_data="tz:type_other",
                )
            ],
        ]
    )


def tz_business_goal_kb() -> InlineKeyboardMarkup:
    """Step 2: What business goal?"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📉 Снизить расходы на персонал",
                    callback_data="tz:goal_cost",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📈 Увеличить продажи",
                    callback_data="tz:goal_sales",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏱️ Автоматизировать рутину",
                    callback_data="tz:goal_automation",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎯 Улучшить клиентский сервис",
                    callback_data="tz:goal_service",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚀 Масштабировать бизнес",
                    callback_data="tz:goal_scale",
                )
            ],
        ]
    )


def tz_timeline_kb() -> InlineKeyboardMarkup:
    """Step 3: Timeline?"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔥 Срочно (1-2 недели)",
                    callback_data="tz:time_urgent",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📅 В течение месяца",
                    callback_data="tz:time_month",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📆 В течение квартала",
                    callback_data="tz:time_quarter",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔍 Пока изучаю варианты",
                    callback_data="tz:time_research",
                )
            ],
        ]
    )


def tz_budget_kb() -> InlineKeyboardMarkup:
    """Step 4: Budget range?"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="50-100К₽",
                    callback_data="tz:budget_50",
                )
            ],
            [
                InlineKeyboardButton(
                    text="100-200К₽",
                    callback_data="tz:budget_100",
                )
            ],
            [
                InlineKeyboardButton(
                    text="200-500К₽",
                    callback_data="tz:budget_200",
                )
            ],
            [
                InlineKeyboardButton(
                    text="500К₽+",
                    callback_data="tz:budget_500",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💡 Нужен расчёт",
                    callback_data="tz:budget_calculate",
                )
            ],
        ]
    )


def tz_result_kb() -> InlineKeyboardMarkup:
    """After TZ is generated - action buttons for qualified leads."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Оплатить первый спринт (50,000₽)",
                    callback_data="tz:pay_sprint",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📞 Обсудить с менеджером",
                    url="https://t.me/ShaerWare",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Уточнить требования",
                    callback_data="tz:restart",
                )
            ],
            [
                InlineKeyboardButton(
                    text="← Главное меню",
                    callback_data="sales:back_welcome",
                )
            ],
        ]
    )


def tz_unqualified_kb() -> InlineKeyboardMarkup:
    """Buttons for unqualified leads (project too small)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📦 GitHub (бесплатно)",
                    url=GITHUB_URL,
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚡ Базовая установка (5,000₽)",
                    callback_data="sales:basic_checkout",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📝 У меня проект побольше",
                    callback_data="tz:restart",
                )
            ],
            [
                InlineKeyboardButton(
                    text="← Главное меню",
                    callback_data="sales:back_welcome",
                )
            ],
        ]
    )


# ── FAQ ─────────────────────────────────────────────────────


def faq_kb() -> InlineKeyboardMarkup:
    """FAQ questions as inline buttons."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❓ Что такое AI Secretary?",
                    callback_data="faq:what_is",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💻 Какое железо нужно?",
                    callback_data="faq:hardware",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💰 Сколько стоит?",
                    callback_data="faq:price",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🌐 Работает ли офлайн?",
                    callback_data="faq:offline",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔒 Безопасны ли мои данные?",
                    callback_data="faq:security",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛠️ Как установить самому?",
                    callback_data="faq:install",
                )
            ],
            [
                InlineKeyboardButton(
                    text="☁️ Чем отличается от ChatGPT?",
                    callback_data="faq:vs_cloud",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔗 Какие интеграции есть?",
                    callback_data="faq:integrations",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📞 Есть ли техподдержка?",
                    callback_data="faq:support",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🆓 Можно попробовать бесплатно?",
                    callback_data="faq:free_trial",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🌐 Работает с облачными AI?",
                    callback_data="faq:cloud_models",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📚 Открыть Wiki",
                    url=WIKI_URL,
                )
            ],
        ]
    )


def faq_back_kb() -> InlineKeyboardMarkup:
    """Back button after FAQ answer."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="← К списку вопросов",
                    callback_data="faq:back",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📚 Открыть Wiki",
                    url=WIKI_URL,
                )
            ],
        ]
    )


# ── Common ─────────────────────────────────────────────────


def menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Подобрать вариант", callback_data="sales:start_quiz")],
            [InlineKeyboardButton(text="📚 GitHub", url=GITHUB_URL)],
            [InlineKeyboardButton(text="📞 Связаться", callback_data="sales:contact")],
        ]
    )


def contact_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="← Главное меню", callback_data="sales:back_welcome")],
        ]
    )
