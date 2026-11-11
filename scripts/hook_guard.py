r"""Claude Code PreToolUse hook: block writes to protected files.

Created using: $\text {Created using: }\ claude-sonnet-5-5-\text{v}5.5-\text {date: }091126$
Modified using: claude-fable-5-2-v5.2-date: 111126 (version 1.1: data/ is guarded in a framework project only;
                the PowerShell tool is checked as Bash is; touch is a writer; a word after `<`, a comment and a/../b
                are read correctly)

Protected: the project `data/` folder (input data), except `data/DATA-NOTES.md` and README files, in a
framework project only (the `CLAUDE.md` in the session folder names `machine.md`, as every project template
does; any other folder may write to its own `data/`). Protected in every folder: every path listed in `<claude folder>/rules/protected-paths.txt` (one absolute path per line, a file
or a folder, `#` starts a comment; for example the EndNote library and its .Data folder).

The hook checks two kinds of call:
- Write, Edit, MultiEdit and NotebookEdit: the target path.
- Bash and PowerShell: each command segment (split at ; & | and line ends; a `cd` moves the folder that relative paths are read against) that names a protected path and either
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
import posixpath
import re
import sys
from pathlib import Path

VERSION = "1.1"
GUARD_DATA = True  # set in main: False when the session folder is not a framework project
FILE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
WRITERS = re.compile(r"(^|\s)(rm|mv|tee|touch|del|erase|truncate|remove-item|move-item|set-content|add-content|"
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


def framework_project(root):
    """True if the CLAUDE.md in the folder names machine.md, as every project template does."""
    f = Path(root) / "CLAUDE.md"
    return f.is_file() and "machine.md" in f.read_text(encoding="utf-8", errors="replace")


def inside(path, base):
    return path == base or path.startswith(base + "/")


def exempt(path, data):
    """DATA-NOTES.md directly in data/, and README files anywhere under it."""
    name = path.rsplit("/", 1)[-1]
    return path == data + "/data-notes.md" or name.startswith("readme")


def protected_file(path, root, listed):
    path = posixpath.normpath(norm(str(path)))  # a/../b is read as b
    data = norm(str(root)).rstrip("/") + "/data"
    if GUARD_DATA and inside(path, data) and not exempt(path, data):
        return "input data (data/)"
    for p in listed:
        if inside(path, p):
            return f"a protected path ({p})"
    return None


def protected_word(word, root, listed, base=None):
    """Does one word of a command name a protected path? Relative words are read against `base`
    (the folder the command is in; the project root unless an earlier `cd` moved it). base "?" means unknown."""
    w = word.strip("\"'()<>=")
    if not w:
        return None
    if re.match(r"^(\./)?data(/|$)", w):
        if base == "?":
            return None
        w = (base or norm(str(root)).rstrip("/")) + "/" + re.sub(r"^\./", "", w)
    elif not re.match(r"^([a-z]:)?/", w):
        return None
    return protected_file(w, root, listed)


def after_cd(words, base, root):
    """The folder after a `cd` segment: absolute targets replace it, relative ones add to it, and a
    target that holds a variable, ~ or a command substitution makes it unknown ("?")."""
    target = words[1].strip("\"'") if len(words) > 1 else ""
    if not target or target.startswith("~") or re.search(r"[$`]", target) \
            or base == "?" and not re.match(r"^([a-z]:)?/", target):
        return "?"
    if re.match(r"^([a-z]:)?/", target):
        return posixpath.normpath(target)
    return posixpath.normpath((base or norm(str(root)).rstrip("/")) + "/" + target)


HEREDOC = re.compile(r"(<<-?\s*(['\"]?)(\w+)\2[^\n]*\n)(.*?)(\n[ \t]*\3[ \t]*(?:\n|$))", re.S)


def strip_heredocs(text):
    """Drop the body of each here-document: it is text for a command, not a command."""
    return HEREDOC.sub(lambda m: m.group(1) + m.group(5), text)


def bash_problem(command, root, listed):
    base = None
    for seg in SEGMENTS.split(strip_heredocs(norm(command))):
        words = seg.split()
        if words and words[0] == "cd":
            base = after_cd(words, base, root)
            continue
        if not re.search(r"[\"']", seg):  # a comment ends the segment (not judged where quotes are used)
            words = re.sub(r"(^|\s)#.*$", "", seg).split()
        # a word that follows `<` is read from, not written to
        reads = {i for i, w in enumerate(words) if (w.startswith("<") and not w.startswith("<<"))
                 or (i and words[i - 1] == "<")}
        hits = [(w, protected_word(w.lstrip(">"), root, listed, base)) for i, w in enumerate(words) if i not in reads]
        hits = [(w, why) for w, why in hits if why]
        if not hits:
            continue
        redirect = re.search(r">>?\s*[\"']?(\S+)", seg)
        if redirect and protected_word(redirect.group(1), root, listed, base):
            return protected_word(redirect.group(1), root, listed, base)
        if WRITERS.search(seg):
            return hits[0][1]
        if COPIERS.search(seg) and protected_word(words[-1], root, listed, base):
            return protected_word(words[-1], root, listed, base)
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
        global GUARD_DATA
        GUARD_DATA = framework_project(root)
        listed = config_paths()
        why = None
        if tool in FILE_TOOLS and args.get(FILE_TOOLS[tool]):
            target = Path(args[FILE_TOOLS[tool]])
            why = protected_file(target if target.is_absolute() else root / target, root, listed)
        elif tool in ("Bash", "PowerShell"):
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
