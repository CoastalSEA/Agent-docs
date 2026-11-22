r"""Find verified metadata for entries of a project EndNote library from their linked PDFs. Writes nothing to the library.

Created using: $\text {Created using: }\ claude-opus-5-5-\text{v}5.5-\text {date: }211126$

Usage: lookup.py --lib <library .enl> --out <folder> (--ids 12,15 | --untitled) [--queries F] [--ocr-dir D]
                 [--window -1,7] [--root <project root>]
       lookup.py --version
  --ids        entry ids to look up; --untitled: every active entry whose title is empty or a file name (<...pdf>)
  --queries F  CSV with columns id, query: the title read from the first page of the PDF, for entries whose file
               name or recorded title is wrong
  --ocr-dir D  folder of OCR text files ref<id>.txt made by ocr_pdf.py (default <out>/ocr)
  --window     publication years searched, relative to the entry year (default -1,7, to allow for a preprint)
Inputs:  the library (read only) and the first linked PDF of each entry (first four pages); OpenAlex (title search),
         CrossRef (record of a DOI) and arXiv. Titles and DOIs are sent off the machine: the caller asks first.
Outputs (in --out): proposals.csv (per entry: status, reasons, evidence, current and proposed fields) and
         proposals.json (the verified records, read by apply.py).
Method:  an entry with a DOI takes its CrossRef record. Otherwise the search text (from --queries, else the recorded
         title, else the words of the file name) gives OpenAlex candidates whose title is at least 85 percent similar,
         published records before arXiv records; each candidate's CrossRef or arXiv record is taken, and the first
         whose first author and title words are on the PDF is kept. As a last step an arXiv id printed on the PDF is
         looked up. Status 'verified' needs the surname of the first author and 70 percent of the title words (four
         letters or more) on the first four pages, and the record year within the window. Everything else is 'flag',
         with the reason, and is not proposed. Comment, review and posted-content records are flagged for a check
         of the entry type by hand.
Exit:    0 on success; 2 for unusable input.
Version: see VERSION.
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import libmeta as lm  # noqa: E402

VERSION = "1.0"
COLUMNS = ["ref_id", "file", "status", "reasons", "evidence", "current_year", "current_title", "proposed_authors",
           "proposed_year", "proposed_title", "proposed_journal", "proposed_volume", "proposed_issue", "proposed_pages",
           "proposed_doi", "record_type"]


def search_text(ref, queries):
    if str(ref["id"]) in queries:
        return queries[str(ref["id"])]
    if ref["title"] and not re.fullmatch(r"<.*\.pdf>", ref["title"].strip(), flags=re.I):
        return ref["title"]
    stem = Path(ref["files"][0]).stem if ref["files"] else ""
    stem = re.sub(r"^[A-Za-z\-]+?\d{4}_", "", stem)
    return " ".join(w for w in re.split(r"[-_\s]+", stem) if w)


def entry_year(ref):
    if str(ref["year"]).strip().isdigit():
        return int(ref["year"])
    m = re.search(r"(19|20)\d{2}", Path(ref["files"][0]).name) if ref["files"] else None
    return int(m.group(0)) if m else None


def candidates(query, y0, y1):
    out = []
    for res in lm.openalex(query, y0, y1):
        if not res.get("doi"):
            continue
        nt, nq = lm.norm(res.get("title") or ""), lm.norm(query)
        sim = lm.similarity(nt, nq)
        if sim >= lm.RECORD_SIMILARITY or (nt and nq and (nt.startswith(nq) or nq.startswith(nt))):
            out.append((("arxiv" in res["doi"].lower()), -sim, res))
    out.sort(key=lambda x: (x[0], x[1]))
    return [(a, r) for a, _, r in out]


def find_record(ref, text, query, window):
    doi = ref.get("electronic_resource_number", "").strip()
    if doi:
        m = lm.crossref(doi)
        return lm.fields_from_crossref(m) if m else None
    first = None
    y0, y1 = window if window else (1800, 2100)
    for is_arxiv, res in candidates(query, y0, y1):
        d = re.sub(r"^https?://doi\.org/", "", res["doi"])
        if is_arxiv:
            g = lm.arxiv(d.lower().split("arxiv.")[-1])
        else:
            m = lm.crossref(d)
            g = lm.fields_from_crossref(m) if m else None
        if g and first is None:
            first = g
        if g and lm.check_pdf(text, g)[0]:
            return g
    aid = re.search(r"arxiv:\s*(\d{4}\.\d{4,5}|[a-z\-]+/\d{7})", text.lower())
    if aid:
        g = lm.arxiv(aid.group(1))
        if g and (first is None or lm.check_pdf(text, g)[0]):
            return g
    return first


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(prog="lookup.py")
    ap.add_argument("--version", action="version", version=f"lookup.py {VERSION}")
    ap.add_argument("--root", default=".")
    ap.add_argument("--lib", required=True)
    ap.add_argument("--out", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ids")
    g.add_argument("--untitled", action="store_true")
    ap.add_argument("--queries")
    ap.add_argument("--ocr-dir")
    ap.add_argument("--window", default="-1,7")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    lib = Path(a.lib) if Path(a.lib).is_absolute() else root / a.lib
    out = Path(a.out) if Path(a.out).is_absolute() else root / a.out
    el = lm.load_helper()
    if not lib.is_file():
        print(f"No library {lib}", file=sys.stderr)
        return 2
    lo, hi = (int(x) for x in a.window.split(","))
    queries = {}
    if a.queries:
        with open(a.queries, encoding="utf-8-sig") as fh:
            queries = {r["id"].strip(): r["query"].strip() for r in csv.DictReader(fh)}
    refs = el.read_refs(lib)
    if a.untitled:
        sel = [r for r in refs if not r["title"].strip() or re.fullmatch(r"<.*\.pdf>", r["title"].strip(), flags=re.I)]
    else:
        ids = {int(x) for x in a.ids.split(",") if x.strip()}
        sel = [r for r in refs if r["id"] in ids]
        missing = ids - {r["id"] for r in sel}
        if missing:
            print(f"Not active entries of the library: {sorted(missing)}", file=sys.stderr)
    _, data, _ = el.paths(lib)
    ocr_dir = Path(a.ocr_dir) if a.ocr_dir else out / "ocr"
    out.mkdir(parents=True, exist_ok=True)
    rows, props = [], {}
    for ref in sel:
        reasons, evidence, f = [], "", None
        if not ref["files"]:
            reasons.append("no linked PDF: cannot be checked against the paper")
        else:
            try:
                text = lm.pdf_text(data / "PDF" / ref["files"][0], ocr_file=ocr_dir / f"ref{ref['id']}.txt")
                if not lm.has_text_layer(text):
                    reasons.append("no text layer and no OCR text: run ocr_pdf.py")
                else:
                    y = entry_year(ref)
                    window = (y + lo, y + hi) if y else None
                    f = find_record(ref, text, search_text(ref, queries), window)
                    if f is None:
                        reasons.append("no record found in CrossRef, OpenAlex or arXiv: enter by hand")
                    else:
                        ok, evidence, why = lm.check_pdf(text, f, window)
                        reasons += why
                        if any(k in f["record_type"] for k in ("comment", "peer-review", "posted-content")):
                            reasons.append(f"record type {f['record_type']}: check the entry type by hand")
            except Exception as e:  # network or parsing failure: flag, do not guess
                reasons.append(f"lookup error: {type(e).__name__}: {e}")
        status = "verified" if f and not reasons else "flag"
        if status == "verified":
            props[str(ref["id"])] = {**f, "_evidence": evidence}
        g = f or {}
        rows.append([ref["id"], Path(ref["files"][0]).name if ref["files"] else "", status, "; ".join(reasons), evidence,
                     ref["year"], ref["title"], g.get("author", "").replace("\r", " | "), g.get("year", ""), g.get("title", ""),
                     g.get("secondary_title", ""), g.get("volume", ""), g.get("number", ""), g.get("pages", ""),
                     g.get("electronic_resource_number", ""), g.get("record_type", "")])
        print(ref["id"], status, "; ".join(reasons), flush=True)
    with open(out / "proposals.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        w.writerows(rows)
    (out / "proposals.json").write_text(json.dumps(props, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"verified: {len(props)}; flagged: {len(rows) - len(props)}; written: {out / 'proposals.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
