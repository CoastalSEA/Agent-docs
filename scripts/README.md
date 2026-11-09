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
| `hook_push_check.py` | Claude Code hook: block `git push` while the handoff is stale |

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

## hook_push_check.py

A Claude Code `PreToolUse` hook. It stops `git push` while the handoff is stale, so the handoff goes with the work. It is not run by hand.

- It reads the tool call as JSON on standard input. It acts only on Bash commands that contain `git push`, and only in a project with a `records/` folder. It runs `wrapup_status.py` there.
- If the handoff is stale or missing, it exits with code 2 and a message. Claude then writes a checkpoint and pushes again. In every other case, and on any error, it exits 0 and the call goes ahead. Commits are not checked.
- Install it with `python deploy.py hooks` from the repository root. That adds one entry to `~/.claude/settings.json`, using the interpreter named in `machine.md`, and backs the file up first. Start a new session for the hook to load.
- Test it by hand: `echo '{"tool_name":"Bash","tool_input":{"command":"git push"},"cwd":"<project root>"}' | <python> hook_push_check.py; echo $?`
