"""Генератор иллюстраций README: python docs/assets/_generate.py

Пишет <name>.ru.svg и <name>.en.svg рядом с собой. Тексты — в словарях T_RU / T_EN,
разметка — в функциях ниже. Данные в примерах условные. Содержимое КП (товары, кнопки
в Telegram) одинаково в обеих версиях: интерфейс бота по-русски, переводятся только подписи.
"""

from pathlib import Path
from xml.sax.saxutils import escape


OUT = Path(__file__).parent
FONT = "Segoe UI, Roboto, Helvetica, Arial, sans-serif"

T_RU = {
    "hero_kicker": "OPEN SOURCE · SELF-HOSTED · RU / EN / KK",
    "hero_tag1": "ИИ-секретарь и менеджер продаж, который собирает КП из переписки",
    "hero_tag2": "и не выдумывает цены. Человек утверждает каждую отправку.",
    "hero_chips": [
        "КП из WhatsApp",
        "утверждение в Telegram",
        "веб-чат с ветками",
        "локальная LLM",
        "клон голоса",
    ],
    "flow_client": "WHATSAPP · КЛИЕНТ",
    "flow_manager": "TELEGRAM · МЕНЕДЖЕР",
    "flow_steps": [
        "вытащил позиции из переписки",
        "нашёл каждую в живом каталоге",
        "сомнительное — только менеджеру",
        "собрал черновик КП",
    ],
    "flow_assistant": "ассистент",
    "flow_sent": "КП отправлено клиенту",
    "flow_caption": "Клиент попросил КП — через минуту у менеджера готовый черновик, одна кнопка — и он у клиента.",
    "honest_title": "Цены и наличие — только из каталога. Правило в коде, не в промпте.",
    "honest_req": "Запрос клиента",
    "honest_req_items": ["автоматы 16А — 12 шт", "кабель 3×2,5 — 100 м", "УЗО 30 мА"],
    "honest_search": "Поиск по живому каталогу",
    "honest_search_sub": "нет совпадения → пустой список",
    "honest_found": "Нашлось уверенно и с ценой",
    "honest_found_sub": "→ в КП, цена из каталога",
    "honest_missing": "Нет точного совпадения",
    "honest_missing_sub": "→ «⚠ Не вошло» — менеджеру, не клиенту",
    "honest_never": "Никогда",
    "honest_never_items": [
        "«похожий товар» с выдуманной ценой",
        "«в наличии» без остатка",
        "цены из памяти о клиенте",
        "отправка без человека",
    ],
    "chat_title": "Подготовка тендерной заявки",
    "chat_meta": "14 сообщений · свой промпт · 3 файла контекста",
    "chat_ctx": "41% контекста",
    "chat_rag": "RAG: 2 базы ▾",
    "chat_tree_btn": "Дерево веток",
    "chat_q1": "Сравни два варианта поставки",
    "chat_q2": "и посчитай итог с НДС",
    "chat_a": "Вариант Б дешевле на 12%, но срок 21 день…",
    "chat_versions": "◀ 2 / 3 ▶   ответ перегенерирован, все версии сохранены",
    "chat_btns": ["Итоги ветки", "В контекст", "Озвучить"],
    "chat_settings": "Настройки сессии",
    "chat_prompt": "Промпт: «Ты — тендерный специалист…»",
    "chat_files": "Контекст: ТЗ.md · прайс.csv · summary_10-42.md",
    "chat_files_sub": "файлы подставляются в каждый запрос этой сессии",
    "chat_input": "Сообщение…  (голосом тоже можно)",
    "chat_tree": "Дерево веток",
    "chat_tree_notes": [
        "правка вопроса или перегенерация = новая ветка;",
        "клик по узлу — переключиться, старое не теряется;",
        "при шаринге коллега видит только свою ветку",
    ],
    "off_title": "Полностью офлайн: всё на одной RTX 3060 12 ГБ",
    "off_sub": "облачные модели — по желанию, данные не покидают сервер",
    "off_tiles": [
        ("LLM", "vLLM · Qwen2.5 · Llama-3.1 · DeepSeek"),
        ("Голос", "клон XTTS v2 · OpenVoice · Piper"),
        ("Речь → текст", "Vosk (стриминг) · Whisper"),
        ("Дообучение", "LoRA по экспорту Telegram, hot-swap"),
        ("Знания", "Wiki-RAG · локальные эмбеддинги"),
        ("Данные", "SQLite + Redis · свой сервер"),
    ],
    "off_cloud": "или облако: Claude · GPT · Gemini · DeepSeek · Kimi · OpenRouter · мост Claude Code",
    "ch_title": "Все каналы — один ассистент, одна панель",
    "ch_in": [
        ("Telegram", "много ботов"),
        ("WhatsApp", "Cloud API или QR-мост"),
        ("Виджет на сайт", "несколько сайтов"),
        ("Телефон", "SIM7600: звонки и SMS"),
        ("Android", "приватные сессии"),
    ],
    "ch_core": "AI Secretary",
    "ch_core_sub": ["FAQ · RAG · CRM · КП", "память о клиенте"],
    "ch_out": [
        ("Менеджер", "утверждает КП в мессенджере"),
        ("Админ-панель", "Vue 3 PWA · роли · аудит"),
        ("amoCRM", "лиды и заметки"),
        ("Оплата", "ЮMoney · Telegram Stars"),
    ],
}

