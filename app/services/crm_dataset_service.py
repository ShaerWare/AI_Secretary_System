"""CRM Dataset Service — transforms amoCRM data into markdown for RAG indexing.

Pure functions: no DB access, no side effects (except file I/O in get/clean helpers).
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


CRM_DIR = Path("data/crm-dataset")
CRM_FILE_PREFIX = "crm-"


def format_price(kopecks: int) -> str:
    """Format price from kopecks to rubles with thousands separator."""
    rubles = kopecks // 100 if kopecks else 0
    return f"{rubles:,} ₽".replace(",", " ")


def format_timestamp(ts: Optional[int]) -> str:
    """Format Unix timestamp to human-readable date."""
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y")


def _extract_contact_info(contact: dict[str, Any]) -> dict[str, str]:
    """Extract name, phone, email from contact's custom_fields_values.

    Uses field_code (PHONE, EMAIL) which is stable across amoCRM accounts.
    """
    info: dict[str, str] = {"name": contact.get("name", "Неизвестный")}
    for field in contact.get("custom_fields_values") or []:
        code = field.get("field_code", "")
        values = field.get("values", [])
        if not values:
            continue
        val = values[0].get("value", "")
        if code == "PHONE" and val:
            info["phone"] = val
        elif code == "EMAIL" and val:
            info["email"] = val
    return info


def _build_lead_section(
    lead: dict[str, Any],
    status_map: dict[int, str],
) -> str:
    """Build a ## section for a single lead/deal."""
    name = lead.get("name", "Без названия")
    price = format_price(lead.get("price", 0))
    status_id = lead.get("status_id", 0)
    status_name = status_map.get(status_id, f"status_{status_id}")

    lines = [f"## Сделка: {name} — {status_name} ({price})", ""]
    lines.append(f"- **Статус**: {status_name}")
    lines.append(f"- **Сумма**: {price}")

    # Contacts (embedded — id + name only, no custom fields)
    embedded_contacts = (lead.get("_embedded") or {}).get("contacts", [])
    for c in embedded_contacts:
        lines.append(f"- **Контакт**: {c.get('name', 'Контакт')}")

    # Tags
    tags = (lead.get("_embedded") or {}).get("tags", [])
    if tags:
        tag_names = ", ".join(t.get("name", "") for t in tags if t.get("name"))
        if tag_names:
            lines.append(f"- **Теги**: {tag_names}")

    lines.append(f"- **Создана**: {format_timestamp(lead.get('created_at'))}")
    lines.append(f"- **Обновлена**: {format_timestamp(lead.get('updated_at'))}")

    if lead.get("responsible_user_id"):
        lines.append(f"- **Ответственный**: user_{lead['responsible_user_id']}")

    return "\n".join(lines)


def build_pipeline_document(
    pipeline: dict[str, Any],
    leads: list[dict[str, Any]],
    status_map: dict[int, str],
    sync_time: str,
) -> str:
    """Build markdown document for one pipeline with all its leads."""
    pipeline_name = pipeline.get("name", "Без названия")
    count = len(leads)

    lines = [
        f"# Воронка: {pipeline_name} ({count} сделок)",
        "",
        f"Данные из amoCRM. Последнее обновление: {sync_time}",
        "",
    ]

    if not leads:
        lines.append("Сделок в этой воронке нет.")
        return "\n".join(lines)

    # Sort leads by status sort order, then by updated_at desc
    leads_sorted = sorted(leads, key=lambda x: x.get("updated_at", 0), reverse=True)
    for lead in leads_sorted:
        lines.append(_build_lead_section(lead, status_map))
        lines.append("")

    return "\n".join(lines)


def build_summary_document(
    pipelines: list[dict[str, Any]],
    pipeline_leads: dict[int, list[dict[str, Any]]],
    status_maps: dict[int, dict[int, str]],
    sync_time: str,
) -> str:
    """Build the crm-summary.md with aggregate stats."""
    total_deals = sum(len(leads) for leads in pipeline_leads.values())
    total_price = sum(lead.get("price", 0) for leads in pipeline_leads.values() for lead in leads)

    lines = [
        "# amoCRM: Сводка по сделкам",
        "",
        f"Данные из amoCRM. Последнее обновление: {sync_time}",
        "",
        "## Общая статистика",
        "",
        f"- **Всего сделок**: {total_deals}",
        f"- **Общая сумма**: {format_price(total_price)}",
        f"- **Воронок**: {len(pipelines)}",
        "",
    ]

    # Per-pipeline breakdown
    for pipeline in pipelines:
        pid = pipeline["id"]
        pname = pipeline.get("name", "—")
        p_leads = pipeline_leads.get(pid, [])
        p_total = format_price(sum(lead.get("price", 0) for lead in p_leads))

        lines.append(f"## Воронка: {pname} ({len(p_leads)} сделок, {p_total})")
        lines.append("")

        # Status breakdown table
        smap = status_maps.get(pid, {})
        status_counts: dict[str, list[int]] = {}  # name -> [count, sum]
        for lead in p_leads:
            sname = smap.get(lead.get("status_id", 0), "Неизвестный")
            if sname not in status_counts:
                status_counts[sname] = [0, 0]
            status_counts[sname][0] += 1
            status_counts[sname][1] += lead.get("price", 0)

        if status_counts:
            lines.append("| Статус | Количество | Сумма |")
            lines.append("|--------|-----------|-------|")
            for sname, (count, total) in status_counts.items():
                lines.append(f"| {sname} | {count} | {format_price(total)} |")
            lines.append("")

    # Recently updated deals (last 7 days)
    week_ago = time.time() - 7 * 86400
    recent: list[tuple[dict[str, Any], dict[int, str]]] = []
    for pid, leads in pipeline_leads.items():
        smap = status_maps.get(pid, {})
        for lead in leads:
            if (lead.get("updated_at") or 0) > week_ago:
                recent.append((lead, smap))

    if recent:
        recent.sort(key=lambda x: x[0].get("updated_at", 0), reverse=True)
        lines.append("## Сделки обновлённые за последние 7 дней")
        lines.append("")
        for lead, smap in recent[:20]:
            name = lead.get("name", "—")
            status = smap.get(lead.get("status_id", 0), "—")
            price = format_price(lead.get("price", 0))
            updated = format_timestamp(lead.get("updated_at"))
            lines.append(f"- {name} — {status} ({price}) — обновлена {updated}")
        lines.append("")

    return "\n".join(lines)


def get_crm_filenames() -> list[str]:
    """List existing CRM dataset files."""
    if not CRM_DIR.exists():
        return []
    return [f.name for f in CRM_DIR.glob(f"{CRM_FILE_PREFIX}*.md")]


def clean_crm_files() -> list[str]:
    """Remove all existing CRM dataset files. Returns removed filenames."""
    removed = []
    if not CRM_DIR.exists():
        return removed
    for f in CRM_DIR.glob(f"{CRM_FILE_PREFIX}*.md"):
        f.unlink()
        removed.append(f.name)
    return removed
