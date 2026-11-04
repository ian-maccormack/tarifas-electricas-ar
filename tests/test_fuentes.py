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
