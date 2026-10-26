"""Google Drive sources: change detection, price-file delivery, conversion."""

import io
import os
import unicodedata

import pytest

from app.services import google_drive_sync_service as gd
from modules.procurement.suppliers import drive_files, parser


@pytest.fixture
def price_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(parser, "SUPPLIER_PRICES_DIR", str(tmp_path))
    monkeypatch.setattr(drive_files, "SUPPLIER_PRICES_DIR", str(tmp_path))
    return tmp_path


# ── links & change detection ────────────────────────────────────


@pytest.mark.parametrize(
    "link",
    [
        "https://drive.google.com/drive/folders/1tGv9Xna18REcHiLbER3CBx0__5Xzmtcz",
        "https://drive.google.com/drive/folders/1tGv9Xna18REcHiLbER3CBx0__5Xzmtcz?usp=sharing",
        "https://drive.google.com/open?id=1tGv9Xna18REcHiLbER3CBx0__5Xzmtcz",
        "1tGv9Xna18REcHiLbER3CBx0__5Xzmtcz",
    ],
)
def test_extract_drive_id(link):
    assert gd.extract_drive_id(link) == "1tGv9Xna18REcHiLbER3CBx0__5Xzmtcz"


def test_extract_drive_id_file_link():
    link = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOp/edit#gid=0"
    assert gd.extract_drive_id(link) == "1AbCdEfGhIjKlMnOp"


def test_extract_drive_id_rejects_garbage():
    assert gd.extract_drive_id("привет") is None


def _f(fid, name, modified):
    return {"id": fid, "name": name, "mimeType": "application/pdf", "modifiedTime": modified}


def test_state_unchanged_ignores_local_name():
    files = [_f("a", "X-Trade.pdf", "2026-10-01T00:00:00Z")]
    old = gd.files_fingerprint(files)
    old["a"]["local"] = "X-Trade.pdf"
    assert not gd.state_changed(old, gd.files_fingerprint(files))


@pytest.mark.parametrize(
    "new",
    [
        [_f("a", "X-Trade.pdf", "2026-10-25T00:00:00Z")],  # file replaced
        [_f("a", "X-Trade.pdf", "2026-10-01T00:00:00Z"), _f("b", "new.pdf", None)],  # added
        [],  # removed
        [_f("a", "X-Trade v2.pdf", "2026-10-01T00:00:00Z")],  # renamed
    ],
)
def test_state_changed(new):
    old = gd.files_fingerprint([_f("a", "X-Trade.pdf", "2026-10-01T00:00:00Z")])
    assert gd.state_changed(old, gd.files_fingerprint(new))


def test_first_sync_is_a_change():
    assert gd.state_changed(None, {})


# ── supplier file matching ──────────────────────────────────────


def test_pattern_ignores_case_and_unicode_form():
    nfd = unicodedata.normalize("NFD", "Аксима прайс октябрь.xlsx")
    assert parser.matches_pattern(nfd, "аксима*.xlsx")
    assert parser.matches_pattern("ДИЛЛЕР 25.10.XLSX", "Диллер*.xlsx")
    assert not parser.matches_pattern("Диллер.xls", "Диллер*.xlsx")


def test_resolve_file_takes_newest(price_dir):
    old = price_dir / "Диллер 01.10.xlsx"
    new = price_dir / "Диллер 25.10.xlsx"
    old.write_bytes(b"old")
    new.write_bytes(b"new")
    os.utime(old, (2_000_000_000, 2_000_000_000))  # alphabetically first, but newer
    os.utime(new, (1_000_000_000, 1_000_000_000))
    assert parser.resolve_file("Диллер*.xlsx") == str(old)


def test_resolve_file_ignores_archive(price_dir):
    (price_dir / "_archive" / "x").mkdir(parents=True)
    (price_dir / "_archive" / "x" / "X-Trade.pdf").write_bytes(b"%PDF")
    assert parser.resolve_file("X-Trade*.pdf") is None


# ── delivery ────────────────────────────────────────────────────


