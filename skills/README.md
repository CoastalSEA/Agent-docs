# skills

One subfolder per skill, each holding a `SKILL.md`, regardless of whether the skill is
deployed at project scope (`.claude/skills/`) or user scope (`~/.claude/skills/`) in a
given project. See `skill_location.md` for the mechanics of project-level vs. user-level
vs. plugin-based deployment.

`blank-skill-template.md` is the starting point for a new skill — copy it, fill in
the brackets, then restructure into `<name>/SKILL.md` once the design has settled.
The template is a single file with no folder of its own, so `deploy.py` does not install it.
See `../prompts/new-skill-workflow.md` for the draft-refine-deploy process to run it through.

## What each skill needs

`deploy.py apply` installs all six skills, except those named in `~/.claude/rules/skip-skills.txt` (one
name per line, `#` for a comment). Every skill uses the Python and the run control command
named in `machine.md`, except `proofread`, which uses the Python only. The table lists what else a skill needs. List a skill
that you cannot use in that file before `apply`. A copy that is already installed is left alone: remove its
folder from `~/.claude/skills/` by hand.

| Skill | Also needs | Sends data off the machine |
|---|---|---|
| `analysis-adversary` | Nothing else. | No. |
| `document-adversary` | Nothing else. | No. |
| `project-disclosure` | The Claude Code session logs of the project under `~/.claude/projects/`. | No. |
| `proofread` | Windows with Microsoft Word (driven from PowerShell), and the Anthropic `docx` skill (found by `check_docx_skill.py`; see `scripts/README.md`). | No. |
| `citation-check` | The EndNote server (`mcp/endnote/`) connected, and a Word manuscript with EndNote cite-while-write fields. It stops if the server is not connected. | Yes, after it asks: CrossRef, Semantic Scholar, OpenAlex and arXiv. |
| `literature-search` | The EndNote server for the local search. The Exa and Consensus connectors for those two sources. | Yes, after it asks: OpenAlex, arXiv, Semantic Scholar, Exa and Consensus. |

The interactive use of the skills has been on Windows only (see the Notes in the root README).

## Checking a skill

`check_frontmatter.py` checks that a `SKILL.md` frontmatter will parse (description on one
line, no `: ` or ` #` in it). Run it on every new or edited skill before deploying. A
frontmatter that does not parse is ignored silently, and the skill then does not fork.
To run a skill as a command, type `/name` at the start of the message (for example `/document-adversary docs/spec.md`). A name after other text, such as "Run /name", is only a request and may not run the skill.
It also warns, without failing, when a description is over 350 characters (it is loaded in every session) or a file
is over 15,000 characters (long instructions are followed less reliably).