T_EN = {
    "hero_kicker": "OPEN SOURCE · SELF-HOSTED · RU / EN / KK",
    "hero_tag1": "An AI secretary and sales assistant that drafts offers from chats",
    "hero_tag2": "and never invents prices. A human approves every send.",
    "hero_chips": [
        "offers from WhatsApp",
        "approve in Telegram",
        "branching web chat",
        "local LLM",
        "voice cloning",
        "phone line",
    ],
    "flow_client": "WHATSAPP · CLIENT",
    "flow_manager": "TELEGRAM · MANAGER",
    "flow_steps": [
        "extracted items from the chat",
        "found each one in the live catalog",
        "doubtful lines go to the manager only",
        "built a draft offer",
    ],
    "flow_assistant": "assistant",
    "flow_sent": "Offer sent to the client",
    "flow_caption": "A client asks for a quote — a minute later the manager has a draft; one tap and the client has it.",
    "honest_title": "Prices and stock come only from the catalog. Enforced in code, not in a prompt.",
    "honest_req": "Client request",
    "honest_req_items": ["16A breakers — 12 pcs", "cable 3×2.5 — 100 m", "RCD 30 mA"],
    "honest_search": "Live catalog search",
    "honest_search_sub": "no match → empty list",
    "honest_found": "Confident match with a price",
    "honest_found_sub": "→ into the offer, catalog price",
    "honest_missing": "No exact match",
    "honest_missing_sub": "→ «⚠ Left out»: manager only",
    "honest_never": "Never",
    "honest_never_items": [
        "a «similar item» with a made-up price",
        "«in stock» without stock",
        "prices from client memory",
        "a send without a human",
    ],
    "chat_title": "Tender bid preparation",
    "chat_meta": "14 messages · custom prompt · 3 context files",
    "chat_ctx": "41% of context",
    "chat_rag": "RAG: 2 bases ▾",
    "chat_tree_btn": "Branch tree",
    "chat_q1": "Compare the two delivery options",
    "chat_q2": "and total them up with VAT",
    "chat_a": "Option B is 12% cheaper, but takes 21 days…",
    "chat_versions": "◀ 2 / 3 ▶   answer regenerated, every version kept",
    "chat_btns": ["Summarize", "To context", "Read aloud"],
    "chat_settings": "Session settings",
    "chat_prompt": "Prompt: «You are a tender specialist…»",
    "chat_files": "Context: spec.md · prices.csv · summary_10-42.md",
    "chat_files_sub": "files go into every request of this session",
    "chat_input": "Message…  (or use your voice)",
    "chat_tree": "Branch tree",
    "chat_tree_notes": [
        "editing a question or regenerating = a new branch;",
        "click a node to switch, nothing is lost;",
        "a shared chat shows only the shared branch",
    ],
    "off_title": "Fully offline: everything on one RTX 3060 12 GB",
    "off_sub": "cloud models are optional, data stays on your server",
    "off_tiles": [
        ("LLM", "vLLM · Qwen2.5 · Llama-3.1 · DeepSeek"),
        ("Voice", "XTTS v2 cloning · OpenVoice · Piper"),
        ("Speech → text", "Vosk (streaming) · Whisper"),
        ("Fine-tuning", "LoRA on a Telegram export, hot-swap"),
        ("Knowledge", "Wiki-RAG · local embeddings"),
        ("Data", "SQLite + Redis · your own server"),
    ],
    "off_cloud": "or cloud: Claude · GPT · Gemini · DeepSeek · Kimi · OpenRouter · Claude Code bridge",
    "ch_title": "Every channel — one assistant, one panel",
    "ch_in": [
        ("Telegram", "many bots"),
        ("WhatsApp", "Cloud API or QR bridge"),
        ("Website widget", "several sites"),
        ("Phone", "SIM7600: calls and SMS"),
        ("Android", "private sessions"),
    ],
    "ch_core": "AI Secretary",
    "ch_core_sub": ["FAQ · RAG · CRM · offers", "client memory"],
    "ch_out": [
        ("Manager", "approves offers in a messenger"),
        ("Admin panel", "Vue 3 PWA · roles · audit"),
        ("amoCRM", "leads and notes"),
        ("Payments", "YooMoney · Telegram Stars"),
    ],
}