def test_install_archives_previous_and_keeps_others(price_dir):
    (price_dir / "аксима старая.xlsx").write_bytes(b"old")
    (price_dir / "чужой.pdf").write_bytes(b"other source")

    result = drive_files.install_price_files(
        [("аксима новая.xlsx", b"new", "2026-10-25T10:00:00Z")], keep={"чужой.pdf"}
    )

    assert result["installed"] == ["аксима новая.xlsx"]
    assert result["archived"] == ["аксима старая.xlsx"]
    assert sorted(p.name for p in price_dir.iterdir() if p.is_file()) == [
        "аксима новая.xlsx",
        "чужой.pdf",
    ]
    archived = list((price_dir / "_archive").rglob("аксима старая.xlsx"))
    assert len(archived) == 1
    # Drive's modifiedTime becomes the mtime — resolve_file picks newest by it
    from datetime import datetime, timezone

    expected = datetime(2026, 10, 25, 10, tzinfo=timezone.utc).timestamp()
    assert (price_dir / "аксима новая.xlsx").stat().st_mtime == expected


def test_install_never_overwrites_other_source(price_dir):
    (price_dir / "общий.pdf").write_bytes(b"theirs")
    result = drive_files.install_price_files([("общий.pdf", b"ours", None)], keep={"общий.pdf"})
    assert result["conflicts"] == ["общий.pdf"]
    assert (price_dir / "общий.pdf").read_bytes() == b"theirs"


def test_supplier_report_flags_unmatched():
    report = drive_files.supplier_report(["X-Trade KZ.pdf", "Прайс от нового поставщика.xlsx"])
    xtrade = next(s for s in report["suppliers"] if s["key"] == "xtrade")
    assert xtrade["price_file"]["files"] == ["X-Trade KZ.pdf"]
    sunwell = next(s for s in report["suppliers"] if s["key"] == "sunwell")
    assert sunwell["price_file"]["files"] == []
    assert report["unmatched"] == ["Прайс от нового поставщика.xlsx"]


def test_price_file_name():
    sheet = {"name": "Остатки", "mimeType": gd.SHEET_MIME}
    assert gd.price_file_name(sheet) == "Остатки.xlsx"
    assert gd.price_file_name({"name": "a/b.pdf", "mimeType": "application/pdf"}) == "a_b.pdf"
    assert gd.price_file_name({"name": "фото.jpg", "mimeType": "image/jpeg"}) is None


# ── conversion to markdown ──────────────────────────────────────


def test_xlsx_to_markdown_sections_repeat_header(monkeypatch):
    openpyxl = pytest.importorskip("openpyxl")
    monkeypatch.setattr(gd, "ROWS_PER_SECTION", 2)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Прайс"
    ws.append(["Артикул", "Наименование", "Цена"])
    for i in range(1, 6):
        ws.append([f"A{i}", f"Товар | {i}", 100.0 * i])
    buf = io.BytesIO()
    wb.save(buf)

    md = gd.document_to_markdown("прайс.xlsx", buf.getvalue())

    assert md.startswith("## Прайс")
    assert md.count("| Артикул | Наименование | Цена |") == 3  # 5 rows / 2 per section
    assert "### Прайс: строки 5–5" in md
    assert "| A1 | Товар / 1 | 100 |" in md  # pipe escaped, 100.0 → 100


def test_unknown_binary_is_skipped():
    assert gd.document_to_markdown("x.xlsx", b"not a zip") is None


async def test_empty_source_does_not_wipe_prices(price_dir):
    from modules.knowledge.drive_sources import _deliver_prices

    (price_dir / "X-Trade.pdf").write_bytes(b"%PDF current")
    only_photos = [{"id": "p", "name": "склад.jpg", "mimeType": "image/jpeg"}]

    with pytest.raises(RuntimeError, match="нет файлов прайсов"):
        await _deliver_prices(1, "token", only_photos, {})

    assert (price_dir / "X-Trade.pdf").read_bytes() == b"%PDF current"


def test_delivery_keeps_suppliers_it_does_not_cover(price_dir):
    """Drive folder has SunWell stock only — the 20k-row dealer list must stay."""
    (price_dir / "Диллер.xlsx").write_bytes(b"dealer")
    (price_dir / "ОСТАТКИ 14.07.xlsx").write_bytes(b"old stock")
    (price_dir / "X-Trade KZ.pdf").write_bytes(b"%PDF")
    (price_dir / "Reestr.xlsx").write_bytes(b"not a price list")

    result = drive_files.install_price_files([("ОСТАТКИ 15.10.xlsx", b"new", None)], keep=set())

    assert result["archived"] == ["ОСТАТКИ 14.07.xlsx"]
    names = sorted(p.name for p in price_dir.iterdir() if p.is_file())
    assert set(names) == {"Диллер.xlsx", "Reestr.xlsx", "X-Trade KZ.pdf", "ОСТАТКИ 15.10.xlsx"}


