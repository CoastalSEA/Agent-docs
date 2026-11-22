r"""Shared functions of the library-metadata scripts: the helper, text matching, PDF text, CrossRef, OpenAlex, arXiv.

Created using: $\text {Created using: }\ claude-opus-5-5-\text{v}5.5-\text {date: }211126$

Inputs:  none of its own; imported by lookup.py, apply.py, add.py and ocr_pdf.py.
Outputs: functions only. Network calls use the standard library (urllib) with a generic User-Agent and no e-mail
         address. OpenAlex: the key in the environment variable OPENALEX_API_KEY is sent as an Authorization header
         when set (never as a URL parameter); no mailto. CrossRef and arXiv: no key.
PDF text: pymupdf when importable, else pypdf; an OCR text file (from ocr_pdf.py) is added when the text layer is short.
Version: see VERSION.
"""
import difflib
import importlib.util
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

VERSION = "1.0"
USER_AGENT = "library-metadata/1.0"
SHORT_TEXT = 500            # characters of text below which a PDF counts as having no text layer
TITLE_COVER = 0.7           # share of title words (four letters or more) that must be on the first pages
RECORD_SIMILARITY = 0.85    # title similarity for accepting a CrossRef record against a recorded title


def load_helper():
    """The shared helper endnote_lib.py, found from this file: <repo or claude folder>/scripts/endnote_lib.py."""
    path = Path(__file__).resolve().parents[3] / "scripts" / "endnote_lib.py"
    if not path.is_file():
        raise SystemExit(f"The shared helper is missing: {path}. Deploy the Agent-docs scripts first.")
    spec = importlib.util.spec_from_file_location("endnote_lib", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------- text ----------

def norm(s):
    s = re.sub("[‐-―−]", " ", s or "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s).split())


def words(s, n=4):
    return [w for w in norm(s).split() if len(w) >= n]


def clean(s):
    """Strip HTML tags and collapse white space (CrossRef titles hold line breaks and <sub> tags)."""
    return " ".join(re.sub(r"<[^>]+>", "", str(s or "")).split())


def similarity(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def first_surname(authors):
    first = (authors or "").split("\r")[0].split(",")[0]
    return norm(first).split()[-1] if norm(first) else ""


def check_pdf(text, fields, year_window=None):
    """(verified, evidence, reasons): the first author's surname and TITLE_COVER of the title words on the pages read,
    and the record year within year_window (y0, y1) when given."""
    t = norm(text)
    sur = first_surname(fields.get("author", ""))
    tw = words(fields.get("title", ""))
    cover = sum(1 for w in tw if w in t) / max(len(tw), 1)
    ok_author = bool(sur) and (sur in t or sur in t.replace(" ", ""))
    reasons = []
    if not ok_author:
        reasons.append("first author not found on the pages read")
    if cover < TITLE_COVER:
        reasons.append("title words not found on the pages read")
    year = str(fields.get("year", ""))
    if year_window:
        if not (year.isdigit() and year_window[0] <= int(year) <= year_window[1]):
            reasons.append("record year outside the window")
    evidence = f"first author {sur or '-'}; title words on the pages read {cover:.2f}; record year {year or '-'}"
    return not reasons, evidence, reasons


# ---------- PDF ----------

def pdf_text(path, pages=4, ocr_file=None):
    """Text of the first pages of a PDF, plus the OCR text file when the text layer is short."""
    text = ""
    if importlib.util.find_spec("pymupdf"):
        import pymupdf
        d = pymupdf.open(path)
        try:
            text = "\n".join(d[i].get_text() for i in range(min(pages, len(d)))) + "\n" + (d.metadata.get("author") or "")
        finally:
            d.close()
    elif importlib.util.find_spec("pypdf"):
        from pypdf import PdfReader
        r = PdfReader(str(path))
        text = "\n".join((p.extract_text() or "") for p in r.pages[:pages])
    else:
        raise SystemExit("Reading a PDF needs pymupdf or pypdf in this interpreter.")
    if len(text.strip()) < SHORT_TEXT and ocr_file and Path(ocr_file).is_file():
        text += "\n" + Path(ocr_file).read_text(encoding="utf-8")
    return text


def has_text_layer(text):
    return len(norm(text)) >= SHORT_TEXT


# ---------- network ----------

def http_get(url, params=None, headers=None, timeout=60):
    """(status, bytes). A 404 or other HTTP error returns its status, not an exception."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def crossref(doi):
    """The CrossRef record of a DOI, or None. Not found is not proof that the DOI is wrong (DOIs from other agencies)."""
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", doi.strip(), flags=re.I)
    status, body = http_get("https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="/:()"))
    time.sleep(0.3)
    return json.loads(body)["message"] if status == 200 else None


def openalex(query, year0, year1):
    headers = {"Authorization": "Bearer " + os.environ["OPENALEX_API_KEY"]} if os.environ.get("OPENALEX_API_KEY") else {}
    status, body = http_get("https://api.openalex.org/works", headers=headers, params={
        "search": query, "filter": f"publication_year:{year0}-{year1}", "per-page": 10,
        "select": "id,doi,title,publication_year,type,authorships"})
    time.sleep(0.3)
    if status == 429:
        raise RuntimeError("OpenAlex rate limit (429)")
    return json.loads(body).get("results", []) if status == 200 else []


def arxiv(aid):
    status, body = http_get("http://export.arxiv.org/api/query", params={"id_list": aid})
    time.sleep(3)
    if status != 200:
        return None
    ns = {"a": "http://www.w3.org/2005/Atom"}
    e = ET.fromstring(body).find("a:entry", ns)
    if e is None or e.find("a:title", ns) is None:
        return None
    au = []
    for a in e.findall("a:author", ns):
        nm = a.find("a:name", ns).text.strip().split()
        au.append(f"{nm[-1]}, {' '.join(nm[:-1])}" if len(nm) > 1 else nm[0])
    return {"author": "\r".join(au), "year": e.find("a:published", ns).text[:4], "title": clean(e.find("a:title", ns).text),
            "secondary_title": "arXiv preprint", "volume": "", "number": "", "pages": f"arXiv:{aid}",
            "electronic_resource_number": f"10.48550/arXiv.{aid}", "publisher": "", "record_type": "preprint (arXiv)"}


def record_year(m):
    for k in ("issued", "published-print", "published-online", "created"):
        y = (m.get(k, {}).get("date-parts") or [[None]])[0][0]
        if y:
            return str(y)
    return ""


def fields_from_crossref(m):
    """EndNote fields from a CrossRef record; record_type is the CrossRef type (not written)."""
    au = [" ".join(f"{a.get('family', '')}, {a.get('given', '')}".strip(", ").split()) for a in m.get("author", [])]
    chapter = m.get("type") == "book-chapter"
    title = re.sub(r"^\d+\s+(?=[A-Z])", "", clean((m.get("title") or [""])[0])) if chapter else clean((m.get("title") or [""])[0])
    return {"author": "\r".join(a for a in au if a), "year": record_year(m), "title": title,
            "secondary_title": clean((m.get("container-title") or [""])[-1 if chapter else 0]),
            "volume": clean(m.get("volume", "")), "number": clean(m.get("issue", "")),
            "pages": clean(m.get("page", "") or m.get("article-number", "")), "publisher": clean(m.get("publisher", "")),
            "electronic_resource_number": m.get("DOI", ""), "record_type": m.get("type", "")}


def entry_type(record_type, types):
    """The entry type integer for a record type, from the types file of the library (keys journal-article, book-chapter)."""
    key = "book-chapter" if record_type == "book-chapter" else "journal-article"
    if key not in types:
        raise SystemExit(f"The types file has no '{key}': derive it with endnote_lib.py types and add it with its evidence.")
    return int(types[key])


def read_types(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}
