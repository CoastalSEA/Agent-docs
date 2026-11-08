# Hook template

A prompt to hand to Claude to create a hook. Fill in the brackets. Hook guide: https://code.claude.com/docs/en/hooks-guide

A hook is a command, prompt or agent that Claude Code runs at a fixed point in its lifecycle. It enforces a rule in code instead of asking the model to remember it.

## Task

Create a hook that <one sentence: what it blocks, checks, formats or reports>.

## Design

- **Event:** <PreToolUse | PostToolUse | Stop | SessionStart | UserPromptSubmit | other event from the guide>.
- **Matcher:** <tool name or pattern, for example `Edit|Write` or `Bash`. Matchers are case-sensitive.>
- **Handler:** <`command` for a fixed rule; `prompt` or `agent` only where the decision needs judgement.>
- **Effect:** <block with a reason | allow | add context | log only>.
- **Scope:** <`~/.claude/settings.json` (all projects, this machine) | `.claude/settings.json` (this project, shareable) | `.claude/settings.local.json` (this project, local)>.

## How a command hook works

- Claude Code sends a JSON object on stdin with `hook_event_name`, `tool_name`, `tool_input`, `session_id` and `cwd`. For Bash, `tool_input.command` holds the command; for Edit and Write, `tool_input.file_path` holds the path.
- Exit 0: no decision, and the normal permission flow applies. Exit 2: block, and write the reason to stderr, which Claude receives. Other exit codes do not block on most events.
- To return a structured decision, exit 0 and print JSON on stdout. Use one approach per hook, not both.
- A PreToolUse hook cannot loosen a deny rule, and a deny from a hook holds in every permission mode.

## Constraints

- Keep the script in `hooks/` with no personal paths. Reference project scripts with `"$CLAUDE_PROJECT_DIR"/...`. Take interpreter and tool paths from `machine.md`.
- Parse the JSON with Python or `jq`. `jq` may not be installed.
- Normalise Windows backslashes in file paths before matching.
- On macOS and Linux the script must be executable (`chmod +x`). On Windows, hooks run under Git Bash.
- A hook that blocks must say why, in one line, on stderr.

## Acceptance criteria

- [ ] Piping a sample event to the script gives the expected exit code and message, for one case that should block and one that should pass.
- [ ] The hook appears under the right event in `/hooks`.
- [ ] A real tool call is blocked or passed as designed. Press Ctrl+O to read the hook result in the transcript.
- [ ] The settings entry is shown, and nothing else in the settings file changed.

## Out of scope

Editing other hooks, changing permission rules, or installing the hook into any settings file without being asked.

## Definition of done

The script and the settings entry are written, the tests above were run, and you have reported what each one showed.