def test_delivery_retires_files_the_source_dropped(price_dir):
    (price_dir / "старый файл источника.pdf").write_bytes(b"x")
    result = drive_files.install_price_files(
        [("X-Trade.pdf", b"%PDF", None)], keep=set(), previously_owned={"старый файл источника.pdf"}
    )
    assert result["archived"] == ["старый файл источника.pdf"]


def test_latin_axima_replaces_cyrillic_aksima(price_dir):
    (price_dir / "аксима-7.xlsx").write_bytes(b"july")
    result = drive_files.install_price_files([("axima.xlsx", b"october", None)], keep=set())
    assert result["archived"] == ["аксима-7.xlsx"]


def test_real_drive_names_map_to_one_supplier_each():
    names = [
        "Остатки от 12.10.2026.xls",
        "ОСТАТКИ 15.10.xlsx",
        "axima.xlsx",
        "Остатки и доступность товаров с ценой (для рассылки) (XLSX) (42).xlsx",
        "Диллер.xlsx",
    ]
    report = drive_files.supplier_report(names)
    by_key = {s["key"]: s for s in report["suppliers"]}
    assert by_key["promsitech"]["price_file"]["files"] == ["Остатки от 12.10.2026.xls"]
    assert by_key["sunwell"]["stock_file"]["files"] == ["ОСТАТКИ 15.10.xlsx"]
    assert by_key["aksima"]["price_file"]["files"] == ["axima.xlsx"]
    assert by_key["aksima_chint_rrc"]["price_file"]["files"] == [names[3]]
    assert report["unmatched"] == []
    assert report["ambiguous"] == []


# ── columns by header ───────────────────────────────────────────


def _aksima_head(offset: int, warehouses: list[str]) -> list[list]:
    width = 7 + 6 - offset + 1 + len(warehouses)
    title = [""] * width
    title[0] = "Прайс-лист на 12 октября 2026 г."
    cols = [""] * width
    cols[0] = "Артикул"
    cols[7 - offset] = "Номенклатура, Упаковка"
    cols[13 - offset] = "Дилерская"
    for i, w in enumerate(warehouses):
        cols[14 - offset + i] = f'Склад: "{w}"'
    return [title, [""] * width, cols, [""] * width, [""] * width, [""] * width]


def test_columns_found_by_header_july_and_october():
    from modules.procurement.suppliers.registry import get_supplier

    cfg = get_supplier("aksima")
    cols, stock = parser.resolve_columns(cfg, _aksima_head(0, ["ВТО", "Теректы"]))
    assert (cols["name"], cols["price"], stock) == (7, 13, [14, 15])
    cols, stock = parser.resolve_columns(cfg, _aksima_head(1, ["ВТО", "Рыскулова", "Теректы"]))
    assert (cols["name"], cols["price"], stock) == (6, 12, [13, 14, 15])


def test_promsitech_banner_is_not_the_price_column():
    from modules.procurement.suppliers.registry import get_supplier

    head = [[""] * 15 for _ in range(6)]
    head[0][0] = "Прайс-лист на 12 октября 2026 г."
    head[2][0], head[2][4], head[2][13], head[2][14] = (
        "Артикул",
        "Номенклатура, Упаковка",
        "Прайс-лист",
        "Основной склад",
    )
    cols, stock = parser.resolve_columns(get_supplier("promsitech"), head)
    assert (cols["article"], cols["name"], cols["price"], stock) == (0, 4, 13, [14])


def test_stock_sum_unknown_vs_zero():
    assert parser._stock_sum(["", None]) is None
    assert parser._stock_sum(["", "0"]) == 0
    assert parser._stock_sum(["3", "", 4.0]) == 7


def test_promsitech_price_as_is_without_margin_flag():
    from modules.procurement.pricing import compute_pricing

    p = compute_pricing({"source": "supplier", "source_key": "promsitech#1", "price": 93540.0})
    assert p["ok"] and p["client_price"] == 93540.0
    assert p["purchase_price"] is None
    assert p["zero_margin_flag"] is False
