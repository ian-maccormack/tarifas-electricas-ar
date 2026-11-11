import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
import parsers  # noqa: E402
from parsers import PARSERS  # noqa: E402
from simulador import BUILDERS, DEMANDA, cost  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"


def _txt(name):
    return gzip.open(FIX / name, "rt").read()


def _cats(sim):
    return [(c["hasta"], c["fijo"], c["escalones"]) for c in sim["categorias"]]


def test_edesa_octubre_2026():
    p = PARSERS["edesa"](_txt("edesa-2026-10.txt.gz"))
    assert p["vigencia"] == "Resolución ENRESP N° 1770/26"
    sim = BUILDERS["edesa"](p["tablas"])
    assert sim["periodo"] == "mes"
    assert _cats(sim) == [(192, 5842.64, [[None, 291.9371]]), (500, 10564.94, [[None, 305.6299]]),
                          (700, 14165.59, [[None, 309.8772]]), (1400, 20814.68, [[None, 309.5418]]),
                          (None, 30232.14, [[None, 310.4589]])]


def test_dpec_108g():
    p = PARSERS["dpec"](_txt("dpec-108g.txt.gz"))
    assert p["vigencia"] == "Cuadro Tarifario N° 108-G: agosto a octubre de 2026"
    sim = BUILDERS["dpec"](p["tablas"])
    assert sim["periodo"] == "bimestre"
    assert _cats(sim) == [(None, 33878.0, [[600, 205.87], [None, 244.294]])]
    assert DEMANDA["dpec"](p["tablas"])["tarifas"]


def test_ejesa_octubre_2026():
    p = PARSERS["ejesa"](_txt("ejesa-2026-10.txt.gz"))
    sim = BUILDERS["ejesa"](p["tablas"])
    assert _cats(sim)[0] == (150, 5116.0, [[None, 253.2436]])
    assert _cats(sim)[-1] == (None, 93847.0, [[None, 265.2628]])
    assert len(sim["categorias"]) == 8
    assert DEMANDA["ejesa"](p["tablas"])["tarifas"]


def test_edelap_por_posicion(monkeypatch):
    lines = json.load(gzip.open(FIX / "edelap-2026-09-chars.json.gz", "rt"))
    monkeypatch.setattr(parsers, "_pdf_lines", lambda content: lines)
    p = PARSERS["edelap"]("Cuadro tarifario vigente a partir del  é\n01/09/2026", content=b"%PDF-fixture")
    assert p["vigencia"] == "Vigente a partir del 01/09/2026"
    titulos = [t["titulo"] for t in p["tablas"]]
    assert titulos[0].startswith("T1-R") and not any("peaje" in t or "T4-R" in t for t in titulos)
    sim = BUILDERS["edelap"](p["tablas"])
    assert _cats(sim)[:2] == [(150, 5762.32, [[None, 174.2926]]), (325, 17892.17, [[None, 165.1251]])]
    assert _cats(sim)[-1] == (None, 89317.04, [[None, 211.0473]])
    assert len(sim["categorias"]) == 9
    t3 = next(t for t in p["tablas"] if t["titulo"].startswith("Tarifa Nº3"))
    assert t3["filas"][0]["valores"] == [25918.15, 20814.57, 11616.83]
    assert t3["filas"][0]["columnas"] == ["BT", "MT", "AT"]
    assert round(cost(sim, 300)) == round(17892.17 + 300 * 165.1251)


def test_ejesa_vigencia():
    assert PARSERS["ejesa"](_txt("ejesa-2026-10.txt.gz"))["vigencia"] == "Octubre 2026 (Res. 297-SUSEPU-2026)"
