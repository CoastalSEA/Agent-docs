"""Check the project record files and the memory notes against the project folders.

Usage: check_records.py [project_root] [--root <project_root>] [--max N] [--memory DIR]. The root defaults to the current folder.
Version: see VERSION; --version prints it and the report names it.
Inputs:  data/DATA-NOTES.md, records/DECISIONS.md and outputs/INDEX.md (a missing file is reported and its checks are
         skipped), the files and folders under the project root, the session logs in
         ~/.claude/projects/<launch-folder-key>/ and the memory notes in ~/.claude/projects/<launch-folder-key>/memory/
         (the key is the project path with every character that is not a letter or digit replaced by '-';
         --memory overrides the memory folder).
Outputs: a report on standard output. No file is written. Exit code 1 if any check fails, otherwise 0.
Checks (a failure counts towards the exit code):
  1. every backticked path-like token in the three record files exists (relative to the project root, data/, outputs/
     or records/; a bare file name is looked up anywhere under the root). Tokens with < > * { } | = [ ] and tokens that
     start with 'log ' are skipped. A name that is not found is a flag, not a failure, when it is a bare name (no
     folder in it) or lies in a git-ignored location (git cannot hold it). '~/' paths and absolute paths are checked as written. A path under a task folder
     whose INDEX.md status is archived counts as existing (the folder is held by an archive tag: see archive_control.py).
  2. every citation of the form 'log <8 hex characters> L<n>' points to line n (1-based) of a session log whose file
     name starts with those characters, and that line is a user or assistant message.
  3. INDEX.md rows against runs. The first cell of a row names a run: a git tag (<task>-<DDMMYY>-run<N>, optionally
     with '-rejected') or a legacy run folder in outputs/. The second cell names the task folder for tagged runs.
     Fails: a row whose run is neither a tag nor a folder (an archived row is exempt); a run tag with no row; a folder in outputs/ that is
     neither a legacy run row nor the task folder of a row, unless it holds uncommitted files (a pending run,
     reported but not counted as a failure).
  4. the files in data/ (other than DATA-NOTES.md) and the entries of DATA-NOTES.md match one to one.
  7. MEMORY.md exists, every link in it resolves to a note, and every note is linked from it.
Flags (for review, not failures; a legitimate edit also changes a file time):
  8. a path-like token in a memory note that does not exist (same rules as check 1, and tokens that start with '.' or
     '/', contain '...' or contain a space without a file extension are skipped). Notes cite loosely, so example
     file names and deleted test files also appear here.
  5. a file in data/ modified after DATA-NOTES.md, so its entry may be stale.
  6. a DECISIONS.md line whose cited evidence file (or the newest file in a cited folder) was modified on a later day
     than the date of the line.
  9. a memory note that contains a status word (awaiting, pending, not yet, not run, NOT pasted, TODO, draft, drafted,
     proposed), or that cites a file or folder whose newest file was modified on a later day than the note's
     'modified' date (or the note's file date if it has none). A note is not updated when the state it describes
     changes, so task status belongs in records/HANDOFF.md and not in a note.
  10. uncommitted changes under outputs/ (a run pending review; accept with a commit and tag, or discard).
  11. a file listed in products/PRODUCTS.md that is missing from products/ (the folder is git-ignored; keep a copy elsewhere).
  12. DECISIONS.md rows longer than 800 characters. The target is an average of 500 or less, which is reported. A row
      over 1,000 characters dated 091126 or later is a failure; an older one is a flag (the limit is not retroactive).
  13. DECISIONS.md with more rows than --max-lines (default 100), or more than 60,000 characters: move the oldest rows
      with rotate_records.py.
Office lock files (names that start with '~$') are skipped everywhere: they are temporary, not project files.
The checks find missing items, wording and dates only. A wrong status in INDEX.md, or a stale statement that has no
status word and cites no changed file, is not detected. Update a status when later work changes what a run means.

Created using: Sonnet5-v1.0-date: 200926
(revised by Claude Opus-v5.5-date: 230926: run tags and task folders in check 3; pending-run flag 10)
(revised by Claude Opus-v5.5-date: 240926: skip Office lock files '~$*')
(revised by Claude Sonnet-v5.5-date: 141026: paths under archived task folders count as existing; archived rows exempt from
 'run not found'; flag 11 for the products register. Ported from a project copy, 131026)
(revised by claude-sonnet-5-5-v5.5-date: 081126: moved to scripts/; --root and --version)
(revised by claude-sonnet-5-5-v5.5-date: 091126: version 1.1, checks 12 and 13 on the size of DECISIONS.md)
(revised by claude-fable-5-2-v5.2-date: 111126: version 1.2, a missing bare name or git-ignored path is a flag)
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

VERSION = "1.2"
ROW_WARN, ROW_HARD, ROW_TARGET = 800, 1000, 500  # characters in a DECISIONS.md row
HARD_FROM = (26, 11, 9)  # (year, month, day): rows dated on or after 091126 must keep to ROW_HARD
MAX_CHARS = 60000  # characters in DECISIONS.md
DECISION_ROW = re.compile(r"^\| (\d{2})(\d{2})(\d{2}) \|")

EXT =r"\.(md|txt|csv|py|m|mat|pdf|xlsx?|png|docx?|json|jsonl|html|tex|bib)$"
SKIP_DIRS = {".git", "__pycache__", "node_modules"}
RUN_TAG = re.compile(r"^.+-\d{6}-run\d+(-rejected)?$")
ARCHIVED_RUNS = set()  # first cell of the archived INDEX.md rows (a legacy folder has no tag)
ARCHIVED = set()  # task folders with status archived in outputs/INDEX.md (filled in main)
STATUS_WORDS = re.compile(r"\b(awaiting|pending|not yet|not run|NOT pasted|TODO|draft|drafted|proposed)\b", re.I)


def is_lock(name):
    # Office writes a hidden lock file '~$<name>' beside an open document.
    return name.startswith("~$")


def record_files(root):
    return {"DATA-NOTES": root / "data" / "DATA-NOTES.md",
            "DECISIONS": root / "records" / "DECISIONS.md",
            "INDEX": root / "outputs" / "INDEX.md"}


def name_index(root):
    names = set()
    for _, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        names.update(dirs)
        names.update(f for f in files if not is_lock(f))
    return names


def pathlike(tok):
    if any(c in tok for c in "<>*{}|=[]") or tok.startswith("log "):
        return False
    return "/" in tok or "\\" in tok or re.search(EXT, tok, re.I) is not None


def resolve(tok, root, names):
    rel = tok.replace("\\", "/").rstrip("/")
    if rel.startswith("~/"):
        p = Path(rel).expanduser()
        return p if p.exists() else None
    if re.match(r"^[A-Za-z]:/", rel):
        return Path(rel) if Path(rel).exists() else None
    for base in (root, root / "data", root / "outputs", root / "records"):
        if (base / rel).exists():
            return base / rel
    if "/" not in rel and rel in names:
        return root
    parts = rel.split("/")
    first = parts[1] if parts[0] == "outputs" and len(parts) > 1 else parts[0]
    if first in ARCHIVED:  # a folder removed by archive_control.py: the archive tag holds it
        return root
    return None


def soft_missing(tok, root):
    """Why a cited name that was not found is a flag and not a failure, or None if it is a failure.

    A bare name (no folder in it) may be a file kept elsewhere or a general term. A path in a git-ignored
    location is local: git cannot hold it, so its absence is for review."""
    rel = tok.replace("\\", "/").rstrip("/")
    if "/" not in rel:
        return "bare name"
    if rel.startswith("~/") or re.match(r"^[A-Za-z]:/", rel) or rel.startswith("/"):
        return None
    try:
        res = subprocess.run(["git", "check-ignore", "-q", "--", rel], cwd=root, capture_output=True, text=True)
    except OSError:
        return None
    return "git-ignored location" if res.returncode == 0 else None


def newest_mtime(path):
    if path.is_file():
        return dt.date.fromtimestamp(path.stat().st_mtime)
    best = None
    for dirpath, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if is_lock(f):
                continue
            d = dt.date.fromtimestamp(os.path.getmtime(os.path.join(dirpath, f)))
            best = d if best is None or d > best else best
    return best


def note_date(text, path):
    m = re.search(r"^\s*modified:\s*(\d{4}-\d{2}-\d{2})", text, re.M)
    if m:
        return dt.date.fromisoformat(m.group(1))
    return dt.date.fromtimestamp(path.stat().st_mtime)


def split_root(argv):
    """Remove --root from argv wherever it stands; return (root or None, remaining arguments)."""
    rest, root, i = [], None, 0
    while i < len(argv):
        if argv[i] == "--root" and i + 1 < len(argv):
            root, i = argv[i + 1], i + 2
        elif argv[i].startswith("--root="):
            root, i = argv[i][7:], i + 1
        else:
            rest.append(argv[i])
            i += 1
    return root, rest


def main():
    root_arg, argv = split_root(sys.argv[1:])
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", action="version", version=f"check_records.py {VERSION}")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--max", type=int, default=40, help="maximum number of lines listed per flag")
    ap.add_argument("--memory", default=None, help="memory folder (default: derived from the project root)")
    ap.add_argument("--max-lines", type=int, default=100, help="rows allowed in DECISIONS.md before it should be rotated")
    args = ap.parse_args(argv)
    root = Path(root_arg or args.root).resolve()
    rec = record_files(root)
    text, failures, flags = {}, 0, 0
    print(f"Records check for {root} (check_records.py {VERSION})")
    for k, p in rec.items():
        if p.exists():
            text[k] = p.read_text(encoding="utf-8", errors="replace")
        else:
            print(f"  {k}: {p.relative_to(root)} not found, its checks are skipped")
    names = name_index(root)
    if "INDEX" in text:
        for line in text["INDEX"].splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.startswith("|") else []
            if len(cells) == 5 and cells[0].startswith("`") and cells[3] == "archived":
                ARCHIVED.add((cells[1] or cells[0]).strip("`"))
                ARCHIVED_RUNS.add(cells[0].strip("`"))

    # 1. cited paths
    n_tok, missing, soft = 0, [], []
    for k, t in text.items():
        for tok in sorted(set(re.findall(r"`([^`\n]+)`", t))):
            tok = tok.strip()
            if not pathlike(tok):
                continue
            n_tok += 1
            if resolve(tok, root, names) is None:
                why = soft_missing(tok, root)
                (soft if why else missing).append((k, tok, why))
    print(f"1. Cited paths: {n_tok} checked, {len(missing)} not found")
    for k, tok, _ in missing[:args.max]:
        print(f"     NOT FOUND in {k}: {tok}")
    failures += len(missing)
    if soft:
        print(f"   Flag: {len(soft)} cited names not found that are a bare name or in a git-ignored location")
        for k, tok, why in soft[:args.max]:
            print(f"     not found in {k} ({why}): {tok}")
        flags += len(soft)

    # 2. session log citations
    cites = {}
    for t in text.values():
        for sid, n in re.findall(r"log ([0-9a-f]{8}) L(\d+)", t):
            cites.setdefault(sid, set()).add(int(n))
    projdir = Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(root))
    bad = []
    for sid, nums in sorted(cites.items()):
        files = sorted(projdir.glob(sid + "*.jsonl")) if projdir.exists() else []
        if not files:
            bad += [(sid, n, "log file not found") for n in sorted(nums)]
            continue
        found = {}
        with open(files[0], encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh, 1):
                if i in nums:
                    try:
                        found[i] = json.loads(line).get("type")
                    except ValueError:
                        found[i] = "unparsed"
        bad += [(sid, n, f"line is {found.get(n, 'missing')}") for n in sorted(nums) if found.get(n) not in ("user", "assistant")]
    n_cites = sum(len(v) for v in cites.values())
    print(f"2. Session log citations: {n_cites} in {len(cites)} logs, {len(bad)} invalid")
    for sid, n, why in bad[:args.max]:
        print(f"     INVALID log {sid} L{n}: {why}")
    failures += len(bad)

    # 3. INDEX against run tags, task folders and legacy run folders
    tags = set()
    try:
        res = subprocess.run(["git", "tag", "-l"], cwd=root, capture_output=True, text=True)
        if res.returncode == 0:
            tags = {t for t in res.stdout.split() if RUN_TAG.match(t)}
    except OSError:
        pass
    if "INDEX" in text:
        runs, folders = set(), set()
        for line in text["INDEX"].splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.startswith("|") else []
            if not cells or not cells[0].startswith("`") or "<" in cells[0]:
                continue
            runs.add(cells[0].strip("`"))
            if len(cells) > 1 and cells[1].startswith("`"):
                folders.add(cells[1].strip("`").rstrip("/\\"))
        disk = {p.name for p in (root / "outputs").iterdir() if p.is_dir()} if (root / "outputs").exists() else set()
        a = sorted(r for r in runs if r not in tags and r not in disk and r not in ARCHIVED_RUNS)
        b = sorted(tags - runs)
        try:
            res = subprocess.run(["git", "status", "--porcelain", "-uall", "--", "outputs"], cwd=root,
                                 capture_output=True, text=True)
            dirty = {ln[3:].split("/")[1] for ln in res.stdout.splitlines()
                     if ln[3:].count("/") >= 2 and not is_lock(ln[3:].rsplit("/", 1)[-1])} if res.returncode == 0 else set()
        except OSError:
            dirty = set()
        pend = sorted((disk - runs - folders) & dirty)
        c = sorted(disk - runs - folders - dirty)
        print(f"3. INDEX: {len(runs)} runs ({len(runs & tags)} tagged), {len(folders)} task folders, {len(disk)} folders in outputs/;"
              f" run not found: {len(a)}; tag without row: {len(b)}; folder without row: {len(c)}; pending folders: {len(pend)}")
        for x in a[:args.max]:
            print(f"     no tag or folder: {x}")
        for x in b[:args.max]:
            print(f"     no INDEX row for tag: {x}")
        for x in c[:args.max]:
            print(f"     no INDEX row for folder: {x}")
        for x in pend[:args.max]:
            print(f"     pending review, no INDEX row until accepted: {x}")
        failures += len(a) + len(b) + len(c)

    # 4. DATA-NOTES against data
    if "DATA-NOTES" in text:
        ent = set(e for e in re.findall(r"^### `([^`]+)`", text["DATA-NOTES"], flags=re.M) if "<" not in e)
        disk = {p.name for p in (root / "data").iterdir() if not is_lock(p.name)} - {"DATA-NOTES.md"}
        a, b = sorted(ent - disk), sorted(disk - ent)
        print(f"4. DATA-NOTES: {len(ent)} entries, {len(disk)} files in data/; entry without file: {len(a)}; file without entry: {len(b)}")
        for x in a[:args.max]:
            print(f"     no file: {x}")
        for x in b[:args.max]:
            print(f"     no entry: {x}")
        failures += len(a) + len(b)

        # 5. data files newer than DATA-NOTES
        notes_time = rec["DATA-NOTES"].stat().st_mtime
        newer = sorted(p.name for p in (root / "data").iterdir() if p.is_file() and p.name != "DATA-NOTES.md" and not is_lock(p.name) and p.stat().st_mtime > notes_time)
        print(f"5. Flag: {len(newer)} data files modified after DATA-NOTES.md")
        for x in newer[:args.max]:
            print(f"     newer than the notes: {x}")
        flags += len(newer)

    # 6. DECISIONS evidence newer than the line date
    if "DECISIONS" in text:
        stale, n_rows, n_bad = [], 0, 0
        for line in text["DECISIONS"].split("\n"):
            m = re.match(r"^\| (\d{2})(\d{2})(\d{2}) \|", line)
            if not m:
                continue
            n_rows += 1
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            try:
                d = dt.date(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                n_bad += 1
                continue
            if len(cells) != 4:
                n_bad += 1
                continue
            for tok in set(re.findall(r"`([^`\n]+)`", cells[3])):
                if not pathlike(tok):
                    continue
                p = resolve(tok.strip(), root, names)
                if p is None or p == root:
                    continue
                nm = newest_mtime(p)
                if nm is not None and nm > d:
                    stale.append((line[2:8], tok.strip(), nm))
        print(f"6. Flag: {len(stale)} evidence citations in {n_rows} DECISIONS lines are newer than the line date"
              + (f" ({n_bad} malformed lines skipped)" if n_bad else ""))
        for ddmmyy, tok, nm in stale[:args.max]:
            print(f"     line {ddmmyy}: {tok} modified {nm.strftime('%d%m%y')}")
        flags += len(stale)

    # 7 to 9. memory notes
    memdir = Path(args.memory).resolve() if args.memory else projdir / "memory"
    if not memdir.exists():
        print(f"7. Memory folder {memdir} not found, the memory checks are skipped")
    else:
        notes = {p.name: p for p in memdir.glob("*.md") if p.name != "MEMORY.md"}
        index = memdir / "MEMORY.md"
        if not index.exists():
            print(f"7. Memory index: MEMORY.md not found in {memdir} ({len(notes)} notes)")
            failures += 1
        else:
            links = set(re.findall(r"\]\(([^)\s]+\.md)\)", index.read_text(encoding="utf-8", errors="replace")))
            broken, unlisted = sorted(links - set(notes)), sorted(set(notes) - links)
            print(f"7. Memory index: {len(links)} links, {len(notes)} notes; link without note: {len(broken)}; note not in MEMORY.md: {len(unlisted)}")
            for x in broken[:args.max]:
                print(f"     no note: {x}")
            for x in unlisted[:args.max]:
                print(f"     not indexed: {x}")
            failures += len(broken) + len(unlisted)

        n_tok, missing, words, newer = 0, [], [], []
        for name, p in sorted(notes.items()):
            t = p.read_text(encoding="utf-8", errors="replace")
            body = t.split("---", 2)[-1] if t.startswith("---") else t
            nd = note_date(t, p)
            for tok in sorted(set(re.findall(r"`([^`\n]+)`", body))):
                tok = tok.strip()
                if (not pathlike(tok) or tok.startswith((".", "/")) or "..." in tok
                        or (" " in tok and not re.search(EXT, tok, re.I))):
                    continue
                n_tok += 1
                q = resolve(tok, root, names)
                if q is None:
                    missing.append((name, tok))
                elif q != root:
                    nm = newest_mtime(q)
                    if nm is not None and nm > nd:
                        newer.append((name, tok, nm, nd))
            hits = sorted(set(w.group(0).lower() for w in STATUS_WORDS.finditer(body)))
            if hits:
                words.append((name, hits))
        print(f"8. Flag: {len(missing)} of {n_tok} paths cited in memory notes not found")
        for name, tok in missing[:args.max]:
            print(f"     not found in {name}: {tok}")
        flags += len(missing)
        print(f"9. Flag: {len(words)} notes contain a status word; {len(newer)} cited paths are newer than their note")
        for name, hits in words[:args.max]:
            print(f"     status words in {name}: {', '.join(hits)}")
        for name, tok, nm, nd in newer[:args.max]:
            print(f"     {name}: {tok} modified {nm.strftime('%d%m%y')}, note dated {nd.strftime('%d%m%y')}")
        flags += len(words) + len(newer)

    # 10. pending runs
    try:
        res = subprocess.run(["git", "status", "--porcelain", "-uall", "--", "outputs"], cwd=root, capture_output=True, text=True)
        pending = [ln for ln in res.stdout.splitlines() if not is_lock(ln[3:].rsplit("/", 1)[-1])] if res.returncode == 0 else []
    except OSError:
        pending = []
    print(f"10. Flag: {len(pending)} uncommitted paths under outputs/ (runs pending review)")
    for x in pending[:args.max]:
        print(f"     {x}")
    flags += len(pending)

    # 11. products register
    reg = root / "products" / "PRODUCTS.md"
    if reg.exists():
        listed = [m for m in re.findall(r"^\| `([^`]+)`", reg.read_text(encoding="utf-8", errors="replace"), flags=re.M) if "*" not in m and "(" not in m]
        gone = sorted(x for x in listed if not (root / "products" / x.replace("\\", "/")).exists())
        print(f"11. Flag: {len(gone)} of {len(listed)} files listed in products/PRODUCTS.md are missing (git does not hold them)")
        for x in gone[:args.max]:
            print(f"     missing: {x}")
        flags += len(gone)

    # 12 and 13. size of DECISIONS.md
    if "DECISIONS" in text:
        rows = []
        for n, ln in enumerate(text["DECISIONS"].splitlines(), 1):
            m = DECISION_ROW.match(ln)
            if m:
                dd, mm, yy = (int(x) for x in m.groups())
                rows.append((n, len(ln), (yy, mm, dd)))
        if rows:
            avg = sum(r[1] for r in rows) // len(rows)
            long_rows = [r for r in rows if r[1] > ROW_WARN]
            hard = [r for r in long_rows if r[1] > ROW_HARD and r[2] >= HARD_FROM]
            soft = [r for r in long_rows if r not in hard]
            print(f"12. DECISIONS.md rows: {len(rows)}, average {avg} characters (target {ROW_TARGET} or less); "
                  f"{len(soft)} flagged over {ROW_WARN}, {len(hard)} failed over {ROW_HARD} (dated 091126 or later)")
            for n, size, _ in (hard + soft)[:args.max]:
                print(f"     line {n}: {size} characters" + (" (failure)" if (n, size, _) in hard else ""))
            failures += len(hard)
            flags += len(soft)
            total = len(text["DECISIONS"])
            over_rows, over_chars = len(rows) > args.max_lines, total > MAX_CHARS
            print(f"13. DECISIONS.md size: {len(rows)} rows (limit {args.max_lines}), {total} characters (limit {MAX_CHARS})"
                  + ("; move the oldest rows with rotate_records.py" if over_rows or over_chars else ""))
            flags += int(over_rows) + int(over_chars)

    print(f"Result:{'FAIL' if failures else 'PASS'} ({failures} failures, {flags} flags for review)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
