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
