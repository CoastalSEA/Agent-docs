# skills

One subfolder per skill, each holding a `SKILL.md`, regardless of whether the skill is
deployed at project scope (`.claude/skills/`) or user scope (`~/.claude/skills/`) in a
given project. See `skill_location.md` for the mechanics of project-level vs. user-level
vs. plugin-based deployment.

`blank-skill-template.md` is the starting point for a new skill — copy it, fill in
the brackets, then restructure into `<name>/SKILL.md` once the design has settled.
Also flat, also not deployed as-is. See `../prompts/new-skill-workflow.md` for the
draft-refine-deploy process to run it through.

`check_frontmatter.py` checks that a `SKILL.md` frontmatter will parse (description on one
line, no `: ` or ` #` in it). Run it on every new or edited skill before deploying. A
frontmatter that does not parse is ignored silently, and the skill then does not fork.
To run a skill as a command, type `/name` at the start of the message (for example `/document-adversary docs/spec.md`). A name after other text, such as "Run /name", is only a request and may not run the skill.
It also warns, without failing, when a description is over 350 characters (it is loaded in every session) or a file
is over 15,000 characters (long instructions are followed less reliably).
