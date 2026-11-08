---
name: analysis-adversary
description: Try to break a reported quantitative result — a fitted value or a negative/no-model-found finding — before it is trusted or written up. Reproduce it independently from raw inputs, check whether the reproduction actually tests what it's claimed to, trace any reused parameter back through its own provenance, stress test it under defensible alternative specifications, and report what would change the answer. Never edits anything under review, because the review runs in a read-only Explore subagent. Use on any estimate or model-search conclusion heading for a paper, a report, or a decision. Not for exploratory analysis you already intend to redo yourself. Pass the result, the raw input paths and the code paths in the invocation arguments, because the skill runs in a forked context and cannot see the conversation.
context: fork
agent: Explore
background: true
---

# Analysis adversary

Your job is to make this result fail. You are not looking for reassurance,
and a clean bill of health is the least likely correct answer. This skill
never edits the analysis, the data, or the write-up it is reviewing — it
only reports. That boundary depends on the review running in a restricted
subagent. `context: fork` and `agent: Explore` make the harness run this
skill in a forked Explore subagent, but only if the frontmatter parses.
Confirmed 20 September 2026 in fresh `claude -p` sessions, by natural-language
and by literal slash invocation, once the description was on one line. Before
that fix the description had unindented continuation lines, the frontmatter
did not parse, and the skill ran in the main session with full tool access.
An earlier note here that the harness ignores the frontmatter in `claude -p`
was wrong. Keep the description on a single line, with no ": " or " #" in it.
Because a forked run cannot see the conversation, the invocation arguments
must name the result, the raw input paths and the code paths.

**Explore has no `Write` or `Edit` tool, which is deliberate, not an
oversight — see Deliverables below for how the report still gets saved. It
does have Bash, which can write files, so the boundary also rests on the
rules in this file and in the subagent's prompt, not on tools alone.**

## Run the review in a subagent

The usual case is that the harness has forked this skill, and you are the
Explore subagent. The rest of this section is the fallback for a session that
finds itself running this text without a fork, for example when the
frontmatter did not parse.

- **If you are already running as an Explore subagent (the usual case):** do
  the review directly.
- **If you are the main session, not forked:** call the Agent tool with
  `subagent_type: Explore` and `run_in_background: false`. The prompt
  contains: the scoped result, raw input paths and code paths from the
  invocation; the Scoping, Steps and Checks sections of this skill pasted in
  full; any data status statement from the invocation; the Subagents
  instructions from the global CLAUDE.md; and instructions to return the
  complete report as its final message, to write scratch scripts only in the
  system temp folder, and to write nothing inside the project. Wait for the
  result, then save the returned text to the deliverable path (see
  Deliverables). Say in your reply that the review ran in a subagent.
- **If the Agent tool is not available:** do not review silently. State at
  the top of the report that the review ran inline, without the tool
  restriction, and why. Follow the same rules by instruction, use Bash only
  to read and to run your own scratch scripts outside the project, and change
  nothing under review.

## Scoping — what you're reviewing

If the invocation doesn't say which result, dataset, and write-up (if any)
to review, ask rather than guessing — a project can have many superseded
runs of the same analysis (this is common, not unusual), and reviewing the
wrong one silently is worse than asking. **Where the task itself has a run
history** (a task file with its own "Done"/status log naming a current
result and superseded ones, or a report that says which earlier run it
replaces) — common in exploratory, relationship-hunting work where several
specifications are tried before one is accepted — scope to the specific
result that history marks current, not the whole genealogy, unless asked
to review the history itself. Once scoped, state explicitly: the specific
reported outcome under review (a fitted value, *or* a negative/no-model-
found result across a stated candidate set — both are reviewable claims,
not just the former), the specific raw input file(s) it's claimed to
derive from, and the specific script or method (if one exists) that
produced it.

