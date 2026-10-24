import io
import re
import subprocess
import tempfile
import unicodedata
import zipfile
from urllib.parse import urljoin

import requests
import urllib3

urllib3.disable_warnings()

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept-Language": "es-AR,es;q=0.9"})

MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
         "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
         "noviembre": 11, "diciembre": 12}


def fetch(url, timeout=40):
    last = None
    for verify in (True, False):
        try:
            r = SESSION.get(url, timeout=timeout, verify=verify, allow_redirects=True)
            r.raise_for_status()
            return r
        except requests.exceptions.SSLError as e:
            last = e
            continue
        except Exception as e:
            last = e
            break
    raise last


def links(html, base):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("blank:#"):
            href = href[len("blank:#"):]
        out.append((a.get_text(" ", strip=True), urljoin(base, href)))
    return out


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm(s):
    return re.sub(r"\s+", " ", strip_accents(s).lower()).strip()


def parse_num(s, dec=None):
    """Parse '1.882,6359', '1,812.81', '7562,923', '$ 35.180,3356', '-87,9650'.
    `dec` is the document's decimal separator; it resolves '29.710' style ambiguity."""
    s = str(s).strip().replace("$", "").replace(" ", "")
    if not s or s in {"-", "—"}:
        return None
    neg = s.startswith("-")
    s = s.lstrip("-")
    if not re.fullmatch(r"[\d.,]+", s):
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".") if (dec == "," or (dec is None and s.count(",") == 1)) else s.replace(",", "")
    elif "." in s:
        if dec == "," or s.count(".") > 1:
            s = s.replace(".", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def pdf_text(data):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(data)
        f.flush()
        res = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True)
    return res.stdout.decode("utf-8", errors="replace")


def xlsx_sheets(data):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    sheets = []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = ["" if v is None else (f"{v:.6f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)).strip()
                     for v in row]
            while cells and cells[-1] == "":
                cells.pop()
            if any(cells):
                rows.append(cells)
        sheets.append({"nombre": ws.title, "filas": rows})
    return sheets


def sheets_to_text(sheets):
    out = []
    for sh in sheets:
        out.append(f"=== Hoja: {sh['nombre']} ===")
        for r in sh["filas"]:
            out.append(" | ".join(r))
    return "\n".join(out)


def detect_kind(url, content, ctype=""):
    if content[:4] == b"%PDF":
        return "pdf"
    if content[:2] == b"PK":
        try:
            names = zipfile.ZipFile(io.BytesIO(content)).namelist()
        except zipfile.BadZipFile:
            return "unknown"
        if any(n.startswith("xl/") for n in names):
            return "xlsx"
        return "zip"
    if b"<html" in content[:2000].lower() or "html" in ctype:
        return "html"
    return "unknown"


def document_text(content, url="", ctype=""):
    """Return (kind, text, extra) for a downloaded document."""
    kind = detect_kind(url, content, ctype)
    if kind == "pdf":
        return kind, pdf_text(content), None
    if kind == "xlsx":
        sh = xlsx_sheets(content)
        return kind, sheets_to_text(sh), sh
    if kind == "zip":
        z = zipfile.ZipFile(io.BytesIO(content))
        texts, sheets = [], []
        for n in z.namelist():
            d = z.read(n)
            k, t, extra = document_text(d, n)
            if k in ("pdf", "xlsx"):
                texts.append(f"##### Archivo: {n}\n{t}")
                if extra:
                    sheets.extend(extra)
        return "zip", "\n".join(texts), sheets or None
    if kind == "html":
        return kind, content.decode("utf-8", errors="replace"), None
    return kind, "", None
