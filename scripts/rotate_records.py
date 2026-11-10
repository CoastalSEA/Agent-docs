r"""Move the oldest decision lines to an archive so that the active log stays short.

Created using: $\text {Created using: }\ claude-sonnet-5-5-\text{v}5.5-\text {date: }091126$

The active log is records/DECISIONS.md. Its table rows start with `| DDMMYY |` and run oldest first.
When the log holds more than --max-lines rows (default 100), the oldest rows beyond that number
are appended to records/DECISIONS-archive.md and removed from the active log. Nothing is deleted:
the rows of the two files add up to the rows of the original. The archive is searched as well as
the active log (see the search-first rule in the project CLAUDE.md).

Usage: rotate_records.py [--root <project root>] [--max-lines N] [--apply] [--version]
  Without --apply the script prints what it would move and changes nothing.
  --root may stand anywhere in the command line; the default is the current folder.
Inputs:  records/DECISIONS.md.
         The report gives the size of the active log in characters, now and after the move, against the 60,000
         limit that check_records.py applies, and the number of rows to keep to get under it.
Outputs: with --apply, records/DECISIONS-archive.md (created with a header if missing, otherwise
         appended to) and the shortened records/DECISIONS.md. Line endings of each file are kept.
Exit:    0 on success or when nothing needs to move; 1 with a message on stderr on any problem.
Version: see VERSION; `--version` prints it.
"""
import argparse
import os
import re
import sys
from pathlib import Path

VERSION = "1.1"
MAX_CHARS = 60000  # characters in DECISIONS.md, as check_records.py counts them
ROW = re.compile(r"^\| \d{6} \|")
ARCHIVE_HEAD = (
    "# Decisions archive{nl}{nl}"
    "Older lines moved from `records/DECISIONS.md` by `rotate_records.py`. Oldest first. "
    "Search this file as well as the active log.{nl}{nl}"
    "| Date (DDMMYY) | Decision | Reason | Evidence |{nl}"
    "|---|---|---|---|{nl}"
)


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


def read_lines(path):
    """The lines of a file with their line endings, and the ending the file uses."""
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    return text.splitlines(keepends=True), ("\r\n" if "\r\n" in text else "\n")


def rows_of(lines):
    return [ln for ln in lines if ROW.match(ln)]


def chars(lines):
    """Characters in a log as check_records.py counts them: a line ending counts as one."""
    return len("".join(lines).replace("\r\n", "\n"))


def rows_to_fit(lines, limit=MAX_CHARS):
    """(largest number of newest rows whose log fits in `limit` characters, the size then), or (0, size) if none fits."""
    positions = [i for i, ln in enumerate(lines) if ROW.match(ln)]
    for keep_rows in range(len(positions), 0, -1):
        dropped = set(positions[:len(positions) - keep_rows])
        size = chars([ln for i, ln in enumerate(lines) if i not in dropped])
        if size <= limit:
            return keep_rows, size
    return 0, chars([ln for i, ln in enumerate(lines) if not ROW.match(ln)])


def write_atomic(path, text):
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def main(argv):
    root_arg, argv = split_root(argv)
    ap = argparse.ArgumentParser(prog="rotate_records.py",
                                 description="Move the oldest decision lines to records/DECISIONS-archive.md.")
    ap.add_argument("--root", default=None, help="project root (default: current folder)")
    ap.add_argument("--max-lines", type=int, default=100, help="rows kept in the active log (default 100)")
    ap.add_argument("--apply", action="store_true", help="write the files (default: show only)")
    ap.add_argument("--version", action="version", version=f"rotate_records.py {VERSION}")
    args = ap.parse_args(argv)
    if args.max_lines < 1:
        print("--max-lines must be at least 1", file=sys.stderr)
        return 1
    root = Path(root_arg or ".").resolve()
    active = root / "records" / "DECISIONS.md"
    archive = root / "records" / "DECISIONS-archive.md"
    if not active.exists():
        print(f"{active} not found", file=sys.stderr)
        return 1
    lines, nl = read_lines(active)
    rows = rows_of(lines)
    extra = len(rows) - args.max_lines
    if extra <= 0:
        size = chars(lines)
        print(f"{len(rows)} rows in records/DECISIONS.md, at most {args.max_lines}: nothing to move. "
              f"The log is {size} characters (limit {MAX_CHARS}).")
        if size > MAX_CHARS:
            fit, fit_size = rows_to_fit(lines)
            print(f"Over the character limit. Keeping the newest {fit} rows ({fit_size} characters) would fit: "
                  f"run with --max-lines {fit}.")
        return 0
    moving = [i for i, ln in enumerate(lines) if ROW.match(ln)][:extra]
    moved_lines = [lines[i] for i in moving]
    keep = [ln for i, ln in enumerate(lines) if i not in set(moving)]
    first, last = moved_lines[0][2:8], moved_lines[-1][2:8]
    print(f"{len(rows)} rows in records/DECISIONS.md; keeping the newest {args.max_lines}.")
    print(f"Moving {extra} rows (dated {first} to {last}) to {archive.relative_to(root)}.")
    after = chars(keep)
    print(f"The active log is {chars(lines)} characters now and {after} after (limit {MAX_CHARS}).")
    if after > MAX_CHARS:
        fit, fit_size = rows_to_fit(lines)
        print(f"Still over the character limit. Keeping the newest {fit} rows ({fit_size} characters) would fit: "
              f"use --max-lines {fit}.")
    if not args.apply:
        print("Nothing written. Run again with --apply to move them.")
        return 0
    if archive.exists():
        a_lines, a_nl = read_lines(archive)
        if a_lines and not a_lines[-1].endswith(("\n", "\r")):
            a_lines[-1] += a_nl
        before_archive = len(rows_of(a_lines))
        new_archive = "".join(a_lines + [ln.rstrip("\r\n") + a_nl for ln in moved_lines])
    else:
        before_archive = 0
        new_archive = ARCHIVE_HEAD.format(nl=nl) + "".join(moved_lines)
    new_active = "".join(keep)
    if len(rows_of(new_active.splitlines(keepends=True))) + extra != len(rows):
        print("Row count check failed before writing; nothing was changed.", file=sys.stderr)
        return 1
    write_atomic(archive, new_archive)
    write_atomic(active, new_active)
    a_after = len(rows_of(read_lines(archive)[0]))
    n_after = len(rows_of(read_lines(active)[0]))
    if a_after != before_archive + extra or n_after + a_after != len(rows) + before_archive:
        print("Row count check failed after writing. Restore the files from git or the archive.", file=sys.stderr)
        return 1
    print(f"Done. Active log {n_after} rows; archive {a_after} rows. Nothing was deleted.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
