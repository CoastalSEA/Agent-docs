# Decisions archive

Older lines moved from `records/DECISIONS.md` by `rotate_records.py`. Oldest first. Search this file as well as the active log.

| Date (DDMMYY) | Decision | Reason | Evidence |
|---|---|---|---|
| 180926 | Literature synthesis and reanalysis triage are prompt templates, not skills. Triage is advisory and never runs the reanalysis. | Judging materiality or building a theoretical account is open reasoning over varying evidence that a fixed checklist cannot anticipate. | `prompts/literature-synthesis-template.md`; `prompts/reanalysis-triage-template.md` |
| 200926 | Project templates come at three levels: minimal (`CLAUDE.md` only), handoff (adds `records/HANDOFF.md`) and full. An upgrade is offered when `data/` holds 3 or more files or `outputs/` holds 5 or more runs. | Small projects need less structure than long ones. The thresholds are assumed defaults. | `claude-md/README.md`; `claude-md/project-template*/CLAUDE.md` |
| 200926 | The search-first principle is in the global `CLAUDE.md`; project files keep only the paths. | A project without records is still covered, and subagents receive the global file. | `claude-md/global-CLAUDE.md` |
