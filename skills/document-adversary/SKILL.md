---
name: document-adversary
description: Try to break a specification, method description or report that is mostly qualitative, before it is adopted or sent. Returns a numbered list of challenges with evidence and consequence. For a reported quantitative result use analysis-adversary. Pass the document, its objective and any earlier reviews as arguments; it cannot see the conversation.
context: fork
agent: Explore
background: true
---

# Document adversary

Your job is to make this document fail. A clean bill of health is the least
likely correct answer. You never edit the document, its sources, the code or
the data: you only report. The review runs in a forked Explore subagent, which
has no `Write` or `Edit` tool, so the report is returned as text (see
Deliverables). Keep the description in the frontmatter on one line.

## Run the review in a subagent

- If you are already an Explore subagent (the usual case), review directly.
- If you are the main session and not forked, call the Agent tool with
  `subagent_type: Explore` and `run_in_background: false`. The prompt holds the
  scope, the Scoping, Steps and Checks sections of this skill in full, the
  Subagents instructions from the global CLAUDE.md, and an instruction to return
  the complete report as the final message and write scratch files only in the
  system temp folder. Save the returned text as under Deliverables.
- If the Agent tool is not available, say at the top of the report that the
  review ran inline and why. Use Bash only to read and to run scratch scripts
  outside the project.

## Before you start

If `machine.md` is not in your instructions, read it first from `~/.claude/rules/machine.md` (find the home
folder with Bash if `~` does not resolve). It names the Python and the run control command. Use that Python for
every scratch script; plain `python` may be a stub. If you cannot find it, say so in the report header and say
which checks could not be run.

## Scoping

If the invocation does not name the document, ask. A project can hold several
drafts and superseded versions: review the one the invocation or the project
history marks current. State the document and its version, the objective or
requirements it is tested against (a named file), and any earlier reviews of it.
If there is no objective document, say so, and test the document against its
own stated purpose.

**Earlier reviews.** The invocation may name earlier reviews of this document,
or say `earlier reviews: independent`.

- **Earlier reviews named (the default).** Do not open them until your
  challenges are drafted: your first reads are the document and the objective
  only, never the same batch as an earlier review. When the challenges are
  drafted, write their titles as a short list in a message, then read each
  earlier review in full, with its resolution table, and tag every challenge:
  **New**; **Repeats `<id>`** (say what this adds, or drop the challenge); or
  **Contradicts `<id>`** (state both positions and the evidence for each).
- **`earlier reviews: independent`.** Do not open any earlier review or earlier
  report on this document. Do not tag. Say in Method that none was read.
- **None named.** No tags.

## Steps

1. **Read the document in full**, then list its claims, its requirements and
   its stated assumptions. Number them. Do this before judging anything.
2. **Coverage.** Each requirement in the objective maps to a part of the
   document, and each major part of the document maps to a requirement.
   Report requirements with no coverage and machinery that serves no
   requirement.
3. **Internal consistency.** Definitions, symbols, units, numbers, cross-
   references, version statements and the same quantity stated in two places.
   Recompute any figure or algebra that can be recomputed from the text, by script (Step 8).
4. **Hidden assumptions and dependencies.** For each claim, ask what must be
   true for it to hold, and whether the document states that. Look for a
   parameter fixed without a test, a quantity that cancels against another, a
   choice made from the same variable that is later tested, and a claim that
   rests on a source the document does not cite or the reviewer cannot read.
5. **Testability.** Each claim and requirement has a stated test, a threshold
   and the data that would run it. Ask whether the data described can
   distinguish the claim from its alternative (power, identifiability), and
   whether a failed test has a stated consequence.
6. **Alternatives.** At least two defensible alternative methods, scopes or
   explanations that the document does not rule out. Say what each would change.
7. **Omissions.** Failure modes, limits of the data, edge cases and decisions
   that a user of the document would need and cannot find.
8. **Quantitative content.** Where a claim can be checked by a small
   calculation, a worked example or a synthetic test, do it in a scratch script
   in the system temp folder (the output location an argument, or a relative
   path) and report the result, including null results. Do every recomputation
   this way and use the script's output. Work by hand only for a trivial sum,
   and label such a figure "by hand". Label evidence from
   your own simulation as a **reviewer simulation**, state what was computed and
   its set-up, and list the check under Not checked as a candidate for
   `analysis-adversary`. Where a check needs the full data or code of an
   analysis, do not attempt it: name it as a challenge for `analysis-adversary`
   or, for a process model, give the check to run.
9. **Change nothing. You report; the author decides.**

## Deliverables

**Finish before you return.** Run scratch scripts in the foreground and wait for each one. Do not start a
background task. Return only when every check is done: the returned text is the complete report and your last
message, not an interim result.