**Independently re-derive before comparing to any existing script — and
never execute the existing script to make that comparison.** If an
existing analysis script produced the claimed result, do not simply re-run
it and call that "reproducing" — that only confirms the script is
deterministic, not that it's correct, and inherits any bug or assumption
in it unchecked. Write your own independent implementation from the raw
inputs and the stated method first. Only after that, compare your result
against the existing script's **already-written output** — its report,
its already-existing output files, read as they stand — and against its
**code**, read for logic, never run. **Do not execute the original
script under review, even just to compare.** Confirmed live: doing so
overwrote two of the target project's own output files in place at their
original path, changing their timestamps (the content is very likely
unchanged, since the script is deterministic, but the file state of the
project under review was still altered — the "never edit anything"
boundary should not depend on a reviewed script happening to be
idempotent or side-effect-free). If comparing against the existing
script's logic genuinely requires running code, run your own independent
reimplementation, never the original file, and never with its output path
unchanged if you do.

**Data notes are allowed input, but they are not verification.** If the
project has a `data/DATA-NOTES.md`, read it for what each data file is
(source, row order, units, links between files, known problems). It
records facts about the data, not results, so reading it does not
compromise an independent re-derivation. Treat its statements as claims to
check, not as checked: where the result depends on a stated fact (row
order, units, a link between two files), confirm it against the data
itself and report that check.

**Data status: check the invocation.** If it says the data is taken as
given (already validated, or not in scope), do not check the accuracy of
the data values: no external searches, and no comparison with source
literature, other datasets or other reports to validate them. Everything
else still applies: reproduce the result, review the analysis, the
exclusions and splits, the parameter provenance and the alternative
specifications. Keep only the internal consistency checks the result
depends on (row alignment, units as used, a stated link between two
files), made with the files supplied, and report any mismatch as a fact
without judging the data. State in the report that data accuracy was out
of scope by instruction. With no such instruction, the steps below apply
as written.

## Steps