def e(s: str) -> str:
    return escape(s)


def svg(w: int, h: int, body: str, style: str = "") -> str:
    css = f"<style>{style}</style>" if style else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="{FONT}">{css}\n{body}\n</svg>\n'
    )


def text(x, y, s, size=14, fill="#e9edef", weight=None, anchor=None, cls=None, spacing=None):
    attrs = f'x="{x}" y="{y}" fill="{fill}" font-size="{size}"'
    if weight:
        attrs += f' font-weight="{weight}"'
    if anchor:
        attrs += f' text-anchor="{anchor}"'
    if cls:
        attrs += f' class="{cls}"'
    if spacing:
        attrs += f' letter-spacing="{spacing}"'
    return f"<text {attrs}>{e(s)}</text>"


# ---------------------------------------------------------------- hero


def hero(t) -> str:
    chips, x = [], 48
    for c in t["hero_chips"]:
        w = int(len(c) * 7.1) + 24
        chips.append(
            f'<rect x="{x}" y="176" width="{w}" height="30" rx="15" fill="#ffffff" fill-opacity=".09"/>'
            + text(x + w / 2, 196, c, 12.5, "#dbe4ec", anchor="middle")
        )
        x += w + 7
    body = f"""
<defs>
  <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#0e1621"/><stop offset=".6" stop-color="#132a43"/><stop offset="1" stop-color="#1d4c7a"/>
  </linearGradient>
  <radialGradient id="glow" cx=".86" cy=".3" r=".5">
    <stop offset="0" stop-color="#6ab3f3" stop-opacity=".35"/><stop offset="1" stop-color="#6ab3f3" stop-opacity="0"/>
  </radialGradient>
</defs>
<rect width="880" height="232" rx="18" fill="url(#g)"/>
<rect width="880" height="232" rx="18" fill="url(#glow)"/>
<g transform="translate(724 34)" opacity=".95">
  <rect x="0" y="0" width="118" height="78" rx="14" fill="#182533" stroke="#2b5278"/>
  <rect x="12" y="14" width="70" height="8" rx="4" fill="#6ab3f3"/>
  <rect x="12" y="30" width="94" height="6" rx="3" fill="#3a5068"/>
  <rect x="12" y="42" width="80" height="6" rx="3" fill="#3a5068"/>
  <rect x="12" y="56" width="44" height="14" rx="4" fill="#2b5278"/>
  <rect x="62" y="56" width="44" height="14" rx="4" fill="#2b5278"/>
  <path class="tick" d="M24 63 l5 4 l9 -9" stroke="#4ade80" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <rect x="-58" y="88" width="104" height="34" rx="12" fill="#005c4b"/>
  <rect x="-48" y="99" width="60" height="5" rx="2.5" fill="#9fe3cf"/>
  <rect x="-48" y="109" width="40" height="5" rx="2.5" fill="#9fe3cf"/>
</g>
{text(48, 54, t["hero_kicker"], 13, "#6ab3f3", spacing="2")}
{text(48, 104, "AI Secretary System", 46, "#ffffff", weight="700")}
{text(48, 136, t["hero_tag1"], 17, "#dbe4ec")}
{text(48, 160, t["hero_tag2"], 17, "#dbe4ec")}
{"".join(chips)}
"""
    style = ".tick{stroke-dasharray:20;animation:d 3s ease-in-out infinite}@keyframes d{0%,30%{stroke-dashoffset:20}55%,100%{stroke-dashoffset:0}}"
    return svg(880, 232, body, style)


# ---------------------------------------------------------------- animated КП flow

CYCLE = 14  # seconds


