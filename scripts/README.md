# Scripts

Project scripts for output control, project records and Claude Code hooks. They are written for Python 3 and use only the standard library. `deploy.py apply` installs them to `~/.claude/scripts/`. They are not copied into projects.

## Running a script

Run each script with the interpreter and path given in the live `machine.md` (do not use plain `python` unless `machine.md` says it works):

```
<python> <scripts folder>/<script>.py <command> [arguments] --root "<project root>"
```

- `--root` may stand anywhere in the command line. The default is the current folder.
- `--version` prints the script name and version.
- Exit code 0 means success. Exit code 1 means a refused step or a failed check, with the reason on standard error or in the report.

| Script | Purpose |
|---|---|
| `run_control.py` | Output folders, run tags and the file guard |
| `archive_control.py` | Archive and restore task output folders |
| `check_records.py` | Check the record files and memory notes against the project |
| `wrapup_status.py` | Report whether `records/HANDOFF.md` is current |
| `rotate_records.py` | Move the oldest decision lines to an archive |
| `project.py` | Report the project template level and add the missing template files |
| `hook_push_check.py` | Claude Code hook: block `git push` while the handoff is stale |
| `hook_guard.py` | Claude Code hook: block writes to `data/` and to listed protected paths |
| `hook_confirm.py` | Claude Code hook: ask the user before accept, reject, discard, archive or restore |
| `log_retention.py` | Report session transcripts of a project that will be deleted soon; optional start-of-session notice |
| `check_docx_skill.py` | Find the `docx` skill scripts that `proofread` uses, check their interface and warn when they change |

## run_control.py

Prepares and closes the output folder of a task, `outputs/<task>/`. In a git project where `outputs/` is tracked, a run overwrites the task folder and stays pending until you review it. Otherwise each run gets a new folder `outputs/<task>-<DDMMYY>-run<N>/`.

| Command | What it does |
|---|---|
| `start <task>` | Prepares the folder, writes `run_info.txt` and prints the absolute path. Run it before a task writes outputs. |
| `path <task>` | Prints the folder a `start` would use. Changes nothing. |
| `check <task> [--allow F]` | Runs the file guard and shows what `accept` would commit. |
| `accept <task> ["question"] [--allow F]` | Guard, commit, annotated tag and `outputs/INDEX.md` row (if the project keeps one). |
| `reject <task> ["question"] [--allow F]` | As `accept`, with the tag suffix `-rejected` and the status "not adopted". |
| `discard <task>` | Restores the folder to the last accepted run and deletes pending files. Ask first. |
| `status` | Lists pending task folders, guard failures and tags with no INDEX row. |

- Only the user accepts, rejects or discards a run.
- Without a question, `accept` and `reject` reuse the question of the last tag of the task.
- The file guard excludes `.pdf .docx .pptx .zip .7z .rar .gz .pyc` and Office lock files. Images may be up to 1 MB, other files up to 5 MB, and a folder up to 25 MB. `--allow <file>` (repeatable, path relative to the task folder) passes a named file.
- Task names are reduced to letters, digits, `-` and `_`.
- Data check: `start` records the state of `data/` (names, sizes and times; not `DATA-NOTES.md` or README files) in `run_info.txt`. If `data/` differs later, `check` fails and `accept` and `reject` refuse, naming the files changed after the start. Deleted files are only counted. `--data-changed-ok` passes it once the user has reviewed the change. Runs without a record are not checked.

Example: `<python> run_control.py start trend-fit --root "<project root>"`

## archive_control.py

Removes finished task folders from the working tree without losing them. The folder stays in git history and under the tag `archive-<task>-<DDMMYY>`. Run tags and INDEX rows stay valid.

| Command | What it does |
|---|---|
| `archive <task> [<task> ...] [--message TEXT] [--no-commit]` | Refuses unless the folder is committed, unchanged, has no git-ignored files and has a `current` row in `outputs/INDEX.md`. Then tags, marks the row `archived`, removes the folder and commits the removal with `INDEX.md`. |
| `restore <task>` | Checks the latest archive tag out into `outputs/<task>/` (staged, not committed) and sets the row back to `current`. |
| `list` | Prints the archived tasks and their tags. |

## check_records.py

Checks `data/DATA-NOTES.md`, `records/DECISIONS.md`, `outputs/INDEX.md` and the Claude memory notes for the project against the files and git tags.

```
<python> check_records.py [project root] [--root <project root>] [--max N] [--memory DIR] [--max-lines N]
```

