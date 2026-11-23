r"""Write the verified records of proposals.json into a project EndNote library, through the shared helper.

Created using: $\text {Created using: }\ claude-opus-5-5-\text{v}5.5-\text {date: }231126$

Usage: apply.py --lib <library .enl> --proposals <folder> --types F --log <folder> [--overrides F] [--root <project root>]
       apply.py --version
  --proposals  folder of proposals.json (lookup.py)
  --types F    JSON of the library's entry types, {"journal-article": <int>, "book-chapter": <int>, "_evidence": "..."},
               derived from `endnote_lib.py types`
  --overrides F JSON {"<id>": {"fields": {...}, "source": "..."}}: values read from the PDF where the record is incomplete
  --log        folder for changes.csv (the helper appends each changed field with its source)
Inputs:  proposals.json, the types file, the library.
Outputs: the changed entries (through endnote_lib.py, with its backup and guards) and the log: one row per changed
         field, and one summary row per entry (action 'check') with the result, so that an entry verified with no
         change is listed too.
Method:  the values of proposals.json are written as lookup.py cleaned them; nothing is cleaned again, so a DOI keeps
         every character (SICI DOIs hold angle brackets). Fields written when not empty: author, year, title, journal
         or book title, volume, issue, pages, publisher, DOI and entry type (book chapter: the book-chapter type and the
         book title; otherwise the journal-article type). The DOI: when the entry holds a DOI equivalent to the
         proposed one (same after removing a https://doi.org/ or doi: prefix, in any case), the recorded form is
         kept and nothing is written; when it holds a different DOI, nothing is written for the entry and it is
         flagged. Guard: if the DOI about to be written differs from the proposed DOI other than in case or prefix,
         nothing is written for that entry and it is flagged. An arXiv record keeps a year already recorded when it
         differs by at most one (the recorded year may be that of the published version); the summary row says so.
         The source of every value (the service, with the evidence of the check) is logged. Unchanged values are not
         written or logged (endnote_lib.py).
Exit:    0 on success; 1 when the helper refuses (for example a locked library); 2 for unusable input.
Version: see VERSION.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import libmeta as lm  # noqa: E402

VERSION = "1.1"
FIELDS = ("author", "year", "title", "secondary_title", "volume", "number", "pages", "publisher", "electronic_resource_number")
DOI = "electronic_resource_number"


def build_updates(props, current, types, overrides):
    """(updates {id: fields}, summary {id: text}, flagged {id: reason})."""
    updates, summary, flagged = {}, {}, {}
    for rid, f in props.items():
        cur = current.get(int(rid))
        if cur is None:
            flagged[int(rid)] = "not an active entry of the library"
            continue
        new = {k: (f.get(k) or "") for k in FIELDS}
        new = {k: (v.strip() if isinstance(v, str) else v) for k, v in new.items()}
        new["reference_type"] = lm.entry_type(f.get("record_type", ""), types)
        notes = [f["_notes"]] if f.get("_notes") else []
        arx = f.get("source") == "arXiv" or "arXiv" in f.get("record_type", "")
        if arx and str(cur["year"]).isdigit() and str(new["year"]).isdigit() and new["year"] != cur["year"] \
                and abs(int(cur["year"]) - int(new["year"])) <= 1:
            notes.append(f"entry year {cur['year']} kept (arXiv year {new['year']}, within one year)")
            new["year"] = cur["year"]
        proposed, recorded = (f.get(DOI) or "").strip(), (cur.get(DOI) or "").strip()
        if recorded and proposed:
            if lm.norm_doi(recorded) == lm.norm_doi(proposed):
                new[DOI] = ""                       # keep the recorded form: nothing to write
            else:
                flagged[int(rid)] = f"the entry holds DOI {recorded}; the proposal has {proposed}: nothing written"
                continue
        if new[DOI] and lm.norm_doi(new[DOI]) != lm.norm_doi(proposed):
            flagged[int(rid)] = f"the DOI to be written ({new[DOI]}) differs from the proposal ({proposed}): nothing written"
            continue
        src = f"{f.get('source') or ('arXiv' if arx else 'CrossRef')}; checked against the PDF: {f.get('_evidence', '')}"
        ov = overrides.get(str(rid), {})
        if ov:
            new.update(ov.get("fields", {}))
            src += f"; {ov.get('source', 'read from the PDF')}"
        fields = {k: v for k, v in new.items() if v not in ("", None)}
        fields["_source"] = src
        updates[int(rid)] = fields
        summary[int(rid)] = "verified" + (f"; {'; '.join(notes)}" if notes else "")
    return updates, summary, flagged


def main(argv):
    ap = argparse.ArgumentParser(prog="apply.py")
    ap.add_argument("--version", action="version", version=f"apply.py {VERSION}")
    ap.add_argument("--root", default=".")
    ap.add_argument("--lib", required=True)
    ap.add_argument("--proposals", required=True)
    ap.add_argument("--types", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--overrides")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    lib = Path(a.lib) if Path(a.lib).is_absolute() else root / a.lib
    log = Path(a.log) if Path(a.log).is_absolute() else root / a.log
    el = lm.load_helper()
    props = json.loads((Path(a.proposals) / "proposals.json").read_text(encoding="utf-8"))
    overrides = json.loads(Path(a.overrides).read_text(encoding="utf-8")) if a.overrides else {}
    types = lm.read_types(a.types)
    try:
        el.guard(lib, root)
        current = {r["id"]: r for r in el.read_refs(lib)}
        updates, summary, flagged = build_updates(props, current, types, overrides)
        sources = {i: f["_source"] for i, f in updates.items()}
        changes = el.update_refs(lib, root, updates, log_dir=log) if updates else []
    except el.LibraryError as e:
        print(f"Refused: {e}", file=sys.stderr)
        return 1
    per_entry = {}
    for c in changes:
        per_entry[c["id"]] = per_entry.get(c["id"], 0) + 1
    rows = [{"action": "check", "id": i, "field": "", "before": "", "after": f"{text}; fields changed: {per_entry.get(i, 0)}",
             "source": sources[i]} for i, text in summary.items()]
    rows += [{"action": "check", "id": i, "field": "", "before": "", "after": f"flagged: {why}", "source": "apply.py"}
             for i, why in flagged.items()]
    el.log_rows(log, lib, rows)
    for i, why in flagged.items():
        print(f"{i} flagged: {why}")
    print(f"entries verified: {len(summary)}; entries changed: {len(per_entry)}; fields changed: {len(changes)}; "
          f"flagged: {len(flagged)}; log: {log / 'changes.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
