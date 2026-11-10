r"""Find the docx skill scripts that the proofread skill uses, and warn when they have changed.

Created using: $\text {Created using: }\ claude-sonnet-5-5-\text{v}5.5-\text {date: }101126$

The proofread skill edits Word files with scripts from the `docx` skill (`office/validate.py`, `comment.py`,
`merge_runs.py`). That skill is maintained by Anthropic and is synced to the machine from the claude.ai account
(`~/.claude/skills/synced/<ids>/docx/`), so its folder name is not fixed, a later sync can replace it, and it may be absent
(an API-key or Bedrock sign-in does not sync it). This script does three things.
  1. Finds the folder that holds the scripts (see the search order below).
  2. Checks the interface the proofread skill relies on: each script exists, runs with --help and shows the flags used
     (`validate.py --original --author`, `comment.py --author`, `merge_runs.py --output`).
  3. Compares a fingerprint of the scripts (a hash of every .py file) with the one recorded when they were last accepted.
     A change is a warning: re-run the proofread fixtures (tests/skills/run_fixtures.py), then record the new one with --accept.

Search order: the environment variable DOCX_SKILL_DIR (a scripts folder); each --search-dir; `<claude dir>/skills/docx/scripts`;
`<claude dir>/skills/synced/*/docx/scripts`; `<claude dir>/plugins/...` to a fixed depth; and, only when the claude folder is the
default `~/.claude`, the Claude desktop app's skills-plugin folder for the platform.

Usage: check_docx_skill.py [--find] [--accept] [--claude-dir DIR] [--search-dir DIR ...] [--quiet] [--version]
  --find        print only the folder that holds the scripts; exit 1 with a message on standard error if there is none
  --accept      record the fingerprint of the scripts found now as the known-good one (only if the interface check passes)
  --claude-dir  the Claude configuration folder (default: ~/.claude)
  --search-dir  an extra folder to search: a scripts folder, or one that holds docx/scripts (may be repeated)
  --quiet       print only the problems and warnings
Inputs:  the docx skill scripts; `<claude dir>/docx-skill.json` (the recorded fingerprint, if any).
Outputs: a short report on standard output. With --accept, writes `<claude dir>/docx-skill.json`. Nothing else is written.
Exit:    0 if the scripts are found and the interface check passes (a changed fingerprint is a warning, not a failure);
         1 if they are not found or the check fails.
Version: see VERSION; `--version` prints it.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

VERSION = "1.0"
STATE = "docx-skill.json"
# script (relative to the scripts folder) -> flags that its --help must show
EXPECTED = {
    "office/validate.py": ["--original", "--author"],
    "comment.py": ["--author"],
    "merge_runs.py": ["--output"],
}


def is_default(claude_dir):
    return Path(claude_dir).resolve() == (Path.home() / ".claude").resolve()


def desktop_bases():
    """The Claude desktop app's skills-plugin folder for this platform."""
    tail = Path("Claude") / "local-agent-mode-sessions" / "skills-plugin"
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        return [Path(os.environ["APPDATA"]) / tail]
    if sys.platform == "darwin":
        return [Path.home() / "Library" / "Application Support" / tail]
    return [Path.home() / ".config" / tail]


def candidates(claude_dir, extra=()):
    found = []
    if os.environ.get("DOCX_SKILL_DIR"):
        found.append(Path(os.environ["DOCX_SKILL_DIR"]))
    for d in extra:
        d = Path(d)
        found += [d, d / "docx" / "scripts"] + sorted(d.glob("*/docx/scripts"))
    claude_dir = Path(claude_dir)
    found.append(claude_dir / "skills" / "docx" / "scripts")
    found += sorted((claude_dir / "skills" / "synced").glob("*/docx/scripts"))
    for pattern in ("plugins/*/skills/docx/scripts", "plugins/*/*/skills/docx/scripts",
                    "plugins/*/*/*/skills/docx/scripts", "plugins/*/*/*/*/skills/docx/scripts"):
        found += sorted(claude_dir.glob(pattern))
    if is_default(claude_dir):
        for base in desktop_bases():
            found += sorted(base.glob("*/*/skills/docx/scripts"))
    seen, out = set(), []
    for c in found:
        key = str(c.resolve()) if c.exists() else str(c)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def complete(folder):
    return all((folder / rel).is_file() for rel in EXPECTED)


