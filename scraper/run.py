"""Download every distributor's current tariff document, extract it and write site/data."""
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import pathlib
import sys
import traceback

from common import document_text, fetch
from parsers import PARSERS
from simulador import build as build_sim, build_demanda, build_ocr, build_subsidio
from sources import ORIGEN_SE, SOURCES, WAYBACK, _date_key, _wayback, date_key, se_archive

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "site" / "data"
TEXTS = DATA / "textos"
CACHE = ROOT / ".cache"
NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def candidates(s):
    if s["primary"]:
        yield "primary", s["primary"], s["origen"]
    if s.get("known"):
        yield "known", lambda: {"url": s["known"], "titulo": s["known"].rsplit("/", 1)[-1]}, s["origen"]
    if s["se"]:
        yield "se", se_archive(s["se"]), ORIGEN_SE


def get_doc(url, headers=None):
    CACHE.mkdir(exist_ok=True)
    if url.startswith(WAYBACK):
        # An archived capture never changes: keep a copy so the daily run does not depend on the
        # Internet Archive answering (it often rate-limits GitHub's servers).
        copy = DATA / "copias" / (hashlib.sha256(url.encode()).hexdigest()[:16] + ".pdf")
        if copy.exists():
            return copy.read_bytes(), "application/pdf"
        r = _wayback(url, timeout=90)
        if r.content[:5] == b"%PDF-":
            copy.parent.mkdir(exist_ok=True)
            copy.write_bytes(r.content)
        return r.content, r.headers.get("content-type", "")
    r = fetch(url, timeout=90, headers=headers)
    return r.content, r.headers.get("content-type", "")


# First residential tier in OCR documents: (concepto_re, column, grupo_re, unit) checked against each
# document's layout. A missing or non-agreeing value simply stays empty.
OCR_COMPARABLE = {
    "edea": ((r"^Cargo variable 1 \(consumo en KWH-Mes . 100\)", 0, r"^T1 ", "$/mes"),
             (r"^Cargo variable 1 \(consumo en KWH-Mes . 100\)", 1, r"^T1 ", "$/kWh"),
             "T1R Nivel 1, consumo < 100 kWh-mes (OCR)"),
    "secheep": ((r"^Cargo Fijo$", 2, None, "$/mes"), (r"^Cargo Variable .{0,5}ros\.? 50", 2, None, "$/kWh"),
                "Residencial sin SEF, Total Neto, primeros 50 kWh-mes (OCR)"),
    "dpe": ((r"^S.?mes$", 0, None, "$/mes"), (r"^Primeros 150", 0, None, "$/kWh"),
            "TR1 Nivel 1, primeros 150 kWh/mes (OCR)"),
    "edesa": ((r"^T[1I]R[1I]\s*\[\s*[0O]\s*<=", 0, None, "$/mes"), (r"^T[1I]R[1I]\s*\[\s*[0O]\s*<=", 1, None, "$/kWh"),
              "T1R1 (0 a 192 kWh/mes) (OCR)"),
}


def ocr_comparable(id, tablas):
    from parsers import pick
    if id not in OCR_COMPARABLE:
        return None
    fijo, var, nota = OCR_COMPARABLE[id]
    out = {"nota": nota}
    for key, (rx, col, grx, unit) in (("cargo_fijo", fijo), ("cargo_variable", var)):
        v = pick(tablas, rx, col, grx)
        out[key] = {**v, "unidad": unit} if v else None
    return out if out["cargo_fijo"] or out["cargo_variable"] else None


def ocr_tables(id, content, dpi=None):
    """OCR is slow, so results are cached in the repo by document hash."""
    from ocr import DPI, MAX_PX, ocr_rows, read_pages
    sha = hashlib.sha256(content).hexdigest()[:16]
    cache = DATA / "ocr" / f"{id}-{sha}.json"
    if cache.exists():
        pages = json.loads(cache.read_text())
    else:
        pages = read_pages(content, dpi or DPI, max(MAX_PX, int(11.7 * (dpi or DPI))))
        cache.parent.mkdir(exist_ok=True)
        for old in cache.parent.glob(f"{id}-*.json"):
            old.unlink()
        cache.write_text(json.dumps(pages, ensure_ascii=False, separators=(",", ":")))
    rows = ocr_rows(pages)
    tablas = []
    for r in rows:
        key = (r["pagina"], tuple(r.get("columnas") or ()))
        if not tablas or tablas[-1][0] != key:
            tablas.append((key, {"titulo": f"Página {r['pagina']} — transcripción por OCR", "filas": []}))
        tablas[-1][1]["filas"].append({"grupo": r["grupo"], "concepto": r["concepto"], "unidad": r["unidad"],
                                       "valores": r["valores"], "columnas": r.get("columnas")})
    return [t for _, t in tablas]


