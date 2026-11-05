import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
from run import _interpret, coincidencias  # noqa: E402


def test_number_conventions():
    assert _interpret("1.812,81") == [1812.81]
    assert _interpret("1,812.81") == [1812.81]
    assert _interpret("159,128") == [159.128, 159128.0]
    assert _interpret("44.061") == [44.061, 44061.0]
    assert _interpret("2.472.424") == [2472424.0]


def test_coincidencias_tolerates_rounding_only():
    tablas = [{"filas": [{"valores": [1812.81, 159.128, None]}, {"valores": [999.99]}]}]
    ok, total = coincidencias(tablas, "Cargo fijo 1.812,81 $/mes · energía 159,1283 $/kWh · otro 12,00")
    assert (ok, total) == (2, 3)


def test_choose_newest_with_values_then_ente():
    from run import choose
    from sources import ORIGEN_DIST, ORIGEN_ENTE
    t = [{"filas": [{"valores": [1.0]}]}]
    ente_oct = ({"tablas": t}, "", (2026, 10), ORIGEN_ENTE, 0)
    dist_oct = ({"tablas": t}, "", (2026, 10), ORIGEN_DIST, 1)
    dist_nov_empty = ({"tablas": []}, "", (2026, 11), ORIGEN_DIST, 2)
    best, newer = choose([dist_oct, ente_oct, dist_nov_empty])
    assert best is ente_oct and newer is dist_nov_empty
    dist_nov = ({"tablas": t}, "", (2026, 11), ORIGEN_DIST, 2)
    assert choose([ente_oct, dist_nov]) == (dist_nov, None)
    assert choose([]) == (None, None)
    old = ({"tablas": t}, "", (2025, 9), ORIGEN_DIST, 0)
    bo_empty = ({"tablas": []}, "", (2026, 9), ORIGEN_ENTE, 1)
    assert choose([old, bo_empty]) == (bo_empty, None)


def test_edesal_pdf_text_layout():
    from common import pdf_text
    from parsers import PARSERS
    from simulador import DEMANDA, SUB_BUILDERS
    root = Path(__file__).resolve().parents[1]
    r = PARSERS["edesal"](pdf_text((root / "site/docs/entregados/edesal-cuadro-tarifario-2026-09.pdf").read_bytes()))
    t1 = r["tablas"][0]
    assert t1["filas"][0]["valores"] == [6448.4817, 10668.3161, 143.5892, 3506.6446, 10668.3161, 57.408, 143.5892]
    sub = SUB_BUILDERS["edesal"](r["tablas"])
    assert sub["categorias"][0]["escalones"] == [[200, 57.408], [None, 143.5892]]
    valle = r["tablas"][2]["filas"][-1]
    assert valle["concepto"].endswith("hs.Valle") and valle["valores"][0] == 176.568 and valle["valores"][-1] == 154.2795
    assert r["tablas"][1]["filas"][0]["concepto"] == "Cargo Comercial"
    assert len(DEMANDA["edesal"](r["tablas"])["tarifas"]) == 6


def test_dpe_manual_transcription():
    import json
    from simulador import BUILDERS
    root = Path(__file__).resolve().parents[1]
    man = json.loads((root / "scraper/manual/dpe-res-595-26.json").read_text())
    sim = BUILDERS["dpe"](man["tablas"])
    assert sim["categorias"][0]["fijo"] == 4412.16
    assert sim["categorias"][0]["escalones"] == [[150, 173.2748], [300, 191.2397], [None, 203.3643]]


def test_edenor_own_pdf_matches_enre_layout():
    from common import pdf_text
    from parsers import PARSERS
    from simulador import BUILDERS, DEMANDA
    c = (Path(__file__).resolve().parent / "fixtures/edenor-2026-11.pdf").read_bytes()
    r = PARSERS["enre"](pdf_text(c), source={"empresa": "EDENOR"}, content=c)
    assert r["vigencia"] == "Resolución ENReGE N° 886/2026 vigente a partir del 01/11/2026"
    cats = BUILDERS["edenor"](r["tablas"])["categorias"]
    assert [(x["nombre"], x["hasta"], x["fijo"], x["escalones"][0][1]) for x in cats[:2]] == [
        ("R1", 150, 1870.51, 163.597), ("R2", 400, 3989.51, 164.279)]
    assert cats[-1] == {"nombre": "R6", "hasta": None, "fijo": 68900.6, "escalones": [[None, 197.755]]}
    dem = {t["nombre"]: t for t in DEMANDA["edenor"](r["tablas"])["tarifas"]}
    assert dem["Tarifa 2"]["fijo"] == 50443.95 and dem["Tarifa 2"]["energia"]["unica"] == 148.772
    assert dem["Tarifa 3 - AT > 300"]["energia"] == {"pico": 154.086, "resto": 149.064, "valle": 148.106}


def test_edenor_pdf_subsidy_limit_from_cuadro():
    from common import pdf_text
    from parsers import PARSERS
    from simulador import SUB_BUILDERS
    c = (Path(__file__).resolve().parent / "fixtures/edenor-2026-11.pdf").read_bytes()
    sub = SUB_BUILDERS["edenor"](PARSERS["enre"](pdf_text(c), source={"empresa": "EDENOR"}, content=c)["tablas"])
    assert "base_mes" not in sub
    assert sub["categorias"][1] == {"nombre": "R2", "hasta": 400, "fijo": 3989.51, "escalones": [[200, 65.754], [None, 164.279]]}


