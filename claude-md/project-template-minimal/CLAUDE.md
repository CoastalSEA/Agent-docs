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

- **Upgrade check.** In the first reply of each session, tell the user if any threshold is met:
  - Memory folder or outputs show earlier work → move to `project-template-handoff/`
  - `data/` holds 3+ files or `outputs/` holds 5+ runs (run tags or run folders) → move to `project-template/`
  
  Both templates are in the `claude-md/` folder of the Agent-docs repository (location in `machine.md`). Offer the upgrade; ask before any change. If declined, save a memory note (date, counts); do not raise again unless a count doubles.
