r"""Find verified metadata for entries of a project EndNote library from their linked PDFs. Writes nothing to the library.

Created using: $\text {Created using: }\ claude-opus-5-5-\text{v}5.5-\text {date: }231126$

Usage: lookup.py --lib <library .enl> --out <folder> (--ids 12,15 | --untitled) [--queries F] [--ocr-dir D]
                 [--window -1,7] [--root <project root>]
       lookup.py --version
  --ids        entry ids to look up; --untitled: every active entry whose title is empty or a file name (<...pdf>)
  --queries F  CSV with columns id, query: the title read from the first page of the PDF, for entries whose file
               name or recorded title is wrong
  --ocr-dir D  folder of OCR text files ref<id>.txt made by ocr_pdf.py (default <out>/ocr)
  --window     publication years searched, relative to the entry year (default -1,7, to allow for a preprint)
Inputs:  the library (read only) and the first linked PDF of each entry (first four pages); arXiv, CrossRef, DataCite
         and OpenAlex. Titles and DOIs are sent off the machine: the caller asks first.
Outputs (in --out): proposals.csv (per entry: status, reasons, notes, evidence, the services searched, current and
         proposed fields) and proposals.json (the verified records, read by apply.py).
Method:  an entry with a DOI is looked up by that DOI: arXiv for a 10.48550/arXiv. DOI, then CrossRef, DataCite and
         OpenAlex. When none has it, and for an entry without a DOI, the search text (from --queries, else the recorded
         title, else the words of the file name) gives OpenAlex candidates whose title is at least 85 percent similar,
         published records before arXiv records; each candidate's record is looked up by its DOI the same way, and the
         first whose first author and title words are on the PDF is kept. As a last step an arXiv id printed on the
         PDF is looked up. A record found by title whose DOI differs from the recorded DOI is flagged with both DOIs;
         the recorded DOI is never replaced. Status 'verified' needs the surname of the first author and 70 percent of
         the title words (four letters or more) on the first four pages, and the record year within the window.
         Everything else is 'flag', with the reason, and is not proposed. Records of a type other than an article,
         chapter, report or preprint (a dataset, a book, a comment) are flagged for the entry type to be set by hand.
         An entry is flagged when another active entry holds the same DOI; a copy in the trash gives a note. An arXiv
         year that differs from the recorded year gives a note, because apply.py keeps a recorded year within one year.
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

VERSION = "1.1"
COLUMNS = ["ref_id", "file", "status", "reasons", "notes", "evidence", "searched", "current_year", "current_title",
           "current_doi", "proposed_authors", "proposed_year", "proposed_title", "proposed_journal", "proposed_volume",
           "proposed_issue", "proposed_pages", "proposed_doi", "record_type", "record_source"]


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
            out.append((lm.arxiv_id_from_doi(res["doi"]) is not None or "arxiv" in res["doi"].lower(), -sim, res))
    out.sort(key=lambda x: (x[0], x[1]))
    return [r for _, _, r in out]


def find_record(ref, text, query, window):
    """(record or None, services searched, how found: 'doi' or 'title')."""
    searched = []
    doi = ref.get("electronic_resource_number", "").strip()
    if doi:
        g, s = lm.record_for_doi(doi)
        searched += s
        if g:
            return g, searched, "doi"
    first = None
    y0, y1 = window if window else (1800, 2100)
    searched.append("OpenAlex by title")
    for res in candidates(query, y0, y1):
        g, _ = lm.record_for_doi(res["doi"])
        if g and first is None:
            first = g
        if g and lm.check_pdf(text, g)[0]:
            return g, searched, "title"
    aid = re.search(r"arxiv:\s*(\d{4}\.\d{4,5}|[a-z\-]+/\d{7})", text.lower())
    if aid:
        searched.append("arXiv id on the PDF")
        g = lm.arxiv(aid.group(1))
        if g and (first is None or lm.check_pdf(text, g)[0]):
            return g, searched, "title"
    return first, searched, "title"


def duplicate_reasons(ref, doi, by_doi):
    """(reasons, notes) for other entries holding the same DOI: an active one flags, a trashed one is a note."""
    reasons, notes = [], []
    for other in by_doi.get(lm.norm_doi(doi), []) if doi else []:
        if other["id"] == ref["id"]:
            continue
        if other["trash_state"]:
            notes.append(f"a copy with the same DOI is in the trash (entry {other['id']})")
        else:
            reasons.append(f"active entry {other['id']} holds the same DOI")
    return reasons, notes


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
    all_refs = el.read_refs(lib, include_trash=True)
    by_doi = {}
    for r in all_refs:
        if r["electronic_resource_number"].strip():
            by_doi.setdefault(lm.norm_doi(r["electronic_resource_number"]), []).append(r)
    refs = [r for r in all_refs if not r["trash_state"]]
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
        reasons, notes, evidence, f, searched = [], [], "", None, []
        recorded = ref["electronic_resource_number"].strip()
        r_dup, n_dup = duplicate_reasons(ref, recorded, by_doi)
        reasons += r_dup
        notes += n_dup
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
                    f, searched, how = find_record(ref, text, search_text(ref, queries), window)
                    if f is None:
                        reasons.append("no record found (searched: " + ", ".join(searched) + "): enter by hand")
                    else:
                        ok, evidence, why = lm.check_pdf(text, f, window)
                        reasons += why
                        if lm.needs_type_check(f["record_type"]):
                            reasons.append(f"record type {f['record_type']} ({f['source']}): set the entry type by hand")
                        if recorded and lm.norm_doi(f["electronic_resource_number"]) != lm.norm_doi(recorded):
                            reasons.append(f"the record found by title has DOI {f['electronic_resource_number']}; "
                                           f"the entry holds {recorded}: check by hand (the recorded DOI is not replaced)")
                        if not recorded:
                            r2, n2 = duplicate_reasons(ref, f["electronic_resource_number"], by_doi)
                            reasons += r2
                            notes += n2
                        if f["source"] == "arXiv" and str(ref["year"]).isdigit() and f["year"] != str(ref["year"]):
                            near = abs(int(ref["year"]) - int(f["year"])) <= 1 if f["year"].isdigit() else False
                            notes.append(f"arXiv year {f['year']}, entry year {ref['year']}"
                                         + ("; apply.py keeps the entry year (within one year): check the year" if near else ""))
            except Exception as e:  # network or parsing failure: flag, do not guess
                reasons.append(f"lookup error: {type(e).__name__}: {e}")
        status = "verified" if f and not reasons else "flag"
        if status == "verified":
            props[str(ref["id"])] = {**f, "_evidence": evidence, "_notes": "; ".join(notes)}
        g = f or {}
        rows.append([ref["id"], Path(ref["files"][0]).name if ref["files"] else "", status, "; ".join(reasons),
                     "; ".join(notes), evidence, ", ".join(searched), ref["year"], ref["title"], recorded,
                     g.get("author", "").replace("\r", " | "), g.get("year", ""), g.get("title", ""),
                     g.get("secondary_title", ""), g.get("volume", ""), g.get("number", ""), g.get("pages", ""),
                     g.get("electronic_resource_number", ""), g.get("record_type", ""), g.get("source", "")])
        print(ref["id"], status, "; ".join(reasons), ("| " + "; ".join(notes)) if notes else "", flush=True)
    with open(out / "proposals.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        w.writerows(rows)
    (out / "proposals.json").write_text(json.dumps(props, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"verified: {len(props)}; flagged: {len(rows) - len(props)}; written: {out / 'proposals.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
