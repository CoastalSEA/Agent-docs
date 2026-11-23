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
- **Upgrade check.** In the first reply of each session, run `project.py status` (in `machine.md`) and tell the user if its last line suggests an upgrade. Offer the move and ask before any change. `project.py init --level <level> --templates <the claude-md folder of the Agent-docs repository>` is a dry run that lists what it would add; `--apply` writes it. If declined, save a memory note (date, counts); do not raise again unless a count doubles. Also tell the user when earlier results are not found.
- **Outputs layout.** If `project.py status` or the run control `start` reports the outputs layout undecided, ask the user to choose topics or flat before the first run, and run `run_control.py layout <choice>` with the answer. In a topic project, when the plan is agreed, draft the topic rows from its phases or work packages with their plan references, and add them with `topics add` once the user agrees the table. Add, close, reopen or rename a topic only on the user's instruction. Topics follow one axis (work phase or package, kind of work, or object of study), 4 to 8 of broadly similar size. A run that serves several phases goes in the phase that asked the question; its question records the link. A follow-up to the same question edits the note in place in the same task folder; a new folder is for a new question. Read another run's outputs through `run_control.py where <task>`, never through a literal `outputs/<task>` path.
