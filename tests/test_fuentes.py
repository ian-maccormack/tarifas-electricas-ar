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
