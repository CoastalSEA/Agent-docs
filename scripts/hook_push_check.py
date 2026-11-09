r"""Claude Code PreToolUse hook: stop a `git push` while the handoff is stale.

Created using: $\text {Created using: }\ claude-sonnet-5-5-\text{v}5.5-\text {date: }091126$

The hook receives the tool call as JSON on standard input. It acts only on Bash commands that contain
`git push` and only in a project that has a `records/` folder. It runs wrapup_status.py for that
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

VERSION = "1.0"
PUSH = re.compile(r"(^|[;&|(\s])git(\s+-\S+(\s+\S+)?)*\s+push(\s|$)")


def main():
    if "--version" in sys.argv[1:]:
        print(f"hook_push_check.py {VERSION}")
        return 0
    try:
        call = json.load(sys.stdin)
        command = call.get("tool_input", {}).get("command", "")
        if call.get("tool_name") != "Bash" or not PUSH.search(command):
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
