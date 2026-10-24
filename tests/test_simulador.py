import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
from simulador import build_demanda, cost_demanda, _limit, build, cost  # noqa: E402


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


def _entry(id):
    import gzip, json
    from parsers import PARSERS
    fx = json.load(gzip.open(Path(__file__).resolve().parent / "fixtures" / f"{id}.json.gz", "rt"))
    out = PARSERS[fx["source"]["parser"]](fx["text"], content=None, source=fx["source"], sheets=fx.get("sheets"))
    return {"id": id, "estado": "ok", "ocr": False, "tablas": out["tablas"]}


def test_oceba_category_by_monthly_consumption():
    s = build(_entry("eden"))
    assert [c["hasta"] for c in s["categorias"]] == [100, 200, 400, 500, 700, 1400, None]
    assert round(cost(s, 150), 2) == round(7427.07 + 150 * 217.5914, 2)


def test_epe_cumulative_blocks():
    s = build(_entry("epe"))
    assert [h for h, _ in s["categorias"][0]["escalones"]] == [75, 150, 300, None]
    assert round(cost(s, 150), 2) == round(3944.25564 + 75 * 247.6447 + 75 * 270.56492, 2)



def test_enersa_stops_at_excedente():
    s = build(_entry("enersa"))
    assert [h for h, _ in s["categorias"][0]["escalones"]] == [100, 200, 300, None]
    assert round(cost(s, 250), 2) == round(3193.22 + 100 * 243.94 + 100 * 275.87 + 50 * 319.04, 2)


def test_mendoza_bimonthly_categories():
    s = build(_entry("edemsa"))
    assert [c["hasta"] for c in s["categorias"]] == [299, 599, None]
    assert round(cost(s, 150), 2) == round((8334.011 + 300 * 270.4639) / 2, 2)


def test_ejesa_sums_network_and_energy():
    s = build(_entry("ejesa"))
    assert "R5" in [c["nombre"] for c in s["categorias"]]
    assert round(cost(s, 150), 2) == round(5116 + 150 * (95.248 + 157.9956), 2)
    assert round(cost(s, 1000), 2) == round(33501 + 1000 * (101.8901 + 157.8779), 2)



def test_ape_components():
    s = build(_entry("ape"))
    assert [c["hasta"] for c in s["categorias"]] == [120, 220, 500, 700, 1400, None]
    fijo = 1517.32 + 2188.68 + 84.26
    assert round(cost(s, 100), 2) == round(fijo + 60 * (127.502866 + 19.34) + 40 * (127.502866 + 29.69), 2)



def test_oceba_t2_t3():
    d = build_demanda(_entry("eden"))
    names = [t["nombre"] for t in d["tarifas"]]
    assert names[:2] == ["T2BT", "T2MT"] and len(names) == 6
    exp = 51711.45 + 20 * (16722.16 + 11401.10) + 5000 * 0.25 * 125.0918 + 5000 * 0.75 * 123.5126
    assert round(cost_demanda(d, "BT", 20, 5000, 0.25, 0.3), 2) == round(exp, 2)
    exp = 73070.14 + 400 * (18317.99 + 12085.20) + 90000 * (0.2 * 119.1169 + 0.5 * 116.1533 + 0.3 * 114.745)
    assert round(cost_demanda(d, "MT", 400, 90000, 0.2, 0.3), 2) == round(exp, 2)
    assert cost_demanda(d, "AT", 100, 1000, 0.2, 0.3) is None
    assert cost_demanda(d, "BT", 5, 1000, 0.2, 0.3) is None


def test_enre_t2_t3():
    d = build_demanda(_entry("edenor"))
    assert [t["nombre"] for t in d["tarifas"]][0] == "Tarifa 2" and len(d["tarifas"]) == 7
    t2 = d["tarifas"][0]
    exp = t2["fijo"] + 20 * sum(p for _, p in t2["potencia"]) + 4000 * t2["energia"]["unica"]
    assert round(cost_demanda(d, "MT", 20, 4000, 0.25, 0.25), 2) == round(exp, 2)
    t3 = next(t for t in d["tarifas"] if t["nombre"] == "Tarifa 3 - BT > 300")
    assert t3["desde_kw"] == 300 and set(t3["energia"]) == {"pico", "resto", "valle"}