def fade_kf(name: str, start: float, end: float = 93) -> str:
    """opacity 0 → 1 at start% (with a slide-up), stays until end%, gone 3% later."""
    a = max(start - 3, 0)
    return (
        f"@keyframes {name}{{0%,{a}%{{opacity:0;transform:translateY(8px)}}"
        f"{start}%,{end}%{{opacity:1;transform:none}}{min(end + 3, 100)}%,100%{{opacity:0}}}}"
        f".{name}{{opacity:0;animation:{name} {CYCLE}s infinite}}"
    )


def kp_flow(t) -> str:
    style = [fade_kf("c1", 4), fade_kf("ty", 10, 40), fade_kf("card", 42)]
    for i in range(4):
        style.append(fade_kf(f"s{i}", 14 + i * 7))
    style.append(fade_kf("press", 62, 70))
    style.append(fade_kf("sent", 72))
    style.append(fade_kf("c2", 76))
    style.append(
        "@keyframes btn{0%,60%{fill:#2b5278}63%,72%{fill:#3f8bd6}76%,100%{fill:#2b5278}}"
        f".btn{{animation:btn {CYCLE}s infinite}}"
        "@keyframes dot{0%,100%{opacity:.25}50%{opacity:1}}"
        ".d1{animation:dot 1s infinite}.d2{animation:dot 1s .2s infinite}.d3{animation:dot 1s .4s infinite}"
        ".c1,.c2,.card,.s0,.s1,.s2,.s3,.sent{transform-box:fill-box}"
    )
    steps = "".join(
        f'<g class="s{i}"><circle cx="44" cy="{214 + i * 28}" r="8" fill="#22c55e"/>'
        f'<path d="M40 {214 + i * 28} l3 3 l5 -6" stroke="#0e1621" stroke-width="2" fill="none"/>'
        + text(60, 219 + i * 28, s, 14, "#c5d0da")
        + "</g>"
        for i, s in enumerate(t["flow_steps"])
    )
    body = f"""
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#0e1621"/><stop offset="1" stop-color="#17212b"/></linearGradient></defs>
<rect width="880" height="540" rx="18" fill="url(#bg)"/>
{text(32, 44, t["flow_client"], 13, "#8b9bab", spacing="1")}
<g class="c1">
  <rect x="32" y="62" width="310" height="74" rx="12" fill="#1f2c34"/>
  {text(48, 90, "Пришлите КП: автоматы 16А 12 шт,", 15)}
  {text(48, 112, "кабель ВВГнг 3×2,5 — 100 м и УЗО", 15)}
  {text(300, 128, "10:42", 11, "#8696a0")}
</g>
<g class="ty">
  {text(32, 176, t["flow_assistant"], 13, "#8b9bab")}
  <circle class="d1" cx="118" cy="172" r="4" fill="#6ab3f3"/>
  <circle class="d2" cx="132" cy="172" r="4" fill="#6ab3f3"/>
  <circle class="d3" cx="146" cy="172" r="4" fill="#6ab3f3"/>
</g>
{steps}
<g class="c2">
  <rect x="32" y="360" width="310" height="74" rx="12" fill="#005c4b"/>
  {text(48, 388, "Здравствуйте! Подготовили КП:", 15)}
  {text(48, 410, "ar-gs.ru/kp/0018", 15, "#53bdeb")}
  {text(286, 426, "10:44 ✓✓", 11, "#53bdeb")}
</g>

{text(404, 44, t["flow_manager"], 13, "#8b9bab", spacing="1")}
<rect x="404" y="62" width="444" height="404" rx="14" fill="#141e29" stroke="#1f2d3b" stroke-dasharray="6 6"/>
<g class="card">
  <rect x="404" y="62" width="444" height="404" rx="14" fill="#182533"/>
  {text(424, 94, "КП-0018 — черновик, ждёт подтверждения", 17, "#ffffff", "600")}
  {text(424, 122, "Клиент: ТОО «Альфа-Строй» · 87 600 ₸", 14, "#c5d0da")}
  {text(424, 158, "Что подобрал ассистент", 14, "#6ab3f3", "600")}
  {text(424, 182, "1. Автомат 1P 16А C — 12 × 1 550 = 18 600 ₸", 14)}
  {text(440, 200, "по запросу «автоматы 16А»", 12, "#7f91a4")}
  {text(424, 224, "2. Кабель ВВГнг-LS 3×2,5 — 100 × 690 = 69 000 ₸", 14)}
  {text(440, 242, "по запросу «кабель 3 на 2,5»", 12, "#7f91a4")}
  {text(424, 276, "⚠ Не вошло в КП", 14, "#e5a54b", "600")}
  {text(424, 298, "• «УЗО» — точного совпадения нет", 14)}
  <rect class="btn" x="420" y="330" width="204" height="40" rx="8" fill="#2b5278"/>
  {text(522, 355, "✓ Отправить", 14, "#ffffff", "600", "middle")}
  <rect x="632" y="330" width="200" height="40" rx="8" fill="#2b5278"/>
  {text(732, 355, "Изменить текст", 14, "#ffffff", anchor="middle")}
  <rect x="420" y="378" width="204" height="40" rx="8" fill="#2b5278"/>
  {text(522, 403, "Отменить", 14, "#ffffff", anchor="middle")}
  <rect x="632" y="378" width="200" height="40" rx="8" fill="#2b5278"/>
  {text(732, 403, "Открыть в PIM", 14, "#ffffff", anchor="middle")}
  <g class="press"><circle cx="560" cy="352" r="18" fill="#ffffff" fill-opacity=".18"/>
    <path d="M556 344 l0 22 l6 -6 l4 9 l4 -2 l-4 -9 l8 0 z" fill="#ffffff" stroke="#0e1621" stroke-width="1.2"/></g>
  <g class="sent"><rect x="424" y="430" width="224" height="26" rx="13" fill="#14532d"/>
    {text(536, 448, "✓ " + t["flow_sent"], 13, "#bbf7d0", anchor="middle")}</g>
</g>
<path d="M352 256 h38" stroke="#5288c1" stroke-width="2.5"/><path d="M386 249 l10 7 l-10 7 z" fill="#5288c1"/>
{text(32, 520, t["flow_caption"], 14, "#8b9bab")}
"""
    return svg(880, 540, body, "".join(style))


