# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with tasks and code in this project.

## About this project

[One or two sentences: what the project is and what it is for.]
- input data files are held in the `data/` folder in the project root
- outputs are written to the `outputs/` folder in the project root (see the global Outputs rules; start each run with the run control command in `machine.md`)
- downloaded sources are held in the `sources/` folder in the project root, with downloaded references (papers, reports) in `sources/references/`, named `<FirstAuthor><Year>_<short title>.pdf` (for example `Kirby2000_tidal-flat-shape.pdf`; no spaces); if the project is a git repository, add `sources/` to `.gitignore`
- start every session from the project root. Claude memory is keyed to the launch folder, so a session started from a sub-folder gets a separate, empty memory.

Use global settings for everything else. This project keeps no record files.

## Working rules for this project

- **Upgrade check.** In the first reply of each session, run `project.py status` (in `machine.md`) and tell the user if its last line suggests an upgrade. Offer the move and ask before any change. `project.py init --level <level> --templates <the claude-md folder of the Agent-docs repository>` is a dry run that lists what it would add; `--apply` writes it. If declined, save a memory note (date, counts); do not raise again unless a count doubles.
