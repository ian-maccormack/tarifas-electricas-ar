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



def _dem(id, ten, kw, kwh, pico=0.25, valle=0.3):
    return round(cost_demanda(build_demanda(_entry(id)), ten, kw, kwh, pico, valle), 2)


def _mix(p, r, v, kwh, pico=0.25, valle=0.3):
    return kwh * (pico * p + (1 - pico - valle) * r + valle * v)


def test_epen_t2_t3():
    assert _dem("epen", "BT", 20, 3000) == round(20 * 49800.44 + 3000 * 402.702, 2)
    assert _dem("epen", "BT", 100, 20000) == round(100 * (57359.77 + 44175.27) + _mix(366.999, 359.733, 355.983, 20000), 2)
    assert _dem("epen", "AT", 400, 90000) == round(400 * (21636.34 + 20472.54) + _mix(293.757, 293.592, 295.094, 90000), 2)


def test_refsa_only_t3_from_300():
    assert cost_demanda(build_demanda(_entry("refsa")), "BT", 100, 20000, 0.25, 0.3) is None
    assert _dem("refsa", "BT", 400, 90000) == round(400 * (15977.78 + 5548.42) + _mix(182.7234, 178.5493, 178.061, 90000), 2)


def test_esj_t2_t3():
    assert _dem("esj", "BT", 15, 3000) == round(115977.79 + 3000 * 264.9631, 2)
    assert _dem("esj", "BT", 30, 5000) == round(72314.83 + 30 * 22867.565 + 5000 * 195.7255, 2)
    assert _dem("esj", "BT", 100, 20000) == round(206912.86 + 100 * (21029.36 + 8483.329) + _mix(157.9653, 153.2696, 152.1565, 20000), 2)
    assert cost_demanda(build_demanda(_entry("esj")), "MT", 100, 20000, 0.25, 0.3) is None


def test_dpec_t2_t3():
    assert _dem("dpec", "MT", 30, 5000) == round(30 * 31763 + 5000 * 109.386, 2)
    assert _dem("dpec", "MT", 400, 90000) == round(400 * 18115 + _mix(99.909, 98.153, 97.26, 90000), 2)


def test_mendoza_t2():
    assert _dem("edemsa", "BT", 50, 10000) == round(38358.729 + 50 * (56868.335 + 10454.284) + _mix(151.0511, 146.561, 145.4966, 10000), 2)
    assert _dem("edemsa", "MT", 400, 90000) == round(561205.887 + 400 * (44323.856 + 10038.096) + _mix(159.6745, 154.8244, 153.6745, 90000), 2)


def test_ejesa_t2_t3():
    assert cost_demanda(build_demanda(_entry("ejesa")), "BT", 12, 3000, 0.25, 0.3) is None
    assert _dem("ejesa", "BT", 20, 4000) == round(114185 + 20 * 26108 + _mix(196.3388, 191.5834, 190.4561, 4000), 2)
    assert _dem("ejesa", "MT", 400, 90000) == round(328464 + 400 * 21271 + _mix(195.129, 190.1941, 189.0241, 90000), 2)



def test_edesal_t2():
    assert _dem("edesal", "BT", 50, 10000) == round(29660.804159 + 50 * (20824.278775 + 8859.217648) + _mix(126.0977, 122.6623, 121.0631, 10000), 2)
    assert _dem("edesal", "AT", 400, 90000) == round(112516.602049 + 400 * (6920.349048 + 6932.760414) + _mix(110.0093, 106.9651, 105.5473, 90000), 2)


def test_edese_t2_t3():
    assert _dem("edese", "BT", 20, 3000) == round(20 * 30897.22 + 3000 * 257.368, 2)
    assert _dem("edese", "MT", 100, 20000) == round(100 * (20606.34 + 6652.43) + _mix(153.098, 148.878, 147.878, 20000), 2)
    assert _dem("edese", "BT", 400, 90000) == round(400 * (34692.62 + 15551.06) + _mix(180.515, 175.386, 174.17, 90000), 2)


