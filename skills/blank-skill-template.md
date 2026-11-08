[Copy to skills/<name>/SKILL.md, fill in brackets, delete this note. File must begin with ---. 
Process: see prompts/new-skill-workflow.md. A SKILL.md holds scope, steps, deliverable and checks only; no dates, test history or reasons for a change (those go in DECISIONS), and long reference material goes in a file in the skill folder.
Before deploying: run python skills/check_frontmatter.py.

Frontmatter constraints: description on one line, no `: ` or ` #` inside it. Failed parse is silent—the skill will not fork.
- name: kebab-case folder name.
- description: what it does AND when to use it. Be specific—the harness uses this alone for relevance. If forked, say caller must pass scope in invocation.
- context: fork (optional). Use only when the skill's work generates heavy intermediate output the caller doesn't need and doesn't require mid-task interaction. Otherwise omit.
- agent: general-purpose if skill writes or edits files. Explore/Plan have no Write/Edit—they return text starting with FILE: <path> (caller saves it). Omit for harness default.
- background: true (default) returns agent name at once, result arrives as notification. false blocks and returns inline.]

---
name: <kebab-case-name>
description: <One line saying what the skill does and when to use it, in specific terms>
context: fork
agent: general-purpose
background: true
---

# [Skill title]

[One paragraph: what this skill does, its scope, and any fixed context it
depends on rather than asks for or guesses — e.g. "the project root is the cwd
this skill was invoked from." State the dependency explicitly; don't leave a
fresh agent to infer it.]

## Finding/scoping [the thing this skill acts on]

[If the skill has to locate something (a folder, a file, a record) from an
ambiguous or encoded identifier, say so explicitly and give the verification
step, not just the guess. Ambiguous shortcuts should be a pre-filter only,
confirmed against an authoritative field before being trusted — never the
final answer on their own.]

[State what's out of scope and why, so the skill doesn't silently expand its
remit — e.g. "only sessions logged under this literal path; a renamed root
won't be found this way."]

## What to extract / do

[The concrete steps or fields to pull, one bullet each. For each one that
comes from an external source (a log, an API, a file), name the exact field
or signal it comes from — don't let a fresh agent guess where a fact lives.
Flag anything that's a constant (doesn't need deriving) vs. anything that's
genuinely absent from the source and should be reported as MISSING rather
than inferred.]

## Deliverables

[Exact output location and file name. Follow the global Outputs rules through
the shared run script, run for `<project-root>` (the absolute path of the cwd the
skill was invoked from, noted first, because the shell may move later). The task name is `<skill-name>-<subject>`, where `<subject>` names what
the run is about (a manuscript file name, or a short name given in the
invocation). Before the main work, run
the run control command in `machine.md`, as `path <task> --root "<project-root>"`
(changes nothing; on an error, stop and report it). When the output is ready,
run it with `start` and write into the folder it prints: `outputs/<task>/` in a
git project with tracked outputs (report the run as pending review, with the
proposed tag; only when the user decides, run `accept`, `reject` or `discard`),
otherwise `outputs/<task>-<DDMMYY>-run<N>/`.
A read-only fork runs only `path`; the invoking session runs `start`. The
invoking session never sees this file, so the fork's returned text must carry
that instruction (a `BEFORE SAVING, RUN: <full start command>` line under `FILE:`). Fix the
file name inside the folder, so it is not invented per run. A forked subagent may be refused a Write of a `.md` file whose
name begins with report, summary, findings or analysis, so have it return that file
as text under a `FILE: <path>` line and have the invoking session save it.]

1. [...]
2. [...]

## Checks

- Use only what the [logs/data/inputs] support. Where they are silent, write
  `MISSING` and say what would need to be looked up, rather than filling the
  gap with something plausible.
- Name the checks that failed as well as the ones that passed.
- Report facts plainly; do not characterize or draw conclusions that belong
  to the person reading the output (e.g. don't assert a judgment the source
  data can't actually support).
- [Any limitation the live test surfaced, so it is written into the skill and
  not left as something only you remember.]
