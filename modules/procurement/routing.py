"""Category routing — which supplier to query for a given request.

From the client's Reestr v3 (sheet "3. Маршрутизация"). A keyword classifier
maps a free-text request to a category; each category has an ordered supplier
list. Special rule (11/17): any client from Atyrau → ЭКТ Атырау first.

Supplier data types (Reestr sheet 1): A = has price+stock files (search finds
it), B = has prices, availability to confirm, C = no files, always request.
"""

import re
from typing import Optional


# Supplier metadata incl. those without price files yet (Промситех, ELTECH) —
# routing still names them as request targets.
SUPPLIER_META = {
    "aksima": {"name": "Аксима (AXIMA)", "type": "A", "city": "Алматы"},
    "sunwell": {"name": "Санвел / EKF", "type": "A", "city": "Алматы"},
    "promsitech": {"name": "Промситех", "type": "A", "city": "Алматы"},
    "elektrokomplekt": {"name": "ЭКТ Атырау", "type": "A", "city": "Атырау"},
    "xtrade": {"name": "X-Trade KZ", "type": "B", "city": "Алматы"},
    "megazakaz": {"name": "Мегазаказ (бренд Stalker)", "type": "B", "city": "Алматы"},
    "eltech": {"name": "ELTECH", "type": "C", "city": "Алматы", "competitor": True},
}

ATYRAU_SUPPLIER = "elektrokomplekt"

# Ordered by specificity — first category whose keywords hit wins ties by score.
CATEGORIES = [
    {
        "key": "vfd",
        "name": "ЧРП, УПП, устройства плавного пуска",
        "keywords": ["чрп", "частотник", "частотный", "преобразователь частот", "упп", "плавн"],
        "suppliers": ["promsitech", "elektrokomplekt", "aksima"],
    },
    {
        "key": "motors",
        "name": "Двигатели, насосы",
        "keywords": ["двигател", "насос", "мотор", "электродвигател"],
        "suppliers": ["promsitech"],
    },
    {
        "key": "premium",
        "name": "Премиум: Siemens, ABB, Legrand, LOGO!",
        "keywords": ["siemens", "сименс", "abb", "авв", "legrand", "легранд", "logo"],
        "suppliers": ["eltech"],
    },
    {
        "key": "lighting",
        "name": "Светильники, LED, прожекторы, уличное освещение",
        "keywords": [
            "светильник",
            "прожектор",
            "led",
            "лед",
            "освещен",
            "спот",
            "уфо",
            "панель свет",
        ],
        "suppliers": ["megazakaz", "elektrokomplekt", "sunwell"],
    },
    {
        "key": "track",
        "name": "Магнитные/трековые системы, даунлайты GX53",
        "keywords": ["трек", "магнитн", "gx53", "даунлайт"],
        "suppliers": ["megazakaz"],
    },
    {
        "key": "sockets",
        "name": "Розетки, выключатели, рамки, удлинители",
        "keywords": ["розетк", "рамк", "удлинител", "выключатель одноклав", "выключатель двухклав"],
        "suppliers": ["megazakaz", "elektrokomplekt", "sunwell"],
    },
    {
        "key": "modular",
        "name": "Автоматы, УЗО, дифавтоматы, модульное",
        "keywords": ["автомат", "узо", "дифавтомат", "дифференциальн", "модульн", "ва47", "mcb"],
        "suppliers": ["aksima", "sunwell", "xtrade"],
    },
    {
        "key": "contactors",
        "name": "Контакторы, пускатели, тепловые реле",
        "keywords": ["контактор", "пускател", "тепловое реле", "реле тепл"],
        "suppliers": ["aksima", "xtrade", "sunwell"],
    },
    {
        "key": "cabinets",
        "name": "Шкафы, корпуса, щиты",
        "keywords": ["шкаф", "корпус", "щит", "бокс навесн", "нку", "вру"],
        "suppliers": ["aksima", "xtrade", "sunwell"],
    },
    {
        "key": "assembly",
        "name": "Комплектация шкафа (клеммы, наконечники, кабель-канал, шины, DIN)",
        "keywords": [
            "клемм",
            "наконечник",
            "кабель-канал",
            "кабельный канал",
            "шина",
            "din",
            "дин-рейк",
            "нши",
            "ншви",
        ],
        "suppliers": ["xtrade", "sunwell", "aksima"],
    },
    {
        "key": "ventilation",
        "name": "Вентиляция и обогрев шкафов, термостаты",
        "keywords": ["вентил", "обогрев", "термостат", "нагреватель щит"],
        "suppliers": ["xtrade", "sunwell"],
    },
    {
        "key": "cable",
        "name": "Кабель, провод, лотки, трубы",
        "keywords": ["кабель", "провод", "лоток", "гофр", "ввг", "аввг", "труба"],
        "suppliers": ["elektrokomplekt", "sunwell", "eltech"],
    },
    {
        "key": "kip",
        "name": "КИПиА, датчики, релейная защита, измерение",
        "keywords": ["кипиа", "датчик", "релейная защит", "измерен", "амперметр", "вольтметр"],
        "suppliers": ["promsitech", "eltech", "aksima"],
    },
    {
        "key": "tools",
        "name": "Инструмент, КИП, стабилизаторы",
        "keywords": ["инструмент", "стабилизатор"],
        "suppliers": ["elektrokomplekt", "xtrade"],
    },
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower())


def classify(query: str) -> Optional[dict]:
    """Best-matching category by keyword hits (most specific keyword wins)."""
    q = _norm(query)
    if not q:
        return None
    best = None
    best_score = 0
    for cat in CATEGORIES:
        score = sum(1 for kw in cat["keywords"] if kw in q)
        # weight by longest matched keyword so specific phrases beat single words
        if score:
            longest = max((len(kw) for kw in cat["keywords"] if kw in q), default=0)
            weighted = score * 100 + longest
            if weighted > best_score:
                best_score = weighted
                best = cat
    return best


def route(query: str, city: Optional[str] = None) -> dict:
    """Return {category, suppliers:[{key,name,type}], atyrau} for a request.

    Atyrau clients get ЭКТ Атырау first (deduped). Suppliers are enriched with
    type A/B/C so the caller knows which are searchable vs request-only.
    """
    cat = classify(query)
    keys: list[str] = list(cat["suppliers"]) if cat else []

    atyrau = bool(city and "атырау" in city.lower()) or "атырау" in _norm(query)
    if atyrau and ATYRAU_SUPPLIER not in keys:
        keys = [ATYRAU_SUPPLIER, *keys]
    elif atyrau:
        keys = [ATYRAU_SUPPLIER, *[k for k in keys if k != ATYRAU_SUPPLIER]]

    suppliers = [
        {
            "key": k,
            "name": SUPPLIER_META[k]["name"],
            "type": SUPPLIER_META[k]["type"],
            "competitor": SUPPLIER_META[k].get("competitor", False),
        }
        for k in keys
        if k in SUPPLIER_META
    ]
    return {
        "category": cat["name"] if cat else None,
        "category_key": cat["key"] if cat else None,
        "suppliers": suppliers,
        "atyrau_priority": atyrau,
    }
