---
name: project-disclosure
description: Find every session run against the current project (root plus any subfolders) and draft an AI-use disclosure from those logs, and only from those logs.
context: fork
agent: general-purpose
background: true
---

# Project AI-use disclosure

This is a global skill: it must be invoked from the project's root folder, and
it builds the disclosure from the session logs under `~/.claude/projects`
(the global log store in the Claude configuration folder),
not from anything local to the project itself.

## Finding this project's sessions

The project root is the cwd this skill was invoked from. Do not ask for it or
guess it.

Each session's logs live in a subfolder of `~/.claude/projects` named after
the cwd it ran from, with `:` and path separators replaced by `-`. This
encoding is ambiguous — a literal `-` inside a real folder name is
indistinguishable from an encoded separator — so never trust the encoded name
by itself to decide what is "inside" the project. Instead:

1. Build the encoded root prefix from the project root path and glob
   `~/.claude/projects` for folders starting with it. This is a cheap
   pre-filter, not the final answer.
2. For each candidate folder, open its session file(s) and read the literal
   `cwd` field logged at the start of the session (present in the first
   `user`-type entry). Keep the session only if that `cwd`, normalized
   (case-insensitive, slashes unified, trailing slash trimmed), is exactly
   the project root or a true subpath of it (a full path-segment match, not
   a raw string prefix — `D:\ProjectX-Old` must not match root `D:\ProjectX`).
3. A project folder can hold multiple `.jsonl` files — one per session.
   Filenames are random UUIDs, not date-ordered, so sort all matching
   sessions chronologically by their logged timestamps, not by filename.

Report, in the output, which directories were actually found to have
sessions (root plus any subfolders) so the scope is visible rather than
assumed. If the project root was ever renamed or moved, sessions logged
under the old path won't be found this way — say so as a known limitation
rather than silently omitting them.

## What to extract, per session

- **Model**: the `model` field on assistant messages. This is a model
  id/nickname (e.g. `claude-sonnet-5`), not a formal version string — report
  it as given, don't invent a version number.
- **Provider / access method**: constant for every Claude Code session —
  "Anthropic, via Claude Code CLI" — plus the CLI `version` field if present.
  This doesn't need to be inferred from ambiguous log analysis; state it
  plainly.
- **Permission mode**: the `permissionMode` field. This is the *only*
  approval-related signal the logs contain — there is no per-tool-call
  approve/deny event. It is not necessarily constant for the whole
  session — it can change partway through (e.g. `auto` to `default` and
  back). Report it as the sequence of modes and the intervals they applied
  to, not as a single fixed value. Do not describe or imply per-action
  approval records that don't exist, and do not conclude "a human stayed in
  the loop" from this — that is a judgment call for the human, not the
  skill (see Checks).
- **Files touched and commands run**: from `tool_use` entries (Read, Write,
  Edit, Bash, etc.) — tool name plus its input.
- **Prompts**: the human `user` message text, in chronological order.
  Before including any prompt or command verbatim, scan it for anything
  that looks like a secret, credential, key, or token; redact it in place
  and note in the output that a redaction was made, rather than
  reproducing it.
- **Dates**: session start and end timestamps.

## Deliverables

Produce all three in a single file, `AI-DISCLOSURE.md`, written to the
project root. Overwrite it on each run rather than creating dated copies,
so it stays current as the project continues.

1. **One sentence**, suitable for a presentation slide.
2. **One short paragraph**, suitable for a methods section in a report or paper.
3. **A reporting checklist**, one row per session, with columns: date,
   model, access method, task/purpose (summarized from that session's
   prompts), permission mode, files touched, commands run, and a pointer
   to that session's entry in the prompt appendix (don't inline full
   prompt text into the table — it doesn't fit a row).

   Follow the table with an **appendix** listing, per session, the
   chronological prompt text (redacted per above).

## Checks

- Use only what the logs support. Where they are silent, write `MISSING`
  and say what would need to be looked up, rather than filling the gap
  with something plausible.
- Name the checks that failed as well as the ones that passed.
- Report permission mode and other facts plainly; do not characterize or
  draw conclusions from them (e.g. "a human stayed in the loop", "this was
  closely supervised") — that judgment belongs to the person reading the
  disclosure, not this skill.
