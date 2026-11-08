r"""Deploy the Agent-docs master files to the Claude configuration folder.

Created using: $\text {Created using: }\ claude-sonnet-5-5-\text{v}1.0-\text {date: }081126$

Compares the master files in this repository with the live copies in the Claude configuration
folder, and copies the ones that differ. Needs only Python 3 (standard library). Writes nothing
unless the command is `apply`.

Usage (run from any folder; the repository is the folder that holds this script):
  python deploy.py [status]   show what differs; changes nothing; exit 1 if anything differs
  python deploy.py status --diff        also print a unified diff for each differing text file
  python deploy.py apply [--yes]        sync repository copies, back up each live file that will
                                        change, copy, then compare again. Asks for confirmation on
                                        a terminal; without a terminal `--yes` is required.
  python deploy.py doctor     check the two local user files in <target>/rules: present, marker
                              line found, form filled in, and each absolute path in machine.md
                              exists. Changes nothing; exit 1 on any problem.
Options:
  --target PATH   the configuration folder (default: ~/.claude). Use a scratch folder to test.

Inputs:
  claude-md/global-CLAUDE.md              -> <target>/CLAUDE.md
  skills/<name>/ (folders with SKILL.md)  -> <target>/skills/<name>/ (every file except docs/)
  scripts/*.py                            -> <target>/scripts/ (run_control, archive_control, check_records)
  claude-md/project-CLAUDE.md             -> claude-md/project-template/CLAUDE.md (repository copy,
                                             written by `apply`; the first file is the source)
Outputs:
  `apply` writes the files above and copies each live file it replaces to
  <target>/backups/deploy-<DDMMYY-HHMM>/<path under target>. Nothing is ever deleted.
  The local files <target>/rules/machine.md and profile.md are never written; the blank forms
  are in claude-md/user-files/.
Line endings: files that differ only in line endings count as the same and are not copied.
Not covered yet: agents, hooks, statusline, MCP servers.
"""
import argparse
import difflib
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent

# (source file, repository copy): the first file is the master.
REPO_COPIES = [
    (REPO / "claude-md" / "project-CLAUDE.md", REPO / "claude-md" / "project-template" / "CLAUDE.md"),
]

MARKERS = {"machine.md": "machine-file-v1", "profile.md": "profile-file-v1"}


def items(target):
    """Return (label, source, live) for every file to deploy."""
    out = [("global rules", REPO / "claude-md" / "global-CLAUDE.md", target / "CLAUDE.md")]
    for d in sorted((REPO / "skills").iterdir()):
        if d.is_dir() and (d / "SKILL.md").exists():
            for f in sorted(p for p in d.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                             and "docs" not in p.relative_to(d).parts[:-1]):
                out.append(("skill " + d.name, f, target / "skills" / d.name / f.relative_to(d)))
    for f in sorted((REPO / "scripts").glob("*.py")):
        out.append(("script " + f.stem, f, target / "scripts" / f.name))
    return out


def norm(b):
    return b.replace(b"\r\n", b"\n")


def state(src, dst):
    """same | eol (differs only in line endings) | differs | missing"""
    if not dst.exists():
        return "missing"
    a, b = src.read_bytes(), dst.read_bytes()
    if a == b:
        return "same"
    return "eol" if norm(a) == norm(b) else "differs"


def show_diff(src, dst):
    try:
        a = norm(src.read_bytes()).decode("utf-8").splitlines()
        b = norm(dst.read_bytes()).decode("utf-8").splitlines() if dst.exists() else []
    except UnicodeDecodeError:
        print("      (binary file, no diff)")
        return
    for line in difflib.unified_diff(b, a, "live", "repository", lineterm="", n=1):
        print("      " + line)


def collect(target):
    rows, bad = [], 0
    for master, copy in REPO_COPIES:
        s = state(master, copy)
        rows.append(("repository copy", master, copy, s))
        bad += s in ("differs", "missing")
    for label, src, dst in items(target):
        s = state(src, dst)
        rows.append((label, src, dst, s))
        bad += s in ("differs", "missing")
    return rows, bad


def status(target, want_diff):
    rows, bad = collect(target)
    print(f"Repository: {REPO}\nTarget:     {target}\n")
    for label, src, dst, s in rows:
        rel = dst.relative_to(target) if target in dst.parents else dst.relative_to(REPO)
        flag = {"same": "same   ", "eol": "same*  ", "differs": "DIFFERS", "missing": "MISSING"}[s]
        print(f"  {flag}  {label:<24} {rel}")
        if want_diff and s == "differs":
            show_diff(src, dst)
    if any(r[3] == "eol" for r in rows):
        print("\n  same* = differs only in line endings; not copied")
    live_only = []
    sk = target / "skills"
    if sk.is_dir():
        known = {d.name for d in (REPO / "skills").iterdir() if d.is_dir() and (d / "SKILL.md").exists()}
        live_only = sorted(p.name for p in sk.iterdir() if p.is_dir() and p.name not in known)
    if live_only:
        print("  live only (not in the repository, left alone): " + ", ".join(live_only))
    print(f"\n{bad} file(s) to copy." if bad else "\nIn sync.")
    return bad, rows


