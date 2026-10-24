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
from sources import ORIGEN_SE, SOURCES, se_archive

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


def get_doc(url):
    CACHE.mkdir(exist_ok=True)
    r = fetch(url, timeout=90)
    return r.content, r.headers.get("content-type", "")


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
            content, ctype = get_doc(d["url"])
            tipo, text, sheets = document_text(content, d["url"], ctype)
            if tipo in ("html",) and s["parser"] != "enre":
                raise ValueError("el enlace devolvió una página HTML en vez del documento")
            if not text.strip() and tipo == "pdf":
                text = ""
            doc = dict(url=d["url"], titulo=d.get("titulo"), pagina=d.get("pagina"), origen=origen,
                       tipo=tipo, sha256=hashlib.sha256(content).hexdigest(), bytes=len(content),
                       via={"primary": "búsqueda automática", "known": "URL conocida",
                            "se": "archivo nacional"}[kind])
            parsed = {"vigencia": None, "tablas": []}
            fn = PARSERS.get(s["parser"])
            if fn and text.strip():
                try:
                    parsed = fn(text, content=content, source=s, sheets=sheets) or parsed
                except Exception as e:
                    entry["intentos"].append(f"parser: {type(e).__name__}: {e}")
            tablas = validate(parsed.get("tablas", []))
            entry.update(documento=doc, vigencia=parsed.get("vigencia"), tablas=tablas, comparable=parsed.get("comparable"),
                         texto=bool(text.strip()), escaneado=(tipo == "pdf" and len(text.strip()) < 200))
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
    out = {"generado": NOW, "distribuidoras": [by_id[i] for i in order if i in by_id]}
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
