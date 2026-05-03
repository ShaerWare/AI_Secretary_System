"""
Shared configuration for DigiTax web scrapers.

Site definitions, helpers, and constants used by scrape.py, parse.py, upload.py.
"""

import logging
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
RAW_DIR = BASE_DIR / "raw"
PARSED_DIR = BASE_DIR / "parsed"

# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------

SITES = {
    "boards-ie-accountancy": {
        "name": "Boards.ie Accountancy Forum",
        "base_url": "https://www.boards.ie",
        "seed_paths": ["/categories/accountancy"],
        "max_pages": 300,
        "type": "forum",
        "description": (
            "Irish discussion forum — accountancy category. "
            "Threads on tax, audit, bookkeeping, CAI/CPA exams."
        ),
    },
    "chartered-accountants-ie": {
        "name": "Chartered Accountants Ireland",
        "base_url": "https://www.charteredaccountants.ie",
        "seed_paths": ["/"],
        "max_pages": 500,
        "type": "professional",
        "description": (
            "Chartered Accountants Ireland — professional body. "
            "Technical guidance, standards, publications, CPD."
        ),
    },
    "cpa-ireland": {
        "name": "CPA Ireland",
        "base_url": "https://www.cpaireland.ie",
        "seed_paths": ["/"],
        "max_pages": 500,
        "type": "professional",
        "description": (
            "CPA Ireland — professional body. Resources, publications, technical articles."
        ),
    },
    "accounting-technicians-ie": {
        "name": "Accounting Technicians Ireland",
        "base_url": "https://accountingtechniciansireland.ie",
        "seed_paths": ["/"],
        "max_pages": 300,
        "type": "professional",
        "description": (
            "Accounting Technicians Ireland — education, qualifications, "
            "professional development, technical resources."
        ),
    },
    "iafa": {
        "name": "Irish Accounting & Finance Association",
        "base_url": "https://iafa.ie",
        "seed_paths": ["/"],
        "max_pages": 200,
        "type": "academic",
        "description": (
            "IAFA — academic body. Conferences, papers, research in Irish accounting and finance."
        ),
    },
    "accountant-forums-ireland": {
        "name": "Accountant Forums (Ireland)",
        "base_url": "https://www.accountantforums.com",
        "seed_paths": ["/search/483201/?q=Ireland&o=date"],
        "max_pages": 200,
        "type": "forum",
        "ireland_filter": True,
        "ireland_keywords": [
            "ireland",
            "irish",
            "revenue.ie",
            "ros",
            "paye",
            "prsi",
            "usc",
            "vat ireland",
            "chartered accountants ireland",
            "cpa ireland",
            "form 11",
            "form 12",
            "ct1",
        ],
        "description": ("International accountancy forum — Ireland-related threads only."),
    },
    # ------------------------------------------------------------------
    # Russian accountant assistant — USN (6% / 15%) for legal entities
    # ------------------------------------------------------------------
    "ru-fns-usn": {
        "name": "ФНС России — УСН",
        "base_url": "https://www.nalog.gov.ru",
        "seed_paths": [
            "/rn77/taxation/taxes/usn/",
            "/rn77/taxation/taxes/nds_usn/",
            "/rn77/taxation/taxes/usn/all_about/",
        ],
        "stay_under": "/rn77/taxation/",
        "max_pages": 300,
        "type": "official",
        "description": (
            "Федеральная налоговая служба — официальный раздел УСН. "
            "Ставки, льготы, переход/отказ, декларация, КУДиР, разъяснения. "
            "Включает НДС при УСН (актуально с 2025)."
        ),
    },
    "ru-nk-rf-glava-26-2": {
        "name": "НК РФ — Глава 26.2 (УСН)",
        "base_url": "https://www.consultant.ru",
        "seed_paths": [
            "/document/cons_doc_LAW_28165/d29da7b903e5cc351ee08a2f10414ccee3c12bad/",
        ],
        # Whole Part 2 of Taxcode lives under this document id. Stay inside it
        # to avoid drifting onto unrelated КонсультантПлюс content.
        "stay_under": "/document/cons_doc_LAW_28165/",
        "max_pages": 60,
        "type": "legal",
        "description": (
            "Налоговый кодекс РФ — Глава 26.2 «Упрощенная система "
            "налогообложения». Первоисточник: ст. 346.11 — 346.25.1."
        ),
    },
    "ru-moedelo-usn": {
        "name": "МоеДело — клуб",
        "base_url": "https://www.moedelo.org",
        "seed_paths": [
            "/club/nalogovyj-uchet",
            "/club/buhgalterskij-uchet",
            "/club/registratsiya-biznesa",
            "/club/likvidaciya-biznesa",
        ],
        "stay_under": "/club/",
        "max_pages": 400,
        "type": "practical",
        "description": (
            "МоеДело (Моё Дело) — клуб, практические статьи по бухгалтерскому "
            "и налоговому учёту. Не весь контент про УСН — на пост-парсинге "
            "отфильтруем не-USN статьи по ключевым словам."
        ),
    },
    # ------------------------------------------------------------------
    # Russian lawyer assistant — federal codes (consultant.ru)
    # ------------------------------------------------------------------
    "ru-uk-rf": {
        "name": "УК РФ — Уголовный кодекс",
        "base_url": "https://www.consultant.ru",
        "seed_paths": ["/document/cons_doc_LAW_10699/"],
        "stay_under": "/document/cons_doc_law_10699/",
        "max_pages": 800,
        "type": "legal",
        "description": (
            "Уголовный кодекс Российской Федерации, полный текст. Первоисточник — КонсультантПлюс."
        ),
    },
    "ru-koap-rf": {
        "name": "КоАП РФ — Кодекс об административных правонарушениях",
        "base_url": "https://www.consultant.ru",
        "seed_paths": ["/document/cons_doc_LAW_34661/"],
        "stay_under": "/document/cons_doc_law_34661/",
        "max_pages": 1500,
        "type": "legal",
        "description": (
            "Кодекс Российской Федерации об административных правонарушениях. "
            "Один из самых объёмных кодексов РФ (~600 статей)."
        ),
    },
    "ru-gk-rf-1": {
        "name": "ГК РФ часть 1",
        "base_url": "https://www.consultant.ru",
        "seed_paths": ["/document/cons_doc_LAW_5142/"],
        "stay_under": "/document/cons_doc_law_5142/",
        "max_pages": 700,
        "type": "legal",
        "description": "Гражданский кодекс РФ — Часть первая (общие положения, юр.лица, сделки, обязательства).",
    },
    "ru-gk-rf-2": {
        "name": "ГК РФ часть 2",
        "base_url": "https://www.consultant.ru",
        "seed_paths": ["/document/cons_doc_LAW_9027/"],
        "stay_under": "/document/cons_doc_law_9027/",
        "max_pages": 800,
        "type": "legal",
        "description": "Гражданский кодекс РФ — Часть вторая (отдельные виды обязательств, договоры).",
    },
    "ru-gk-rf-3": {
        "name": "ГК РФ часть 3",
        "base_url": "https://www.consultant.ru",
        "seed_paths": ["/document/cons_doc_LAW_34154/"],
        "stay_under": "/document/cons_doc_law_34154/",
        "max_pages": 250,
        "type": "legal",
        "description": "Гражданский кодекс РФ — Часть третья (наследственное и международное частное право).",
    },
    "ru-gk-rf-4": {
        "name": "ГК РФ часть 4",
        "base_url": "https://www.consultant.ru",
        "seed_paths": ["/document/cons_doc_LAW_64629/"],
        "stay_under": "/document/cons_doc_law_64629/",
        "max_pages": 500,
        "type": "legal",
        "description": "Гражданский кодекс РФ — Часть четвёртая (интеллектуальная собственность).",
    },
    "ru-tk-rf": {
        "name": "ТК РФ — Трудовой кодекс",
        "base_url": "https://www.consultant.ru",
        "seed_paths": ["/document/cons_doc_LAW_34683/"],
        "stay_under": "/document/cons_doc_law_34683/",
        "max_pages": 700,
        "type": "legal",
        "description": "Трудовой кодекс Российской Федерации.",
    },
    "ru-upk-rf": {
        "name": "УПК РФ — Уголовно-процессуальный кодекс",
        "base_url": "https://www.consultant.ru",
        "seed_paths": ["/document/cons_doc_LAW_34481/"],
        "stay_under": "/document/cons_doc_law_34481/",
        "max_pages": 800,
        "type": "legal",
        "description": "Уголовно-процессуальный кодекс Российской Федерации.",
    },
    "ru-sk-rf": {
        "name": "СК РФ — Семейный кодекс",
        "base_url": "https://www.consultant.ru",
        "seed_paths": ["/document/cons_doc_LAW_8982/"],
        "stay_under": "/document/cons_doc_law_8982/",
        "max_pages": 250,
        "type": "legal",
        "description": "Семейный кодекс Российской Федерации.",
    },
    "ru-zhk-rf": {
        "name": "ЖК РФ — Жилищный кодекс",
        "base_url": "https://www.consultant.ru",
        "seed_paths": ["/document/cons_doc_LAW_51057/"],
        "stay_under": "/document/cons_doc_law_51057/",
        "max_pages": 400,
        "type": "legal",
        "description": "Жилищный кодекс Российской Федерации.",
    },
    # ------------------------------------------------------------------
    # Kazakhstan — codes via adilet.zan.kz
    # adilet.zan.kz uses a Kazakh root CA not in the standard bundle, so
    # `verify_ssl: False` is required. Each Kazakh code lives at a single
    # monolithic URL — no BFS needed, just fetch the seed page.
    # ------------------------------------------------------------------
    "kz-nk-rk": {
        "name": "НК РК — Налоговый кодекс",
        "base_url": "https://adilet.zan.kz",
        "seed_paths": ["/rus/docs/K1700000120"],
        "stay_under": "/rus/docs/k1700000120",
        "verify_ssl": False,
        "max_pages": 5,
        "type": "legal",
        "description": (
            "Кодекс Республики Казахстан о налогах и других обязательных "
            "платежах в бюджет (Налоговый кодекс) от 25.12.2017 № 120-VI. "
            "Источник: adilet.zan.kz."
        ),
    },
    "kz-uk-rk": {
        "name": "УК РК — Уголовный кодекс",
        "base_url": "https://adilet.zan.kz",
        "seed_paths": ["/rus/docs/K1400000226"],
        "stay_under": "/rus/docs/k1400000226",
        "verify_ssl": False,
        "max_pages": 5,
        "type": "legal",
        "description": "Уголовный кодекс Республики Казахстан от 03.07.2014 № 226-V.",
    },
    "kz-koap-rk": {
        "name": "КоАП РК — Кодекс об административных правонарушениях",
        "base_url": "https://adilet.zan.kz",
        "seed_paths": ["/rus/docs/K1400000235"],
        "stay_under": "/rus/docs/k1400000235",
        "verify_ssl": False,
        "max_pages": 5,
        "type": "legal",
        "description": "Кодекс Республики Казахстан об административных правонарушениях от 05.07.2014 № 235-V.",
    },
    "kz-upk-rk": {
        "name": "УПК РК — Уголовно-процессуальный кодекс",
        "base_url": "https://adilet.zan.kz",
        "seed_paths": ["/rus/docs/K1400000231"],
        "stay_under": "/rus/docs/k1400000231",
        "verify_ssl": False,
        "max_pages": 5,
        "type": "legal",
        "description": "Уголовно-процессуальный кодекс Республики Казахстан от 04.07.2014 № 231-V.",
    },
    "kz-tk-rk": {
        "name": "ТК РК — Трудовой кодекс",
        "base_url": "https://adilet.zan.kz",
        "seed_paths": ["/rus/docs/K1500000414"],
        "stay_under": "/rus/docs/k1500000414",
        "verify_ssl": False,
        "max_pages": 5,
        "type": "legal",
        "description": "Трудовой кодекс Республики Казахстан от 23.11.2015 № 414-V.",
    },
    "kz-gk-rk-general": {
        "name": "ГК РК — общая часть",
        "base_url": "https://adilet.zan.kz",
        "seed_paths": ["/rus/docs/K940001000_"],
        "stay_under": "/rus/docs/k940001000_",
        "verify_ssl": False,
        "max_pages": 5,
        "type": "legal",
        "description": "Гражданский кодекс Республики Казахстан (общая часть) от 27.12.1994 № 268-XIII.",
    },
    "kz-gk-rk-special": {
        "name": "ГК РК — особенная часть",
        "base_url": "https://adilet.zan.kz",
        "seed_paths": ["/rus/docs/K990000409_"],
        "stay_under": "/rus/docs/k990000409_",
        "verify_ssl": False,
        "max_pages": 5,
        "type": "legal",
        "description": "Гражданский кодекс Республики Казахстан (особенная часть) от 01.07.1999 № 409-I.",
    },
    "icaew-ireland": {
        "name": "ICAEW Ireland Standards",
        "base_url": "https://www.icaew.com",
        "seed_paths": [
            "/technical/by-country/europe/ireland",
            "/technical/by-country/europe/ireland/accounting-in-ireland",
            "/technical/by-country/europe/ireland/doing-business-in-ireland",
            "/technical/by-country/europe/ireland/tax-in-ireland",
            "/library/subject-gateways/tax-and-duty/country-tax-guides/ireland",
            "/library/doing-business-in/ireland",
            "/insights/tax-news/ireland",
            "/regulation-and-working-in-the-profession/regulations/tax",
        ],
        # Previous `stay_under=/technical/by-country/europe/ireland` produced
        # only 3 pages because that subsection is tiny. Broaden to allow the
        # crawler to follow outgoing ICAEW links from the Ireland seeds,
        # relying on Ireland-keyword filtering (below) + the generic filter
        # to avoid drifting onto unrelated countries.
        "stay_under": "/",
        "ireland_filter": True,
        "ireland_keywords": [
            "ireland",
            "irish",
            "dublin",
            "revenue.ie",
            "cai",
            "cro",
        ],
        "max_pages": 200,
        "type": "standards",
        "description": (
            "ICAEW technical resources specific to Ireland — "
            "accounting standards, regulations, guidance."
        ),
    },
}


