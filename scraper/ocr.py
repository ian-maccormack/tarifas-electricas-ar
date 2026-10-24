"""OCR for scanned tariff PDFs. A number is published only if Tesseract and RapidOCR read the
exact same digits at the same position on the page; otherwise the cell is left empty."""
import re
import subprocess
import tempfile
import threading
from pathlib import Path

from common import parse_num

DPI = 300
MAX_PX = 3600  # cap for very large pages, otherwise Tesseract takes minutes per page
_LOCK = threading.Lock()  # the scraper runs sources in threads; OCR is CPU-bound, run it one at a time
NUM = re.compile(r"-?\d[\d.,]*\d|\d")
# Tariff amounts always carry decimals. Readings without a decimal separator (e.g. "1029346" for
# "102,9346") are typical OCR failures that both engines can share, so they are never published.
# Integers are accepted only with thousands separators ("10.139" in a comma-decimal document).
AMOUNT = {",": re.compile(r"-?((\d{1,3}(\.\d{3})+|\d+),\d{2,5}|\d{1,3}(\.\d{3})+)"),
          ".": re.compile(r"-?((\d{1,3}(,\d{3})+|\d+)\.\d{2,5}|\d{1,3}(,\d{3})+)")}
# "44.061" could be 44061 or 44,061: such tokens do not count when detecting the decimal separator.
_AMBIGUOUS = re.compile(r"-?\d{1,3}[.,]\d{3}")
UNIT = re.compile(r"^[S$5]\s?/\s?\S+$|^\S{0,3}/\s?(mes|kwh?|k\s?w\S*)$", re.I)
TOL = 0.012  # max distance between both engines' readings, as a fraction of page width


def _pages(pdf_bytes, d):
    p = Path(d) / "doc.pdf"
    p.write_bytes(pdf_bytes)
    subprocess.run(["pdftoppm", "-r", str(DPI), "-scale-to", str(MAX_PX), "-png", str(p), str(Path(d) / "pg")], check=True,
                   stderr=subprocess.DEVNULL)
    return sorted(Path(d).glob("pg-*.png"))


def _tesseract(img):
    out = subprocess.run(["tesseract", str(img), "-", "-l", "spa", "--psm", "6", "tsv"],
                         capture_output=True, text=True, timeout=600).stdout
    words = []
    for ln in out.splitlines()[1:]:
        c = ln.split("\t")
        if len(c) == 12 and c[11].strip() and float(c[10]) >= 0:
            x, y, w, h = map(int, c[6:10])
            words.append({"t": c[11].strip(), "x0": x, "x1": x + w, "y": y + h / 2, "h": h,
                          "line": (int(c[2]), int(c[3]), int(c[4]))})
    return words


_RAPID = None


def _rapid(img):
    global _RAPID
    if _RAPID is None:
        from rapidocr_onnxruntime import RapidOCR
        _RAPID = RapidOCR()
    res, _ = _RAPID(str(img))
    toks = []
    for box, text, _score in res or []:
        xs, ys = [float(p[0]) for p in box], [float(p[1]) for p in box]
        x0, x1, n = min(xs), max(xs), max(len(text), 1)
        for m in NUM.finditer(text):
            toks.append({"t": m.group(0), "x": x0 + (x1 - x0) * (m.start() + m.end()) / 2 / n,
                         "y": sum(ys) / 4})
    return toks


def _norm(s):
    return s.replace(" ", "")


def read_pages(pdf_bytes):
    """Raw readings of both engines for every page (this is the slow part, so it is cached)."""
    from PIL import Image
    pages = []
    with _LOCK, tempfile.TemporaryDirectory() as d:
        for img in _pages(pdf_bytes, d):
            pages.append({"width": Image.open(img).size[0], "tesseract": _tesseract(img), "rapid": _rapid(img)})
    return pages


def detect_dec(pages):
    toks = [w["t"] for pg in pages for w in pg["tesseract"]]
    toks = [t for t in toks if not _AMBIGUOUS.fullmatch(t)]
    return max((",", "."), key=lambda d: sum(bool(AMOUNT[d].fullmatch(t)) for t in toks))