# ---------------------------------------------------------------- honest search


def honest(t) -> str:
    req = "".join(
        text(48, 128 + i * 24, "• " + s, 14, "#c5d0da") for i, s in enumerate(t["honest_req_items"])
    )
    never = "".join(
        f'<g transform="translate(0 {i * 30})"><circle cx="545" cy="{305}" r="9" fill="#7f1d1d"/>'
        f'<path d="M541 301 l8 8 M549 301 l-8 8" stroke="#fecaca" stroke-width="2"/>'
        + text(564, 310, s, 13, "#fca5a5")
        + "</g>"
        for i, s in enumerate(t["honest_never_items"])
    )
    body = f"""
<rect width="880" height="440" rx="18" fill="#0f172a"/>
{text(32, 46, t["honest_title"], 17, "#ffffff", "600")}

<rect x="32" y="76" width="220" height="130" rx="12" fill="#1e293b"/>
{text(48, 102, t["honest_req"], 14, "#93c5fd", "600")}
{req}

<path d="M252 141 h40" stroke="#475569" stroke-width="2.5"/><path d="M288 134 l10 7 l-10 7 z" fill="#475569"/>
<rect x="302" y="96" width="250" height="90" rx="12" fill="#1e3a5f" stroke="#3b82f6"/>
<g transform="translate(322 122)"><circle cx="10" cy="10" r="9" stroke="#93c5fd" stroke-width="2.5" fill="none"/>
  <path d="M17 17 l8 8" stroke="#93c5fd" stroke-width="3" stroke-linecap="round"/></g>
{text(360, 136, t["honest_search"], 15, "#ffffff", "600")}
{text(360, 158, t["honest_search_sub"], 12, "#93c5fd")}

<path d="M552 126 C 580 126 575 98 602 98" stroke="#22c55e" stroke-width="2.5" fill="none"/>
<path d="M552 156 C 580 156 575 196 602 196" stroke="#f59e0b" stroke-width="2.5" fill="none"/>
<rect x="602" y="70" width="246" height="56" rx="12" fill="#052e16" stroke="#22c55e"/>
{text(620, 94, "✓ " + t["honest_found"], 14, "#86efac", "600")}
{text(620, 114, t["honest_found_sub"], 12, "#bbf7d0")}
<rect x="602" y="168" width="246" height="56" rx="12" fill="#451a03" stroke="#f59e0b"/>
{text(620, 192, "⚠ " + t["honest_missing"], 14, "#fcd34d", "600")}
{text(620, 212, t["honest_missing_sub"], 12, "#fde68a")}

<rect x="32" y="250" width="470" height="164" rx="12" fill="#111c30"/>
<g transform="translate(52 276)">
  <rect width="150" height="108" rx="10" fill="#182533"/>
  <rect x="12" y="14" width="96" height="7" rx="3.5" fill="#6ab3f3"/>
  <rect x="12" y="32" width="126" height="5" rx="2.5" fill="#3a5068"/>
  <rect x="12" y="44" width="110" height="5" rx="2.5" fill="#3a5068"/>
  <rect x="12" y="60" width="80" height="5" rx="2.5" fill="#f59e0b"/>
  <rect x="12" y="80" width="60" height="16" rx="4" fill="#2b5278"/>
  <rect x="78" y="80" width="60" height="16" rx="4" fill="#2b5278"/>
</g>

{text(222, 300, "✓", 30, "#22c55e", "700")}
{text(258, 296, "КП-0018", 15, "#ffffff", "600")}
{text(258, 318, "человек жмёт «Отправить»" if t is T_RU else "a person taps «Send»", 13, "#c5d0da")}
{text(258, 340, "двойное нажатие не отправит дважды" if t is T_RU else "a double tap won't send twice", 13, "#c5d0da")}
{text(258, 362, "таймеры напомнят, если клиент молчит" if t is T_RU else "timers nudge if the client goes quiet", 13, "#c5d0da")}

<rect x="518" y="250" width="330" height="164" rx="12" fill="#1c0a0a" stroke="#7f1d1d"/>
{text(536, 278, t["honest_never"], 14, "#fca5a5", "700")}
{never}
"""
    return svg(880, 440, body)


