r"""Report which session transcripts of a project will be deleted soon.

Created using: $\text {Created using: }\ claude-sonnet-5-5-\text{v}5.5-\text {date: }091126$

Claude Code deletes session transcripts (`~/.claude/projects/<project key>/<session>.jsonl`) that are
older than the setting `cleanupPeriodDays` (default 30). The project-disclosure skill and the log
citations in the decision log read those transcripts. This script lists the transcripts of one project
that will expire within a number of days, so they can be used or copied first.

Assumption: the age of a transcript is the time the file was last written, which a resumed session
updates. The Claude Code documentation says only "older than cleanupPeriodDays".

The period is read from `cleanupPeriodDays` in `~/.claude/settings.json`, then `<root>/.claude/settings.json`
and `<root>/.claude/settings.local.json` (the last file that sets it wins), or taken from --days.
The project key is the project path with every character that is not a letter or digit replaced by '-'.

Usage: log_retention.py [--root <project root>] [--warn-days N] [--days N] [--list] [--hook]
                        [--claude-dir DIR] [--version]
  --root        the project folder (default: the current folder)
  --warn-days   report transcripts that expire within this many days (default 14)
  --days        use this period and ignore the settings files
  --list        print every transcript with its expiry date, not only the ones that are due
  --hook        for a Claude Code SessionStart hook: read the hook JSON on standard input, use its `cwd` as
                the root, print nothing if no transcript is due, otherwise print a JSON reply that shows
                a message to the user and tells Claude
  --claude-dir  the Claude configuration folder (default: ~/.claude)
Inputs:  the transcripts of the project and the settings files.
Outputs: a short report on standard output. No file is written.
Exit:    0 always in --hook mode; otherwise 0, or 1 if a transcript is due.
Version: see VERSION; `--version` prints it.
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

VERSION = "1.0"
DEFAULT_DAYS = 30
DAY = 86400.0


def project_key(root):
    return re.sub(r"[^A-Za-z0-9]", "-", str(Path(root).resolve()))


def period(root, claude_dir):
    """cleanupPeriodDays from the settings files; the default if none sets it."""
    days = DEFAULT_DAYS
    for f in (claude_dir / "settings.json", Path(root) / ".claude" / "settings.json",
              Path(root) / ".claude" / "settings.local.json"):
        try:
            value = json.loads(f.read_text(encoding="utf-8")).get("cleanupPeriodDays")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
            days = value
    return days


def transcripts(root, claude_dir, days, now):
    """[(session id, last written, expiry, days left)] for the project, soonest expiry first."""
    folder = claude_dir / "projects" / project_key(root)
    found = []
    for f in folder.glob("*.jsonl") if folder.is_dir() else []:
        written = f.stat().st_mtime
        expiry = written + days * DAY
        found.append((f.stem, written, expiry, int((expiry - now) // DAY)))
    return sorted(found, key=lambda x: x[2])


def ddmmyy(ts):
    return datetime.fromtimestamp(ts).strftime("%d%m%y")


def summary(due, days, warn):
    first = due[0]
    return (f"{len(due)} session transcript(s) for this project expire within {warn} days (the first on "
            f"{ddmmyy(first[2])}; transcripts are kept {days} days). Use the project-disclosure skill, or copy "
            "the logs from ~/.claude/projects/, before then.")


def main(argv):
    ap = argparse.ArgumentParser(prog="log_retention.py", description="Report session transcripts that expire soon.")
    ap.add_argument("--version", action="version", version=f"log_retention.py {VERSION}")
    ap.add_argument("--root", default=None)
    ap.add_argument("--warn-days", type=int, default=14)
    ap.add_argument("--days", type=int, default=None)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--hook", action="store_true")
    ap.add_argument("--claude-dir", default=str(Path.home() / ".claude"))
    a = ap.parse_args(argv)
    claude_dir = Path(a.claude_dir)
    root = a.root
    if a.hook:
        try:
            root = json.load(sys.stdin).get("cwd") or root
        except Exception:
            return 0
    root = Path(root or ".")
    try:
        days = a.days or period(root, claude_dir)
        now = time.time()
        found = transcripts(root, claude_dir, days, now)
        due = [t for t in found if t[3] < a.warn_days]
        if a.hook:
            if due:
                text = summary(due, days, a.warn_days)
                print(json.dumps({"systemMessage": text, "hookSpecificOutput": {
                    "hookEventName": "SessionStart", "additionalContext": text}}))
            return 0
    except Exception:
        if a.hook:
            return 0
        raise
    print(f"Project: {root}  (transcripts kept {days} days)")
    if not found:
        print("No transcripts found for this project.")
        return 0
    for sid, written, expiry, left in (found if a.list else due):
        print(f"  {sid[:8]}  last written {ddmmyy(written)}  expires {ddmmyy(expiry)}  ({left} days left)")
    print(f"Transcripts: {len(found)}; due within {a.warn_days} days: {len(due)}")
    if due:
        print(summary(due, days, a.warn_days))
    return 1 if due else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
