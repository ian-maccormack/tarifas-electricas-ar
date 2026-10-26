import json, shutil, subprocess, sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
from sources import PAGO_MENSUAL  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node") or str(Path.home() / ".nvm/versions/node/v24.22.1/bin/node")

HARNESS = r"""
const vm = require("vm"), fs = require("fs");
const el = new Proxy(function () {}, { get: (t, k) => (k === "then" ? undefined : el), apply: () => el });
const ctx = { document: { querySelector: () => el, querySelectorAll: () => [], addEventListener() {} },
  fetch: () => new Promise(() => {}), window: {}, console, Intl, Date, Math };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), ctx);
process.stdout.write(JSON.stringify(vm.runInContext(fs.readFileSync(0, "utf8"), ctx)));
"""


def js(expr):
    if not Path(NODE).exists():
        pytest.skip("node no disponible")
    out = subprocess.run([NODE, "-e", HARNESS, str(ROOT / "site/app.js")], input=expr,
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


SIM = json.dumps({"periodo": "bimestre", "criterio": "", "categorias": [
    {"nombre": "T.1-R1", "hasta": 300, "fijo": 1000.0, "escalones": [[None, 10.0]]},
    {"nombre": "TR1 Nivel 2", "hasta": None, "fijo": 3000.0, "escalones": [[400, 20.0], [None, None]]}]})


def test_primer_escalon_conserva_unidad_original():
    r = js(f"compRes({{}}, {{s: {SIM}}}, 'primero', 0, 1, false)")
    assert (r["cat"], r["nombre"], r["fact"], r["fijo"], r["ufijo"], r["precio"]) == \
        ("Residencial 1 de 2", "T.1-R1", "Bimestral", 1000.0, "$/bim", 10.0)


def test_consumo_mensual_se_busca_en_bimestre_y_convierte_fijo():
    r = js(f"compRes({{}}, {{s: {SIM}}}, 'kwh', 250, 1, true)")
    assert (r["cat"], r["fijo"], r["ufijo"], r["precio"]) == ("Residencial 2 de 2", 1500.0, "$/mes (bimestral ÷ 2)", None)
    assert r["tramo"] == "más de 400 kWh/bim"


def test_valor_faltante_queda_vacio():
    r = js(f"compRes({{}}, {{s: {SIM}}}, 'kwh', 180, 1, false)")
    assert (r["precio"], r["tramo"]) == (20.0, "0–400 kWh/bim")


def test_pago_mensual_solo_con_fuente_oficial_https():
    data = {e["id"]: e for e in json.loads((ROOT / "site/data/tarifas.json").read_text())["distribuidoras"]}
    for k, (texto, url) in PAGO_MENSUAL.items():
        assert texto and url.startswith("https://")
        assert data[k]["simulador"]["periodo"] == "bimestre"