# ---------------------------------------------------------------- web chat with branch tree


def chat(t) -> str:
    btns = "".join(
        f'<rect x="{40 + i * 96}" y="208" width="88" height="24" rx="6" fill="#374151"/>'
        + text(84 + i * 96, 225, s, 11, "#e5e7eb", anchor="middle")
        for i, s in enumerate(t["chat_btns"])
    )
    notes = "".join(
        text(490, 424 + i * 18, s, 12, "#9ca3af") for i, s in enumerate(t["chat_tree_notes"])
    )
    nodes = [
        (520, 136, "1", "#374151"),
        (520, 196, "2", "#374151"),
        (520, 256, "A", "#374151"),
        (640, 256, "B", "#4f46e5"),
        (760, 256, "C", "#374151"),
        (520, 316, "A2", "#374151"),
        (640, 316, "B2", "#4f46e5"),
        (760, 376, "B3′", "#374151"),
    ]
    node_svg = "".join(
        f'<circle cx="{x}" cy="{y}" r="15" fill="{c}"/>'
        + text(x, y + 4, s, 11, "#ffffff", anchor="middle")
        for x, y, s, c in nodes
    )
    body = f"""
<rect width="880" height="500" rx="18" fill="#111827"/>
<path d="M18 0 H862 A18 18 0 0 1 880 18 V56 H0 V18 A18 18 0 0 1 18 0 Z" fill="#1f2937"/>
{text(24, 26, t["chat_title"], 15, "#f9fafb", "600")}
{text(24, 44, t["chat_meta"], 11, "#9ca3af")}
<rect x="296" y="34" width="110" height="6" rx="3" fill="#374151"/>
<rect x="296" y="34" width="45" height="6" rx="3" fill="#22c55e"/>
{text(414, 40, t["chat_ctx"], 11, "#9ca3af")}
<rect x="520" y="14" width="128" height="28" rx="7" fill="#374151"/>
{text(584, 33, "Claude · Qwen · GPT ▾", 12, "#e5e7eb", anchor="middle")}
<rect x="656" y="14" width="96" height="28" rx="7" fill="#374151"/>
{text(704, 33, t["chat_rag"], 12, "#e5e7eb", anchor="middle")}
<rect x="760" y="14" width="96" height="28" rx="7" fill="#4f46e5"/>
{text(808, 33, t["chat_tree_btn"], 12, "#ffffff", anchor="middle")}

<rect x="24" y="80" width="330" height="54" rx="12" fill="#4f46e5"/>
{text(40, 104, t["chat_q1"], 13, "#ffffff")}
{text(40, 122, t["chat_q2"], 13, "#ffffff")}
<rect x="24" y="148" width="420" height="96" rx="12" fill="#1f2937"/>
{text(40, 172, t["chat_a"], 13, "#e5e7eb")}
{text(40, 194, t["chat_versions"], 12, "#9ca3af")}
{btns}
<rect x="24" y="262" width="420" height="104" rx="12" fill="#0f172a" stroke="#374151"/>
{text(40, 286, t["chat_settings"], 12, "#a5b4fc", "600")}
{text(40, 308, t["chat_prompt"], 12, "#d1d5db")}
{text(40, 328, t["chat_files"], 12, "#d1d5db")}
{text(40, 348, t["chat_files_sub"], 11, "#9ca3af")}
<rect x="24" y="386" width="420" height="40" rx="10" fill="#1f2937"/>
{text(40, 411, t["chat_input"], 13, "#6b7280")}
<g transform="translate(408 394)"><rect width="24" height="24" rx="12" fill="#4f46e5"/>
  <rect x="9" y="5" width="6" height="10" rx="3" fill="#fff"/><path d="M7 12 a5 5 0 0 0 10 0 M12 17 v3" stroke="#fff" stroke-width="1.5" fill="none"/></g>

<rect x="470" y="72" width="386" height="406" rx="12" fill="#0b1220" stroke="#1f2937"/>
{text(490, 100, t["chat_tree"], 14, "#f9fafb", "600")}
<g stroke="#4b5563" stroke-width="2" fill="none">
  <path d="M520 136 V256"/><path d="M520 196 C520 226 640 226 640 256"/><path d="M520 196 C520 226 760 226 760 256"/>
  <path d="M520 256 V316"/><path d="M640 256 V376"/><path d="M640 316 C640 346 760 346 760 376"/>
</g>
<g stroke="#818cf8" stroke-width="3" fill="none" class="path"><path d="M520 136 V196 C520 226 640 226 640 256 V376"/></g>
{node_svg}
<circle cx="640" cy="376" r="17" fill="#22c55e"/>{text(640, 380, "B3", 11, "#0b1220", "700", "middle")}
<circle class="pulse" cx="640" cy="376" r="17" fill="none" stroke="#22c55e" stroke-width="2"/>
{notes}
"""
    style = (
        ".path{stroke-dasharray:300;animation:p 6s ease-in-out infinite}"
        "@keyframes p{0%{stroke-dashoffset:300}40%,100%{stroke-dashoffset:0}}"
        ".pulse{transform-box:fill-box;transform-origin:center;animation:u 2s infinite}"
        "@keyframes u{0%{transform:scale(1);opacity:.9}100%{transform:scale(1.9);opacity:0}}"
    )
    return svg(880, 500, body, style)


