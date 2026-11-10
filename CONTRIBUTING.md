# Contributing

Thank you for helping. This repository is a set of rules, skills, scripts and templates for Claude Code. A change is useful when it is small, tested and explained.

## Before you start

- Open an issue first for anything larger than a fix, so that the direction is agreed before you write it. Use the issue templates.
- Read `README.md` (what each folder holds, and the conventions) and, for a script, `scripts/README.md`.
- The files in `claude-md/global-CLAUDE.md` and `claude-md/project-CLAUDE.md` are rules that other people will run. Keep a rule short, and say what to do, not why. The reason for a change goes in the decision log row and the commit message.

## Making a change

1. Fork the repository and make one change per pull request.
2. Run the tests from the repository root with Python 3 and git installed:

   ```
   python -m unittest discover -s tests
   ```

   They use only the standard library, make no model calls and do not touch `~/.claude`. `tests/README.md` says what each file covers. Add a test for a new behaviour, and one that fails for each new check.
3. Keep shared files free of text that belongs to one person or machine (user names, home folders, e-mail addresses, personal library paths). `tests/test_framework.py` checks for this.
4. For a new or edited skill, follow `prompts/new-skill-workflow.md` and run `python skills/check_frontmatter.py skills/<name>/SKILL.md`. It must print `OK`. Keep the description to one line of 350 characters or fewer. The fixtures in `tests/skills/` run a skill in a headless Claude Code session and make model calls, so you do not need to run them. Say in the pull request if you did.
5. For a new script, add a `VERSION` line and `--version`, a section in `scripts/README.md` and tests in `tests/test_scripts.py`.
6. After a change to a skill, `claude-md/global-CLAUDE.md` or a script, `python deploy.py status` shows what would change in a live configuration. Do not run `apply` on a configuration you cannot restore. It backs up each file it replaces.
7. If you decided something (including a decision not to do something), add one row to `records/DECISIONS.md`: date `DDMMYY`, decision, reason, evidence. Keep a row to about 500 characters.

## Style

- Plain words, short sentences, sentence case for titles, no contractions. Define an acronym on first use.
- A new script starts with a header block that names its inputs, outputs, usage and exit codes, like the existing scripts.
- Do not commit `outputs/`, `working_docs/` or `records/HANDOFF.md`. They are local.

## Pull requests

State what changed and why, the tests you ran and their result, and anything you did not check. CI runs the tests on Windows, macOS and Linux, and it must pass.

By contributing you agree that your work is licensed under the BSD 3-Clause licence in `LICENSE`.
