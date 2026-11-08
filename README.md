# Agent-docs

Reusable tooling for working with Claude Code across projects: rules (`CLAUDE.md` files and
project templates), skills, an MCP server, prompt, agent and hook templates, and the scripts
that control run outputs and check project records. A deploy script installs the shared parts
into your Claude configuration folder, and two small local files (`machine.md`, `profile.md`)
hold what differs from one user to the next.

Requires Python 3 and git. The scripts and tests pass on Windows, macOS and Linux. Licensed under
the BSD 3-Clause licence (see `LICENSE`). To start, read the Deployment section below.

## Structure

```
deploy.py   copies the master files to the Claude configuration folder (python deploy.py status | apply | doctor)
scripts/    project scripts installed to ~/.claude/scripts: run_control.py (output folders, tags, file guard), archive_control.py, check_records.py
agents/     template for defining and tasking subagents
claude-md/  template CLAUDE.md files (global, and project at three levels) and project record stubs
hooks/      template prompt for creating a hook
mcp/        one subfolder per MCP server: its code, spec, generator prompt, and reports
prompts/    general-purpose prompt/workflow templates not tied to one specific tool
skills/     one subfolder per skill, each holding a SKILL.md
statusline/ statusline scripts for Claude Code's terminal status bar
```

## Conventions

**Item folders** (a skill, an MCP server): the files the item runs on sit in the folder (`SKILL.md`,
scripts, `README.md`). Two optional subfolders hold the rest, named by content as `<subject>-<kind>.md`:
`reference/` for files the agent reads on demand, named in the instruction, and `docs/` for records
about the item (spec, generator prompt, review and test reports), which the agent never reads at run
time. `reference/` is deployed with the item; `docs/` is not.

**MCP servers** (`mcp/<name>/`): the server code and a `README.md`, with the spec, the generator prompt
and any reports in `docs/`. See `mcp/endnote/` for the pattern.

**Skills** (`skills/<name>/SKILL.md`): a skill lives in its own folder named to match the
skill, regardless of whether it is deployed at project scope (`.claude/skills/`) or user
scope (`~/.claude/skills/`) in a given project. See `skills/skill_location.md` for the
mechanics of project-level vs. user-level vs. plugin-based deployment.

**Hooks** (`hooks/`): definition files paired with their `.sh` shell script implementations.

**Agents, prompts, settings, statusline, claude-md**: each is lower-volume than skills/mcp,
so no per-item subfolder convention yet — see each folder's own `README.md` for what
belongs there.

## Tests

```
python -m unittest discover -s tests
```

`tests/test_scripts.py` runs `run_control`, `archive_control`, `check_records` and `deploy.py` in throwaway projects.
`tests/test_framework.py` checks the shared files: no machine-specific text, the template copy equals its master, skill
frontmatter parses, the user-file forms keep their marker lines, every script has a version, and `deploy.py` installs
every script and skill. Neither touches `~/.claude`. `.github/workflows/tests.yml` runs both on Windows, macOS and Linux
for each push to `main`.

## Deployment

This repo is the source of truth for the tooling it holds, not the live, deployed copy. The
script `deploy.py` copies part of it to the Claude configuration folder (`~/.claude`). It needs
only Python 3 and no other package. Run it from the repo root with any Python 3 interpreter
(the command for this machine is in `machine.md`):

```
python deploy.py [status|apply|doctor] [--target PATH] [--diff] [--yes]
```

### First-time setup on a machine

1. Copy `claude-md/user-files/machine.example.md` to `~/.claude/rules/machine.md` and
   `claude-md/user-files/profile.example.md` to `~/.claude/rules/profile.md`. Fill in each file.
   They hold what differs between users (interpreter paths, tools, writing rules) and are never
   stored in this repo.
2. Run `python deploy.py doctor`. It must report no problems.
3. Run `python deploy.py status`, then `python deploy.py apply`.
4. Start a new session and ask it to quote the `Marker:` line of each file. A missing rules file
   fails silently, and `doctor` cannot test that a session loads the files.

### Commands

| Command | What it does | Writes anything? |
|---|---|---|
| `status` (default) | Lists each master file as `same`, `DIFFERS` or `MISSING` against its live copy. Files that differ only in line endings show as `same*` and are not copied. Lists live skills that are not in the repo, and leaves them alone. Exits 1 if any file would be copied. `--diff` also prints a unified diff for each differing text file. | No |
| `apply` | Rewrites `claude-md/project-template/CLAUDE.md` from `claude-md/project-CLAUDE.md` (the master), copies each file that differs or is missing, then compares again. Before it replaces a live file it copies that file to `<target>/backups/deploy-<DDMMYY-HHMM>/`. It asks `[y/N]` at a terminal. Without a terminal it copies nothing unless `--yes` is given. | Yes |
| `doctor` | Checks `~/.claude/rules/machine.md` and `profile.md`: each file is present, has its `Marker:` line and is filled in, and every absolute path named in `machine.md` exists. Exits 1 on any problem. | No |

`--target PATH` points the script at another configuration folder. Use a scratch folder to
test. In a Claude session, ask the user before running `apply`, because it changes live
configuration.

### What deploy installs

| Repo file | Live file |
|---|---|
| `claude-md/global-CLAUDE.md` | `<target>/CLAUDE.md` |
| `skills/<name>/` (each folder with a `SKILL.md`, every file in it except `docs/`) | `<target>/skills/<name>/` |
| `scripts/*.py` (`run_control`, `archive_control`, `check_records`) | `<target>/scripts/` |

### What deploy does not install

- **Hooks, agents and the status line.** Copy or register these by hand. They are not
  covered yet: `hooks/`, `agents/` and `statusline/`.
- **MCP servers.** Register them with `claude mcp add`, pointing at this repo's copy (see
  below).
- **Project-scope skills.** Skills go to the user scope only (`<target>/skills/`). A skill used in
  one project only is copied into that project's `.claude/skills/` by hand.
- **Project templates.** The template folders in `claude-md/` are copied into a project by hand.
  `deploy.py` only keeps the two copies of the project `CLAUDE.md` in step.
- **The two local user files.** `machine.md` and `profile.md` are never written or overwritten.
  The blank forms are in `claude-md/user-files/`.
- **Prompts.** The templates in `prompts/` are copied into a task by hand.
- **Deletions.** The script never deletes. A skill removed or renamed in the repo stays in the
  live folder until it is removed by hand. Live skills with no repo copy are listed and left alone.

### Notes

- The scripts and tests pass on Windows, macOS and Linux (the workflow in `.github/workflows/tests.yml`). The
  interactive parts have only been used on Windows: skills, the status line, the EndNote server and the machine files.
- A skill edited in a session does not take effect until a new session starts.
- Before the script, files were copied by hand and checked with `diff`. The script replaces
  that routine for the files in the table above.
- For skills, see `skills/skill_location.md` for project-level, user-level and plugin-based
  deployment. When an MCP server's code lives here, its registration should point directly at
  this repo's copy rather than a project-local duplicate.

## Acknowledgement

The starting point for many of the ideas contained in this repo, especially the structure of prompts, skills and hooks comes from the excellent course led by Prof. Charles Crabtree (see https://github.com/lobsterbush), entitled "AI Agent-Driven Research Workflows", organised by AI Horizons.