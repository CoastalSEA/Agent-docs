# Machine file

Marker: machine-file-v1

Copy this form to `~/.claude/rules/machine.md` and fill in each value. Delete a capability you do not have; do not leave a placeholder. The file is local to one machine and is not shared. Rules that hold on any machine are in the global `CLAUDE.md`. Personal preferences are in `profile.md`.

## System

- Operating system: <Windows 11 | macOS <version> | Linux <distribution>>
- Shells: <Bash | PowerShell 5.1 | PowerShell 7 | zsh>. Say which one the Bash tool uses.
- Home folder: <absolute path>
- Path style in commands: <for example `C:\...` in PowerShell and `/c/...` in Git Bash>

## Commands

Give each command as a complete, copy-ready line for each shell in use. Say whether the plain command name (`python`, `Rscript`) works.

- Python: <full path to the interpreter>. Plain `python` works: <yes | no, and why>. `pip` works: <in any environment | only inside a venv>.
- Run control: `<python command> <scripts folder>/run_control.py <command> <task> --root "<project root>"`. The commands are `start`, `path`, `check`, `accept`, `reject`, `discard` and `status`.
- Other project scripts, in the same folder with the same `--root` option: `archive_control.py` (`archive`, `restore`, `list`) and `check_records.py` (the records check).
- R: <full path to Rscript, or "not installed">
- MATLAB: <full path and a non-interactive example, or "not installed">
- OCR: <full path to Tesseract, installed languages, the OCR venv path, or "not installed">
- EndNote: <library path and how the server is registered, or "not installed">

## Environments

- Project environments: <whether projects use a `.venv`, and who creates it>
- Shared environments: <path and purpose of each, and any rule about what may be installed in it>

## Locations

- This repository: <absolute path>
- Claude configuration folder: <absolute path>
- Private companion repository (optional; holds personal templates, settings and the private decision log): <absolute path>
