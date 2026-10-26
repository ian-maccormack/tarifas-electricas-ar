"""Common, source-independent view of each distribuidora's tariff.

Built only from the structures the simulators already verified (simulador,
simulador_subsidio, simulador_ocr, demanda): nothing here reads the raw
document, so a missing value stays None.
"""

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
FRANJA = {"unica": "todo el consumo", "pico": "pico", "fuera_pico": "fuera de pico",
          "resto": "resto", "valle": "valle"}
VARIANTES = (("simulador", "sin subsidio"), ("simulador_subsidio", "con subsidio"),
             ("simulador_ocr", "sin subsidio (OCR)"))


def _n(v):
    return f"{v:g}".replace(".", ",")


def _rango(prev, hasta, u):
    if hasta is None:
        return f"más de {_n(prev)} {u}" if prev else "todos los consumos"
    return f"más de {_n(prev)} y hasta {_n(hasta)} {u}" if prev else f"hasta {_n(hasta)} {u}"


def _tramo(prev, hasta, u):
    if hasta == "base":
        return "consumo base subsidiado"
    if prev == "base":
        return "excedente del consumo base"
    if hasta is None:
        return f"excedente de {_n(prev)} {u}" if prev else "todo el consumo"
    return f"de {_n(prev)} a {_n(hasta)} {u}" if prev else f"primeros {_n(hasta)} {u}"


def _residencial(sim, variante):
    per = "bim" if sim["periodo"] == "bimestre" else "mes"
    u = f"kWh/{per}"
    sec = f"Residencial (T1) — {variante}"
    filas, prev = [], 0
    for c in sim["categorias"]:
        nombre = c.get("nombre") or ""
        # Long names are the cuadro's full sentence; the range already says it.
        base = dict(seccion=sec, categoria=nombre if len(nombre) <= 45 else "",
                    condicion=_rango(prev, c["hasta"], u), tension=None)
        filas.append({**base, "concepto": "Cargo fijo", "tramo": "", "unidad": f"$/{per}", "valor": c["fijo"]})
        p0 = 0
        for hasta, precio in c["escalones"]:
            filas.append({**base, "concepto": "Energía", "tramo": _tramo(p0, hasta, u),
                          "unidad": "$/kWh", "valor": precio})
            p0 = hasta
        prev = c["hasta"] if c["hasta"] is not None else prev
    notas = [f"{sec}: {sim['criterio']}"]
    if sim["periodo"] == "bimestre":
        notas.append(f"{sec}: el cuadro factura por bimestre; los límites de consumo son por bimestre.")
    if sim.get("minimo_kwh") and "mínima" not in sim["criterio"]:
        notas.append(f"{sec}: energía mínima facturada {_n(sim['minimo_kwh'])} {u}.")
    if sim.get("base_mes"):
        notas.append(f"{sec}: consumo base subsidiado por mes ({u}): "
                     + ", ".join(f"{m} {_n(b)}" for m, b in zip(MESES, sim["base_mes"])) + ".")
    return filas, notas


def _kw(t):
    if t["hasta_kw"] is None:
        return f"desde {_n(t['desde_kw'])} kW"
    return f"desde {_n(t['desde_kw'])} hasta menos de {_n(t['hasta_kw'])} kW"


def _demanda(d):
    sec = "Medianas y grandes demandas (T2 y T3)"
    filas = []
    for t in d["tarifas"]:
        base = dict(seccion=sec, categoria=t["nombre"], condicion=_kw(t), tension=t["tension"])
        # 0.0 is how the builders encode "the cuadro has no monthly fixed charge" (see criterio).
        if t["fijo"] != 0:
            filas.append({**base, "concepto": "Cargo fijo", "tramo": "", "unidad": "$/mes", "valor": t["fijo"]})
        for nombre, p in t["potencia"]:
            filas.append({**base, "concepto": nombre, "tramo": "", "unidad": "$/kW-mes", "valor": p})
        for k, p in t["energia"].items():
            filas.append({**base, "concepto": "Energía", "tramo": FRANJA[k], "unidad": "$/kWh", "valor": p})
    return filas, [f"{sec}: {d['criterio']}"]


def normalizar(e):
    filas, notas = [], []
    for campo, variante in VARIANTES:
        if e.get(campo):
            f, n = _residencial(e[campo], variante)
            filas += f
            notas += n
    if e.get("demanda"):
        f, n = _demanda(e["demanda"])
        filas += f
        notas += n
    return {"filas": filas, "notas": notas} if filas else None