# ---------------------------------------------------------------- offline stack

ICONS = {
    0: '<rect x="0" y="4" width="26" height="18" rx="3" fill="none" stroke="#c4b5fd" stroke-width="2"/>'
    '<path d="M6 10 h14 M6 15 h9" stroke="#c4b5fd" stroke-width="2"/>',
    1: '<path d="M4 9 v8 M10 5 v16 M16 2 v22 M22 7 v12" stroke="#c4b5fd" stroke-width="2.5" stroke-linecap="round"/>',
    2: '<rect x="8" y="1" width="10" height="16" rx="5" fill="none" stroke="#c4b5fd" stroke-width="2"/>'
    '<path d="M3 12 a10 10 0 0 0 20 0 M13 22 v4" stroke="#c4b5fd" stroke-width="2" fill="none"/>',
    3: '<path d="M3 20 l7 -7 l5 5 l9 -11" stroke="#c4b5fd" stroke-width="2.5" fill="none" stroke-linecap="round"/>'
    '<path d="M18 7 h6 v6" stroke="#c4b5fd" stroke-width="2.5" fill="none"/>',
    4: '<path d="M3 3 h9 a4 4 0 0 1 4 4 v16 a3 3 0 0 0 -3 -3 h-10 z M23 3 h-5" stroke="#c4b5fd" stroke-width="2" fill="none"/>',
    5: '<ellipse cx="13" cy="5" rx="10" ry="4" fill="none" stroke="#c4b5fd" stroke-width="2"/>'
    '<path d="M3 5 v14 a10 4 0 0 0 20 0 v-14 M3 12 a10 4 0 0 0 20 0" stroke="#c4b5fd" stroke-width="2" fill="none"/>',
}


