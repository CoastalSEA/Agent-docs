"""Check the frontmatter of SKILL.md files for the plain-value mistakes that make strict YAML parsing fail.

Run it on every new or edited skill before deploying. A frontmatter that does not parse is silently ignored by the harness:
context, agent and background have no effect (the skill does not fork) and the description is not used to list the skill.
Confirmed on 20 September 2026 for analysis-adversary and literature-search.

Two mistakes are reported.
1. A value that runs over several lines has an unindented continuation line. Strict YAML needs continuation lines indented, so
   the parser reads the text as an implicit key that spans lines ('Implicit keys need to be on a single line').
2. A plain value contains ': ' or ' #'. A colon followed by a space ends a key, and ' #' starts a comment.
The simplest fix for both is a description on a single line. This script needs no packages. It is a pattern check for these two
mistakes and not a full YAML parse.

Usage:   python skills/check_frontmatter.py skills/<name>/SKILL.md [...]
         python skills/check_frontmatter.py skills/*/SKILL.md
Inputs:  the SKILL.md files named on the command line.
Outputs: one line per file on standard output (OK or FAIL), then up to six problems for a failing file. No file is written.
         Exit code 1 if any file fails or has no frontmatter block, otherwise 0.

Created using: Sonnet5-v1.0-date: 200926
"""
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
TOP_KEY = re.compile(r"^([A-Za-z_][\w-]*):(\s|$)(.*)$")


def check(path):
    """Return None if the file has no frontmatter block, else a list of problem strings."""
    text = open(path, encoding="utf-8").read().replace("\r\n", "\n")
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None
    problems, key, block = [], None, False
    for n, line in enumerate(m.group(1).split("\n"), 2):
        k = TOP_KEY.match(line)
        if k:
            key, value = k.group(1), k.group(3)
            block = value.strip() in ("|", ">", "|-", ">-", "|+", ">+") or value.strip().startswith(('"', "'"))
            body = value
        elif key and line.strip():
            if not line.startswith((" ", "\t")):
                problems.append(f"line {n}: unindented continuation line of '{key}': {line.strip()[:60]!r}")
            body = line
        else:
            continue
        if block:
            continue
        if ": " in body:
            problems.append(f"line {n}: ': ' inside the value of '{key}': {body.strip()[:80]!r}")
        if " #" in body:
            problems.append(f"line {n}: ' #' inside the value of '{key}'")
    return problems


def main(paths):
    failed = False
    for path in paths:
        problems = check(path)
        if problems is None:
            print(f"{path}: no frontmatter block")
            failed = True
            continue
        print(f"{path}: {'OK' if not problems else 'FAIL'}")
        for p in problems[:6]:
            print("   ", p)
        failed = failed or bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
