r"""Shared functions of the library-metadata scripts: the helper, text matching, PDF text, and the record lookups
(arXiv, CrossRef, DataCite, OpenAlex).

Created using: $\text {Created using: }\ claude-opus-5-5-\text{v}5.5-\text {date: }231126$

Inputs:  none of its own; imported by lookup.py, apply.py, add.py and ocr_pdf.py.
Outputs: functions only. Network calls use the standard library (urllib) with a generic User-Agent and no e-mail
         address. OpenAlex: the key in the environment variable OPENALEX_API_KEY is sent as an Authorization header
         when set (never as a URL parameter); no mailto. CrossRef, DataCite and arXiv: no key.
Method:  record_for_doi looks a DOI up widely, in this order: arXiv (for a 10.48550/arXiv. DOI), CrossRef, DataCite,
         OpenAlex. Each record carries 'source' (the service that gave it) and 'record_type'. Text fields are cleaned
         once, here (tags stripped, white space collapsed); a DOI is never cleaned, only stripped of white space.
         norm_doi gives the form used to compare DOIs (no https://doi.org/ or doi: prefix, lower case); it is never
         written to the library.
PDF text: pymupdf when importable, else pypdf; an OCR text file (from ocr_pdf.py) is added when the text layer is short.
Version: see VERSION; `--version` prints it (the module is otherwise not run by hand).
"""
import difflib
import importlib.util
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

VERSION = "1.1"
USER_AGENT = "library-metadata/1.1"
SHORT_TEXT = 500            # characters of text below which a PDF counts as having no text layer
TITLE_COVER = 0.7           # share of title words (four letters or more) that must be on the first pages
RECORD_SIMILARITY = 0.85    # title similarity for accepting a record against a recorded title
# record types written as a journal article or a book chapter without a check by hand
TEXT_TYPES = {"journal-article", "book-chapter", "proceedings-article", "article", "preprint", "posted-content",
              "preprint (arxiv)", "journalarticle", "text", "report", "book-section"}   # lower case
FLAG_TYPES = ("comment", "peer-review", "posted-content")


