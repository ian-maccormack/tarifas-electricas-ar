import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
from ocr import ocr_rows  # noqa: E402


def w(t, x0, x1, y, line):
    return {"t": t, "x0": x0, "x1": x1, "y": y, "h": 30, "line": line}


def r(t, x, y):
    return {"t": t, "x": x, "y": y}


def page(tess, rapid):
    return [{"width": 2000, "tesseract": tess, "rapid": rapid}]


def test_only_agreeing_amounts_are_published():
    tess = [w("T1-R:", 50, 150, 100, (1, 1, 1)), w("Residencial", 160, 400, 100, (1, 1, 1)),
            w("Cargo", 50, 150, 200, (1, 1, 2)), w("fijo", 160, 230, 200, (1, 1, 2)),
            w("$/mes", 500, 600, 200, (1, 1, 2)),
            w("4.789,94", 700, 820, 200, (1, 1, 2)), w("3.451,87", 900, 1020, 200, (1, 1, 2))]
    rapid = [r("4.789,94", 760, 202), r("3.451,81", 960, 201)]
    rows = ocr_rows(page(tess, rapid))
    assert rows == [{"pagina": 1, "concepto": "Cargo fijo", "unidad": "$/mes",
                     "valores": [4789.94, None], "grupo": "T1-R: Residencial", "columnas": None}]


def test_amount_without_decimals_is_rejected_even_if_both_agree():
    tess = [w("Cargo", 50, 150, 200, (1, 1, 1)), w("variable", 160, 300, 200, (1, 1, 1)),
            w("1029346", 700, 820, 200, (1, 1, 1))]
    assert ocr_rows(page(tess, [r("1029346", 760, 200)])) == []


def test_reading_at_other_position_does_not_confirm():
    tess = [w("Cargo", 50, 150, 200, (1, 1, 1)), w("fijo", 160, 230, 200, (1, 1, 1)),
            w("4.789,94", 700, 820, 200, (1, 1, 1))]
    assert ocr_rows(page(tess, [r("4.789,94", 1500, 200)])) == []


def test_thousands_dot_in_comma_document():
    tess = [w("Cargo", 50, 150, 200, (1, 1, 1)), w("fijo", 160, 230, 200, (1, 1, 1)),
            w("44.061", 700, 800, 200, (1, 1, 1)), w("176,77", 900, 1000, 200, (1, 1, 1)),
            w("Otro", 50, 150, 300, (1, 1, 2)), w("cargo", 160, 260, 300, (1, 1, 2)),
            w("24,36", 700, 800, 300, (1, 1, 2))]
    rapid = [r("44.061", 750, 200), r("176,77", 950, 200), r("24,36", 750, 300)]
    rows = ocr_rows(page(tess, rapid))
    assert [x["valores"] for x in rows] == [[44061.0, 176.77], [24.36]]


def _hdr_page(h1, h2, x1, x2):
    tess = [w("Concepto", 50, 200, 100, (1, 1, 1)), w(h1, 650, 870, 100, (1, 1, 1)), w(h2, 1250, 1450, 100, (1, 1, 1)),
            w("Cargo", 50, 150, 200, (1, 1, 2)), w("fijo", 160, 230, 200, (1, 1, 2)),
            w("4.789,94", x1, x1 + 120, 200, (1, 1, 2)), w("3.451,87", x2, x2 + 120, 200, (1, 1, 2))]
    rapid = [r("4.789,94", x1 + 60, 200), r("3.451,87", x2 + 60, 200)]
    return page(tess, rapid)


def test_values_get_the_header_above_them():
    rows = ocr_rows(_hdr_page("Monofásicas", "Trifásicas", 700, 1290))
    assert rows[0]["columnas"] == ["Monofásicas", "Trifásicas"]


def test_values_far_from_headers_get_no_columns():
    assert ocr_rows(_hdr_page("Monofásicas", "Trifásicas", 300, 1800))[0]["columnas"] is None


def test_garbled_headers_are_ignored():
    assert ocr_rows(_hdr_page("A", "»", 700, 1290))[0]["columnas"] is None



def test_ocr_vigencia_explicit_forms_only():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
    from run import ocr_vigencia
    assert ocr_vigencia("tendrá vigencia a partir de la facturación con vencimiento en el mes de SEPTIEMBRE de 2025") \
        == "Facturación con vencimiento en septiembre de 2025 (leído por OCR)"
    assert ocr_vigencia("Anexo VI ... Vigencia: SEPT'26 Cargo por Energía") == "Vigencia: septiembre de 2026 (leído por OCR)"
    assert ocr_vigencia("Res. ERSEPT 868/26 y Res. SEN 334-25") is None