# ---------------------------------------------------------------------------
# Russian lawyer assistant — Constitution, federal codes, federal laws
# ---------------------------------------------------------------------------
# Every law on consultant.ru has the same URL shape:
#   https://www.consultant.ru/document/cons_doc_LAW_<id>/...
# so we generate SITES entries from a flat list to avoid ~10 lines of
# boilerplate per law.


def _consultant_law(slug: str, name: str, doc_id: str, max_pages: int, description: str) -> dict:
    """Build a SITES entry for a consultant.ru cons_doc_LAW_* document."""
    return {
        "name": name,
        "base_url": "https://www.consultant.ru",
        "seed_paths": [f"/document/cons_doc_LAW_{doc_id}/"],
        # filter_icaew compares against lower-cased path, so keep this lowercase.
        "stay_under": f"/document/cons_doc_law_{doc_id}/",
        "max_pages": max_pages,
        "type": "legal",
        "description": description,
    }


# (slug, display name, cons_doc_LAW_ id, max_pages, description)
# IDs were verified against consultant.ru via curl on 2026-05-01. max_pages is
# a generous cap based on the law's volume; raising it later costs nothing
# (already-downloaded pages are skipped on re-run).
RU_FEDERAL_LAWS: list[tuple[str, str, str, int, str]] = [
    (
        "ru-konstitutsiya",
        "Конституция РФ",
        "28399",
        300,
        "Конституция Российской Федерации (с поправками 2020 г.).",
    ),
    # --- Codes (кодексы) not yet covered by separate slugs ---
    (
        "ru-nk-rf-1",
        "НК РФ часть 1",
        "19671",
        800,
        "Налоговый кодекс РФ — Часть первая (общие положения, налоги, налоговый контроль).",
    ),
    (
        "ru-nk-rf-2",
        "НК РФ часть 2",
        "28165",
        1500,
        "Налоговый кодекс РФ — Часть вторая (НДС, НДФЛ, налог на прибыль, спецрежимы и др.).",
    ),
    (
        "ru-bk-rf",
        "БК РФ — Бюджетный кодекс",
        "19702",
        700,
        "Бюджетный кодекс Российской Федерации от 31.07.1998 № 145-ФЗ.",
    ),
    (
        "ru-gpk-rf",
        "ГПК РФ — Гражданский процессуальный кодекс",
        "39570",
        500,
        "Гражданский процессуальный кодекс РФ от 14.11.2002 № 138-ФЗ.",
    ),
    (
        "ru-apk-rf",
        "АПК РФ — Арбитражный процессуальный кодекс",
        "37800",
        500,
        "Арбитражный процессуальный кодекс РФ от 24.07.2002 № 95-ФЗ.",
    ),
    (
        "ru-kas-rf",
        "КАС РФ — Кодекс административного судопроизводства",
        "176147",
        500,
        "Кодекс административного судопроизводства РФ от 08.03.2015 № 21-ФЗ.",
    ),
    (
        "ru-zk-rf",
        "ЗК РФ — Земельный кодекс",
        "33773",
        500,
        "Земельный кодекс Российской Федерации от 25.10.2001 № 136-ФЗ.",
    ),
    (
        "ru-lk-rf",
        "ЛК РФ — Лесной кодекс",
        "64299",
        300,
        "Лесной кодекс Российской Федерации от 04.12.2006 № 200-ФЗ.",
    ),
    (
        "ru-vk-rf",
        "ВК РФ — Водный кодекс",
        "60683",
        300,
        "Водный кодекс Российской Федерации от 03.06.2006 № 74-ФЗ.",
    ),
    (
        "ru-gsk-rf",
        "ГсК РФ — Градостроительный кодекс",
        "51040",
        700,
        "Градостроительный кодекс Российской Федерации от 29.12.2004 № 190-ФЗ.",
    ),
    # --- Federal laws (ФЗ) — corporate / civil ---
    (
        "ru-fz-14",
        "ФЗ-14 «Об ООО»",
        "17819",
        300,
        "Федеральный закон от 08.02.1998 № 14-ФЗ «Об обществах с ограниченной ответственностью».",
    ),
    (
        "ru-fz-208",
        "ФЗ-208 «Об АО»",
        "8743",
        500,
        "Федеральный закон от 26.12.1995 № 208-ФЗ «Об акционерных обществах».",
    ),
    (
        "ru-fz-7",
        "ФЗ-7 «О НКО»",
        "8824",
        300,
        "Федеральный закон от 12.01.1996 № 7-ФЗ «О некоммерческих организациях».",
    ),
    (
        "ru-fz-127",
        "ФЗ-127 «О банкротстве»",
        "39331",
        1000,
        "Федеральный закон от 26.10.2002 № 127-ФЗ «О несостоятельности (банкротстве)».",
    ),
    (
        "ru-fz-129",
        "ФЗ-129 «О гос.регистрации ЮЛ и ИП»",
        "32881",
        300,
        "Федеральный закон от 08.08.2001 № 129-ФЗ «О гос. регистрации юр.лиц и индивидуальных предпринимателей».",
    ),
    # --- Federal laws — administrative / public service ---
    (
        "ru-fz-79",
        "ФЗ-79 «О гос. гражданской службе»",
        "48601",
        400,
        "Федеральный закон от 27.07.2004 № 79-ФЗ «О государственной гражданской службе РФ».",
    ),
    (
        "ru-fz-131",
        "ФЗ-131 «Об МСУ»",
        "44571",
        700,
        "Федеральный закон от 06.10.2003 № 131-ФЗ «Об общих принципах организации местного самоуправления в РФ».",
    ),
    (
        "ru-fz-59",
        "ФЗ-59 «Об обращениях граждан»",
        "59999",
        100,
        "Федеральный закон от 02.05.2006 № 59-ФЗ «О порядке рассмотрения обращений граждан Российской Федерации».",
    ),
    (
        "ru-fz-99",
        "ФЗ-99 «О лицензировании»",
        "113658",
        300,
        "Федеральный закон от 04.05.2011 № 99-ФЗ «О лицензировании отдельных видов деятельности».",
    ),
    (
        "ru-fz-248",
        "ФЗ-248 «О гос.контроле»",
        "358750",
        500,
        "Федеральный закон от 31.07.2020 № 248-ФЗ «О государственном контроле (надзоре) и муниципальном контроле в РФ».",
    ),
    (
        "ru-fz-3",
        "ФЗ-3 «О полиции»",
        "110165",
        300,
        "Федеральный закон от 07.02.2011 № 3-ФЗ «О полиции».",
    ),
    (
        "ru-fz-53",
        "ФЗ-53 «О воинской обязанности»",
        "18260",
        300,
        "Федеральный закон от 28.03.1998 № 53-ФЗ «О воинской обязанности и военной службе».",
    ),
    (
        "ru-fz-prokuratura",
        "ФЗ «О прокуратуре»",
        "366148",
        300,
        "Федеральный закон от 17.01.1992 № 2202-1 «О прокуратуре Российской Федерации».",
    ),
    # --- Federal laws — social sphere ---
    (
        "ru-fz-273",
        "ФЗ-273 «Об образовании»",
        "140174",
        700,
        "Федеральный закон от 29.12.2012 № 273-ФЗ «Об образовании в Российской Федерации».",
    ),
    (
        "ru-fz-323",
        "ФЗ-323 «Об охране здоровья»",
        "121895",
        700,
        "Федеральный закон от 21.11.2011 № 323-ФЗ «Об основах охраны здоровья граждан в РФ».",
    ),
    (
        "ru-fz-181",
        "ФЗ-181 «О соц. защите инвалидов»",
        "8559",
        300,
        "Федеральный закон от 24.11.1995 № 181-ФЗ «О социальной защите инвалидов в РФ».",
    ),
    (
        "ru-fz-255",
        "ФЗ-255 «Об ОСС»",
        "72601",
        300,
        "Федеральный закон от 29.12.2006 № 255-ФЗ «Об обязательном социальном страховании на случай временной нетрудоспособности и в связи с материнством».",
    ),
    # --- Federal laws — finance / procurement ---
    (
        "ru-fz-44",
        "ФЗ-44 «Контрактная система»",
        "144624",
        1000,
        "Федеральный закон от 05.04.2013 № 44-ФЗ «О контрактной системе в сфере закупок товаров, работ, услуг для гос. и муниципальных нужд».",
    ),
    (
        "ru-fz-115",
        "ФЗ-115 «О ПОД/ФТ»",
        "32834",
        400,
        "Федеральный закон от 07.08.2001 № 115-ФЗ «О противодействии легализации (отмыванию) доходов, полученных преступным путём, и финансированию терроризма».",
    ),
    # --- Federal laws — information / personal data ---
    (
        "ru-fz-152",
        "ФЗ-152 «О перс. данных»",
        "61801",
        200,
        "Федеральный закон от 27.07.2006 № 152-ФЗ «О персональных данных».",
    ),
    (
        "ru-fz-149",
        "ФЗ-149 «Об информации»",
        "61798",
        300,
        "Федеральный закон от 27.07.2006 № 149-ФЗ «Об информации, информационных технологиях и о защите информации».",
    ),
    # --- Federal constitutional laws (ФКЗ) ---
    (
        "ru-fkz-pravitelstvo",
        "ФКЗ-4 «О Правительстве РФ»",
        "366950",
        200,
        "Федеральный конституционный закон от 06.11.2020 № 4-ФКЗ «О Правительстве Российской Федерации».",
    ),
    (
        "ru-fkz-ks",
        "ФКЗ-1 «О Конституционном Суде»",
        "4172",
        300,
        "Федеральный конституционный закон от 21.07.1994 № 1-ФКЗ «О Конституционном Суде Российской Федерации».",
    ),
    (
        "ru-fkz-sudsystem",
        "ФКЗ-1 «О судебной системе»",
        "12834",
        100,
        "Федеральный конституционный закон от 31.12.1996 № 1-ФКЗ «О судебной системе Российской Федерации».",
    ),
    (
        "ru-fkz-vs",
        "ФКЗ-3 «О Верховном Суде»",
        "158641",
        200,
        "Федеральный конституционный закон от 05.02.2014 № 3-ФКЗ «О Верховном Суде Российской Федерации».",
    ),
    (
        "ru-fkz-ombudsman",
        "ФКЗ-1 «Об Уполномоченном по правам человека»",
        "13440",
        100,
        "Федеральный конституционный закон от 26.02.1997 № 1-ФКЗ «Об Уполномоченном по правам человека в Российской Федерации».",
    ),
    (
        "ru-fkz-arbitr",
        "ФКЗ-1 «Об арбитражных судах»",
        "6510",
        100,
        "Федеральный конституционный закон от 28.04.1995 № 1-ФКЗ «Об арбитражных судах в Российской Федерации».",
    ),
    (
        "ru-fkz-voennoe",
        "ФКЗ-1 «О военном положении»",
        "35227",
        100,
        "Федеральный конституционный закон от 30.01.2002 № 1-ФКЗ «О военном положении».",
    ),
    (
        "ru-fkz-cs",
        "ФКЗ-3 «О чрезвычайном положении»",
        "31866",
        100,
        "Федеральный конституционный закон от 30.05.2001 № 3-ФКЗ «О чрезвычайном положении».",
    ),
    (
        "ru-fkz-referendum",
        "ФКЗ-5 «О референдуме РФ»",
        "48221",
        500,
        "Федеральный конституционный закон от 28.06.2004 № 5-ФКЗ «О референдуме Российской Федерации».",
    ),
    (
        "ru-fkz-sou",
        "ФКЗ-1 «О судах общей юрисдикции»",
        "110271",
        200,
        "Федеральный конституционный закон от 07.02.2011 № 1-ФКЗ «О судах общей юрисдикции в Российской Федерации».",
    ),
    (
        "ru-fkz-voensud",
        "ФКЗ-1 «О военных судах»",
        "23479",
        100,
        "Федеральный конституционный закон от 23.06.1999 № 1-ФКЗ «О военных судах Российской Федерации».",
    ),
    # --- Additional federal laws (second wave) ---
    (
        "ru-fz-223",
        "ФЗ-223 «Закупки отд. видов ЮЛ»",
        "116964",
        700,
        "Федеральный закон от 18.07.2011 № 223-ФЗ «О закупках товаров, работ, услуг отдельными видами юридических лиц».",
    ),
    (
        "ru-fz-414",
        "ФЗ-414 «Публичная власть в субъектах»",
        "404070",
        500,
        "Федеральный закон от 21.12.2021 № 414-ФЗ «Об общих принципах организации публичной власти в субъектах Российской Федерации».",
    ),
    (
        "ru-fz-326",
        "ФЗ-326 «Об ОМС»",
        "107289",
        500,
        "Федеральный закон от 29.11.2010 № 326-ФЗ «Об обязательном медицинском страховании в Российской Федерации».",
    ),
    (
        "ru-fz-400",
        "ФЗ-400 «О страховых пенсиях»",
        "156525",
        400,
        "Федеральный закон от 28.12.2013 № 400-ФЗ «О страховых пенсиях».",
    ),
    (
        "ru-fz-422",
        "ФЗ-422 «Налог на проф.доход (самозанятые)»",
        "311977",
        200,
        "Федеральный закон от 27.11.2018 № 422-ФЗ «О проведении эксперимента по установлению специального налогового режима „Налог на профессиональный доход“».",
    ),
]

