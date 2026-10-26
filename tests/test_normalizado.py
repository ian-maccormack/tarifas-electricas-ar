import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
from normalizado import normalizar  # noqa: E402


def test_residential_rows_keep_units_ranges_and_missing_values():
    e = {"simulador": {"periodo": "bimestre", "criterio": "c", "categorias": [
        {"nombre": "R1", "hasta": 299, "fijo": 100.0, "escalones": [[None, 5.0]]},
        {"nombre": "R2", "hasta": None, "fijo": None, "escalones": [[300, 6.0], [None, None]]}]}}
    f = normalizar(e)["filas"]
    assert [(r["categoria"], r["condicion"], r["concepto"], r["tramo"], r["unidad"], r["valor"]) for r in f] == [
        ("R1", "hasta 299 kWh/bim", "Cargo fijo", "", "$/bim", 100.0),
        ("R1", "hasta 299 kWh/bim", "Energía", "todo el consumo", "$/kWh", 5.0),
        ("R2", "más de 299 kWh/bim", "Cargo fijo", "", "$/bim", None),
        ("R2", "más de 299 kWh/bim", "Energía", "primeros 300 kWh/bim", "$/kWh", 6.0),
        ("R2", "más de 299 kWh/bim", "Energía", "excedente de 300 kWh/bim", "$/kWh", None)]


def test_subsidy_base_and_demand_rows():
    e = {"simulador_subsidio": {"periodo": "mes", "criterio": "s", "base_mes": [300] * 12, "categorias": [
        {"nombre": "R1", "hasta": None, "fijo": 1.0, "escalones": [["base", 2.0], [None, 3.0]]}]},
         "demanda": {"criterio": "d", "tarifas": [
             {"nombre": "T3", "tension": "BT", "desde_kw": 50, "hasta_kw": None, "fijo": 0.0,
              "potencia": [["Potencia en pico", 10.0]], "energia": {"pico": 4.0, "valle": None}}]}}
    n = normalizar(e)
    tramos = [r["tramo"] for r in n["filas"] if r["seccion"].startswith("Residencial")]
    assert tramos == ["", "consumo base subsidiado", "excedente del consumo base"]
    dem = [(r["concepto"], r["tramo"], r["unidad"], r["valor"]) for r in n["filas"] if r["tension"] == "BT"]
    # no monthly fixed charge in the cuadro (encoded 0.0) -> no row, not a 0
    assert dem == [("Potencia en pico", "", "$/kW-mes", 10.0), ("Energía", "pico", "$/kWh", 4.0),
                   ("Energía", "valle", "$/kWh", None)]
    assert n["filas"][-1]["condicion"] == "desde 50 kW"
    assert any("ene 300" in x for x in n["notas"])


def test_no_structure_gives_none():
    assert normalizar({"tablas": [{"titulo": "x", "filas": []}]}) is None
