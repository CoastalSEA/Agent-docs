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
| `hook_confirm.py` | Claude Code hook: ask the user before reject, discard, archive or restore |
| `log_retention.py` | Report session transcripts of a project that will be deleted soon; optional start-of-session notice |
| `check_docx_skill.py` | Find the `docx` skill scripts that `proofread` uses, check their interface and warn when they change |
| `endnote_lib.py` | Read and maintain a project EndNote library under `sources/references/` |
| `outputs_layout.py` | Shared module: the outputs layout (flat or topic folders) read from `outputs/TOPICS.md` |

## run_control.py

Prepares and closes the output folder of a task, `outputs/<task>/`, or `outputs/<topic>/<task>/` in a topic project (see outputs_layout.py below). In a git project where `outputs/` is tracked, a run overwrites the task folder and stays pending until you review it. Otherwise each run gets a new folder `outputs/<task>-<DDMMYY>-run<N>/`.

| Command | What it does |
|---|---|
| `start <task> [--topic T]` | Prepares the folder, writes `run_info.txt` and prints the absolute path. Run it before a task writes outputs. On a rerun it removes the files of the earlier run, in subfolders too, and keeps `.md` reports. In a topic project a new task takes `--topic T` or the form `T/<task>`, or goes to the default topic; an existing task goes to its present folder. |
| `path <task> [--topic T]` | Prints the folder a `start` would use. Changes nothing. |
| `where <task>` | Prints the present folder of a task (the latest run folder in run folder mode). Exit code 1 for an unknown or archived task. Project code reads another run's outputs through it. |
| `check <task> [--allow F]` | Runs the file guard and shows what `accept` would commit. |
| `accept <task> ["question"] [--allow F]` | Guard, commit, annotated tag and `outputs/INDEX.md` row (if the project keeps one). |
| `reject <task> ["question"] [--allow F]` | As `accept`, with the tag suffix `-rejected` and the status "not adopted". |
| `discard <task>` | Restores the folder to the last accepted run and deletes pending files. Ask first. |
| `status` | Lists pending task folders, guard failures and tags with no INDEX row. |
| `layout flat\|topics` | Settles the outputs layout and writes `outputs/TOPICS.md` (`topics` adds the default topic `general`). Refused once any task folder, run tag or INDEX row exists. |
| `topics list` | The topics, their state, scope, plan reference and task folders. |
| `topics add <T> "<scope>" --plan "<reference>"` | Adds an open topic. `close <T>` stops new tasks in it (reruns are allowed, with a notice); `reopen <T>` undoes that; `rename <old> <new>` only for a topic that holds no task. The default topic cannot be closed. These edit `TOPICS.md` only; run them only on the user's instruction. |

- Only the user accepts, rejects or discards a run.
- Without a question, `accept` and `reject` reuse the question of the last tag of the task.
- The file guard excludes `.pdf .docx .pptx .zip .7z .rar .gz .pyc` and Office lock files. Images may be up to 1 MB, other files up to 5 MB, and a folder up to 25 MB. `--allow <file>` (repeatable, path relative to the task folder) passes a named file.
- Task names are reduced to letters, digits, `-` and `_`. In a topic project the topic and the task are reduced separately, and the slash is only a separator.
- In a topic project, task names are unique in the project: a new name that equals a task folder in any topic, an INDEX row or a run tag is refused. Tags do not name the topic. `run_info.txt` and the tag message add `topic` and `folder` lines; `accept` also commits a changed `outputs/TOPICS.md`. A flat project's files are unchanged.
- If the commit of `accept` or `reject` fails, nothing is tagged and `outputs/INDEX.md` is put back as it was. Fix the cause and run the command again.
- Data check: `start` records the state of `data/` (names, sizes and times; not `DATA-NOTES.md` or README files) in `run_info.txt`. If `data/` differs later, `check` fails and `accept` and `reject` refuse, naming the files changed after the start. Deleted files are only counted. `--data-changed-ok` passes it once the user has reviewed the change. Runs without a record are not checked.

Example: `<python> run_control.py start trend-fit --root "<project root>"`

## outputs_layout.py

The module that `run_control.py`, `archive_control.py`, `check_records.py`, `wrapup_status.py` and `project.py` import from their own folder; `deploy.py` installs it beside them. It is not run by hand (`--version` prints its version; `show` prints the layout and the task folders).

`outputs/TOPICS.md` holds the layout:

| `TOPICS.md` | Layout |
|---|---|
| none | Flat: `outputs/<task>/`. Every project made before the topic layout; nothing changes for it. |
| `Layout: flat` | Flat; the file records that the choice was made. |
| `Layout: undecided` | `start` refuses until `run_control.py layout topics` or `layout flat`. |
| `Layout: topics` | `outputs/<topic>/<task>/`. Every folder in `outputs/` is a topic in the table (columns topic, scope, plan reference, state `open` or `closed`), with a line `Default topic: general` for tasks given without a topic. INDEX rows name `topic/task`. |

The layout is fixed once any task folder, run tag or INDEX row exists. There is no migration tool, and a topic that holds a task is never renamed or merged.

## archive_control.py

Removes finished task folders from the working tree without losing them. The folder stays in git history and under the tag `archive-<task>-<DDMMYY>`. Run tags and INDEX rows stay valid.

| Command | What it does |
|---|---|
| `archive <task> [<task> ...] [--message TEXT] [--no-commit]` | Refuses unless the folder is committed, unchanged, has no git-ignored files and has a `current` row in `outputs/INDEX.md`. Then tags, marks the row `archived`, removes the folder and commits the removal with `INDEX.md`. |
| `restore <task>` | Checks the latest archive tag out into the folder named in its tag message, `outputs/<task>/` or `outputs/<topic>/<task>/` (staged, not committed), and sets the row back to `current`. |
| `list` | Prints the archived tasks and their tags. |

## check_records.py

Checks `data/DATA-NOTES.md`, `records/DECISIONS.md`, `outputs/INDEX.md` and the Claude memory notes for the project against the files and git tags.

```
<python> check_records.py [project root] [--root <project root>] [--max N] [--memory DIR] [--max-lines N]
```

- Failures set exit code 1: cited paths that do not exist (a missing bare name with no folder in it, or a missing path in a git-ignored location, is only a flag), bad session log citations, INDEX rows that do not match runs or tags, data files that do not match `DATA-NOTES.md`, memory index problems, and a decision row over 1,000 characters dated 091126 or later.
- Flags are for review and do not set the exit code: stale memory notes, files changed after the entry that describes them, uncommitted outputs, decision rows over 800 characters, and a log with more than `--max-lines` rows (default 100) or 60,000 characters.
- `--max N` limits the lines listed per flag (default 40).
- `--memory DIR` overrides the memory folder (default `~/.claude/projects/<launch-folder-key>/memory/`).
- A missing record file is reported and its checks are skipped.
- Check 14 runs only when `outputs/TOPICS.md` exists. It fails on a missing or unknown layout line, a topic layout without its default topic row, a folder in `outputs/` that is not a topic, and an undecided layout once runs exist; an undecided layout with no runs is a note. In a topic project the INDEX check compares the task folders one level below the topics.
- No file is written.

## wrapup_status.py

Shows whether the handoff is current, so a checkpoint is not forgotten.

```
<python> wrapup_status.py [--root <project root>] [--max-lines N] [--quiet]
```

- The handoff is `records/HANDOFF.md`. It is stale when a changed file is newer than it. Changed files are uncommitted files and, if the branch has an upstream, files in commits not yet pushed. The handoff itself is not counted. An uncommitted deletion of a tracked file counts too, with the time of the folder it was in. A deleted git-ignored file is not seen here; `check_records.py` reports a cited path that is missing.
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
<python> project.py init --level minimal|handoff|full [--topics | --flat | --layout-later] [--library] [--apply] --templates <claude-md folder> [--root <project root>]
```

- `status` prints the level in use, the number of files in `data/` (not `DATA-NOTES.md` or README files), the number of runs (task folders and git tags that look like `<task>-<DDMMYY>-run<N>`), the number of notes in the Claude memory folder for the project, the recommended level and the files each level is missing. The last line is `Status: OK at <level>`, `Status: UPGRADE SUGGESTED to <level>` or `Status: NO TEMPLATE`; `--quiet` prints only that line. Nothing is written.
- The recommendation: from minimal or handoff to full when `data/` holds 3 or more files or there are 5 or more runs; from minimal to handoff when the memory folder holds notes or there are earlier runs. The script cannot count a repeated check because an earlier result was not found, so the handoff template still names it.
- `init` is a dry run unless `--apply` is given. It adds the files of the level that are missing, never overwrites a file, and appends the missing lines to `.gitignore` (the `sources/` line at least, in a git project). An existing `CLAUDE.md` that differs from the template is left as it is and named, so that it is merged by hand.
- `status` also reports the outputs layout: flat, topics with the open topics, or undecided. While it is undecided the last line ends with `OUTPUTS LAYOUT UNDECIDED`, so the session raises it. In a flat project with 15 or more task folders it adds advice that acts within the project: archive finished tasks, and begin new task names with a phase prefix such as `wp2-`.
- In a project with no task folder, run tag, INDEX row or `outputs/TOPICS.md`, the dry run of `init` prints the layout choice, and `--apply` needs one of `--topics` (a plan with phases or work packages, or many runs expected), `--flat` (a series of prompts with no plan) or `--layout-later` (decide before the first run). It writes `outputs/TOPICS.md` at every level; `--topics` also writes the default topic. In a project that already has runs, or a `TOPICS.md`, the options are not needed and nothing about the layout is written. Exit code 1 when `--apply` needs an option.
- `--library` also appends the block in `claude-md/project-library-block.md` to `CLAUDE.md` (a project EndNote library under `sources/references/`), unless `CLAUDE.md` already has a `## Project library` heading. Fill in its brackets.
- `--templates` is needed when the script is run from `~/.claude/scripts/`. It is optional when the script is run from the repository.
- The memory folder is `~/.claude/projects/<project path with dashes>/memory/` (under `CLAUDE_CONFIG_DIR` if that is set).
- Exit code 0 on success, 1 if `init --apply` needs a layout option, 2 if the folder or the templates cannot be used.

