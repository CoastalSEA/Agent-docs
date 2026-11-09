# CLAUDE.md

Guidance for Claude Code in this project.

## About this project

[One or two sentences: what the project is and what it is for.]
- input data files are held in the `data/` folder in the project root
- outputs are written to task folders in the `outputs/` folder in the project root. `outputs/` is tracked in git, and each accepted run is a git tag (see the global Outputs rules)
- analysis scripts are saved in the `code/` folder and start each run with `start <task>` of the run control command in `machine.md` and write into the folder it prints. When the user accepts, rejects or discards a run, use its `accept`, `reject` or `discard`
- downloaded sources are held in the git-ignored `sources/` folder in the project root, with downloaded references (papers, reports) in `sources/references/`, named `<FirstAuthor><Year>_<short title>.pdf` (for example `Kirby2000_tidal-flat-shape.pdf`; no spaces). The user decides which to keep and makes any `.ris` import file
- project records (decisions, handoff) are held in the `records/` folder in the project root
- start every session from the project root. Claude memory is keyed to the launch folder, so a session started from a sub-folder gets a separate, empty memory.

## Environment, Code standards, Analysis rules, Methodological guardrails, Hard boundaries, Outputs, What done means

Use global settings, `machine.md` and `profile.md`, with the two exceptions below.
- `data/DATA-NOTES.md` is documentation, not input data. It may be edited.
- `outputs/INDEX.md` sits in the `outputs/` folder, not in a task folder. It may be edited.

## Project memory

Pointers only. What persists between sessions:

- `data/DATA-NOTES.md`: One entry per data file (source, row order, units, links, problems). Links to per-file READMEs in `data/`; does not copy them.
- `records/DECISIONS.md`: One line per decision: `DDMMYY | decision | reason | evidence file`.
- `outputs/INDEX.md`: One line per accepted run: run tag (or legacy run folder), task folder, question answered, status (current, superseded or not adopted) and replacement.
- `products/PRODUCTS.md`: register of large generated files in the git-ignored `products/` folder, with the rule for what goes there (script-made files over the file guard limit, any video or animation, intermediates a later script reads; not downloaded files, which go in `sources/`). Each file has script, run tag, size and hash. Git does not hold them: keep a copy elsewhere.
- Archived runs: the archive control command `archive <task>` (in `machine.md`) removes a task folder from the working tree and keeps it under the tag `archive-<task>-<DDMMYY>` (INDEX status archived); `restore <task>` brings it back. Run tags and INDEX rows stay valid.
- `records/HANDOFF.md`: Latest handoff, overwritten each session.
- Claude memory folder: `~/.claude/projects/<launch-folder-key>/memory/`. Local, not in git. Key is project path with dashes for separators. Save durable facts and pointers only. Do NOT save task status here—that goes in HANDOFF.md.

## Working rules for this project

- **Search first.** Before any check, test, or data question, search `data/DATA-NOTES.md`, `records/DECISIONS.md` and `records/DECISIONS-archive.md` (if it exists), `outputs/INDEX.md`, `records/HANDOFF.md`, and the memory folder; cite what you find.
- **Keep the records current.** The run control `accept` and `reject` add the `INDEX.md` line and mark the superseded run; edit a status by hand only when later work changes what a run means. A pending (uncommitted) run gets no line until it is accepted. Add a line to `DECISIONS.md` for every decision when it is made, with reason and evidence file. Keep a line to about 500 characters; detail goes in the commit message or run record.
- **Checkpoint and wrap up.** A checkpoint overwrites `records/HANDOFF.md` (3,000 characters or less): what was decided, what is open, next step. Do one when a unit of work closes or before a push. A wrap-up is a checkpoint plus the missing lines in `DECISIONS.md` and `INDEX.md`, changed memory notes, and a check of the handoff against those files. Do one at the end of a session. `wrapup_status.py` (in `machine.md`) shows whether the handoff is current. Report what changed. `/exit` skips this rule.
- **Check the records at wrap-up.** Before reporting wrap-up done, run the run control `status` and `check_records.py` (both in `machine.md`) from project root. Report pending runs and file guard failures. Fix or flag each failure:
  - All paths cited in `DATA-NOTES.md`, `DECISIONS.md`, `INDEX.md` exist; session log citations point to messages.
  - Every run tag has one line in `INDEX.md`; every line names an existing tag or legacy run folder; every folder in `outputs/` appears in `INDEX.md`.
  - Flag: uncommitted changes under `outputs/` (a run pending review; its task folder needs no `INDEX.md` line until it is accepted).
  - Every file in `data/` has an entry in `DATA-NOTES.md`; every entry names an existing file.
  - Flag: file in `data/` modified after `DATA-NOTES.md` (entry may be stale).
  - Flag: evidence file in `DECISIONS.md` modified after its line date (possibly stale; check before relying).
  - Every memory note is listed in `MEMORY.md`; every link resolves.
  - Flag: memory note containing status word (awaiting, pending, not yet, draft), missing path, or file modified after note date (review and correct or delete).
  - Flag: file listed in `products/PRODUCTS.md` that is missing from `products/`.
  - Flag: `DECISIONS.md` row over 800 characters, or more than 100 rows or 60,000 characters. Fail: a row over 1,000 characters dated 091126 or later. Move the oldest rows with `rotate_records.py`.
  
  Report counts and flags in wrap-up. Note: check cannot detect wrong status in `INDEX.md`—update manually when work changes what a run means.
- **Subagents.** Include the search-first rule and pointers above in every subagent prompt.
- **Clean-start runs.** A run told to ignore earlier results may still read `DATA-NOTES.md` (data facts are not results). It reads `DECISIONS.md`, `INDEX.md`, and earlier outputs only if the task says so.

## Project progress

Current state and next step only. Decisions go in `DECISIONS.md`, not here.

