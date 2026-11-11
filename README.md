# Agent-docs

[![tests](https://github.com/CoastalSEA/Agent-docs/actions/workflows/tests.yml/badge.svg)](https://github.com/CoastalSEA/Agent-docs/actions/workflows/tests.yml)

Reusable tooling for working with Claude Code across projects: rules (`CLAUDE.md` files and
project templates), skills, an MCP server, prompt, agent and hook templates, and the scripts
that control run outputs, check project records and set up projects. A deploy script installs the shared parts
into your Claude configuration folder, and two small local files (`machine.md`, `profile.md`)
hold what differs from one user to the next.

Requires Python 3 and git. The scripts and tests pass on Windows, macOS and Linux with Python 3.12 (the
CI workflow) and on Windows with Python 3.14; older versions are not tested. Three of the six skills need
more than that (Word, EndNote or search connectors): see `skills/README.md`. Licensed under
the BSD 3-Clause licence (see `LICENSE`). To start, read the Deployment section below. To set up a project,
see Starting a project, which is in that section. To contribute, see `CONTRIBUTING.md`.

## Structure

```
CONTRIBUTING.md  how to report a problem or propose a change
.github/    the CI workflow and the issue templates
deploy.py   copies the master files to the Claude configuration folder (python deploy.py help | init | status | apply | hooks | statusline | doctor)
scripts/    project scripts and the hook scripts (usage in scripts/README.md) installed to ~/.claude/scripts: run_control.py (output folders, tags, file guard), archive_control.py, check_records.py, wrapup_status.py, rotate_records.py, hook_push_check.py, hook_guard.py, hook_confirm.py, log_retention.py, check_docx_skill.py, project.py
agents/     template for defining and tasking subagents
claude-md/  template CLAUDE.md files (global, and project at three levels) and project record stubs
hooks/      template prompt for creating a hook (the hook scripts that are installed are in scripts/)
mcp/        one subfolder per MCP server: its code, spec, generator prompt, and reports
prompts/    prompt and workflow templates not tied to one tool
records/    the decision log (the handoff file is local and ignored)
skills/     one subfolder per skill, each holding a SKILL.md
statusline/ statusline scripts for Claude Code's terminal status bar
tests/      tests for the scripts, the shared files and the skill fixtures (usage in tests/README.md)
```

## Conventions

**Item folders** (a skill, an MCP server): the files the item runs on sit in the folder (`SKILL.md`,
scripts, `README.md`). Two optional subfolders hold the rest, named by content as `<subject>-<kind>.md`:
`reference/` for files the agent reads on demand, named in the instruction, and `docs/` for records
about the item (spec, generator prompt, review and test reports), which the agent never reads at run
time. `reference/` is deployed with the item; `docs/` is not.

**MCP servers** (`mcp/<name>/`): the server code and a `README.md`, with the spec, the generator prompt
and any reports in `docs/`. See `mcp/endnote/` for the pattern.

**Skills** (`skills/<name>/SKILL.md`): a skill lives in its own folder named to match the
skill, regardless of whether it is deployed at project scope (`.claude/skills/`) or user
scope (`~/.claude/skills/`) in a given project. See `skills/skill_location.md` for the
mechanics of project-level vs. user-level vs. plugin-based deployment.

**Hooks**: `hooks/` holds the template prompt for creating a hook. The hook scripts that `deploy.py hooks` registers (`hook_push_check.py`, `hook_guard.py`, `hook_confirm.py`) are in `scripts/`, with their tests.

**Agents, prompts, settings, statusline, claude-md**: each is lower-volume than skills/mcp,
so no per-item subfolder convention yet — see each folder's own `README.md` for what
belongs there.

## Wrap-up and records

A project keeps its memory of what was done in files, so a new session (or a new person) can pick up
the work. The rules are in the global `CLAUDE.md` and the project `CLAUDE.md`; the scripts are in
`scripts/` and the hooks are optional.

**The record files** (in the project root):

| File | Holds | Kept |
|---|---|---|
| `records/HANDOFF.md` | State, open items, next step. Overwritten each time; 3,000 characters or less. | Local, git-ignored |
| `records/DECISIONS.md` | One row per decision: date, decision, reason, evidence. About 500 characters a row; 100 rows. | In git |
| `records/DECISIONS-archive.md` | Older decision rows moved out by `rotate_records.py`. Nothing is deleted. | In git |
| Claude memory notes | Durable facts (decisions, data problems, sources), one per file. Not task status. | Local, `~/.claude/projects/` |

**Three levels of recording:**

1. **Decision line.** Claude adds a row to `DECISIONS.md` when a decision is made, including a decision
   not to do something, with the reason and the evidence (a commit or a file).
2. **Checkpoint.** Claude overwrites `HANDOFF.md`: what was decided, what is open, the next step. Do one
   when a unit of work closes or before a push. Say "checkpoint".
3. **Wrap-up.** A checkpoint plus the missing decision lines, the `outputs/INDEX.md` update and a memory
   note for each decision or data problem. Do one at the end of a session. Say "wrap up". `/exit` skips it.

**What is automatic and what is not:**

- Automatic, with the push hook installed (`python deploy.py hooks`): `git push` is blocked while the
  handoff is stale, so Claude writes a checkpoint first. The hook acts only in a framework project (its
  `CLAUDE.md` names `machine.md`, as every project template does) that has a `records/` folder. Commits are not checked, so mid-task commits need no checkpoint.
- Not automatic: the checkpoint when you do not push, and the end-of-session wrap-up. Ask for them. Claude
  also suggests a checkpoint before a commit that closes a piece of work, and a wrap-up at the end of a session.
- Without the hooks, the rules still apply, but nothing enforces them.

**Checking the state:**

- `wrapup_status.py` reports whether the handoff is current. It is stale when a changed file (uncommitted,
  or in a commit not yet pushed) is newer than the handoff. It exits 1 when stale or missing.
- `check_records.py` checks the record files against the project: cited paths exist, run tags and INDEX
  rows match, memory notes are linked, decision rows are not too long.
- `rotate_records.py` moves the oldest decision rows to the archive when the log passes 100 rows. It
  shows what it would move unless `--apply` is given.
- `project.py status` reports which project template level a project is at and whether it has outgrown it.
  `project.py init --level minimal|handoff|full` adds the missing template files; it is a dry run unless
  `--apply` is given and it never overwrites a file.

Usage of each script, and the commands to run them, are in `scripts/README.md`.

## Protection and permissions

Four layers limit what a session can do, and they work in every permission mode:

- **Rules.** The global `CLAUDE.md` says to ask before any step that sends data off the machine or changes a live system, never to touch input data or bibliography entries, and that a direct instruction to do a named step is the permission for it.
- **Permission rules in `settings.json`.** Ask rules prompt before a push, and deny rules refuse reads of secrets, force pushes and other destructive commands. You write these yourself: `deploy.py` does not install them.
- **Hooks (optional, `python deploy.py hooks`).** One blocks `git push` while the handoff is stale, one blocks writes to `data/` and protected paths, and one asks before a run is rejected or discarded or an output folder is archived or restored.
- **Run control.** `run_control.py` keeps each run pending until you review it, and its file guard and data check refuse to commit oversize files or changed inputs.

The push check and the `data/` guard act only in a framework project: a folder whose `CLAUDE.md` names `machine.md`. Any other folder is left alone, so a project with its own `data/` folder is not blocked. Paths listed in `rules/protected-paths.txt` are protected in every folder. The hooks guard against slips and are not a lock. `scripts/README.md` explains each hook, the commands that prompt, the commands that are refused, how permission modes change this, and how to change or turn off a hook (see `hook_confirm.py` there). `claude-md/global-CLAUDE.md` holds the rules.

## Tests

```
python -m unittest discover -s tests
```

`tests/test_scripts.py` runs the project scripts (`run_control`, `archive_control`, `check_records`, `wrapup_status`, `rotate_records`, `project`), the three hook scripts, `log_retention.py`, `check_docx_skill.py` and `deploy.py` in throwaway projects. Usage and what each test file covers are in `tests/README.md`.
`tests/test_framework.py` checks the shared files: no machine-specific text, the template copy equals its master, skill
frontmatter parses, the user-file forms keep their marker lines, every script has a version, and `deploy.py` installs
every script and skill. Neither touches `~/.claude`. `tests/test_skill_fixtures.py` tests the skill fixtures without a model; `tests/skills/run_fixtures.py` runs skills on those fixtures with headless Claude Code sessions, by hand (see `tests/skills/README.md`). `.github/workflows/tests.yml` runs both on Windows, macOS and Linux
for each push to `main`.

## Deployment

This repo is the source of truth for the tooling it holds, not the live, deployed copy. The
script `deploy.py` copies part of it to the Claude configuration folder (`~/.claude`). It needs
only Python 3 and no other package. Run it from the repo root with any Python 3 interpreter
(the command for this machine is in `machine.md`):

```
python deploy.py [help|init|status|apply|hooks|statusline|doctor] [--target PATH] [--diff] [--yes]
```

`python deploy.py help` prints these instructions.

### First-time setup on a machine

Two small files hold what differs from one user to the next: `~/.claude/rules/machine.md` (the
system, shells, interpreter and tool paths, and locations) and `~/.claude/rules/profile.md` (your
own writing rules and code header format). They are never stored in this repo. `init` creates both.

1. **Terminal.** Run `python <path>/deploy.py init`, where `<path>` is the full path of this repository
   (it is different on each machine). The short form `python deploy.py init` works
   only when the terminal is already in the repository folder. It detects the operating system, shells, Python,
   and R, MATLAB and Tesseract if they are installed. It shows what it found and the text it will
   write, then asks `[y/N]`. It creates `machine.md` and a short `profile.md` stub, and it never
   overwrites a file that exists. To do this by hand instead, copy
   `claude-md/user-files/machine.example.md` and `profile.example.md` to `~/.claude/rules/`
   and fill them in.
2. **Terminal.** Review the files. Add what `init` could not detect: the EndNote library and
   server, rules for Python environments, and a private companion repository if you keep one. Write
   `profile.md` by hand, because it holds your own rules. A Claude session can help with
   `machine.md`, but it must report each assumption and leave blank what it cannot detect.
3. **Terminal.** Run `python deploy.py status`, then `python deploy.py apply`. This installs the
   global rules, the skills and the scripts. `apply` asks `[y/N]` at a terminal. Read "Before you
   run `apply`" below first if you already use Claude Code.
4. **Terminal.** Run `python deploy.py doctor`. It must report no problems. Run it after
   `apply`, because `machine.md` names the scripts that `apply` installs.
5. **New Claude session.** Ask it to quote the `Marker:` line of each file. A missing rules file
   fails silently, and `doctor` cannot test that a session loads the files.

   In a project folder, a skill or a session that reads `~/.claude/rules/machine.md` is reading outside the
   working directory, and Claude Code may ask first ("Read outside the working directories", with an option to keep
   allowing such reads). If the answer is no, or the read is blocked, a session cannot see `machine.md` and a
   subagent reports that it cannot find it. Allow the read, or add the allow rule `Read(~/.claude/rules/**)` to
   `~/.claude/settings.json`.

**Before you run `apply`.** `apply` overwrites a live file that differs from its repository copy: your
`~/.claude/CLAUDE.md`, any skill with the same name as one in `skills/`, and the scripts in
`~/.claude/scripts/`. Edits you made to those live files are replaced. It copies each file it replaces to
`<target>/backups/deploy-<DDMMYY-HHMM>/` first, but that is one level of backup, and a second `apply` adds a
new folder and does not restore anything. It never touches `rules/machine.md`, `rules/profile.md`,
`settings.json`, or skills and files that are not in this repository, and it never deletes.

Read `claude-md/global-CLAUDE.md` before `apply`, because it becomes your global rules for every project. Some
of its rules were written for research work: how to report a mean and a coefficient of determination, and never
to change a bibliography entry. If a rule does not suit your work, change the repository copy before `apply`.

To leave a skill out, list its name in `~/.claude/rules/skip-skills.txt`, one name per line (`#` starts a
comment). `status` shows it as skipped and `apply` does not install it. `skills/README.md` lists what each skill needs.

If you already have a `~/.claude/CLAUDE.md`, skills or scripts of your own:

1. Run `python deploy.py status --diff` and read what would change.
2. Back up your configuration folder yourself first (copy `~/.claude`, or at least `CLAUDE.md`, `skills/`
   and `scripts/`, to a safe place).
3. If you want to keep edits you made to a live file, merge them into the repository copy before `apply`,
   because `apply` makes the live file equal to the repository.
4. Try it on a scratch folder first: `python deploy.py apply --target <empty folder>`.

Optional: `python deploy.py hooks` adds three hooks to `~/.claude/settings.json`: block `git push` while
`records/HANDOFF.md` is stale, block writes to `data/` and listed protected paths, and ask before reject, discard, archive and restore (`scripts/hook_*.py`, usage in `scripts/README.md`). `python deploy.py hooks --retention-notice` also adds a start-of-session notice when session transcripts of the project are about to be deleted (`scripts/log_retention.py`; the retention period is `cleanupPeriodDays` in `settings.json`). It uses the interpreter named on the Python
line of `rules/machine.md` (the Python running `deploy.py` if there is none), so run `init` and `apply` first. It backs up `settings.json` and keeps other settings.

In a Claude session, ask the user before running `init`, `apply` or `hooks`, because each writes under
`~/.claude`. Without a terminal they need `--yes`.

| Task | Terminal | Claude session |
|---|---|---|
| `help`, `status`, `doctor` | Yes | Yes (read only) |
| `init` | Yes (preferred, with the `[y/N]` prompt) | Only after the user agrees |
| Edit `machine.md` | Yes | Yes, for what `init` could not detect, with assumptions reported |
| Edit `profile.md` | Yes | Not recommended (your own rules) |
| `apply` | Yes (preferred, with the `[y/N]` prompt) | Only after the user agrees |
| `hooks` | Yes (preferred, with the `[y/N]` prompt) | Only after the user agrees |
| Confirm that the files load | No | Yes (new session only) |

### Starting a project

Each project has its own `CLAUDE.md`, at one of three levels: minimal (`CLAUDE.md` only), handoff (adds a handoff
file) and full (adds the data notes, the output index, the decision log and a `.gitignore`). Start at minimal;
`claude-md/README.md` says when to move up. `scripts/project.py` sets a project up (the command forms are in
`machine.md`; details are in `scripts/README.md`):

1. **Terminal, in the project folder.** Preview the files:
   `python <path>/scripts/project.py init --level minimal --templates <path>/claude-md`, where `<path>` is the full
   path of this repository (it is different on each machine, and a relative path does not work from the project
   folder). This is a dry run and writes nothing.
2. **Terminal.** Add `--apply` to write them. It adds only what is missing, never overwrites a file, and adds
   the missing lines to `.gitignore`.
3. **Editor.** Replace the placeholder sentence in the new `CLAUDE.md` with one or two sentences on what the
   project is for.
4. **Claude session.** Start Claude Code from the project root. In the first reply of each session the model runs
   `project.py status` and tells you when the project has outgrown its level. To move up, run `init` again with
   `--level handoff` or `--level full`. An existing `CLAUDE.md` is left as it is, and you merge the new one by hand.
5. **Claude session.** Check the setup: ask "check project setup is clean". The model reports the template level,
   the files that are missing and whether the folder is a git repository. If it is not, the model may offer to run
   `git init`, and you can answer yes. Without git, each run gets its own `outputs/<task>-<DDMMYY>-run<N>/` folder
   and the run control steps that tag and commit do not apply.

### Commands

| Command | What it does | Writes anything? |
|---|---|---|
| `help` | Prints the Deployment section of this README. | No |
| `init` | Creates `<target>/rules/machine.md` from values detected on this machine, and `profile.md` as a stub, only for a file that does not exist. Shows the detected values and the text first, then asks `[y/N]` at a terminal. Without a terminal it creates nothing unless `--yes` is given. Never overwrites. | Yes (new files only) |
| `status` (default) | Lists each master file as `same`, `DIFFERS` or `MISSING` against its live copy. Files that differ only in line endings show as `same*` and are not copied. Lists live skills that are not in the repo, and leaves them alone. Exits 1 if any file would be copied. `--diff` also prints a unified diff for each differing text file. | No |
| `apply` | Rewrites `claude-md/project-template/CLAUDE.md` from `claude-md/project-CLAUDE.md` (the master), copies each file that differs or is missing, then compares again. Before it replaces a live file it copies that file to `<target>/backups/deploy-<DDMMYY-HHMM>/`. It asks `[y/N]` at a terminal. Without a terminal it copies nothing unless `--yes` is given. | Yes |
| `hooks` | Adds the three hooks (push check, guard, confirm), and with `--retention-notice` the start-of-session retention notice, to `<target>/settings.json`, using the interpreter named in `machine.md`. Keeps every other setting, backs the file up to `<target>/backups/hooks-<DDMMYY-HHMM>/`, does nothing if the hooks are already there, and asks `[y/N]` at a terminal (`--yes` without one). Run `apply` first so the scripts exist. | Yes (`settings.json`) |
| `statusline` | Optional, and not part of `apply`. Copies `statusline/statusline-command.sh` to `<target>/statusline-command.sh` and sets `statusLine` in `<target>/settings.json` (needs `bash`). Shows what it will do and asks `[y/N]` at a terminal (`--yes` without one). Backs up a live script or `settings.json` that it changes to `<target>/backups/statusline-<DDMMYY-HHMM>/`, keeps every other setting, and does nothing if it is already installed. A different `statusLine` is replaced only if you agree to that separately (a terminal answer, or `--replace-statusline` with `--yes`). | Yes (the script and `settings.json`) |
| `doctor` | Checks `~/.claude/rules/machine.md` and `profile.md`: each file is present, has its `Marker:` line and is filled in, and every absolute path named in `machine.md` exists. Exits 1 on any problem. It also shows whether the `docx` skill scripts that `proofread` uses are present and unchanged since they were last accepted; that part is a warning and never a problem. | No |

`--target PATH` points the script at another configuration folder. Use a scratch folder to
test. In a Claude session, ask the user before running `apply`, because it changes live
configuration.

### What deploy installs

| Repo file | Live file |
|---|---|
| `claude-md/global-CLAUDE.md` | `<target>/CLAUDE.md` |
| `skills/<name>/` (each folder with a `SKILL.md`, every file in it except `docs/`; not a skill named in `<target>/rules/skip-skills.txt`) | `<target>/skills/<name>/` |
| `scripts/*.py` (the project scripts and hook scripts) | `<target>/scripts/` |
| the three hooks in `scripts/hook_*.py`, and with `--retention-notice` the `SessionStart` entry for `log_retention.py` (only the `hooks` command, not `apply`) | entries in `<target>/settings.json` |
| `statusline/statusline-command.sh` (only the `statusline` command, not `apply`) | `<target>/statusline-command.sh`, and the `statusLine` entry in `<target>/settings.json` |

### What deploy does not install

- **Other hooks and agents.** The `hooks` command registers only the three hooks above. Anything else
  made from the `hooks/` template, and the agents in `agents/`, are copied or registered by hand.
- **The status line, unless you ask for it.** `apply` does not install it. The `statusline` command does
  (see Commands).
- **MCP servers.** Register them with `claude mcp add`, pointing at this repo's copy (see
  below).
- **Project-scope skills.** Skills go to the user scope only (`<target>/skills/`). A skill used in
  one project only is copied into that project's `.claude/skills/` by hand.
- **Project templates.** `deploy.py` does not copy the template folders in `claude-md/` anywhere. It only
  keeps the two copies of the project `CLAUDE.md` in step. A project is set up with `scripts/project.py init`
  (see Starting a project above), or by copying a template folder by hand.
- **Updates to the two local user files.** Only `init` writes `machine.md` and `profile.md`, and only
  when a file is missing. Nothing updates or overwrites them. The blank forms are in
  `claude-md/user-files/`.
- **Prompts.** The templates in `prompts/` are copied into a task by hand.
- **Deletions.** The script never deletes. A skill removed or renamed in the repo stays in the
  live folder until it is removed by hand. Live skills with no repo copy are listed and left alone.

### Notes

- The scripts and tests pass on Windows, macOS and Linux (the workflow in `.github/workflows/tests.yml`). The
  interactive parts have only been used on Windows: skills, the status line, the EndNote server and the machine files.
- After a Claude Code update or a skill sync, the `proofread` summary and `deploy.py doctor` warn if the `docx` skill scripts it uses have changed. Re-run `python tests/skills/run_fixtures.py proofread proofread-structure` (see `tests/skills/README.md`), then `check_docx_skill.py --accept` (see `scripts/README.md`).
- A skill edited in a session does not take effect until a new session starts.
- Permission modes. The rules and settings here use ask and deny rules only, which apply in every mode. The skills work in
  any mode, but in the default mode each shell, Python and PowerShell call asks for approval. The fixture runner needs auto
  mode and checks for it first (see `tests/skills/README.md`).
- Before the script, files were copied by hand and checked with `diff`. The script replaces
  that routine for the files in the table above.
- For skills, see `skills/skill_location.md` for project-level, user-level and plugin-based
  deployment. When an MCP server's code lives here, its registration should point directly at
  this repo's copy rather than a project-local duplicate.

## Acknowledgement

The starting point for many of the ideas contained in this repo, especially the structure of prompts, skills and hooks comes from the excellent course led by Prof. Charles Crabtree (see https://charlescrabtree.org/), entitled "AI Agent-Driven Research Workflows", organised by AI Horizons.