def apply(target, yes):
    bad, rows = status(target, False)
    todo = [r for r in rows if r[3] in ("differs", "missing")]
    if not todo:
        return 0
    if not yes:
        if not ask("\nCopy these files? [y/N] "):
            print("\nNothing copied. Re-run with --yes to confirm without a terminal.")
            return 1
    stamp = datetime.now().strftime("%d%m%y-%H%M")
    bdir = target / "backups" / f"deploy-{stamp}"
    for label, src, dst, s in todo:
        if target in dst.parents and dst.exists():
            keep = bdir / dst.relative_to(target)
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, keep)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    print(f"\nCopied {len(todo)} file(s). Backups of replaced live files: {bdir}")
    print("\nChecking again:")
    bad2, _ = status(target, False)
    return 1 if bad2 else 0


def ask(prompt):
    """True only if a person answers y at a terminal."""
    if not sys.stdin.isatty():
        return False
    try:
        return input(prompt).strip().lower() == "y"
    except EOFError:
        return False


def abs_paths(text):
    """Absolute paths named in the code spans of a markdown file."""
    found = []
    for span in re.findall(r"`([^`\n]+)`", text):
        cands = re.findall(r'"([^"\n]+)"', span) or [span]
        for c in cands:
            c = c.strip()
            if "<" in c or c.startswith("-") or c.endswith("..."):
                continue
            if re.match(r"^[A-Za-z]:[\\/]", c) or c.startswith(("/", "~/", "$HOME")):
                found.append(c)
    return sorted(set(found))


def resolve(p):
    if p.startswith("~/"):
        return Path.home() / p[2:]
    if p.startswith("$HOME"):
        return Path.home() / p[6:]
    m = re.match(r"^/([a-z])/(.*)$", p)  # Git Bash form of a drive path
    if m and sys.platform == "win32":
        return Path(f"{m.group(1).upper()}:/{m.group(2)}")
    return Path(p)


def doctor(target):
    problems = 0
    rules = target / "rules"
    print(f"Target: {target}\n")
    for name, marker in MARKERS.items():
        f = rules / name
        if not f.exists():
            print(f"  MISSING  {f}\n           copy claude-md/user-files/{name[:-3]}.example.md there and fill it in")
            problems += 1
            continue
        t = f.read_text(encoding="utf-8", errors="replace")
        if f"Marker: {marker}" not in t:
            print(f"  PROBLEM  {f}: line 'Marker: {marker}' not found")
            problems += 1
        elif "Copy this form to" in t:
            print(f"  PROBLEM  {f}: looks like the blank form; fill it in")
            problems += 1
        else:
            print(f"  OK       {f}")
        if name == "machine.md":
            for p in abs_paths(t):
                if not resolve(p).exists():
                    print(f"  NOT FOUND  path in machine.md: {p}")
                    problems += 1
    live = target / "CLAUDE.md"
    if live.exists() and "machine.md" not in live.read_text(encoding="utf-8", errors="replace"):
        print("  NOTE     the live CLAUDE.md does not mention machine.md (the old single-file form?)")
    print("\nCannot check from here that a session loads the files. Start a session and ask it to quote the Marker lines.")
    print(f"\n{problems} problem(s)." if problems else "\nNo problems found.")
    return 1 if problems else 0


def main(argv):
    ap = argparse.ArgumentParser(prog="deploy.py", description="Deploy the Agent-docs master files.")
    ap.add_argument("command", nargs="?", default="status", choices=["status", "apply", "doctor"])
    ap.add_argument("--target", default=str(Path.home() / ".claude"))
    ap.add_argument("--diff", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args(argv)
    target = Path(a.target).expanduser().resolve()
    if a.command == "status":
        return 1 if status(target, a.diff)[0] else 0
    if a.command == "apply":
        # repository copies first, so the live copy and the repository copy come from the master
        for master, copy in REPO_COPIES:
            if state(master, copy) in ("differs", "missing"):
                if a.yes or ask(f"Write {copy.relative_to(REPO)} from {master.relative_to(REPO)}? [y/N] "):
                    shutil.copyfile(master, copy)
                    print(f"Wrote {copy.relative_to(REPO)}")
        return apply(target, a.yes)
    return doctor(target)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
