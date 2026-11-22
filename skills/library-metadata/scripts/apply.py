r"""Write the verified records of proposals.json into a project EndNote library, through the shared helper.

Created using: $\text {Created using: }\ claude-opus-5-5-\text{v}5.5-\text {date: }211126$

Usage: apply.py --lib <library .enl> --proposals <folder> --types F --log <folder> [--overrides F] [--root <project root>]
       apply.py --version
  --proposals  folder of proposals.json (lookup.py)
  --types F    JSON of the library's entry types, {"journal-article": <int>, "book-chapter": <int>, "_evidence": "..."},
               derived from `endnote_lib.py types`
  --overrides F JSON {"<id>": {"fields": {...}, "source": "..."}}: values read from the PDF where CrossRef is incomplete
  --log        folder for changes.csv (the helper appends each change with its source)
Inputs:  proposals.json, the types file, the library.
Outputs: the changed entries (through endnote_lib.py, with its backup and guards) and the change log.
Method:  fields written when not empty: author, year, title, journal or book title, volume, issue, pages, publisher,
         DOI and entry type (book chapter: the book-chapter type and the book title; otherwise the journal-article type).
         An arXiv record keeps a year already recorded when it differs by at most one (the recorded year may be that
         of the published version). The source of every value (CrossRef, arXiv or the PDF, with the evidence of the
         check) is logged.
Exit:    0 on success; 1 when the helper refuses (for example a locked library); 2 for unusable input.
Version: see VERSION.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import libmeta as lm  # noqa: E402

VERSION = "1.0"
FIELDS = ("author", "year", "title", "secondary_title", "volume", "number", "pages", "publisher", "electronic_resource_number")


def build_updates(props, current, types, overrides):
    updates = {}
    for rid, f in props.items():
        cur = current.get(int(rid))
        if cur is None:
            continue
        new = {k: (f.get(k, "") if k == "author" else lm.clean(f.get(k, ""))) for k in FIELDS}
        new["reference_type"] = lm.entry_type(f.get("record_type", ""), types)
        arx = "arXiv" in f.get("record_type", "")
        if arx and str(cur["year"]).isdigit() and str(new["year"]).isdigit() and abs(int(cur["year"]) - int(new["year"])) <= 1:
            new["year"] = cur["year"]
        src = ("arXiv" if arx else "CrossRef") + f"; checked against the PDF: {f.get('_evidence', '')}"
        ov = overrides.get(str(rid), {})
        if ov:
            new.update(ov.get("fields", {}))
            src += f"; {ov.get('source', 'read from the PDF')}"
        fields = {k: v for k, v in new.items() if v not in ("", None)}
        fields["_source"] = src
        updates[int(rid)] = fields
    return updates


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
        updates = build_updates(props, current, types, overrides)
        changes = el.update_refs(lib, root, updates, log_dir=log) if updates else []
    except el.LibraryError as e:
        print(f"Refused: {e}", file=sys.stderr)
        return 1
    print(f"entries updated: {len(updates)}; fields written: {len(changes)}; log: {log / 'changes.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