- Failures set exit code 1: cited paths that do not exist, bad session log citations, INDEX rows that do not match runs or tags, data files that do not match `DATA-NOTES.md`, memory index problems, and a decision row over 1,000 characters dated 091126 or later.
- Flags are for review and do not set the exit code: stale memory notes, files changed after the entry that describes them, uncommitted outputs, decision rows over 800 characters, and a log with more than `--max-lines` rows (default 100) or 60,000 characters.
- `--max N` limits the lines listed per flag (default 40).
- `--memory DIR` overrides the memory folder (default `~/.claude/projects/<launch-folder-key>/memory/`).
- A missing record file is reported and its checks are skipped.
- No file is written.

## wrapup_status.py

Shows whether the handoff is current, so a checkpoint is not forgotten.

```
<python> wrapup_status.py [--root <project root>] [--max-lines N] [--quiet]
```

- The handoff is `records/HANDOFF.md`. It is stale when a changed file is newer than it. Changed files are uncommitted files and, if the branch has an upstream, files in commits not yet pushed. The handoff itself is not counted.
- The report gives the handoff age, the counts of uncommitted and unpushed files, pending runs, decision lines added since the last commit and the size of the decision log.
- The last line is `Status: CURRENT` or `Status: STALE, a checkpoint is needed (...)`. `--quiet` prints only that line.
- Exit code 0 if current, 1 if stale or missing, 2 if the folder cannot be used. No file is written.

## rotate_records.py

Keeps `records/DECISIONS.md` short by moving its oldest rows to `records/DECISIONS-archive.md`. Nothing is deleted: the rows of the two files add up to the original, and line endings are kept.

```
<python> rotate_records.py [--root <project root>] [--max-lines N] [--apply]
```

- Without `--apply` it prints what it would move and changes nothing. Run that first.
- `--max-lines` is the number of rows to keep (default 100).
- Run it again later and the next oldest rows are appended in order.
- The report gives the size of the active log in characters, now and after the move, against the 60,000-character limit that `check_records.py` applies. When the log is over the limit it names the `--max-lines` value that fits, which can be smaller than the row limit.

## project.py

Reports which project template level a project is at (minimal, handoff or full), whether it has outgrown it, and adds the files of a level that are missing. The upgrade check in the minimal and handoff `CLAUDE.md` files calls `status`, so the counts are not made by hand.

```
<python> project.py status [--quiet] [--root <project root>]
<python> project.py init --level minimal|handoff|full [--apply] --templates <claude-md folder> [--root <project root>]
```

- `status` prints the level in use, the number of files in `data/` (not `DATA-NOTES.md` or README files), the number of runs (task folders and git tags that look like `<task>-<DDMMYY>-run<N>`), the number of notes in the Claude memory folder for the project, the recommended level and the files each level is missing. The last line is `Status: OK at <level>`, `Status: UPGRADE SUGGESTED to <level>` or `Status: NO TEMPLATE`; `--quiet` prints only that line. Nothing is written.
- The recommendation: from minimal or handoff to full when `data/` holds 3 or more files or there are 5 or more runs; from minimal to handoff when the memory folder holds notes or there are earlier runs. The script cannot count a repeated check because an earlier result was not found, so the handoff template still names it.
- `init` is a dry run unless `--apply` is given. It adds the files of the level that are missing, never overwrites a file, and appends the missing lines to `.gitignore` (the `sources/` line at least, in a git project). An existing `CLAUDE.md` that differs from the template is left as it is and named, so that it is merged by hand.
- `--templates` is needed when the script is run from `~/.claude/scripts/`. It is optional when the script is run from the repository.
- The memory folder is `~/.claude/projects/<project path with dashes>/memory/` (under `CLAUDE_CONFIG_DIR` if that is set).
- Exit code 0 on success, 2 if the folder or the templates cannot be used.

## hook_push_check.py

A Claude Code `PreToolUse` hook. It stops `git push` while the handoff is stale, so the handoff goes with the work. It is not run by hand.

- It reads the tool call as JSON on standard input. It acts only on Bash commands that contain `git push` (words inside quotes or a here-document are ignored, except after `-c` or `eval`), and only in a project with a `records/` folder. It runs `wrapup_status.py` there.
- If the handoff is stale or missing, it exits with code 2 and a message. Claude then writes a checkpoint and pushes again. In every other case, and on any error, it exits 0 and the call goes ahead. Commits are not checked.
- Install it with `python deploy.py hooks` from the repository root (it installs all three hooks). That adds one entry for each to `~/.claude/settings.json`, using the interpreter named in `machine.md`, and backs the file up first. Start a new session for the hooks to load.
- Test it by hand: `echo '{"tool_name":"Bash","tool_input":{"command":"git push"},"cwd":"<project root>"}' | <python> hook_push_check.py; echo $?`

