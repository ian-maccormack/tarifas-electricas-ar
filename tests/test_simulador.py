import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
from simulador import _limit, build, cost  # noqa: E402


def sim(periodo, cats):
    return {"periodo": periodo, "criterio": "", "categorias": cats}


def test_monthly_flat():
    s = sim("mes", [{"hasta": 150, "fijo": 1000, "escalones": [[None, 10]]},
                    {"hasta": None, "fijo": 3000, "escalones": [[None, 20]]}])
    assert cost(s, 100) == 2000
    assert cost(s, 200) == 7000


def test_bimonthly_is_converted_inside_the_calculation():
    s = sim("bimestre", [{"hasta": 300, "fijo": 2000, "escalones": [[None, 10]]}])
    assert cost(s, 150) == (2000 + 300 * 10) / 2


def test_progressive_blocks():
    s = sim("bimestre", [{"hasta": None, "fijo": 0, "escalones": [[600, 1], [None, 2]]}])
    assert cost(s, 400) == (600 * 1 + 200 * 2) / 2
    assert cost(s, 200) == 400 / 2


def test_missing_values_give_no_result():
    s = sim("mes", [{"hasta": 150, "fijo": 1000, "escalones": [[None, 10]]},
                    {"hasta": None, "fijo": None, "escalones": [[None, 20]]}])
    assert cost(s, 200) is None
    s = sim("mes", [{"hasta": None, "fijo": 1000, "escalones": [[100, 10], [None, None]]}])
    assert cost(s, 50) == 1500
    assert cost(s, 150) is None


def test_limits_from_category_text():
    assert _limit("T1-R2-Consumo mensual mayor a 50 KWh e inferior o igual a 100 KWh") == 100
    assert _limit("T1 R2 Consumo Bimestral mayor 300 kWh e inferior e igual 650 kWh") == 650
    assert _limit("T1-R7-Consumo mensual mayor a 1400 KWh") is None
    assert _limit("Hasta 300 kWh/bimestre T1R1") == 300


def test_ocr_and_unknown_distributors_are_not_simulated():
    tablas = [{"titulo": "R1 — Tarifa 1 - R sin subsidio", "filas": [
        {"concepto": "Cargo Fijo 0-150", "valores": [1.0]}, {"concepto": "Cargo Variable 0-150", "valores": [2.0]}]}]
    assert build({"id": "edenor", "estado": "ok", "ocr": None, "tablas": tablas})["categorias"][0]["hasta"] == 150
    assert build({"id": "edenor", "estado": "ok", "ocr": {"x": 1}, "tablas": tablas}) is None
    assert build({"id": "zzz", "estado": "ok", "tablas": tablas}) is None