_ABBR = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "set": 9,
         "oct": 10, "nov": 11, "dic": 12}
_MES_NOMBRE = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
               "noviembre", "diciembre"]


def ocr_vigencia(text):
    """Validity stated in the OCR text in one of the two explicit forms used by these documents."""
    import re
    from common import norm
    t = norm(text)
    m = re.search(r"vencimiento en (?:el mes de )?([a-z]+) (?:de )?(20\d\d)", t)
    if m and m.group(1)[:3] in _ABBR and _MES_NOMBRE[_ABBR[m.group(1)[:3]] - 1].startswith(m.group(1)[:4]):
        return f"Facturación con vencimiento en {_MES_NOMBRE[_ABBR[m.group(1)[:3]] - 1]} de {m.group(2)} (leído por OCR)"
    m = re.search(r"vigencia\s*:?\s*(ene|feb|mar|abr|may|jun|jul|ago|sept?|set|oct|nov|dic)[a-z]*\s*['’`]\s*(\d{2})(?!\d)", t)
    if m:
        return f"Vigencia: {_MES_NOMBRE[_ABBR[m.group(1)[:3]] - 1]} de 20{m.group(2)} (leído por OCR)"
    return None


def _ocr_text(id, content):
    cache = DATA / "ocr" / f"{id}-{hashlib.sha256(content).hexdigest()[:16]}.json"
    if not cache.exists():
        return ""
    return " ".join(w["t"] for pg in json.loads(cache.read_text()) for w in pg["tesseract"])


def validate(tablas):
    """Drop tables without any numeric value; never invent missing cells."""
    out = []
    for t in tablas:
        filas = [f for f in t["filas"] if any(v is not None for v in f["valores"])]
        if filas:
            out.append({**t, "filas": filas})
    return out


def process(s):
    entry = {k: s[k] for k in ("id", "empresa", "nombre", "provincia", "nota")}
    entry.update(estado="sin_datos", documento=None, vigencia=None, tablas=[], intentos=[], verificado=NOW)
    for kind, disc, origen in candidates(s):
        try:
            d = disc()
            content, ctype = get_doc(d["url"], d.get("headers"))
            tipo, text, sheets = document_text(content, d["url"], ctype)
            if tipo in ("html",) and s["parser"] != "enre":
                raise ValueError("el enlace devolvió una página HTML en vez del documento")
            if not text.strip() and tipo == "pdf":
                text = ""
            doc = dict(url=d["url"], titulo=d.get("titulo"), pagina=d.get("pagina"), origen=origen,
                       tipo=tipo, sha256=hashlib.sha256(content).hexdigest(), bytes=len(content),
                       via={"primary": "búsqueda automática", "known": "URL conocida",
                            "se": "archivo nacional"}[kind])
            for k in ("archivado", "resolucion"):
                if d.get(k):
                    doc[k] = d[k]
            parsed = {"vigencia": None, "tablas": []}
            fn = PARSERS.get(s["parser"])
            if fn and text.strip():
                try:
                    parsed = fn(text, content=content, source=s, sheets=sheets) or parsed
                except Exception as e:
                    entry["intentos"].append(f"parser: {type(e).__name__}: {e}")
            tablas = validate(parsed.get("tablas", []))
            used_ocr = False
            if not tablas and tipo == "pdf" and (s.get("ocr") or len(text.strip()) < 200):
                tablas = validate(ocr_tables(s["id"], content, s.get("ocr_dpi")))
                used_ocr = bool(tablas)
                parsed["comparable"] = ocr_comparable(s["id"], tablas)
                if used_ocr and not parsed.get("vigencia"):
                    parsed["vigencia"] = ocr_vigencia(_ocr_text(s["id"], content))
            entry.update(documento=doc, vigencia=parsed.get("vigencia") or d.get("vigencia"), tablas=tablas, comparable=parsed.get("comparable"),
                         texto=bool(text.strip()), escaneado=(tipo == "pdf" and len(text.strip()) < 200), ocr=used_ocr)
            if text.strip() and tipo != "html":
                (TEXTS / f"{s['id']}.txt").write_text(text)
            entry["estado"] = "ok" if tablas else "documento"
            entry["intentos"].append(f"{kind}: OK {d['url']}")
            break
        except Exception as e:
            entry["intentos"].append(f"{kind}: {type(e).__name__}: {str(e)[:200]}")
    if s["se"] and (entry["documento"] or {}).get("via") != "archivo nacional":
        try:
            entry["archivo_nacional"] = se_archive(s["se"])()
        except Exception:
            pass
    return entry