def fingerprint(folder):
    h = hashlib.sha1()
    for f in sorted(Path(folder).rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        h.update(f.relative_to(folder).as_posix().encode("utf-8"))
        h.update(hashlib.sha1(f.read_bytes()).digest())
    return h.hexdigest()


def interface(folder):
    """Problems with the scripts the proofread skill calls: a missing file, a failed --help, or a missing flag."""
    problems = []
    for rel, flags in EXPECTED.items():
        script = Path(folder) / rel
        if not script.is_file():
            problems.append(f"{rel} is missing")
            continue
        try:
            r = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True, timeout=90,
                               env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        except subprocess.TimeoutExpired:
            problems.append(f"{rel} --help did not finish in 90 seconds")
            continue
        if r.returncode != 0:
            last = ((r.stderr or r.stdout).strip().splitlines() or ["no output"])[-1][:150]
            hint = " (install the missing package; machine.md says how)" if "ModuleNotFoundError" in last else ""
            problems.append(f"{rel} --help failed: {last}{hint}")
            continue
        missing = [f for f in flags if f not in r.stdout]
        if missing:
            problems.append(f"{rel} no longer shows the flag(s) {', '.join(missing)}")
    return problems


def recorded(claude_dir):
    try:
        data = json.loads((Path(claude_dir) / STATE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def inspect(claude_dir, extra=()):
    """The result as a dict: folder, others, problems, fingerprint, recorded."""
    paths = candidates(claude_dir, extra)
    valid = [p for p in paths if complete(p)]
    result = {"folder": None, "others": [], "problems": [], "fingerprint": None, "recorded": recorded(claude_dir)}
    if not valid:
        partial = [p for p in paths if p.is_dir()]
        result["problems"].append("the docx skill scripts were not found"
                                  + (f" (an incomplete folder exists: {partial[0]})" if partial else ""))
        return result
    result["folder"] = valid[0]
    result["others"] = valid[1:]
    result["problems"] = interface(valid[0])
    result["fingerprint"] = fingerprint(valid[0])
    return result


def lines(result):
    """(kind, text) rows for a report; kind is OK, WARN or FAIL."""
    out = []
    if result["folder"] is None:
        return [("FAIL", p) for p in result["problems"]]
    out.append(("OK", f"docx skill scripts: {result['folder']}"))
    for other in result["others"]:
        out.append(("OK", f"also found: {other}"))
    if result["problems"]:
        out += [("FAIL", p) for p in result["problems"]]
    else:
        out.append(("OK", "interface: comment.py, merge_runs.py and office/validate.py run and show the flags the proofread skill uses"))
    rec = result["recorded"]
    if not rec or not rec.get("fingerprint"):
        out.append(("WARN", "no fingerprint recorded; run `check_docx_skill.py --accept` after the proofread fixtures pass"))
    elif rec["fingerprint"] == result["fingerprint"]:
        out.append(("OK", f"fingerprint matches the one accepted on {rec.get('accepted', 'an earlier date')}"))
    else:
        out.append(("WARN", f"the scripts changed since {rec.get('accepted', 'the fingerprint was recorded')}: re-run the proofread "
                            "fixtures (tests/skills/run_fixtures.py), then `check_docx_skill.py --accept`"))
    return out


def main(argv):
    ap = argparse.ArgumentParser(prog="check_docx_skill.py", description="Find and check the docx skill scripts.")
    ap.add_argument("--version", action="version", version=f"check_docx_skill.py {VERSION}")
    ap.add_argument("--find", action="store_true")
    ap.add_argument("--accept", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--claude-dir", default=str(Path.home() / ".claude"))
    ap.add_argument("--search-dir", action="append", default=[])
    a = ap.parse_args(argv)
    result = inspect(a.claude_dir, a.search_dir)
    if a.find:
        if result["folder"] is None:
            print("; ".join(result["problems"]), file=sys.stderr)
            return 1
        print(result["folder"])
        return 0
    if a.accept:
        if result["folder"] is None or result["problems"]:
            for kind, text in lines(result):
                if kind == "FAIL":
                    print(f"FAIL  {text}", file=sys.stderr)
            print("Nothing recorded: the interface check did not pass.", file=sys.stderr)
            return 1
        (Path(a.claude_dir) / STATE).write_text(json.dumps({
            "fingerprint": result["fingerprint"], "folder": str(result["folder"]),
            "accepted": date.today().strftime("%d%m%y")}, indent=2) + chr(10), encoding="utf-8")
        print(f"Recorded the fingerprint of {result['folder']} in {Path(a.claude_dir) / STATE}")
        return 0
    for kind, text in lines(result):
        if a.quiet and kind == "OK":
            continue
        print(f"{kind:5} {text}")
    return 1 if result["folder"] is None or result["problems"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
