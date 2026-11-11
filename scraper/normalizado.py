"""Common, source-independent view of each distribuidora's tariff.

Built only from the structures the simulators already verified (simulador,
simulador_ocr, demanda): nothing here reads the raw
document, so a missing value stays None.
"""

import re

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
FRANJA = {"unica": "todo el consumo", "pico": "pico", "fuera_pico": "fuera de pico",
          "resto": "resto", "valle": "valle"}
VARIANTES = (("simulador", "sin subsidio"),
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
    if sim.get("zonas"):
        filas, notas = [], []
        for z in sim["zonas"]:
            f, n = _residencial({**sim, "zonas": None, "categorias": z["categorias"], "criterio": z["criterio"]},
                                f"{variante}, {z['nombre']}")
            filas += f; notas += n
        return filas, notas
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


_UNIDAD = {"kwh": "$/kWh", "kw-mes": "$/kW-mes", "kwmes": "$/kW-mes", "kw": "$/kW", "mes": "$/mes",
           "bim": "$/bim", "kvarh": "$/kVArh", "kwh-mes": "$/kWh"}


def _unidad_ocr(u):
    m = re.fullmatch(r"[S$]\s*/\s*([A-Za-z-]+)\.?", (u or "").strip())
    return _UNIDAD.get(m.group(1).lower(), "") if m else ""


def _ocr(e):
    """Rows of the OCR transcription. A value goes in only when its column is certain: the row has a single
    amount, or every column was read with the same amount, or the columns have a header; rows without a
    certain amount are left to the original table."""
    filas = []
    for t in e.get("tablas") or []:
        for f in t["filas"]:
            concepto = re.sub(r"^(?:[^\w(]+|\w\s+(?=[A-ZÁÉÍÓÚ]))+", "", f.get("concepto") or "").strip()
            if len(re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", concepto)) < 3:
                continue
            grupo = (f.get("grupo") or "").split(" · ", 1)
            base = dict(seccion=f"Transcripción por OCR — {grupo[0] or 'sin título'}",
                        categoria=grupo[1] if len(grupo) > 1 else "", condicion="", tension=None,
                        concepto=concepto, unidad=_unidad_ocr(f.get("unidad")))
            vals, cols = f["valores"], f.get("columnas")
            if cols and len(cols) == len(vals) and len(vals) > 1 and len(set(vals) - {None}) > 1:
                filas += [{**base, "tramo": c, "valor": v} for c, v in zip(cols, vals)]
            else:
                certain = len(vals) == 1 or (None not in vals and len(set(vals)) == 1)
                if certain and vals[0] is not None:
                    filas.append({**base, "tramo": "", "valor": vals[0]})
    if not filas:
        return [], []
    return filas, ["Transcripción por OCR: solo se muestran los montos que leyeron igual los dos motores de OCR "
                   "y cuya columna es segura. Los conceptos sin un monto seguro figuran solo en el cuadro original completo. Los nombres de conceptos salen del OCR y "
                   "pueden tener errores de tipeo. Ante cualquier duda, vale el documento original."]


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
    if e.get("ocr"):
        f, n = _ocr(e)
        filas += f
        notas += n
    return {"filas": filas, "notas": notas} if filas else None