def offline(t) -> str:
    tiles = []
    for i, (h, s) in enumerate(t["off_tiles"]):
        x, y = 32 + (i % 3) * 276, 110 + (i // 3) * 104
        tiles.append(
            f'<rect x="{x}" y="{y}" width="264" height="90" rx="12" fill="#1e1b3a" stroke="#3730a3"/>'
            f'<g transform="translate({x + 18} {y + 18})">{ICONS[i]}</g>'
            + text(x + 56, y + 38, h, 16, "#ffffff", "600")
            + text(x + 18, y + 70, s, 12, "#c7d2fe")
        )
    body = f"""
<rect width="880" height="380" rx="18" fill="#0c0a1f"/>
<g transform="translate(32 28)"><rect width="56" height="40" rx="6" fill="#16a34a"/>
  <rect x="6" y="6" width="44" height="22" rx="3" fill="#052e16"/>
  <circle cx="17" cy="17" r="7" fill="none" stroke="#4ade80" stroke-width="2"/><circle cx="39" cy="17" r="7" fill="none" stroke="#4ade80" stroke-width="2"/>
  <path d="M8 40 v6 M16 40 v6 M24 40 v6 M32 40 v6 M40 40 v6 M48 40 v6" stroke="#ca8a04" stroke-width="2"/></g>
{text(104, 50, t["off_title"], 20, "#ffffff", "700")}
{text(104, 74, t["off_sub"], 14, "#a5b4fc")}
{"".join(tiles)}
<rect x="32" y="328" width="816" height="34" rx="17" fill="#111827" stroke="#374151" stroke-dasharray="5 5"/>
{text(440, 350, t["off_cloud"], 13, "#9ca3af", anchor="middle")}
"""
    return svg(880, 380, body)


# ---------------------------------------------------------------- channels


def channels(t) -> str:
    colors_in = ["#2AABEE", "#25D366", "#f59e0b", "#ef4444", "#3DDC84"]
    ins, outs = [], []
    for i, (h, s) in enumerate(t["ch_in"]):
        y = 82 + i * 66
        c = colors_in[i]
        ins.append(
            f'<rect x="32" y="{y}" width="220" height="54" rx="12" fill="#111827" stroke="{c}" stroke-opacity=".6"/>'
            f'<circle cx="58" cy="{y + 27}" r="11" fill="{c}"/>'
            + text(80, y + 24, h, 14, "#ffffff", "600")
            + text(80, y + 42, s, 12, "#9ca3af")
            + f'<path class="flow" d="M252 {y + 27} C 300 {y + 27} 300 245 344 245" stroke="{c}" stroke-width="2" fill="none" stroke-opacity=".8"/>'
        )
    for i, (h, s) in enumerate(t["ch_out"]):
        y = 96 + i * 76
        outs.append(
            f'<path class="flow" d="M536 245 C 580 245 580 {y + 27} 628 {y + 27}" stroke="#818cf8" stroke-width="2" fill="none" stroke-opacity=".8"/>'
            f'<rect x="628" y="{y}" width="220" height="54" rx="12" fill="#111827" stroke="#4f46e5" stroke-opacity=".7"/>'
            + text(646, y + 24, h, 14, "#ffffff", "600")
            + text(646, y + 42, s, 12, "#9ca3af")
        )
    body = f"""
<rect width="880" height="430" rx="18" fill="#0b1020"/>
{text(32, 46, t["ch_title"], 18, "#ffffff", "700")}
{"".join(ins)}
{"".join(outs)}
<rect x="344" y="180" width="192" height="130" rx="18" fill="#1e1b4b" stroke="#818cf8" stroke-width="2"/>
<circle class="core" cx="440" cy="245" r="70" fill="#818cf8" fill-opacity=".08"/>
{text(440, 230, t["ch_core"], 19, "#ffffff", "700", "middle")}
{text(440, 258, t["ch_core_sub"][0], 11, "#c7d2fe", anchor="middle")}
{text(440, 274, t["ch_core_sub"][1], 11, "#c7d2fe", anchor="middle")}
{text(440, 294, "LLM · TTS · STT", 11, "#a5b4fc", anchor="middle")}
"""
    style = (
        ".flow{stroke-dasharray:6 6;animation:f 1.6s linear infinite}@keyframes f{to{stroke-dashoffset:-24}}"
        ".core{transform-box:fill-box;transform-origin:center;animation:c 3s ease-in-out infinite}"
        "@keyframes c{0%,100%{transform:scale(.9)}50%{transform:scale(1.1)}}"
    )
    return svg(880, 430, body, style)


def main() -> None:
    builders = {
        "hero": hero,
        "kp-flow": kp_flow,
        "honest-search": honest,
        "chat-branches": chat,
        "offline-stack": offline,
        "channels": channels,
    }
    for lang, t in (("ru", T_RU), ("en", T_EN)):
        for name, fn in builders.items():
            (OUT / f"{name}.{lang}.svg").write_text(fn(t), encoding="utf-8")
            print(f"{name}.{lang}.svg")


if __name__ == "__main__":
    main()