def test_epen_subsidy_rows():
    import json
    from simulador import SUB_BUILDERS
    t = [{"titulo": "T1 Residencial", "filas": [
        {"grupo": "T1-R1-Consumo mensual inferior o igual a 50 KWh", "concepto": "Cargo fijo", "unidad": "$/mes", "valores": [9940.22]},
        {"grupo": "T1-R1-Consumo mensual inferior o igual a 50 KWh", "concepto": "Cargo variable por energía - CON SUBSIDIO", "unidad": "$/KWh", "valores": [195.632]},
        {"grupo": "T1-R4-Consumo mensual mayor a 250 KWh e inferior o igual a 500 KWh", "concepto": "Cargo fijo", "unidad": "$/mes", "valores": [17861.4]},
        {"grupo": "T1-R4-Consumo mensual mayor a 250 KWh e inferior o igual a 500 KWh", "concepto": "Cargo variable por energía - CON SUBSIDIO primeros 200 KWh", "unidad": "$/KWh", "valores": [156.351]},
        {"grupo": "T1-R4-Consumo mensual mayor a 250 KWh e inferior o igual a 500 KWh", "concepto": "Cargo variable por energía - CON SUBSIDIO excedente de 200 KWh", "unidad": "$/KWh", "valores": [355.156]}]}]
    cats = SUB_BUILDERS["epen"](t)["categorias"]
    assert cats[0]["escalones"] == [[None, 195.632]]
    assert cats[1] == {"nombre": "T1-R4", "hasta": 500, "fijo": 17861.4, "escalones": [[200, 156.351], [None, 355.156]]}


def test_edese_con_subsidio_section():
    from parsers import PARSERS
    from simulador import SUB_BUILDERS
    import pathlib
    t = (pathlib.Path(__file__).parent.parent / "site/data/textos/edese.txt").read_text()
    r = PARSERS["edese"](t)
    c = SUB_BUILDERS["edese"](r["tablas"])["categorias"][0]
    assert c["hasta"] == 300 and c["fijo"] == 4383.42 and c["escalones"] == [[None, 110.098]]


def test_epe_con_subsidio_por_zona():
    import pathlib
    from parsers import PARSERS
    from simulador import SUB_BUILDERS
    t = (pathlib.Path(__file__).parent.parent / "site/data/textos/epe.txt").read_text()
    s = SUB_BUILDERS["epe"](PARSERS["epe"](t)["tablas"])
    z = {x["id"]: x["categorias"] for x in s["zonas"]}
    assert sorted(z) == ["I", "II", "III"]
    assert z["I"][0]["escalones"] == [[75, 142.23411], [150, 165.15433], [300, 261.40335], [None, 440.80713]]
    assert z["II"][1]["escalones"][1] == [370, 440.80713]
    assert z["III"][1]["escalones"] == [[350, 270.98873], [None, 440.80713]]


def test_edelar_con_subsidio_por_zona():
    import pathlib
    from parsers import PARSERS
    from simulador import SUB_BUILDERS
    t = (pathlib.Path(__file__).parent.parent / "site/data/textos/edelar.txt").read_text()
    s = SUB_BUILDERS["edelar"](PARSERS["edelar"](t)["tablas"])
    z = {x["id"]: x["categorias"] for x in s["zonas"]}
    assert sorted(z) == ["I", "II", "III"]
    assert all(c["fijo"] == 2124.71 for cs in z.values() for c in cs)
    assert z["I"][0]["escalones"] == [[150, 75.676], [200, 150.4463]]
    assert z["I"][2]["escalones"][-1] == [None, 158.2839]
    assert z["II"][2]["escalones"][-1] == [None, 168.1767]


def _txt(name):
    return (Path(__file__).resolve().parents[1] / "site/data/textos" / f"{name}.txt").read_text()


def test_emsa_sin_subsidio():
    from parsers import PARSERS
    from simulador import BUILDERS
    cats = BUILDERS["emsa"](PARSERS["emsa"](_txt("emsa"))["tablas"])["categorias"]
    assert [c["hasta"] for c in cats] == [500, 700, 1400, None]
    assert cats[0]["fijo"] == 2309.1 and cats[0]["escalones"][0] == [30, 272.997]
    assert cats[0]["escalones"][-1] == [500, 278.926]
    assert cats[-1]["escalones"][-1] == [None, 283.132]


def test_spse_sin_subsidio():
    from parsers import PARSERS
    from simulador import BUILDERS
    cats = BUILDERS["spse"](PARSERS["spse"](_txt("spse"))["tablas"])["categorias"]
    assert cats[0] == {"nombre": "Tramo primero", "hasta": 100, "fijo": 16000.0, "escalones": [[None, 127.659]]}
    assert cats[-1]["hasta"] is None and len(cats) == 5


def test_ecsapem_no_subsidiado():
    import pytest
    from parsers import PARSERS
    from simulador import BUILDERS
    t = (Path(__file__).parent / "fixtures/ecsapem_no_subsidiado.txt").read_text()
    c = BUILDERS["ecsapem"](PARSERS["ecsapem"](t)["tablas"])["categorias"]
    assert c == [{"nombre": "T1-R", "hasta": None, "fijo": 29631.97, "escalones": [[None, 159.3583]]}]
    with pytest.raises(ValueError):  # the subsidised cuadro has no 'todo consumo' rows
        BUILDERS["ecsapem"](PARSERS["ecsapem"](t.replace("NO BONIFICADO todo consumo", "BONIFICADO consumos base"))["tablas"])
