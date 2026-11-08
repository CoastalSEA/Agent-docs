# CLAUDE.md

Guidance for Claude Code in this project.

## About this project

This repo maintains version-controlled copies of CLAUDE.md files, prompt templates, skills, and other deployable assets (installed to `~/.claude/` by `deploy.py`, or used for project-specific setups).

- Skills: `skills/<name>/SKILL.md` (live copies in `~/.claude/skills/`)
- Version-controlled CLAUDE: `claude-md/global-CLAUDE.md` (live at `~/.claude/CLAUDE.md`); blank forms for the local `machine.md` and `profile.md` in `claude-md/user-files/
- Outputs and working files: `outputs/` and `working_docs/` (git-ignored, not repo content). Outputs here are test runs, so the global rule for git-ignored outputs applies: one `<task>-<DDMMYY>-run<N>` folder per run
- Shared run script: `scripts/run_control.py` (installed by `deploy.py` to `~/.claude/scripts/`; skills call it)
- Session records: `records/` (handoff, decisions)
- Private companion repository (optional): templates, settings, working documents and the private decision log; its location is under Locations in `machine.md`
- Start every session from project root—Claude memory is keyed to the launch folder

## Environment, Code standards, Analysis rules, Methodological guardrails, Hard boundaries, Outputs, What done means

Use global settings, `machine.md` and `profile.md`. Scripts use the interpreter in `machine.md`; the `.venv` here, made by Positron, holds only `pip` and is git-ignored.

## Project memory

Pointers only. What persists between sessions:

- `records/HANDOFF.md`: Latest handoff, overwritten each session. Git-ignored, local only.
- `records/DECISIONS.md`: One line per decision: `DDMMYY | decision | reason | evidence`. Search `git log` for what changed and why.
- Claude memory folder: `~/.claude/projects/<launch-folder-key>/memory/`. Local, not in git. Save durable facts (sources, machine state) one per file. Do NOT save task status here—that goes in HANDOFF.md.

## Working rules for this project

- **Search first.** Before any check, test, or design question, search `records/HANDOFF.md`, `records/DECISIONS.md`, `git log`, and the memory folder; cite what you find.
- **Keep decisions current.** Add a line to `records/DECISIONS.md` for every decision, with reason and evidence (commit hash, file, or session log line). Record decisions NOT to do something—those get re-argued. Decisions about files in this repository go in this log, without user quotes or session-log citations. Decisions about private material (templates, settings, personal rules) go in the private companion's log; its location is in `machine.md`.
- **Wrap up.** When the user says "wrap up", overwrite `records/HANDOFF.md`: what was decided, what is open, next step. Keep it short. Add missing lines to `records/DECISIONS.md`. Report what changed. `/exit` skips this rule.
- **Deploy and check.** After editing a skill, `claude-md/global-CLAUDE.md` or `scripts/run_control.py`, run `deploy.py status` and ask before `apply`—this changes live config. `apply` backs up each live file it replaces and compares again. After changing the local `machine.md` or `profile.md`, run `deploy.py doctor`.
- **New skills.** Follow `prompts/new-skill-workflow.md`. Run `skills/check_frontmatter.py` (Python from `machine.md`) before deploying; keep the description to one line. Failed parse is silent—skill won't fork. A skill is done only after a fresh session produces a correct deliverable, tested from PowerShell (not Git Bash). A skill edited mid-session doesn't take effect—test in a new session. Delete test artifacts when confirmed; do not commit them.
- **Keep instruction text short.** Instruction files (`CLAUDE.md` files, templates, skills, prompts, agents, hooks) say only what the agent must do. They carry no dates, test history or reasons for a change: those go in one DECISIONS line (decision, reason, evidence as pointers). Before adding a sentence, change an existing one. Long reference material goes in a separate file that the instruction names.
- **Keep copies in step.** `claude-md/project-CLAUDE.md` is the master of `claude-md/project-template/CLAUDE.md`. Edit the master only; `deploy.py apply` writes the copy. Update affected `README.md` when folder content changes.
- **Commit and push only when the user asks.**
- **Subagents.** Include the search-first rule and pointers above in every subagent prompt.
