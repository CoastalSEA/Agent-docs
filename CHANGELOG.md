# Changelog

Each release is an annotated git tag. A beta has a tag only, with no GitHub release page.

## v1.0.0-beta.2

Beta version tested on Windows and Linux.

This release now includes an option to hold an editable project library and for runs to be held in topic subfolders of the outputs folder (e.g. for phases of work in a large project); see README for further details.

### New

- **Project EndNote library.** A project can keep its papers in its own EndNote library under `sources/references/`. Writes go only through `scripts/endnote_lib.py`, which refuses any other library and any protected path, refuses while EndNote has the library open, and backs up before each write. `project.py init --library` adds the "Project library" block to the project `CLAUDE.md`. The read-only server is registered a second time for the project library (`endnote-project`). See README, "A project EndNote library".
- **`library-metadata` skill.** Finds verified metadata for library entries from their PDFs (arXiv, CrossRef, DataCite, OpenAlex), adds papers by DOI with or without a PDF, and appends keywords, writing only through `endnote_lib.py`.
- **Topic folders for run outputs.** `outputs/TOPICS.md` sets the layout: flat (`outputs/<task>/`) or topics (`outputs/<topic>/<task>/`). New `run_control.py` commands `layout`, `topics` and `where`. `project.py init --apply` in a new project takes `--topics`, `--flat` or `--layout-later`. A flat project, also one with runs, may record topic prefixes for its task names. `check_records.py` check 14 checks the file. See README, "Starting a project".
- **EndNote server.** Entries in the trash are left out by default; `search_references` takes an exact keyword filter; `search_by_file_name` finds entries by the name of a linked file; `read_linked_file_text` takes a page range and reports a PDF with no text layer.
- `deploy.py --version` and `skills/check_frontmatter.py --version`.

### Changed

- The hooks find the project root from the session folder upwards, so a session started in a subfolder of a project is covered.
- `run_control.py` and `check_records.py` read `git status` with `-z`, so a path with a space is matched to its task folder.
- The blank prompt template is rewritten. The literature-synthesis and reanalysis-triage templates take their output folder from the run control `start`.
- The project templates, the README files and the skill texts are brought up to date with the topic layout. The project template no longer has a "Project progress" section; the handoff holds that state.

### Script versions

`run_control` 1.6, `check_records` 1.5, `project` 1.4, `hook_push_check` 1.3, `hook_guard` 1.2, `hook_confirm` 1.2, `wrapup_status` 1.2, `archive_control` 1.1, `endnote_lib` 1.1, `outputs_layout` 1.1, `rotate_records` 1.1, `check_docx_skill` 1.0, `log_retention` 1.0, `deploy` 1.0.

### Tested

- 444 unit tests pass on Windows with Python 3.14. CI runs them on Windows, macOS and Linux with Python 3.12 for each push to `main`.
- A clean install on Linux (Ubuntu 24.04, Python 3.13) passed on `v1.0.0-beta.1`: the unit tests, `deploy.py init`, `apply`, `doctor` and `hooks`, a session quoting both marker lines, the data guard, and the `analysis-adversary` fixture. The project library and the topic layout came later and have been used on Windows only.
- macOS is tested by CI only. v1.0 follows a clean install on macOS.

### Upgrading from v1.0.0-beta.1

1. Run `python deploy.py status`, then `python deploy.py apply`. This installs the new scripts (`endnote_lib.py`, `outputs_layout.py`) and the `library-metadata` skill.
2. `init` never changes an existing `machine.md`. Copy the new run control line (`where`, `layout`, `topics`) and the `project.py` and `endnote_lib.py` text from `claude-md/user-files/machine.example.md` into your own `machine.md` by hand, then run `python deploy.py doctor`.
3. Existing projects keep the flat layout and need no change.

## v1.0.0-beta.1

First public beta. The scripts, the tests and a scratch install were tested on Windows, macOS and Linux with Python 3.12 (CI), and on Windows with Python 3.14. Sessions, hooks and skills had been used on Windows only.