def _rows(*rows):
    return [{"grupo": None, "concepto": c, "unidad": None, "valores": v, "columnas": None} for c, v in rows]


def test_ocr_builders_only_for_ocr_entries():
    from simulador import build_ocr
    tablas = [{"titulo": "Página 4", "filas": _rows(("Símes", [4412.16]), ("Primeros 150 kKWh'mes", [146.1422]),
                                                    ("Siguientes 150 kWh'mes", [164.1071]), ("Excedente de 300 kWh'mes", [176.2317]))}]
    s = build_ocr({"id": "dpe", "estado": "ok", "ocr": True, "tablas": tablas})
    assert round(cost(s, 400), 2) == round(4412.16 + 150 * 146.1422 + 150 * 164.1071 + 100 * 176.2317, 2)
    assert build_ocr({"id": "dpe", "estado": "ok", "ocr": False, "tablas": tablas}) is None
    bad = [{"titulo": "Página 4", "filas": _rows(("Símes", [4412.16]), ("Primeros 150", [146.1422]))}]
    assert build_ocr({"id": "dpe", "estado": "ok", "ocr": True, "tablas": bad}) is None


def test_secheep_ocr_empty_above_missing_block():
    from simulador import build_ocr
    tablas = [{"titulo": "Página 1", "filas": _rows(("Cargo Fijo", [None, 3631.72, 3631.72]), ("Cargo Variable Lros. 50 KWh-mes", [171.6, 30.75, 202.3802]),
                                                    ("Cargo Variable stes. 100 KWh-mes", [171.6, 48.38, 220.0146]),
                                                    ("Cargo Variable stes. 150 KWh-mes", [171.6, 103.2, 274.8771]),
                                                    ("Cargo Variable exc. 300 KWh-mes", [171.6302]))}]
    s = build_ocr({"id": "secheep", "estado": "ok", "ocr": True, "tablas": tablas})
    assert round(cost(s, 150), 2) == round(3631.72 + 50 * 202.3802 + 100 * 220.0146, 2)
    assert cost(s, 400) is None


def test_edesa_ocr_categories():
    from simulador import build_ocr
    tablas = [{"titulo": "Página 19", "filas": _rows(("TIR1 [O<= E<= 192]", [5842.64, 291.9371]), ("T1R1 SEF [0<=E<=192]", [1.0, 1.0]),
                                                     ("T1R2 [192 < E<= 500KWh/mes]", [10564.94, 305.6299]), ("T1R2 [E > 500KWh/mes]", [14165.59, 309.8772]))}]
    s = build_ocr({"id": "edesa", "estado": "ok", "ocr": True, "tablas": tablas})
    assert [c["hasta"] for c in s["categorias"]] == [192, 500, None]
    assert round(cost(s, 150), 2) == round(5842.64 + 150 * 291.9371, 2)


def test_consumo_base_por_mes():
    from parsers import consumo_base
    t = ("Nota: Períodos dic/feb y mayo/agosto: consumo base de 300 kWh/mes. "
         "Períodos marzo/abril y septiembre/noviembre: consumo base de 150 kWh/mes.")
    assert consumo_base(t) == [300, 300, 150, 150, 300, 300, 300, 300, 150, 150, 150, 300]
    assert consumo_base("Períodos dic/feb: consumo base de 300 kWh/mes.") is None


def test_enre_subsidio_consumo_base():
    from simulador import enre_sub
    base = [300, 300, 150, 150, 300, 300, 300, 300, 150, 150, 150, 300]
    tablas = [
        {"titulo": "R2 — Tarifa 1 - R sin subsidio", "filas": _rows(("Cargo Fijo 151-400", [3866.44]), ("Cargo Variable 151-400", [159.788]))},
        {"titulo": "R1 — Tarifa 1 - R con subsidio", "consumo_base": base,
         "filas": _rows(("Cargo Fijo 0-150", [1812.81]), ("Cargo Variable 0-150", [61.083]))},
        {"titulo": "R2 — Tarifa 1 - R con subsidio", "consumo_base": base,
         "filas": _rows(("Cargo Fijo 151-400", [3866.44]), ("Cargo Variable consumo base", [61.743]),
                        ("Cargo Variable excedente a consumo base", [159.788]))},
        {"titulo": "G1 — Tarifa 1 - G", "filas": _rows(("Cargo Fijo 0-800", [1.0]))},
    ]
    s = enre_sub(tablas)
    assert [c["nombre"] for c in s["categorias"]] == ["R1", "R2"]
    assert round(cost(s, 250, 10), 2) == round(3866.44 + 150 * 61.743 + 100 * 159.788, 2)
    assert round(cost(s, 250, 1), 2) == round(3866.44 + 250 * 61.743, 2)
    assert cost(s, 250) is None
    assert round(cost(s, 100, 10), 2) == round(1812.81 + 100 * 61.083, 2)