## hook_push_check.py

A Claude Code `PreToolUse` hook. It stops `git push` while the handoff is stale, so the handoff goes with the work. It is not run by hand.

- It reads the tool call as JSON on standard input. It acts only on Bash and PowerShell commands that contain `git push`, also with a path before `git` or as `git.exe` (words inside quotes or a here-document are ignored, except after `-c` or `eval`), and only in a framework project with a `records/` folder. The project is the session folder, or the nearest folder above it, whose `CLAUDE.md` names `machine.md`, so a session started in a subfolder is covered. It runs `wrapup_status.py` there.
- If the handoff is stale or missing, it exits with code 2 and a message. Claude then writes a checkpoint and pushes again. In every other case, and on any error, it exits 0 and the call goes ahead. Commits are not checked.
- Install it with `python deploy.py hooks` from the repository root (it installs all three hooks, for the Bash and PowerShell tools; run it again after an update, and it brings an older entry up to date). That adds one entry for each to `~/.claude/settings.json`, using the interpreter named in `machine.md`, and backs the file up first. Start a new session for the hooks to load.
- Test it by hand: `echo '{"tool_name":"Bash","tool_input":{"command":"git push"},"cwd":"<project root>"}' | <python> hook_push_check.py; echo $?`

## hook_guard.py

A `PreToolUse` hook that blocks writes to protected files with exit code 2 and a message.

- Protected: the project `data/` folder, except `data/DATA-NOTES.md` and README files, in a framework project only (the session folder, or the nearest folder above it, has a `CLAUDE.md` that names `machine.md`, as every project template does; that folder is the project root, and the Claude configuration folder is not one when found above the session folder); and, in every folder, every path in `~/.claude/rules/protected-paths.txt` (one absolute path per line, a file or a folder, `#` for comments; for example the EndNote library file and its `.Data` folder).
- It checks the target of Write, Edit, MultiEdit and NotebookEdit, and each Bash or PowerShell command segment that names a protected path and redirects into it (`>`, `>>`), uses a writing command (`rm`, `mv`, `sed -i`, `tee`, `del`, `Remove-Item`, `Set-Content`, `Out-File` and similar) or copies onto it. Reading and copying out of a protected folder are allowed.
- Relative paths are read against the session folder, so `data/x` in a session started in `code/` means `code/data/x`, and `../data/x` is protected. A `cd` earlier in the command moves that folder; a `cd` to a variable makes later relative paths unknown, and they are allowed. Text in a here-document is not read as commands.
- It cannot see a script that writes to a protected path itself. The data check in `run_control.py` reports that afterwards. The hook guards against slips; it is not a lock.
- Off switch: set the environment variable `CLAUDE_HOOK_GUARD=off` for a session, or delete its entry in `settings.json`. An error in the hook allows the call.

## hook_confirm.py

A `PreToolUse` hook that makes Claude Code ask the user before a Bash or PowerShell command runs a step that only the user decides. These steps commit, tag, delete or restore output folders, so a permission prompt is shown even where Bash commands are otherwise allowed. It acts on a call of the Bash or PowerShell tool only, and any other call, and any error, is allowed without comment.

The `ASK` list in the script holds the steps that prompt:

| Command | Why it asks |
|---|---|
| `run_control.py reject` or `discard` | Only the user rejects or discards a run. |
| `archive_control.py archive` or `restore` | Archiving or restoring an output folder changes the project tags and files. |

