# claude-md

Template `CLAUDE.md` files that hold the shared rules (method, outputs, hard boundaries), so a new
project starts from the same standards. The global file and the project templates are kept
separately, since they serve different purposes. What differs between users (interpreter paths,
writing rules) is not here: it goes in the two local files made from the forms in `user-files/`.

- `global-CLAUDE.md`: the version-controlled copy of the global file at
  `~/.claude/CLAUDE.md`. Machine-wide rules that every project inherits.
- `project-CLAUDE.md`: the template for a project `CLAUDE.md`. It defers to the global file
  and adds the project folder layout, the pointers to the records that carry knowledge
  between sessions, and the working rules that keep those records current.
- `project-template/`: stubs for the files the project template points to, laid out as they
  sit in a project root. Copy the folders into the project root and fill in each file.
  - `CLAUDE.md` (a copy of `project-CLAUDE.md`; keep the two in step)
  - `data/DATA-NOTES.md`
  - `outputs/INDEX.md`
  - `records/DECISIONS.md`
  - `records/HANDOFF.md`
  - `.gitignore`: ignores `sources/` (downloaded sources, with references in `sources/references/`), Office lock files and Python caches.
    Merge it into the project's own `.gitignore`.
  - `products/PRODUCTS.md`: register of large generated files (over the file guard limit, videos, intermediates) held in the git-ignored `products/` folder. The `.gitignore` tracks only the register.
  - The scripts are not copied into projects. They live in `scripts/`; `deploy.py` installs them as `~/.claude/scripts/` and the
    command form is in `machine.md`. Each has `--version`. `run_control` prepares `outputs/<task>/` (`start`), does the git steps and
    `INDEX.md` lines (`accept`, `reject`, `discard`) and applies the file guard (`check`, `status`); its version is written to
    `run_info.txt` and the tag message. `archive_control` removes a task folder from `outputs/` and keeps it under the tag
    `archive-<task>-<DDMMYY>` (INDEX status archived). `check_records` checks the record files and the memory notes against the
    project folders, including the size of `DECISIONS.md`. `wrapup_status` reports whether the handoff is current (exit code 1 if
    stale). `project.py` reports the template level in use and whether an upgrade is suggested (`status`), and adds the missing files of a level (`init --level`, a dry run until `--apply`). `rotate_records` moves the oldest decision rows beyond 100 to `records/DECISIONS-archive.md`; nothing is deleted.
- `project-template-minimal/`: `CLAUDE.md` only, for a small task. It says what the project is and where the data and
  outputs go. The global file supplies the rules. No record files.
- `project-template-handoff/`: `CLAUDE.md` and `records/HANDOFF.md`. The cheapest record. Use it when a project spans
  more than one session. Anything that must outlast the next handoff is saved as a memory note.
- Choosing a level: start with `project-template-minimal/`. Move to `project-template-handoff/` when the work spans more
  than one session. Move to `project-template/` when `data/` holds 3 or more files, `outputs/` holds 5 or more runs
  (run tags or run folders), or a check is repeated because an earlier result was not found. The minimal and handoff templates tell the
  user in the first reply of each session, including a resumed session, when a criterion is met. The user decides
  whether to upgrade. A declined offer is saved as a memory note and is raised again only when a count has doubled.
- `user-files/`: blank forms for the two local files that hold what differs between users. `machine.example.md` is
  the environment (system, shells, interpreter and tool commands, environments, locations). `profile.example.md` is
  personal preferences (writing rules, code header). Copy each to `~/.claude/rules/` as `machine.md` and `profile.md`
  and fill it in; Claude Code loads that folder in every session, including subagents. Each file starts with a marker line
  so a check can confirm it is loaded. The live files hold personal values and are not stored in this repository.
