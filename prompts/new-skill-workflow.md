# New skill workflow

Use this to build a new Claude Code skill from scratch, working from the
`skills/` folder of this repo. Follows the same arc used to build the
`project-disclosure` skill: rough draft, refine, then deploy and validate.
Don't skip to deployment — the refine phase is where most of the real
design problems get caught, cheaply, before anything is live.

## Phase 1 — Rough draft

- Copy `skills/blank-skill-template.md` to `skills/<name>_skill.md` (loose
  file, not yet in the `skills/<name>/SKILL.md` folder convention — that
  restructure happens once the design has settled, not before).
- Fill in `name`, `description`, and a first-pass instruction body, even if
  parts are vague or you're unsure of the mechanics yet. The point of this
  pass is to get the *objective* written down, not to get it right.
- A `SKILL.md` holds scope, steps, deliverable and checks. Dates, test history and reasons for a change go in DECISIONS; long reference material goes in a file in the skill folder that the skill names.
- State the objective in your own words before handing it over: what should
  this skill produce, from what source, and what should it refuse to do
  (invent, guess, overclaim).

## Phase 2 — Refine

Check the draft against reality, not abstractions. For each item below, verify the actual thing before assuming it works as drafted:

- **File formats, APIs, tool behaviour**: Read an actual example, run the real command, check the real folder. Report what the draft assumed wrong.
- **Ambiguous scoping**: How will the skill identify what to act on? If two different things could produce the same identifier, say so and propose verification instead of just matching.
- **Missing constraints**: Fixed output filename or invented per run? What "the current X" means and how it's determined without asking? What should the skill refuse to claim when the source is silent?
- **Design choices**: Raise problems one at a time, get agreement before fixing. Don't decide on the user's behalf (scope, output location, sensitivity/redaction).
- **Readiness check**: Ask directly—does this brief a fresh agent (no memory of this conversation) to execute it correctly on the first try? What's missing? What's not needed?
- **Iterate** until both answers are settled.

## Phase 3 — Deploy and validate

- Restructure the settled draft into `skills/<name>/SKILL.md`, matching the
  repo's own convention, and delete the loose draft file.
- Before deploying, run `check_frontmatter.py` (Python from `machine.md`) on `skills/<name>/SKILL.md` and expect `OK`. **A frontmatter that does not parse is ignored silently:** `context`, `agent`, and `background` have no effect (skill will not fork); the description is not used to list the skill. Keep the description on one line, no `: ` or ` #` inside it. Confirm the full description appears in the session's skill list.
- A user-level skill goes live with `deploy.py status`, then `apply` once the user agrees (see the README
  Deployment section). A skill for one project is copied by hand to `<project>/.claude/skills/<name>/SKILL.md`.
- Commit the repo copy only when asked to.
- **A skill created or edited mid-session will not appear in that same
  session's `Skill` tool listing.** Don't rely on invoking it directly to
  test it in the session that built it. Instead:
  - Dry-run it yourself: follow the SKILL.md's own instructions by hand,
    exactly as written, against real data. This tests whether the
    instructions are actually followable, not just whether the mechanism
    dispatches.
  - Then validate for real in a genuinely fresh session: spawn
    `claude -p "<natural-language invocation>" --permission-mode auto`
    (add `--output-format json` for diagnostics) from the project root.
    **On Windows use PowerShell, not Git Bash** — Git Bash's MSYS layer rewrites a
    leading `/` into a filesystem path before Claude Code ever sees it,
    which silently breaks literal `/skill-name` invocation. Test the exact
    slash form too, not just natural language, since real users will type
    both.
- If the skill declared `context: fork`, confirm in the live test's own log (not the top-level CLI `subagent_stats`, which tracks something else) that a forked subagent ran, that its `agent:` type has the needed tools (`Write`/`Edit` if it saves; `Explore` and `Plan` don't), and that per-session reports resolve correctly from inside the fork (forked transcripts may lack container fields like permission mode—check rather than assume).
- Fix anything the live test finds, redeploy, and re-test until a real run
  produces the correct deliverable end to end.
- Delete test artifacts (output files, scratch scripts) once confirmed
  working; don't commit them.
- Finish with `deploy.py status`: the skill shows `same`, and `git diff HEAD` on it is empty.

## Definition of done

- `skills/<name>/SKILL.md` exists, matches the repo convention, and is
  committed.
- `check_frontmatter.py skills/<name>/SKILL.md` prints `OK`.
- A live copy exists at the intended `.claude/skills/` location.
- A fresh, non-interactive session has produced a correct deliverable from
  a real invocation (both natural-language and literal slash form, if the
  skill is meant to support both) — not just a manual dry run.
- Any limitation the live test surfaced (forked-run gaps, ambiguous
  scoping, fields that turn out MISSING) is written into the skill's own
  `Checks` section, not left as something only you remember.
