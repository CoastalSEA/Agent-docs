# CLAUDE.md

Guidance for Claude Code in this project.

## About this project

[One or two sentences: what the project is and what it is for.]
- input data files are held in the `data/` folder in the project root
- outputs are written to the `outputs/` folder in the project root (see the global Outputs rules; start each run with the run control command in `machine.md`)
- downloaded sources are held in the `sources/` folder in the project root, with downloaded references (papers, reports) in `sources/references/`, named `<FirstAuthor><Year>_<short title>.pdf` (for example `Kirby2000_tidal-flat-shape.pdf`; no spaces); if the project is a git repository, add `sources/` to `.gitignore`
- the handoff is held in `records/HANDOFF.md` in the project root
- start every session from the project root. Claude memory is keyed to the launch folder, so a session started from a sub-folder gets a separate, empty memory.

Use global settings for everything else.

## Project memory

Pointers only. What persists between sessions:

- `records/HANDOFF.md`: Latest handoff, overwritten each session.
- Claude memory folder: `~/.claude/projects/<launch-folder-key>/memory/`. Local, not in git. Key is the project path with separators replaced by dashes. Save durable facts (decisions, data problems, sources) one per file. Do NOT save task status here—that goes in HANDOFF.md.

## Working rules for this project

- **Search first.** Before any check, test, or data question, search `records/HANDOFF.md` and the memory folder; cite what you find.
- **Checkpoint and wrap up.** A checkpoint overwrites `records/HANDOFF.md` (3,000 characters or less): what was decided, what is open, next step. Do one when a unit of work closes or before a push. A wrap-up is a checkpoint plus a memory note for each decision or data problem. Do one at the end of a session. `wrapup_status.py` (in `machine.md`) shows whether the handoff is current. Report what changed. `/exit` skips this rule.
- **Subagents.** Include the search-first rule and pointers above in every subagent prompt.
- **Upgrade check.** In the first reply of each session, tell the user if the project has outgrown this level: `data/` holds 3+ files, `outputs/` holds 5+ runs (run tags or run folders), or earlier results aren't found. Offer to move to `project-template/` in the `claude-md/` folder of the Agent-docs repository (location in `machine.md`). Ask before any change. If declined, save a memory note (date, counts); do not raise again unless a count doubles.