1. **Reproduce the reported outcome independently**, per the scoping note
   above — a specific fitted value, or a negative/no-model-found result
   across a stated candidate set. For a negative result, reproducing means
   confirming the reported search was actually complete and each candidate
   genuinely failed the stated criterion, not just that the "no model
   found" conclusion sounds plausible. If it does not reproduce, stop and
   say so plainly; nothing below matters until it does, or until the
   discrepancy itself is understood and reported.

   **Then check what the reproduction actually tests, not only whether it
   passes.** A parameter fixed at a particular value (rather than fitted)
   can make part of the model cancel out algebraically, so a passing fit
   can be true arithmetic while testing a much weaker or different claim
   than the one being asserted. Confirmed live: a model's channel-geometry
   terms vanished exactly at one specific fixed parameter value.

   **Before concluding the claim isn't being tested, check whether that
   collapse is itself a named, derived special case in the project's own
   theory — not an artifact you're the first to notice.** Confirmed live,
   and the correction matters: what looked like an arbitrary reduction
   turned out to be exactly a limiting case the source derivation document
   stated explicitly (a "no along-channel damping" limit named in the
   project's own method document, reachable by tracing the fixed value
   back through the model's derivation, not just the script). Reframing
   "the theory isn't being tested" as "only the theory's own limiting-case
   prediction is being tested here, not its general content" is a real
   difference — check the theory's source derivation, not just the code,
   before asserting the stronger claim. The weaker, still-real concern
   this often leaves standing is which data points get treated as falling
   into that limiting case — see the classification-circularity check
   below.
2. **Report the estimation sample as a fraction of the rows you were
   given.** Name what was dropped, how much, and whether anything left the
   sample entirely. Missing or excluded data is usually removed silently —
   check whether any exclusion, filter, or group split in the original
   work is itself data-driven and independently verifiable from the data
   under review, not just asserted to be.

   **"Independently verifiable" is not the same as "independent of the
   variable being tested" — check both separately.** A group split can be
   perfectly reproducible from the data (confirm it, as above) while still
   being derived from the same dependent variable a downstream check then
   evaluates against — confirmed live: a split reproduced exactly from raw
   data every time, and was still built by inverting a parameter from each
   row's own value of the variable the downstream fit was checked against.
   Name this **classification circularity** explicitly when it's present,
   distinct from a bare reused-parameter concern (Step 3): the question
   isn't whether the split can be reproduced, it's whether group membership
   was decided using information independent of the outcome being tested,
   or backed out from that same outcome.
3. **Trace any reused or imported parameter back through its own
   provenance chain**, however many hops it takes, rather than treating
   "it was fitted somewhere" as sufficient. A value carried over from a
   different, prior analysis was fitted under that analysis's own sample
   and assumptions — check whether those still hold in this narrower or
   different context, not just whether the value reproduces where it came
   from. This can run several reports deep, not just one hop from the
   result under review — confirmed live in one real case, a chain of
   reused formulas and coefficients ran four analyses deep. Where the
   provenance can be checked, also check whether the acceptance criterion
   this run applies would still favor the reused value over other
   candidates, evaluated on this run's own narrower data — confirmed live
   to matter: a reused correction factor was not the value this run's own
   metric actually preferred, once evaluated against the narrower subset
   alone rather than the broader one it was originally fitted on.
4. **Re-fit under at least two defensible alternative specifications.**
   Report every one, including any that shrink the estimate, widen it past
   zero, or reverse its sign. "Defensible" means an alternative a reviewer
   would accept, not one you expect to agree with the original — examples:
   a different covariate/predictor set, a different subsample restriction
   or inclusion criterion, a different functional form (e.g. linear vs.
   power-law vs. log-log), a different grouping or split rule than the one
   used, or a different treatment of an excluded/flagged data point.
5. **Name the single choice that most changes the answer**, and say
   whether the write-up mentions making it. **When that choice is a
   continuous parameter** (a threshold, a correction factor, a cutoff — not
   a binary or categorical choice), sweep it numerically across a
   defensible range rather than only naming it and checking disclosure.
   Confirmed live to matter: naming a correction factor as consequential
   and stopping there would have missed that a materially different value
   of it passes the same acceptance test *better* than the one actually
   used — the more informative finding was in the sweep, not the
   disclosure check.
6. **Change nothing. You report; the author decides.** Never edit the
   data, the analysis script, or the write-up under review — flag, don't
   fix, the same hard boundary this project's other skills observe for
   their own domains.

## Deliverables

**This skill's own subagent has no `Write` tool — confirmed live, and
deliberate, not a bug to route around.** It does have Bash, so it must not
write the report file by shell either. Return the full report as the
response text instead of saving a file. **Begin that text with a line
`FILE: <deliverable path>`**, so the session that receives it knows to save
it (the global Subagents rule), and put this line directly under it,
with the subject and the absolute project root filled in (the invoking
session never sees this file, so the returned text must carry the
instruction):
`BEFORE SAVING, RUN the run control command in machine.md: start analysis-adversary-<subject> --root "<project-root>", then save this report into the folder it prints, as analysis-adversary-report.md. If it refuses, do not save the report anywhere; show the user the message.`

The output folder comes from the shared run script (global Outputs rules),
run for `<project-root>`: the absolute path of the cwd the skill was
invoked from, noted before any other command, because the shell may move
later. The task
name is `analysis-adversary-<subject>`. `<subject>` is the short name given
in the invocation for the result under review; if none is given, derive two
to four words from the scoped result and state them in the summary, so a
review of the same result can reuse the name (a different name starts a
new task folder). Before Step 1, run
the run control command in `machine.md`, as `path analysis-adversary-<subject> --root "<project-root>"`.
It writes nothing, so it is allowed here. If it exits with an error (for
example the folder would be git-ignored), stop
and return the message; do not work round it. If the script is missing,
stop and say so. The deliverable path is the folder it prints plus the file name
`analysis-adversary-report.md`.

**The session that invoked this skill is responsible for taking that
returned text and writing it** — it has ordinary `Write` access and isn't
the one under the read-only constraint; only the review itself is. It runs
the `BEFORE SAVING, RUN:` command, and writes the report into the folder
that prints. In a git project with
tracked outputs this is `outputs/analysis-adversary-<subject>/`, with its
files other than `.md` removed (overwrite the old report); otherwise it is a new `outputs/analysis-adversary-<subject>-<DDMMYY>-run<N>/`.
If that folder differs from the `FILE:` line, use the printed folder and
say so. In tracked mode, report the run as pending review with the proposed
tag from `run_info.txt`, and say so if `start` warned that it replaced a
pending run. Do not accept the run yourself: when the user accepts, rejects
or discards it, run `run_control.py accept`, `reject` or `discard` for the task. Don't silently drop this
handoff — if you are the invoking session receiving this skill's returned
text, save it before considering the task done.

**Known gap, confirmed 20 September 2026.** When the skill is started by a
literal slash command at the top level of a non-interactive `claude -p`
session, the forked run's report comes back as the command's output and no
session is left to save it, so no file is written. In that form, save the
output yourself. The natural-language form saved the file correctly, because
the invoking session followed the `FILE:` line. The interactive slash form is
untested.

The report itself, whether returned as text or subsequently saved to that
path, covers:

1. **Summary** — the claim under review (a fitted value or a negative/
   no-model-found result), whether it reproduced independently, whether
   the reproduction actually tests what it's reported to test (see Step
   1's structural-collapse check), and pass/fail against whatever
   acceptance criterion the original work stated (or "no stated criterion"
   if none exists).
2. **Sample** — rows given vs. rows used, what was excluded and why,
   whether each exclusion/split is independently verifiable from the raw
   data under review, and separately, whether it exhibits classification
   circularity (group membership decided from the same variable the
   downstream check evaluates against).
3. **Provenance** — any reused or imported parameter, fit, or coefficient,
   traced back through however many prior analyses it came from, and
   whether the assumptions and acceptance criterion behind it still hold
   in this narrower or different context.
4. **Alternative specifications** — every one tried, with its own result,
   not just the ones that changed the answer.
5. **The single most consequential choice**, and whether the original
   write-up disclosed making it.
6. **What could not be checked**, stated plainly. If the data was taken
   as given, say here that data accuracy was out of scope by instruction.

## Checks

- Never edit the data, the analysis code, or the write-up under review —
  flag, don't fix.
- Never execute the original script under review, even for comparison —
  confirmed live that this can silently overwrite the project's own output
  files in place. Compare against its already-written output and its code
  read for logic, not by running it.
- The report states at least one number the author's own write-up did not
  state.
- Every alternative specification is reported with its own sample size,
  not just its coefficient.
- When uncertain, the report names a problem rather than issuing a clean
  bill of health.
- The report ends by naming what it could not check.
- The review ran in an Explore subagent (a forked execution, or an Agent
  call visible in the session log), or the report says at the top that it
  ran inline and why.
- If the invocation said to take the data as given, no data value was
  checked against an outside source, only internal consistency facts the
  result depends on were checked, and the report says so.
- A reused or imported fit, coefficient, or group split (not re-derived
  within the scope of the specific result under review) is flagged
  explicitly, not treated as equivalent to one independently verified here,
  and traced back through its own provenance chain, not just one hop.
- A passing fit is checked for whether a fixed parameter value causes part
  of the model to cancel out algebraically — a pass can be true arithmetic
  while testing something weaker than what's claimed. Before calling this a
  weaker or undisclosed claim, check whether the collapsed form is itself a
  named special case in the project's own theory documentation — if so,
  say what narrower claim is actually being tested, don't assert the
  theory isn't being tested at all.
- A group split is checked separately for independent verifiability (can
  it be reproduced from the data) and for classification circularity
  (was membership decided using the same variable the downstream check
  evaluates) — a split can have one property without the other.
- A negative/no-model-found result is treated as a reviewable claim in its
  own right, not skipped for lack of a single number to reproduce.
- The subagent returns its report as text, and the invoking session saves it
  to the deliverable path before treating the task as done — don't let the
  handoff silently drop. When the review ran inline (see "Run the review in a
  subagent"), the session saves its own report to the same path. The returned
  text begins with the `FILE:` line.
