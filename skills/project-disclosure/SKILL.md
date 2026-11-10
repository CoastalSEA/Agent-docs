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
guess it. Note it before running any other command, because the shell may move later.

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
4. Subagent transcripts are not in the session file. A session id may have
   a folder `<session id>/subagents/` holding `agent-<id>.jsonl` (the
   transcript) and `agent-<id>.meta.json` (agent type and description). Read
   each `.jsonl` with its parent session and count its tools, files and
   commands under that session, marked as subagent calls. A subagent log has
   no permission mode: write `MISSING`. A `.meta.json` with no `.jsonl` is
   also `MISSING`.

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

The output folder comes from the shared run script (global Outputs rules),
run for `<project-root>`. The task name is `project-disclosure-<project>`,
where `<project>` is the name of the project root folder; report it plainly.

- Before reading any log, run the run control command in `machine.md`, as
  `path project-disclosure-<project> --root "<project-root>"`. It changes
  nothing. If it exits with an error, stop and report the message; do not
  work round it. If the script is missing, stop and say so.
- When the disclosure is ready, run the same command with `start` in place
  of `path`, and write into the folder it prints.
- Report the run as pending review, with the tag from `run_info.txt`. The
  appendix holds prompt text, so the user decides whether to accept, reject
  or discard it. Do not accept it yourself.

Produce the deliverable in a single file, `AI-DISCLOSURE.md`, in that folder.
The name is fixed, and it is the only file you write there. Write any helper
script to a temporary folder outside the output folder. Use a helper script to
read the logs: do not read whole session files into the conversation.

There are two forms. The short form is the default. The detailed form is made
only when the arguments contain `--detailed` or the user asks for the detailed
disclosure, the checklist or the prompt appendix. Say in the file which form it is.

Both forms start with parts 1 and 2:

1. **One sentence**, suitable for a presentation slide.
2. **One short paragraph**, suitable for a methods section in a report or paper.
   State only recorded facts: the number of sessions, dates, model, access
   method, permission mode, and the kinds of tools used. Make no statement
   about what was not done or not touched: the logs do not show absences.

Part 3 depends on the form.

**Short form, part 3: timeline.** A dated list of the key events of the
project, at most 15 lines, in chronological order. One line per event: the
date, and what was started, produced or changed, taken from the prompts and
the files written. Give the session count, the scope, and the model and
permission modes (as the sequence of modes, per session) once, above the list.
Do not list every file or command, and do not include prompt text. Name a
Write or Edit that was refused or failed as attempted. Name any redaction.
End with one line saying that `--detailed` adds the per-session checklist and
the prompt appendix.

**Detailed form, part 3: reporting checklist and appendix.** One row per
session, with columns: date, model, access method, task/purpose (summarized
from that session's prompts), permission mode, files touched, commands run,
and a pointer to that session's entry in the prompt appendix (don't inline
full prompt text into the table — it doesn't fit a row).

List a Write or Edit under files touched only if the log pairs it with a
result that is not an error. Mark a refused or failed call as attempted,
and write `MISSING` where no result is logged.

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
