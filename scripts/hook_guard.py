r"""Claude Code PreToolUse hook: block writes to protected files.

Created using: $\text {Created using: }\ claude-sonnet-5-5-\text{v}5.5-\text {date: }091126$

Protected: the project `data/` folder (input data), except `data/DATA-NOTES.md` and README files, and
every path listed in `<claude folder>/rules/protected-paths.txt` (one absolute path per line, a file
or a folder, `#` starts a comment; for example the EndNote library and its .Data folder).

The hook checks two kinds of call:
- Write, Edit, MultiEdit and NotebookEdit: the target path.
- Bash: each command segment (split at ; & | and line ends) that names a protected path and either
  redirects into it with > or >>, or uses a writing command (rm, mv, sed -i, tee, del, truncate,
  Remove-Item, Move-Item, Set-Content, Add-Content, Out-File, Clear-Content, New-Item), or copies
  onto it (cp, Copy-Item with the protected path as the last word).
The hook sees tool calls only. A script that writes to a protected path itself is not caught: the
`data/` check in run_control.py reports that afterwards. This hook guards against slips; it is not a lock.

A call is blocked with exit code 2 and a message. Any error, and any other call, is allowed. To turn
the hook off for one session set the environment variable CLAUDE_HOOK_GUARD=off; to remove it, delete
its entry in settings.json.

Usage: hook_guard.py [--version]   (the call JSON is read from standard input)
Inputs:  the hook JSON (`tool_name`, `tool_input`, `cwd`); the optional protected-paths.txt.
Outputs: a message on standard error when a call is blocked. No file is written.
Exit:    0 allow; 2 block.
Version: see VERSION; `--version` prints it.
"""
import json
import os
import re
import sys
from pathlib import Path

VERSION = "1.0"
FILE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
WRITERS = re.compile(r"(^|\s)(rm|mv|tee|del|erase|truncate|remove-item|move-item|set-content|add-content|"
                     r"out-file|clear-content|new-item|rd|rmdir)(\s|$)|(^|\s)sed\s+(-\S*i|--in-place)", re.I)
COPIERS = re.compile(r"(^|\s)(cp|copy|copy-item|xcopy)(\s|$)", re.I)
SEGMENTS = re.compile(r"[;&|\n]+")


def norm(text):
    """Lower case, forward slashes, and the Git Bash form /c/ turned into c:/."""
    text = text.replace(chr(92), "/").lower()
    return re.sub(r"(^|[\s\"'=<>(])/([a-z])/", lambda m: f"{m.group(1)}{m.group(2)}:/", text)


def config_paths():
    f = Path(__file__).resolve().parent.parent / "rules" / "protected-paths.txt"
    if not f.exists():
        return []
    lines = [ln.strip() for ln in f.read_text(encoding="utf-8").splitlines()]
    return [norm(ln).rstrip("/") for ln in lines if ln and not ln.startswith("#")]


def inside(path, base):
    return path == base or path.startswith(base + "/")


def exempt(path, data):
    """DATA-NOTES.md directly in data/, and README files anywhere under it."""
    name = path.rsplit("/", 1)[-1]
    return path == data + "/data-notes.md" or name.startswith("readme")


def protected_file(path, root, listed):
    path = norm(str(path))
    data = norm(str(root)).rstrip("/") + "/data"
    if inside(path, data) and not exempt(path, data):
        return "input data (data/)"
    for p in listed:
        if inside(path, p):
            return f"a protected path ({p})"
    return None


def protected_word(word, root, listed):
    """Does one word of a command name a protected path? Relative words are read against the project root."""
    w = word.strip("\"'()<>=")
    if not w:
        return None
    if re.match(r"^(\./)?data(/|$)", w):
        w = norm(str(root)).rstrip("/") + "/" + re.sub(r"^\./", "", w)
    elif not re.match(r"^([a-z]:)?/", w):
        return None
    return protected_file(w, root, listed)


def bash_problem(command, root, listed):
    for seg in SEGMENTS.split(norm(command)):
        words = seg.split()
        hits = [(w, protected_word(w.lstrip(">"), root, listed)) for w in words]
        hits = [(w, why) for w, why in hits if why]
        if not hits:
            continue
        redirect = re.search(r">>?\s*[\"']?(\S+)", seg)
        if redirect and protected_word(redirect.group(1), root, listed):
            return protected_word(redirect.group(1), root, listed)
        if WRITERS.search(seg):
            return hits[0][1]
        if COPIERS.search(seg) and protected_word(words[-1], root, listed):
            return protected_word(words[-1], root, listed)
    return None


def main():
    if "--version" in sys.argv[1:]:
        print(f"hook_guard.py {VERSION}")
        return 0
    try:
        if os.environ.get("CLAUDE_HOOK_GUARD", "").lower() == "off":
            return 0
        call = json.load(sys.stdin)
        tool, args = call.get("tool_name"), call.get("tool_input", {})
        root = Path(call.get("cwd") or ".")
        listed = config_paths()
        why = None
        if tool in FILE_TOOLS and args.get(FILE_TOOLS[tool]):
            target = Path(args[FILE_TOOLS[tool]])
            why = protected_file(target if target.is_absolute() else root / target, root, listed)
        elif tool == "Bash":
            why = bash_problem(args.get("command", ""), root, listed)
        if not why:
            return 0
        print(f"Blocked: this call would change {why}. Input data and protected files are not edited: "
              "cleaning happens downstream, in scripts that write to outputs/. Ask the user if a change "
              "is really needed.", file=sys.stderr)
        return 2
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
