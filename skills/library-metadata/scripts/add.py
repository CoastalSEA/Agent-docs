r"""Add papers to a project EndNote library from a list of DOIs, with or without a PDF, through the shared helper.

Created using: $\text {Created using: }\ claude-opus-5-5-\text{v}5.5-\text {date: }211126$

Usage: add.py --lib <library .enl> --list F --types F --log <folder> [--root <project root>]
       add.py --version
  --list F   CSV with columns doi, and optional: record (an id of the caller's records), title (the title recorded
             for the paper), pdf (url:<address> | file:<path>), linked (yes when the file is linked to this paper in
             another library), year_fallback (with its source in note), note (written to the notes field)
  --types F  JSON of the library's entry types (see apply.py)
  --log      folder for changes.csv (helper) and added.csv (this script)
Inputs:  the list; CrossRef (record of each DOI; DOIs are sent off the machine: the caller asks first); the PDFs
         (an open-access address, downloaded to a temporary folder, or a local file such as the linked file of an
         independent library, which is only read and copied); the library.
Outputs: the new entries and their PDFs in the library (through endnote_lib.py, with its backup and guards);
         added.csv in --log (per row: new id or empty, record, DOI, title, PDF source, check or reason).
Method:  a row is skipped and logged when CrossRef has no record, when a recorded title is less than 85 percent
         similar to the CrossRef title, or when the library already holds the paper (same DOI or same title, entries
         in the trash included: a match there is reported, because adding the paper would make a duplicate again; a DOI
         already held is found before CrossRef is called).
         A PDF must show the first author's surname and 70 percent of the title words on its first four pages. A PDF
         without a text layer is accepted only when linked=yes (it is linked to this paper in the other library),
         and the log says so. A book chapter takes the book-chapter type and the book title. A record without a year
         takes year_fallback only when given, and the log names its source.
Exit:    0 on success; 1 when the helper refuses (for example a locked library); 2 for unusable input.
Version: see VERSION.
"""
import argparse
import csv
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import libmeta as lm  # noqa: E402

VERSION = "1.0"


