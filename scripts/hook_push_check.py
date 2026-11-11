r"""Claude Code PreToolUse hook: stop a `git push` while the handoff is stale.

Created using: $\text {Created using: }\ claude-sonnet-5-5-\text{v}5.5-\text {date: }091126$
Modified using: claude-fable-5-2-v5.2-date: 111126 (version 1.1: git named with a path or as git.exe)

The hook receives the tool call as JSON on standard input. It acts only on Bash commands that contain
`git push` (also with a path before `git`, or `git.exe`; not inside quoted text or a here-document, except after `-c` or `eval`) and only in a project that has a `records/` folder. It runs wrapup_status.py for that
project. If the handoff is stale or missing, the hook exits with code 2 and a message, which blocks the
push and tells Claude to write a checkpoint first. Any other case, and any error, lets the call go
ahead: the hook never blocks because of its own fault.

Usage: hook_push_check.py [--version]   (the call JSON is read from standard input)
Inputs:  the hook JSON (`tool_name`, `tool_input.command`, `cwd`); wrapup_status.py in the same folder.
Outputs: a message on standard error when the push is blocked. No file is written.
Exit:    0 allow; 2 block.
Version: see VERSION; `--version` prints it.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

VERSION = "1.1"
PUSH = re.compile(r"(^|[;&|(\s\"'])([^\s\"';&|()]*[\\/])?git(\.exe)?(\s+-\S+(\s+\S+)?)*\s+push([\s\"';&|)]|$)", re.I)
# a quoted program path that ends in git or git.exe, as in "C:/Program Files/Git/bin/git.exe" push
QUOTED_GIT = re.compile(r"(\"[^\"\n]*[\\/]git(\.exe)?\"|'[^'\n]*[\\/]git(\.exe)?')", re.I)
HEREDOC = re.compile(r"(<<-?\s*(['\"]?)(\w+)\2[^\n]*\n)(.*?)(\n[ \t]*\3[ \t]*(?:\n|$))", re.S)
# quoted text is not a command, unless it follows `-c` or `eval` (bash -c "git push")
QUOTED = re.compile(r"(?<!-c )(?<!eval )(\"[^\"]*\"|'[^']*')")


def inert_removed(command):
    """The command without here-document bodies and quoted text, so words inside them are not read as a command."""
    command = HEREDOC.sub(lambda m: m.group(1) + m.group(5), command)
    command = QUOTED_GIT.sub("git", command)
    return QUOTED.sub('""', command)


def main():
    if "--version" in sys.argv[1:]:
        print(f"hook_push_check.py {VERSION}")
        return 0
    try:
        call = json.load(sys.stdin)
        command = call.get("tool_input", {}).get("command", "")
        if call.get("tool_name") != "Bash" or not PUSH.search(inert_removed(command)):
            return 0
        root = Path(call.get("cwd") or ".")
        if not (root / "records").is_dir():
            return 0
        status = Path(__file__).with_name("wrapup_status.py")
        r = subprocess.run([sys.executable, str(status), "--root", str(root)],
                           capture_output=True, text=True, timeout=20)
        if r.returncode != 1:
            return 0
        print("Push blocked: the handoff is not current. Write a checkpoint "
              "(overwrite records/HANDOFF.md) so it goes with the work, then push again.\n"
              + r.stdout.strip(), file=sys.stderr)
        return 2
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