def test_edersa_subsidio_tope():
    from simulador import edersa_sub
    cols = ["Con Subsidio (m)", "Con Subsidio (t)", "Sin Subsidio (m)", "Sin Subsidio (t)"]
    g1, g2 = "Hasta 300 kWh/bimestre", "Mayor a 300 kWh/bimestre"
    filas = [
        {"grupo": g1, "concepto": "CARGO FIJO", "unidad": "$/bimes", "valores": [9621.78, 11258.41, 9715.62, 11352.24], "columnas": cols},
        {"grupo": g1, "concepto": "CARGO VARIABLE", "unidad": "$/kWh", "valores": [193.765, 201.772, 287.765, 295.772], "columnas": cols},
        {"grupo": g2, "concepto": "CARGO FIJO", "unidad": "$/bim", "valores": [27555.82, 30501.74, 29800.46, 32746.38], "columnas": cols},
        {"grupo": g2, "concepto": "CARGO VARIABLE BASE", "unidad": "$/kWh", "valores": [190.015, 191.334, 289.656, 290.974], "columnas": cols},
        {"grupo": g2, "concepto": "CARGO VARIABLE excedente (*)", "unidad": "$/KWh", "valores": [289.656, 290.974], "columnas": None},
    ]
    s = edersa_sub([{"titulo": "Tarifa Residencial", "tope_subsidio": 400, "filas": filas}])
    assert round(cost(s, 100), 2) == round((9621.78 + 200 * 193.765) / 2, 2)
    assert round(cost(s, 250), 2) == round((27555.82 + 400 * 190.015 + 100 * 289.656) / 2, 2)
    assert cost(edersa_sub([{"titulo": "x", "tope_subsidio": None, "filas": filas}]), 250) is None
    from simulador import edersa
    assert round(cost(edersa([{"titulo": "x", "filas": filas}]), 250), 2) == round((29800.46 + 500 * 289.656) / 2, 2)


def test_edesal_fijo_mas_uso_de_red():
    s = build(_entry("edesal"))
    assert [c["hasta"] for c in s["categorias"]] == [160, 200, 400, 700, 1400, None]
    assert round(cost(s, 250), 2) == round(10497.6577 + 20480.406 + 250 * 129.0571, 2)
    e = _entry("edesal")
    e["tablas"][0]["unidades"] = None
    assert build(e) is None


def test_edelar_bloques_sin_subsidio():
    s = build(_entry("edelar"))
    assert [c["nombre"] for c in s["categorias"]] == ["T1-R1-NS", "T1-R2-NS", "T1-R3-NS"]
    assert round(cost(s, 150), 2) == round(2124.71 + 150 * 176.9956, 2)
    assert round(cost(s, 250), 2) == round(2124.71 + 200 * 176.9956 + 50 * 125.467, 2)
    assert round(cost(s, 800), 2) == round(2124.71 + 200 * 176.9956 + 230 * 125.467 + 370 * 197.8549, 2)


def test_epec_sin_sef_y_energia_minima():
    s = build(_entry("epec"))
    assert [c["hasta"] for c in s["categorias"]] == [120, 500, 700, None]
    assert round(cost(s, 250), 2) == round(2948.6141 + 120 * 250.30482 + 130 * 300.9946, 2)
    assert round(cost(s, 10), 2) == round(2123.2848 + 20 * 219.87512, 2)
