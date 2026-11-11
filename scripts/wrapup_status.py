r"""Report whether the handoff is current, so a checkpoint or wrap-up is not forgotten.

Created using: $\text {Created using: }\ claude-sonnet-5-5-\text{v}5.5-\text {date: }091126$
Modified using: claude-fable-5-2-v5.2-date: 111126 (version 1.1: an uncommitted deletion counts as a change)

The handoff is `records/HANDOFF.md`. It is git-ignored in some projects, so its file time is the only
record of when it was written. It is stale when a changed file is newer than it. Changed files are
the uncommitted tracked or new files and, when the branch has an upstream, the files changed by
commits not yet pushed. `records/HANDOFF.md` itself is not counted. An uncommitted deletion of a tracked
file is a change too: a deleted file has no time, so the time of the nearest folder that still exists is
used (a folder's time moves when an entry is added to it or removed from it). A checkpoint rewrites the handoff
after the work it describes, so the handoff then becomes current.

Usage: wrapup_status.py [--root <project root>] [--max-lines N] [--quiet] [--version]
  --root may stand anywhere in the command line; the default is the current folder.
  --max-lines is the limit shown for the decision log (default 100; display only).
  --quiet prints only the last line.
Inputs:  the handoff and DECISIONS.md under records/, and git status and diff for the project.
Outputs: a short report on standard output. No file is written.
Exit:    0 if the handoff is current; 1 if it is missing or stale; 2 if the folder is unusable.
Version: see VERSION; `--version` prints it.
"""
import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

VERSION = "1.1"
ROW = re.compile(r"^\| \d{6} \|")
TOLERANCE = 2.0  # seconds: files written in the same wrap-up step


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


def git(root, *args):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return r.returncode, r.stdout


def changed_paths(root):
    """(uncommitted paths, paths changed by unpushed commits or None if there is no upstream, deleted paths)."""
    code, out = git(root, "status", "--porcelain=v1", "-z", "-uall", "--no-renames")
    entries = [e for e in out.split("\0") if len(e) > 3]
    uncommitted = [e[3:] for e in entries]
    deleted = [e[3:] for e in entries if "D" in e[:2]]
    code, _ = git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    unpushed = None
    if code == 0:
        code, out = git(root, "diff", "--name-only", "-z", "@{u}..HEAD")
        unpushed = [p for p in out.split("\0") if p] if code == 0 else None
    return uncommitted, unpushed, deleted


def folder_time(root, rel):
    """The time of the nearest folder above a deleted path that still exists."""
    folder = (root / rel).parent
    while not folder.is_dir() and folder != root:
        folder = folder.parent
    return folder.stat().st_mtime


def stamp(t):
    return datetime.fromtimestamp(t).strftime("%d%m%y %H:%M")


def main(argv):
    root_arg, argv = split_root(argv)
    ap = argparse.ArgumentParser(prog="wrapup_status.py", description="Report whether the handoff is current.")
    ap.add_argument("--root", default=None, help="project root (default: current folder)")
    ap.add_argument("--max-lines", type=int, default=100, help="decision log limit shown in the report")
    ap.add_argument("--quiet", action="store_true", help="print only the status line")
    ap.add_argument("--version", action="version", version=f"wrapup_status.py {VERSION}")
    args = ap.parse_args(argv)
    root = Path(root_arg or ".").resolve()
    if not root.is_dir():
        print(f"{root} is not a folder", file=sys.stderr)
        return 2
    out = []
    handoff = root / "records" / "HANDOFF.md"
    in_repo = git(root, "rev-parse", "--is-inside-work-tree")[0] == 0
    stale, reason = False, ""
    if not handoff.exists():
        stale, reason = True, "no records/HANDOFF.md"
        out.append("Handoff: missing")
    else:
        hm = handoff.stat().st_mtime
        out.append(f"Handoff: records/HANDOFF.md, written {stamp(hm)}")
        if not in_repo:
            out.append("Not a git repository: whether work followed the handoff was not checked.")
        else:
            uncommitted, unpushed, deleted = changed_paths(root)
            names = {p for p in (uncommitted + (unpushed or [])) if p.replace("\\", "/") != "records/HANDOFF.md"}
            times = [((root / p).stat().st_mtime, p) for p in sorted(names) if (root / p).is_file()]
            times += [(folder_time(root, p), p + " (deleted)") for p in sorted(set(deleted) & names)
                      if not (root / p).exists()]
            newer = [(t, p) for t, p in times if t - hm > TOLERANCE]
            if unpushed is None:
                ahead = "no upstream"
            else:
                ahead = str(len(git(root, "rev-list", "@{u}..HEAD")[1].split()))
            out.append(f"Uncommitted files: {len(uncommitted)}. Unpushed commits: {ahead}")
            if newer:
                t, p = max(newer)
                stale, reason = True, f"{len(newer)} changed file(s) are newer; the newest is {p} ({stamp(t)})"
                out.append(f"Changed after the handoff: {len(newer)} file(s); newest {p}, {stamp(t)}")
            else:
                out.append("No changed file is newer than the handoff.")
            pending = {p.replace("\\", "/").split("/")[1] for p in uncommitted
                       if p.replace("\\", "/").startswith("outputs/") and p.replace("\\", "/").count("/") >= 2}
            out.append(f"Pending runs (uncommitted task folders under outputs/): {len(pending)}")
            code, diff = git(root, "diff", "HEAD", "-U0", "--", "records/DECISIONS.md")
            added = sum(1 for ln in diff.splitlines() if ln.startswith("+") and ROW.match(ln[1:])) if code == 0 else 0
            out.append(f"Decision lines added since the last commit: {added}")
    decisions = root / "records" / "DECISIONS.md"
    if decisions.exists():
        rows = sum(1 for ln in decisions.read_text(encoding="utf-8", errors="replace").splitlines() if ROW.match(ln))
        note = f" (over {args.max_lines}: run rotate_records.py)" if rows > args.max_lines else ""
        out.append(f"Decision log: {rows} rows of {args.max_lines}{note}")
    out.append("Status: STALE, a checkpoint is needed (" + reason + ")" if stale else "Status: CURRENT")
    print("\n".join(out[-1:] if args.quiet else out))
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