STALE_MONTHS = 2


def reference_month(e):
    """(year, month) the published document refers to, from the validity text, else the document
    title/URL. Returns (None, None) when no date can be read: then nothing is claimed."""
    from common import norm
    if e.get("vigencia"):
        k = _date_key(norm(e["vigencia"]))
        if k != (0, 0, 0):
            return k[:2], "vigencia"
    d = e.get("documento") or {}
    for key in ("titulo", "url"):
        k = date_key(d.get("url", "") if key == "url" else "", d.get(key) or "") if key == "titulo" else date_key(d.get("url", ""))
        if k != (0, 0, 0):
            return k[:2], "título" if key == "titulo" else "URL del documento"
    if d.get("publicado"):
        return (int(d["publicado"][:4]), int(d["publicado"][5:7])), "fecha de publicación"
    head = ""
    txt = TEXTS / f"{e['id']}.txt"
    if txt.exists():
        head = txt.read_text(errors="ignore")[:3000]
    for c in (DATA / "ocr").glob(f"{e['id']}-*.json") if not head.strip() else []:
        head = " ".join(w["t"] for w in json.loads(c.read_text())[0]["tesseract"][:400])
    k = _date_key(norm(head))
    if k != (0, 0, 0):
        return k[:2], "texto del documento"
    return None, None


def mark_staleness(e):
    ym, origin = reference_month(e)
    now = dt.datetime.now(dt.timezone.utc)
    e["mes_referencia"] = f"{ym[0]}-{ym[1]:02d}" if ym else None
    e["mes_referencia_origen"] = origin
    e["simulador"] = build_sim(e)
    e["demanda"] = build_demanda(e)
    e["simulador_ocr"] = build_ocr(e)
    e["simulador_subsidio"] = build_subsidio(e)
    e["desactualizado"] = bool(ym) and (now.year * 12 + now.month) - (ym[0] * 12 + ym[1]) > STALE_MONTHS
    return e


def main(only=None):
    TEXTS.mkdir(parents=True, exist_ok=True)
    prev_path = DATA / "tarifas.json"
    prev = {e["id"]: e for e in json.loads(prev_path.read_text())["distribuidoras"]} if prev_path.exists() else {}
    srcs = [s for s in SOURCES if not only or s["id"] in only]
    with cf.ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda s: _safe(process, s), srcs))
    by_id = dict(prev)
    for e in results:
        old = prev.get(e["id"])
        downgraded = (old and old.get("estado") == "ok" and e["estado"] != "ok"
                      and (e.get("documento") or {}).get("via") == "archivo nacional"
                      and (old.get("documento") or {}).get("via") != "archivo nacional")
        if (e["estado"] == "sin_datos" and old and old.get("documento")) or downgraded:
            # Keep the last successfully verified document, flagged as stale.
            old = {**old, "ultimo_intento": NOW, "ultimo_intento_fallido": True, "intentos": e["intentos"]}
            by_id[e["id"]] = old
        else:
            by_id[e["id"]] = e
    order = [s["id"] for s in SOURCES]
    out = {"generado": NOW, "distribuidoras": [mark_staleness(by_id[i]) for i in order if i in by_id]}
    prev_path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    hist_path = DATA / "historial.json"
    hist = json.loads(hist_path.read_text()) if hist_path.exists() else []
    seen = {(h["id"], h["sha256"]) for h in hist}
    for e in results:
        d = e.get("documento")
        if d and (e["id"], d["sha256"]) not in seen:
            hist.append(dict(id=e["id"], detectado=NOW, sha256=d["sha256"], url=d["url"],
                             titulo=d["titulo"], vigencia=e.get("vigencia"),
                             tablas=e["tablas"]))
    hist_path.write_text(json.dumps(hist, ensure_ascii=False, indent=1))
    for e in results:
        print(f"{e['id']:8} {e['estado']:9} {(e.get('vigencia') or '-')[:40]:40} {len(e['tablas'])} tablas | {(e['intentos'] or ['sin fuentes'])[-1][:90]}")


def _safe(fn, s):
    try:
        return fn(s)
    except Exception:
        traceback.print_exc()
        return {"id": s["id"], "estado": "sin_datos", "tablas": [], "intentos": ["error interno"]}


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