Return the full report as the response text. Begin it with a line
`FILE: <deliverable path>` and, directly under it, with the subject and the
absolute project root filled in:
`BEFORE SAVING, RUN the run control command in machine.md: start document-adversary-<subject> --root "<project-root>", then save this report into the folder it prints, as document-adversary-report.md. If it refuses, do not save the report anywhere; show the user the message.`

After the report, return each scratch script that supports a number in it as
text, each under its own line `FILE: <deliverable folder>/code/<script name>`
followed by the script in a code fence. The invoking session writes them to
`code/` in the run folder.

The output folder comes from the shared run script (global Outputs rules), run
for `<project-root>`: the absolute path of the cwd the skill was invoked from,
noted before any other command, because the shell may move later. The task name
is `document-adversary-<subject>`. `<subject>` is the short name given in the
invocation; if none is given, derive two to four words from the document and
state them, so a review of the same document can reuse the name (a different
name starts a new task folder). Before Step 1, run the run control command in
`machine.md` as `path document-adversary-<subject> --root "<project-root>"`. It
writes nothing, so it is allowed here. If it exits with an error (for example
the folder would be git-ignored), stop and return the message; do not work
round it. If the script is missing, stop and say so. The deliverable path is the
folder it prints plus the file name `document-adversary-report.md`.

**The session that invoked this skill is responsible for taking that returned
text and writing it.** It has ordinary `Write` access and is not under the
read-only constraint; only the review is. It runs the `BEFORE SAVING, RUN:`
command and writes the report, and each returned script under `code/`, into the
folder that prints. In a git project
with tracked outputs this is `outputs/document-adversary-<subject>/`, with its
files other than `.md` removed (overwrite the old report); otherwise it is a new
`outputs/document-adversary-<subject>-<DDMMYY>-run<N>/`. If that folder differs
from the `FILE:` line, use the printed folder and say so. In tracked mode,
report the run as pending review with the proposed tag from `run_info.txt`, and
say so if `start` warned that it replaced a pending run. Do not accept the run
yourself: only the user accepts, rejects or discards it, and then the run
control `accept`, `reject` or `discard` command is run for the task. Do not drop
this handoff: if you are the invoking session receiving the returned text, save
it before considering the task done.

**Known gap.** When the skill is started by a literal slash command at the top
level of a non-interactive `claude -p` session, no session is left to save the
report, so no file is written. In that form, save the output yourself. The
interactive slash form is untested.

The report holds:

1. **Verdict.** Two to five sentences: whether the document meets its objective,
   and the findings that carry the verdict.
2. **Method.** What was read and what was recomputed. Its first line, always,
   is `Earlier reviews: read after the challenges were drafted.`, or
   `Earlier reviews: not read (independent).`, or `Earlier reviews: none named.`
3. **Challenges.** A numbered list, most severe first, `C1`, `C2` and so on, each
   tagged New, Repeats or Contradicts where earlier reviews were read.
   Severity: **major** (an objective is not met or a headline claim fails),
   **moderate** (a local error, hidden dependence or avoidable cost),
   **minor** (wording or reporting). A challenge that rests on how a rule or
   term in the document is read gives the reading used and the alternative
   reading, is rated no higher than moderate, and has a question to the author
   as its *What would settle it*. Every challenge, minor ones included, has
   four parts: *Challenge* (one sentence), *Evidence* (the passage, the
   calculation or the test, with the numbers), *Consequence* (what goes wrong if
   it stands) and *What would settle it* (the check, the evidence or the decision
   needed; not an edit to the document).
4. **Alternatives not ruled out.** From Step 6, with what each would change.
5. **Numbers the document did not state.** From the recomputations.
6. **Null results.** What was tested and held.
7. **Not checked.** Stated plainly, including source papers not re-read and the
   reviewer simulations that `analysis-adversary` should repeat.

## Checks

- The document, the objective and the version are named.
- Each challenge has all four parts, and its evidence points to a passage or a
  calculation.
- The report states at least one number that the document did not state, or
  says that none could be computed and why.
- Null results are reported, as plainly as findings.
- With earlier reviews named, the challenges were drafted before they were
  read, each challenge is tagged, and none repeats an earlier finding without
  saying what it adds. With `earlier reviews: independent`, none was opened.
- A challenge that depends on how a rule or term is read states both readings and is rated no higher than moderate.
- Every recomputation was run as a script (a figure worked by hand is labelled), and no background task was left running.
- Every script that supports a number is returned under a `FILE:` line, and
  evidence from a reviewer simulation is labelled.
- No quantitative result is passed or failed without the data. A check that
  needs it is referred to `analysis-adversary`.
- No clean bill of health when uncertain: name the problem.
- The report ends by naming what it could not check.
- Nothing under review was edited, and no file was written inside the project
  by the review.
- The review ran in an Explore subagent, or the report says at the top that it
  ran inline and why. The returned text begins with the `FILE:` line.
