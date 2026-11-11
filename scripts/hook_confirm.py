r"""Claude Code PreToolUse hook: ask the user before steps that only the user decides.

Created using: $\text {Created using: }\ claude-sonnet-5-5-\text{v}5.5-\text {date: }091126$

The hook asks for confirmation (permissionDecision "ask") when a Bash command runs
- run_control.py reject or discard, or
- archive_control.py archive or restore.
These steps commit, tag, delete or restore output folders. The global rules say that only the user
decides them, so the call is shown to the user for approval even where Bash commands are otherwise
allowed. Other calls, and any error, are allowed without comment. To add a step, add a line to ASK.

Usage: hook_confirm.py [--version]   (the call JSON is read from standard input)
Inputs:  the hook JSON (`tool_name`, `tool_input.command`).
Outputs: a JSON reply on standard output when the call needs confirmation. No file is written.
Exit:    0 always.
Version: see VERSION; `--version` prints it.
"""
import json
import re
import sys

VERSION = "1.1"
# (pattern within one command segment, message)
ASK = [
    (re.compile(r"run_control\.py\b[^;&|\n]*?\s(reject|discard)(\s|$)"),
     "Only the user rejects or discards a run. Has the user asked for this?"),
    (re.compile(r"archive_control\.py\b[^;&|\n]*?\s(archive|restore)(\s|$)"),
     "Archiving or restoring an output folder changes the project tags and files. Has the user asked for this?"),
]


def main():
    if "--version" in sys.argv[1:]:
        print(f"hook_confirm.py {VERSION}")
        return 0
    try:
        call = json.load(sys.stdin)
        if call.get("tool_name") != "Bash":
            return 0
        command = call.get("tool_input", {}).get("command", "")
        for pattern, message in ASK:
            if pattern.search(command):
                print(json.dumps({"hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": message}}))
                return 0
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
