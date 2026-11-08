# Where a skill lives

| Scope | Path | Available in |
|---|---|---|
| Project | `<project>/.claude/skills/<name>/SKILL.md` | that project only |
| User | `~/.claude/skills/<name>/SKILL.md` | every project (`deploy.py` installs this repo's skills here) |
| Plugin | `skills/<name>/SKILL.md` inside a plugin | wherever the plugin is installed; listed as `<plugin>:<name>` |

- One folder per skill, named as the skill. The file is named exactly `SKILL.md`.
- The frontmatter needs `name` and `description`. Check it with `skills/check_frontmatter.py`.
- A loose file elsewhere, such as `<project>/citation_skill.md`, is not found.
- A skill added or edited during a session loads only in a new session.