`run_control.py accept` is not on the list: the user's instruction to accept is the permission, as the global rules say. `start`, `check`, `path`, `status` and `archive_control.py list` do not prompt either.

**What else prompts or blocks.** The hook is one of several protections, and they work together:

- **Prompts in every permission mode.** The `ask` rules in `~/.claude/settings.json` (for example `git push *` and `gh repo edit *`) and this hook. `deploy.py` installs the hooks and does not write permission rules: those are in your own `settings.json`.
- **Refused without a prompt.** Deny rules in `settings.json` (for example reads of `~/.ssh` and `.env` files, force pushes, `git reset --hard`, `git clean -f`, `gh repo delete`), `hook_push_check.py` while the handoff is stale, and `hook_guard.py` for writes to `data/` and protected paths.
- **Depends on the mode.** In auto mode, other shell, Python and PowerShell calls are judged by Claude Code's own checks. In the default mode each of them prompts. A read outside the working directory (for example `~/.claude/rules/machine.md` from a project folder) may prompt once.
- **Rule order.** Claude Code applies deny, then ask, then allow, and the first match wins. An ask rule prompts even where an allow rule matches, and a hook's allow does not skip an ask rule.

To change or disable the hook, edit the `ASK` list in `scripts/hook_confirm.py` in the repository and run `deploy.py apply` (a change made only to the live copy in `~/.claude/scripts/` is overwritten by the next `apply`), or delete its entry from `settings.json` to turn it off. Start a new session for the change to take effect.

## log_retention.py

Claude Code deletes session transcripts older than `cleanupPeriodDays` (default 30). The `project-disclosure` skill and the log citations in the decision log read those transcripts. This script lists the transcripts of one project that will expire soon.

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

## endnote_lib.py

Reads and maintains a project EndNote library: a library under `sources/references/` in the project root, which the project keeps as a project source. Every other library is read only: a write is refused unless the library lies inside `<root>/sources/references/`, and always refused for a path in `protected-paths.txt` (the file `hook_guard.py` reads). The EndNote MCP server stays read only; this helper is the only way to write.

```
<python> endnote_lib.py <command> --lib "sources/references/<name>.enl" [options] [--root <project root>]
```

| Command | What it does |
|---|---|
| `info` | Active entries, entries in the trash, the lock state and journal mode of both files, the check, and the number and size of backups |
| `list [--keyword K]` | Active entries: id, year, first author, title. `K` is an exact keyword, for example `read:full` |
| `types` | The entry type integers in use, with a count and one example title each. Use it to map type names to integers for a library |
| `check` | Integrity of the tables the helper writes, in both files, and whether the two files agree |
| `backup` | Copies the `.enl` file and `Data/sdb/` to `library-backups/<name>/<DDMMYY-HHMMSS>/` beside the library |
| `restore <tag>` | Restores a backup; the present state is backed up first |
| `update --json F` | `F` holds `{"<id>": {"<column>": value}}` |
| `add --json F [--pdf P]` | `F` holds `{"<column>": value}`; the PDF is copied into `Data/PDF/<ten digits>/` |
| `tag --csv F --prefixes P` | `F` has the columns `id` and `keywords` (separated by `; `); every keyword must start with a prefix in `P`, for example `read:,proj:`. Keywords already present are kept |

- Write commands take `--source TEXT` (logged with each change), `--log FOLDER` (appends each change to `FOLDER/changes.csv`: time, library, action, entry, field, before, after, source) and `--allow-type N` (an entry type not yet in use in the library; give it only with evidence of its meaning).
- Before each write the library must open for reading. EndNote locks the file while the library is open, so a locked library is refused with a message naming EndNote; stop and tell the user. There is no retry.
- Each write makes a backup, then writes the `.enl` file and `Data/sdb/sdb.eni` in one transaction, with the integrity check before the commit. On a failure both files are rolled back, or restored from the backup if either differs from it, and a PDF folder made by the failed call is removed.
- No command deletes an entry or a PDF, or writes `trash_state`. Editable columns are listed in `EDITABLE` in the script.
- The term lists and the PDF index of EndNote are not updated: new authors, journals and keywords may not appear in the term lists until Library, Recover Library is run in EndNote. Searches are correct at once.
- An update writes, stamps and logs only the values that differ from the library; an update with no change at all makes no backup. `log_rows` (Python only) appends rows, such as a per-entry check result, to `changes.csv` without writing the library.
- Backups are kept; `info` reports their total size.
- The header of the script lists the facts about the EndNote 20 format that it depends on and the evidence for each.
- Exit code 0 on success, 1 for a refused write, a locked library or a failed check, 2 for an unusable path or input.
