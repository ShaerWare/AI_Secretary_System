"""Разбор YML-фида наличия: границы срока, фильтр недоступного, документы RAG."""

from modules.procurement.feed_adapter import (
    _lead_days,
    _unmatched_offers,
    build_documents,
    parse_feed,
)


FEED = """<?xml version="1.0" encoding="utf-8"?>
<yml_catalog date="2026-10-11 19:11">
  <shop>
    <name>ИМ - StalkerElectric</name>
    <categories>
      <category id="1025">Автоматические выключатели в литом корпусе</category>
      <category id="858">Светотехника</category>
    </categories>
    <offers>
      <offer id="271142" available="true">
        <name>Автоматический выключатель NM8N-250C TM 3P 160А (CHINT)</name>
        <vendor>CHINT</vendor>
        <vendorCode>271142</vendorCode>
        <price>89083</price>
        <currencyId>KZT</currencyId>
        <categoryId>1025</categoryId>
        <count>40</count>
        <param name="Срок поставки" unit="дн">1-3</param>
      </offer>
      <offer id="300001" available="true">
        <name>Светильник LED 36Вт</name>
        <vendor>EKF</vendor>
        <vendorCode>300001</vendorCode>
        <price>12500.5</price>
        <currencyId>KZT</currencyId>
        <categoryId>858</categoryId>
        <count>7</count>
        <param name="Срок поставки" unit="дн">1</param>
      </offer>
      <offer id="999999" available="false">
        <name>Снятая с продажи позиция</name>
        <vendorCode>999999</vendorCode>
        <price>100</price>
        <categoryId>858</categoryId>
        <count>0</count>
        <param name="Срок поставки" unit="дн">5</param>
      </offer>
    </offers>
  </shop>
</yml_catalog>
"""


def test_lead_days_takes_upper_bound():
    # Обещать клиенту нижнюю границу диапазона нельзя.
    assert _lead_days("1-3") == 3
    assert _lead_days("3–4") == 4
    assert _lead_days("1") == 1
    assert _lead_days(None) is None
    assert _lead_days("уточняется") is None


def test_parse_feed_skips_unavailable_and_maps_fields():
    parsed = parse_feed(FEED.encode("utf-8"))

    assert parsed["as_of"] == "2026-10-11 19:11"
    assert parsed["skipped"] == 1  # available="false" не попадает в выдачу
    assert len(parsed["items"]) == 2

    first = parsed["items"][0]
    assert first["article"] == "271142"
    assert first["brand"] == "CHINT"
    assert first["category"] == "Автоматические выключатели в литом корпусе"
    assert first["price"] == 89083.0
    assert first["currency"] == "KZT"
    assert first["stock_qty"] == 40
    assert first["lead_time_days"] == 3
    # Фид перечисляет только доступное — наличие утверждает сам источник.
    assert first["in_stock"] is True

    assert parsed["items"][1]["price"] == 12500.5
    assert parsed["items"][1]["lead_time_days"] == 1


def test_build_documents_one_per_category_plus_summary():
    items = parse_feed(FEED.encode("utf-8"))["items"]
    docs = build_documents(items, "2026-10-11 19:11")

    assert len(docs) == 3  # две категории + сводка
    names = [fn for fn, _, _ in docs]
    assert all(fn.startswith("feed-") and fn.endswith(".md") for fn in names)
    assert "feed-summary.md" in names

    bodies = {fn: content for fn, content, _ in docs}
    automatic = next(c for fn, c in bodies.items() if "avtomaticheskie" in fn)
    assert "271142" in automatic
    assert "89083 ₸" in automatic
    assert "доступно к заказу 40 шт." in automatic
    assert "до 3 дн." in automatic

    summary = bodies["feed-summary.md"]
    assert "CHINT: 1 позиций" in summary
    assert "Светотехника: 1 позиций" in summary


def test_unmatched_offers_keeps_only_articles_absent_from_catalog():
    items = parse_feed(FEED.encode("utf-8"))["items"]

    unmatched = _unmatched_offers(items, {"271142"})

    assert [o["article"] for o in unmatched] == ["300001"]
    assert unmatched[0]["extra"] == {"stock_source": "feed"}
    assert unmatched[0]["supplier_name"] is None
    # Своя строка должна остаться полноценным оффером для поиска.
    assert unmatched[0]["name"] and unmatched[0]["price"] and unmatched[0]["source_key"]