def ocr_rows(pages, dec=None):
    """Rows [{pagina, grupo, concepto, unidad, valores}] rebuilt from Tesseract's layout, keeping only
    amounts that RapidOCR read identically at the same spot. Labels come from Tesseract and may have
    typos; grupo is the closest heading above the row that starts at (or left of) the row's column."""
    dec = dec or detect_dec(pages)
    rows = []
    for pi, pg in enumerate(pages, 1):
        width, tw, rw = pg["width"], pg["tesseract"], pg["rapid"]

        def confirmed(w):
            cx = (w["x0"] + w["x1"]) / 2
            return AMOUNT[dec].fullmatch(w["t"]) is not None and any(
                _norm(r["t"]) == _norm(w["t"]) and abs(r["x"] - cx) < TOL * width
                and abs(r["y"] - w["y"]) < max(w["h"], 20) for r in rw)

        heads = []  # (x0, is_section, text), in reading order
        colheads = []  # [(x_center, text), ...] of header lines such as "Cargo fijo  Tarifa plena"

        def columns(xs):
            if not xs:
                return None
            for hdr in reversed(colheads):
                if not hdr or min(abs(x - hx) for x in xs for hx, _ in hdr) > 0.04 * width:
                    continue
                out = []
                for x in xs:
                    hx, ht = min(hdr, key=lambda h: abs(h[0] - x))
                    out.append(ht if abs(hx - x) < 0.04 * width else None)
                if len(out) >= 2 and all(out) and len(set(out)) == len(out):
                    return out
                return None
            return None

        def context(x0):
            near = [h for h in heads if h[0] <= x0 + 0.02 * width and x0 - h[0] < 0.25 * width]
            if not near:
                return None
            sec = [h for h in near if h[1]]
            sec = max(sec, key=lambda h: h[0]) if sec else None
            sub = [h for h in near if not h[1] and (sec is None or heads.index(h) > heads.index(sec))]
            sub = max(sub, key=lambda h: h[0]) if sub else None
            return " · ".join(h[2] for h in (sec, sub) if h) or None
        lines = {}
        for w in tw:
            lines.setdefault(tuple(w["line"]), []).append(w)
        for key in sorted(lines, key=lambda k: min(w["y"] for w in lines[k])):
            ws = sorted(lines[key], key=lambda w: w["x0"])
            segs, cur = [], [ws[0]]
            for a, b in zip(ws, ws[1:]):
                if b["x0"] - a["x1"] > 0.03 * width:
                    segs.append(cur)
                    cur = []
                cur.append(b)
            segs.append(cur)
            row, done = None, []
            labels = [" ".join(w["t"] for w in sg) for sg in segs]
            if len(segs) >= 3 and all(len(t) <= 25 and not NUM.search(t.replace("T", "")) or re.fullmatch(r"T\d\w*", t)
                                      for t in labels[1:]):
                hdr = [((sg[0]["x0"] + sg[-1]["x1"]) / 2, t) for sg, t in zip(segs[1:], labels[1:])
                       if not UNIT.match(t) and not re.fullmatch(r"(?i)unidad|un\.?", t)]
                wordy = [h for h in hdr if re.fullmatch(r"[A-Za-zÁÉÍÓÚáéíóúÑñ][A-Za-zÁÉÍÓÚáéíóúÑñ.\s/]{2,}", h[1])
                         or re.fullmatch(r"T\d[A-Z]{1,3}", h[1])]
                if len(wordy) >= 2 and len(wordy) == len(hdr):
                    colheads.append(hdr)
            for seg in segs:
                text = re.sub(r"\s+", " ", " ".join(w["t"] for w in seg)).strip()
                numeric = all(NUM.fullmatch(w["t"].strip("$")) or w["t"] in ("$", "-") for w in seg)
                if not numeric and row is not None and UNIT.match(text):
                    row["unidad"] = text
                    continue
                if not numeric:
                    if row is not None:
                        done.append(row)
                    row = {"pagina": pi, "x0": seg[0]["x0"], "concepto": text, "unidad": None, "valores": []}
                    continue
                if row is not None:
                    nums = [w for w in seg if NUM.fullmatch(w["t"])]
                    row["valores"] += [parse_num(w["t"], dec) if confirmed(w) else None for w in nums]
                    row.setdefault("_xs", []).extend((w["x0"] + w["x1"]) / 2 for w in nums)
            if row is not None:
                done.append(row)
            for r in done:
                x0 = r.pop("x0")
                if not r["valores"]:
                    r.pop("_xs", None)
                    if re.match(r"^T\s?\d|^Tarifa", r["concepto"]):
                        same = [h for h in heads if abs(h[0] - x0) < 0.05 * width]
                        for h in same:
                            heads.remove(h)
                        heads.append((x0, True, r["concepto"]))
                    elif len(r["concepto"]) > 15:
                        for h in [h for h in heads if not h[1] and abs(h[0] - x0) < 0.05 * width]:
                            heads.remove(h)
                        heads.append((x0, False, r["concepto"]))
                    continue
                r["grupo"] = context(x0)
                r["columnas"] = columns(r.pop("_xs", [])) if r["valores"] else None
                if any(v is not None for v in r["valores"]):
                    rows.append(r)
    return rows