for _slug, _name, _doc_id, _max_pages, _description in RU_FEDERAL_LAWS:
    SITES[_slug] = _consultant_law(_slug, _name, _doc_id, _max_pages, _description)

# ---------------------------------------------------------------------------
# Request settings
# ---------------------------------------------------------------------------

REQUEST_DELAY = 1.5  # seconds between requests
TIMEOUT = 30  # seconds
MAX_RETRIES = 3
USER_AGENT = "Mozilla/5.0 (compatible; DigiTaxResearchBot/1.0; +research)"
MIN_CONTENT_LENGTH = 100  # skip pages with less useful text

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scrape_digitax")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def setup_session() -> requests.Session:
    """Create a requests session with standard headers."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-IE,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    return session


def url_to_filename(url: str) -> str:
    """Convert URL to safe filename (without extension)."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    # Include query for search/pagination URLs
    if parsed.query:
        path = f"{path}__{parsed.query}"
    name = path.replace("/", "__")
    # Remove common extensions
    name = re.sub(r"\.(aspx|html|htm|php)$", "", name, flags=re.IGNORECASE)
    # Sanitize
    name = re.sub(r"[^a-zA-Z0-9_\-.]", "_", name)
    # Truncate to avoid filesystem limits
    if len(name) > 200:
        name = name[:200]
    return name


