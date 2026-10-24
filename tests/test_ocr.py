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
                     "valores": [4789.94, None], "grupo": "T1-R: Residencial"}]


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