## hook_guard.py

A `PreToolUse` hook that blocks writes to protected files with exit code 2 and a message.

- Protected: the project `data/` folder, except `data/DATA-NOTES.md` and README files; and every path in `~/.claude/rules/protected-paths.txt` (one absolute path per line, a file or a folder, `#` for comments; for example the EndNote library file and its `.Data` folder).
- It checks the target of Write, Edit, MultiEdit and NotebookEdit, and each Bash command segment that names a protected path and redirects into it (`>`, `>>`), uses a writing command (`rm`, `mv`, `sed -i`, `tee`, `del`, `Remove-Item`, `Set-Content`, `Out-File` and similar) or copies onto it. Reading and copying out of a protected folder are allowed.
- A `cd` earlier in the command moves the folder that relative paths are read against; a `cd` to a variable makes later relative paths unknown, and they are allowed. Text in a here-document is not read as commands.
- It cannot see a script that writes to a protected path itself. The data check in `run_control.py` reports that afterwards. The hook guards against slips; it is not a lock.
- Off switch: set the environment variable `CLAUDE_HOOK_GUARD=off` for a session, or delete its entry in `settings.json`. An error in the hook allows the call.

## hook_confirm.py

A `PreToolUse` hook that makes Claude Code ask the user before a Bash command runs `run_control.py accept`, `reject` or `discard`, or `archive_control.py archive` or `restore`. These steps commit, tag, delete or restore output folders, and only the user decides them. Other calls are allowed. To cover another step, add a line to the `ASK` list in the script.

## log_retention.py

Claude Code deletes session transcripts older than `cleanupPeriodDays` (default 30; this setup uses 180). The `project-disclosure` skill and the log citations in the decision log read those transcripts. This script lists the transcripts of one project that will expire soon.

```
<python> log_retention.py [--root <project root>] [--warn-days N] [--days N] [--list] [--claude-dir DIR]
```

- The period comes from `cleanupPeriodDays` in `~/.claude/settings.json`, then the project `.claude/settings.json` and `settings.local.json`; `--days` overrides it. Transcripts are found under `~/.claude/projects/<project key>/`.
- A transcript is due when fewer than `--warn-days` days remain (default 14). Age is the time the file was last written; the Claude Code documentation says only "older than". Exit code 1 if any transcript is due; `--list` shows every transcript.
- With `--hook` it is a `SessionStart` hook: it reads the hook JSON, uses its `cwd`, prints nothing when no transcript is due, and otherwise shows the user a message and tells Claude. Install it with `python deploy.py hooks --retention-notice`. It never fails a session.

## check_docx_skill.py

The `proofread` skill edits Word files with scripts from the `docx` skill (`office/validate.py`, `comment.py`, `merge_runs.py`). That skill is maintained by Anthropic and synced from the claude.ai account, so its folder name is not fixed (`~/.claude/skills/synced/<ids>/docx/`), a later sync can replace it, and it is absent after an API-key or Bedrock sign-in. This script finds it, checks it and watches it for change.

```
<python> check_docx_skill.py [--find] [--accept] [--claude-dir DIR] [--search-dir DIR ...] [--quiet]
```

- It takes no `--root`. A plain run prints the folder found, whether each script runs with `--help` and shows the flags `proofread` uses (`validate.py --original --author`, `comment.py --author`, `merge_runs.py --output`), and the fingerprint status. Exit code 1 if the scripts are not found or the interface check fails.
- `--find` prints only the folder, for use by the `proofread` skill, and skips the `--help` checks. If the scripts changed since they were accepted it also writes a one-line warning to standard error (exit code 0), which the skill repeats in its summary. Nothing is printed when they are unchanged, because the fingerprint hashes file contents, so a sync that downloads identical files does not trigger it.
- Search order: the environment variable `DOCX_SKILL_DIR`, each `--search-dir`, `<claude dir>/skills/docx/scripts`, `<claude dir>/skills/synced/*/docx/scripts`, the plugin folders, and, for the default `~/.claude`, the Claude desktop app's skills-plugin folder.
- Fingerprint: a hash of every `.py` file in the scripts folder. `--accept` records it in `<claude dir>/docx-skill.json` (only if the interface check passes). A later run that finds a different fingerprint prints a warning, and the exit code stays 0. When that happens, re-run the `proofread` fixtures (`python tests/skills/run_fixtures.py proofread proofread-structure`, about four minutes), and run `--accept` if they pass. The warning appears in the `proofread` summary, in `deploy.py doctor` and in the fixture runner, and each repeats this instruction.
- `deploy.py doctor` and the fixture runner both show these rows as warnings.