def fetch_page(
    session: requests.Session,
    url: str,
    delay: float = REQUEST_DELAY,
    verify: bool = True,
) -> str | None:
    """Fetch a URL with retries and rate limiting. Returns HTML or None.

    Set ``verify=False`` for sites whose root CA is not in the system trust
    store (e.g. adilet.zan.kz uses a Kazakh root CA not bundled with certifi).
    """
    if not verify:
        # Suppress per-request InsecureRequestWarning spam — we already noted
        # the trade-off in the SITES config that opts out of verification.
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(url, timeout=TIMEOUT, verify=verify)
            if resp.status_code == 429:
                wait = 2 ** (attempt + 2)
                log.warning("Rate limited on %s, waiting %ds", url, wait)
                time.sleep(wait)
                continue
            if resp.status_code in (403, 404, 410):
                log.warning("HTTP %d: %s", resp.status_code, url)
                return None
            resp.raise_for_status()
            time.sleep(delay)
            return resp.text
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** (attempt + 1))
            else:
                log.warning("Failed after %d attempts: %s — %s", MAX_RETRIES, url, e)
    return None


def get_site_raw_dir(slug: str) -> Path:
    """Get raw HTML directory for a site."""
    d = RAW_DIR / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_site_parsed_dir(slug: str) -> Path:
    """Get parsed markdown directory for a site."""
    d = PARSED_DIR / slug
    d.mkdir(parents=True, exist_ok=True)
    return d