def fetch_pdf(src, dest):
    """(path or None, origin or reason)."""
    if src.startswith("url:"):
        status, body = lm.http_get(src[4:], timeout=180)
        if status != 200 or not body.startswith(b"%PDF"):
            return None, f"download failed ({status})"
        dest.write_bytes(body)
        return dest, "open-access address"
    if src.startswith("file:"):
        p = Path(src[5:])
        if not p.is_file():
            return None, f"file not found: {p}"
        shutil.copyfile(p, dest)
        return dest, "local file (read only, copied)"
    return None, f"unknown PDF source {src!r} (use url: or file:)"


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(prog="add.py")
    ap.add_argument("--version", action="version", version=f"add.py {VERSION}")
    ap.add_argument("--root", default=".")
    ap.add_argument("--lib", required=True)
    ap.add_argument("--list", required=True)
    ap.add_argument("--types", required=True)
    ap.add_argument("--log", required=True)
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    lib = Path(a.lib) if Path(a.lib).is_absolute() else root / a.lib
    log = Path(a.log) if Path(a.log).is_absolute() else root / a.log
    el = lm.load_helper()
    types = lm.read_types(a.types)
    with open(a.list, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    try:
        el.guard(lib, root)
        refs = el.read_refs(lib, include_trash=True)
    except el.LibraryError as e:
        print(f"Refused: {e}", file=sys.stderr)
        return 1
    ordered = sorted(refs, key=lambda r: -r["trash_state"])     # active entries last, so that they are the ones reported
    have_doi = {r["electronic_resource_number"].strip().lower(): r for r in ordered if r["electronic_resource_number"].strip()}
    have_title = {lm.norm(r["title"]): r for r in ordered if r["title"].strip()}
    out = []
    for row in rows:
        doi = row.get("doi", "").strip()
        rec = row.get("record", "")
        held = have_doi.get(doi.lower()) if doi else None
        if held:                                   # checked before CrossRef, so nothing is sent for a paper already held
            where = "in the trash" if held["trash_state"] else "active"
            out.append(["", rec, doi, row.get("title", ""), "", f"already in the library as entry {held['id']} ({where}): not added"])
            continue
        m = lm.crossref(doi) if doi else None
        if m is None:
            out.append(["", rec, doi, row.get("title", ""), "", "CrossRef has no record of the DOI: not added"])
            continue
        f = lm.fields_from_crossref(m)
        if row.get("title") and lm.similarity(f["title"], row["title"]) < lm.RECORD_SIMILARITY:
            out.append(["", rec, doi, f["title"], "", f"title similarity {lm.similarity(f['title'], row['title']):.2f} with the recorded title: not added"])
            continue
        dup = have_doi.get(f["electronic_resource_number"].lower()) or have_doi.get(doi.lower()) or have_title.get(lm.norm(f["title"]))
        if dup:
            where = "in the trash" if dup["trash_state"] else "active"
            out.append(["", rec, doi, f["title"], "", f"already in the library as entry {dup['id']} ({where}): not added"])
            continue
        if not f["year"]:
            if row.get("year_fallback"):
                f["year"] = row["year_fallback"].strip()
            else:
                out.append(["", rec, doi, f["title"], "", "CrossRef gives no year and no year_fallback: not added"])
                continue
        fields = {k: v for k, v in f.items() if k != "record_type" and v}
        fields["reference_type"] = lm.entry_type(f["record_type"], types)
        if row.get("note"):
            fields["notes"] = row["note"].strip()
        check, origin = "no PDF", ""
        try:
            with tempfile.TemporaryDirectory() as tmp:
                pdf = None
                if row.get("pdf", "").strip():
                    stem = (lm.first_surname(f["author"]).capitalize() + f["year"] + "_" + "-".join(lm.norm(f["title"]).split()[:8]))[:46]
                    pdf, origin = fetch_pdf(row["pdf"].strip(), Path(tmp) / (stem + ".pdf"))
                    if pdf is None:
                        out.append(["", rec, doi, f["title"], "", origin + ": not added"])
                        continue
                    text = lm.pdf_text(pdf)
                    if not lm.has_text_layer(text):
                        if row.get("linked", "").strip().lower() != "yes":
                            out.append(["", rec, doi, f["title"], origin, "no text layer and not linked to this paper in another library: not added"])
                            continue
                        check = "no text layer; accepted: linked to this paper in another library"
                    else:
                        ok, evidence, why = lm.check_pdf(text, f)
                        if not ok:
                            out.append(["", rec, doi, f["title"], origin, "PDF does not match the record (" + "; ".join(why) + "): not added"])
                            continue
                        check = evidence
                if row.get("year_fallback") and not lm.record_year(m):
                    check += f"; year from year_fallback ({row.get('note', 'source not given')})"
                source = f"CrossRef {doi}" + (f"; PDF from {origin}" if origin else "") + f"; {check}"
                new_id = el.add_reference(lib, root, fields, pdf_path=pdf, log_dir=log, source=source)
        except el.LibraryError as e:
            print(f"Refused: {e}", file=sys.stderr)
            out.append(["", rec, doi, f["title"], origin, f"refused by the helper: {e}"])
            break
        have_doi[f["electronic_resource_number"].lower()] = {"id": new_id, "trash_state": 0}
        have_title[lm.norm(f["title"])] = {"id": new_id, "trash_state": 0}
        out.append([new_id, rec, doi, f["title"], origin, check])
        print("added", new_id, doi, f["title"][:60], flush=True)
    log.mkdir(parents=True, exist_ok=True)
    f_out = log / "added.csv"
    new = not f_out.exists()
    with open(f_out, "a", newline="", encoding="utf-8-sig" if new else "utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["new_id", "record", "doi", "title", "pdf_source", "check_or_reason"])
        w.writerows(out)
    added = sum(1 for r in out if r[0] != "")
    print(f"added: {added}; not added: {len(out) - added}; log: {f_out}")
    return 1 if any(str(r[5]).startswith("refused by the helper") for r in out) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