def load_helper():
    """The shared helper endnote_lib.py, found from this file: <repo or claude folder>/scripts/endnote_lib.py."""
    path = Path(__file__).resolve().parents[3] / "scripts" / "endnote_lib.py"
    if not path.is_file():
        raise SystemExit(f"The shared helper is missing: {path}. Deploy the Agent-docs scripts first.")
    spec = importlib.util.spec_from_file_location("endnote_lib", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------- text and identifiers ----------

def norm(s):
    s = re.sub("[‐-―−]", " ", s or "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s).split())


def words(s, n=4):
    return [w for w in norm(s).split() if len(w) >= n]


def clean(s):
    """Strip HTML tags and collapse white space (for titles and names; never for a DOI)."""
    return " ".join(re.sub(r"<[^>]+>", "", str(s or "")).split())


def doi_text(doi):
    """A DOI as given, without white space or a resolver prefix; case and every other character kept."""
    return re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", str(doi or "").strip(), flags=re.I).strip()


def norm_doi(doi):
    """The form used to compare two DOIs (DOIs are not case sensitive). Never written to the library."""
    return doi_text(doi).lower()


def arxiv_id_from_doi(doi):
    m = re.fullmatch(r"10\.48550/arxiv\.(.+)", norm_doi(doi))
    return m.group(1) if m else None


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


def needs_type_check(record_type):
    """True when the record type is not one that is written as an article or a chapter without a check by hand."""
    rt = (record_type or "").lower()
    return any(k in rt for k in FLAG_TYPES) or rt not in TEXT_TYPES


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


def _quoted(doi):
    return urllib.parse.quote(doi_text(doi), safe="/:()")


def _openalex_headers():
    return {"Authorization": "Bearer " + os.environ["OPENALEX_API_KEY"]} if os.environ.get("OPENALEX_API_KEY") else {}


def crossref(doi):
    """The CrossRef record of a DOI, or None. Not found is not proof that the DOI is wrong (DOIs from other agencies)."""
    status, body = http_get("https://api.crossref.org/works/" + _quoted(doi))
    time.sleep(0.3)
    return json.loads(body)["message"] if status == 200 else None


def datacite(doi):
    """The DataCite record (attributes) of a DOI, or None (arXiv, Zenodo, PANGAEA and other DataCite DOIs)."""
    status, body = http_get("https://api.datacite.org/dois/" + _quoted(doi))
    time.sleep(0.3)
    return json.loads(body)["data"]["attributes"] if status == 200 else None


def openalex_work(doi):
    """The OpenAlex work of a DOI, or None."""
    status, body = http_get("https://api.openalex.org/works/doi:" + _quoted(doi), headers=_openalex_headers())
    time.sleep(0.3)
    if status == 429:
        raise RuntimeError("OpenAlex rate limit (429)")
    return json.loads(body) if status == 200 else None


def openalex(query, year0, year1):
    status, body = http_get("https://api.openalex.org/works", headers=_openalex_headers(), params={
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
            "electronic_resource_number": f"10.48550/arXiv.{aid}", "publisher": "", "record_type": "preprint (arXiv)",
            "source": "arXiv"}


# ---------- records to EndNote fields ----------

def record_year(m):
    for k in ("issued", "published-print", "published-online", "created"):
        y = (m.get(k, {}).get("date-parts") or [[None]])[0][0]
        if y:
            return str(y)
    return ""


def fields_from_crossref(m):
    """EndNote fields from a CrossRef record; record_type is the CrossRef type and source 'CrossRef' (not written)."""
    au = [" ".join(f"{a.get('family', '')}, {a.get('given', '')}".strip(", ").split()) for a in m.get("author", [])]
    chapter = m.get("type") == "book-chapter"
    title = clean((m.get("title") or [""])[0])
    if chapter:
        title = re.sub(r"^\d+\s+(?=[A-Z])", "", title)
    return {"author": "\r".join(a for a in au if a), "year": record_year(m), "title": title,
            "secondary_title": clean((m.get("container-title") or [""])[-1 if chapter else 0]),
            "volume": clean(m.get("volume", "")), "number": clean(m.get("issue", "")),
            "pages": clean(m.get("page", "") or m.get("article-number", "")), "publisher": clean(m.get("publisher", "")),
            "electronic_resource_number": doi_text(m.get("DOI", "")), "record_type": m.get("type", ""), "source": "CrossRef"}


def fields_from_datacite(a):
    """EndNote fields from DataCite attributes; record_type 'datacite:<resourceTypeGeneral>'."""
    au = []
    for c in a.get("creators", []):
        if c.get("familyName"):
            au.append(" ".join(f"{c['familyName']}, {c.get('givenName', '')}".strip(", ").split()))
        elif c.get("name"):
            au.append(clean(c["name"]))
    cont = a.get("container") or {}
    rtype = (a.get("types") or {}).get("resourceTypeGeneral", "")
    return {"author": "\r".join(au), "year": str(a.get("publicationYear") or ""),
            "title": clean(((a.get("titles") or [{}])[0]).get("title", "")),
            "secondary_title": clean(cont.get("title", "")), "volume": clean(cont.get("volume", "")),
            "number": clean(cont.get("issue", "")), "pages": "", "publisher": clean(a.get("publisher", "") if isinstance(a.get("publisher"), str) else (a.get("publisher") or {}).get("name", "")),
            "electronic_resource_number": doi_text(a.get("doi", "")),
            "record_type": "journalarticle" if rtype.lower() == "journalarticle" else (rtype.lower() or "unknown"),
            "source": "DataCite"}


def fields_from_openalex(w):
    """EndNote fields from an OpenAlex work; record_type is the OpenAlex type."""
    au = []
    for x in w.get("authorships", []):
        name = clean((x.get("author") or {}).get("display_name", ""))
        parts = name.split()
        if parts:
            au.append(f"{parts[-1]}, {' '.join(parts[:-1])}".strip(", "))
    src = ((w.get("primary_location") or {}).get("source") or {})
    b = w.get("biblio") or {}
    pages = "-".join(p for p in (b.get("first_page"), b.get("last_page")) if p)
    return {"author": "\r".join(au), "year": str(w.get("publication_year") or ""), "title": clean(w.get("title") or ""),
            "secondary_title": clean(src.get("display_name", "")), "volume": clean(b.get("volume") or ""),
            "number": clean(b.get("issue") or ""), "pages": clean(pages), "publisher": "",
            "electronic_resource_number": doi_text(w.get("doi") or ""), "record_type": (w.get("type") or "unknown").lower(),
            "source": "OpenAlex"}


def record_for_doi(doi):
    """(fields or None, services searched): arXiv for an arXiv DOI, then CrossRef, DataCite and OpenAlex."""
    searched = []
    aid = arxiv_id_from_doi(doi)
    if aid:
        searched.append("arXiv by DOI")
        g = arxiv(aid)
        if g:
            return g, searched
    searched.append("CrossRef by DOI")
    m = crossref(doi)
    if m:
        return fields_from_crossref(m), searched
    searched.append("DataCite by DOI")
    a = datacite(doi)
    if a:
        return fields_from_datacite(a), searched
    searched.append("OpenAlex by DOI")
    w = openalex_work(doi)
    if w:
        return fields_from_openalex(w), searched
    return None, searched


def entry_type(record_type, types):
    """The entry type integer for a record type, from the types file of the library (keys journal-article, book-chapter)."""
    key = "book-chapter" if record_type in ("book-chapter", "book-section") else "journal-article"
    if key not in types:
        raise SystemExit(f"The types file has no '{key}': derive it with endnote_lib.py types and add it with its evidence.")
    return int(types[key])


def read_types(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


if __name__ == "__main__":
    if sys.argv[1:] == ["--version"]:
        print(f"libmeta.py {VERSION}")
        sys.exit(0)
    print("libmeta.py is imported by the other library-metadata scripts; it is not run by hand.")
    sys.exit(2)
