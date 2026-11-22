# Tests

Tests for the scripts, the shared files and the skill fixtures. They use only the Python standard library and need `git` on the path. They make no model calls, no network calls and no changes under `~/.claude`.

Run all of them from the repository root, with the interpreter named in `machine.md`:

```
python -m unittest discover -s tests
```

Add `-v` to list each test. To run one file, or one class, name it:

```
python -m unittest tests.test_scripts
python -m unittest tests.test_scripts.ProjectScript
```

`.github/workflows/tests.yml` runs the same command on Windows, macOS and Linux for each push to `main` and each pull request. It then installs into a scratch folder with `deploy.py init`, `apply`, `hooks` and `doctor`.

| File | What it tests |
|---|---|
| `test_framework.py` | The shared files. No machine-specific text in tracked files, the project template copy equals its master, every skill's frontmatter parses and its description is within the length limit, the user-file forms keep their marker lines, every script has a version, and `deploy.py` installs every script and skill. It reads files only. |
| `test_scripts.py` | The project scripts (`run_control`, `archive_control`, `check_records`, `wrapup_status`, `rotate_records`, `project`), the three hook scripts, `log_retention`, `check_docx_skill` and `deploy.py`. Each test builds a throwaway project in a temporary folder (a git repository where needed), runs the script as a separate process and checks the exit code, the files, the tags and the index rows. `deploy.py` is run with `--target` set to a temporary folder. |
| `test_endnote_lib.py` | `scripts/endnote_lib.py` on a synthetic EndNote library built by `endnote_fixture.py` (the table definitions and triggers of a real EndNote 20 library, invented records): the location and protected-path guards, the lock check, the allow-list, updates, additions with and without a PDF, keywords, agreement of the two files, a failure injected in the second file, backup and restore. |
| `test_endnote_server.py` | `mcp/endnote/endnote_server.py` on the same synthetic library, calling the tool functions directly: the trash left out by default, the exact keyword filter, the entry type name and linked files, the search by file name, a page range, a PDF without text, and the lock message. Skipped when the server packages `mcp` and `pypdf` are not importable. |
| `test_library_metadata.py` | The `library-metadata` skill scripts on the synthetic library, with canned CrossRef and OpenAlex records (no network): the PDF check, the CrossRef field mapping, the apply rules, the add rules (duplicates, title similarity, no record, year fallback, PDFs with and without text) and the lookup status. The PDF tests need `pypdf` or `pymupdf` and are skipped without them. |
| `test_skill_fixtures.py` | The skill fixtures, without a model. Each fixture builds what it says, the planted fault is really in it, and each check passes a good result and fails a result with the planted problem. |
| `skills/run_fixtures.py` | The skills themselves, on those fixtures, with headless Claude Code sessions. It makes model calls, uses the live configuration and is run by hand, never by the tests or CI. See `skills/README.md`. |

## Local pattern file

`test_framework.py` checks that tracked files hold no text that belongs to one user or machine. It always checks for a user-profile path and an e-mail address. To add patterns that are specific to you (a name, a library, a folder), create `tests/personal_patterns.local.txt` with one regular expression per line. Lines that start with `#` are ignored. The file is git-ignored, so it stays on your machine.

## Writing a test

- Build a throwaway project in a temporary folder and clean it up. Do not use the real project or `~/.claude`.
- Run scripts as separate processes with the same interpreter (`sys.executable`).
- Test a refusal as well as a success, and give each check a case that fails it.
- Give each new script a `VERSION` line and a `--version` option: `test_framework.py` checks that every script has a version.
