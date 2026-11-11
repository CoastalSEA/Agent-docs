---
name: analysis-adversary
description: Try to break a reported quantitative result (a fitted value, no-model-found finding or process-model output) before it is trusted or written up. Reproduce it from raw inputs, stress test it and report what would change the answer. Not for exploratory work. Pass the result, raw input paths and code paths as arguments; it cannot see the conversation.
context: fork
agent: Explore
background: true
---

# Analysis adversary

Your job is to make this result fail. You are not looking for reassurance, and
a clean bill of health is the least likely correct answer. This skill never
edits the analysis, the data, or the write-up it is reviewing: it only reports.

The boundary depends on the review running in a restricted subagent.
`context: fork` and `agent: Explore` make the harness run this skill in a forked
Explore subagent, but only if the frontmatter parses. Keep the description on a
single line, with no ": " or " #" in it. A forked run cannot see the
conversation, so the invocation arguments must name the result, the raw input
paths and the code paths.

Explore has no `Write` or `Edit` tool, deliberately. It does have Bash, which
can write files, so the boundary also rests on the rules in this file and in
the subagent's prompt, not on tools alone.

## Run the review in a subagent

The usual case is that the harness has forked this skill and you are the
Explore subagent. The rest of this section is the fallback for a session that
finds itself running this text without a fork.

- **Already an Explore subagent (usual):** do the review directly.
- **Main session, not forked:** call the Agent tool with `subagent_type: Explore`
  and `run_in_background: false`. The prompt contains: the scoped result, raw
  input paths and code paths from the invocation; the Scoping, Steps,
  Process-model results and Checks sections of this skill in full; any data
  status statement from the invocation; the Subagents instructions from the
  global CLAUDE.md; and instructions to return the complete report as its final
  message, to write scratch scripts only in the system temp folder, and to write
  nothing inside the project. Wait for the result, then save the returned text
  to the deliverable path (see Deliverables). Say in your reply that the review
  ran in a subagent.
- **Agent tool not available:** state at the top of the report that the review
  ran inline, without the tool restriction, and why. Follow the same rules by
  instruction, use Bash only to read and to run your own scratch scripts outside
  the project, and change nothing under review.

## Before you start

If `machine.md` is not in your instructions, read it first from `~/.claude/rules/machine.md` (find the home
folder with Bash if `~` does not resolve). It names the Python and the run control command. Use that Python for
every scratch script; plain `python` may be a stub. If you cannot find it, say so in the report header and say
which checks could not be run.

## Scoping

If the invocation does not say which result, dataset and write-up (if any) to
review, ask rather than guess: a project can have many superseded runs of the
same analysis, and reviewing the wrong one silently is worse than asking. Where
the task has a run history (a status log naming a current result and superseded
ones, or a report that says which run it replaces), scope to the result that
history marks current, not the whole genealogy, unless asked to review the
history.

Once scoped, state: the reported outcome under review (a fitted value, or a
negative or no-model-found result across a stated candidate set: both are
reviewable claims), the raw input file(s) it is claimed to derive from, and the
script or method (if one exists) that produced it. When the result comes from a
process model (a simulation or numerical model built from governing equations,
calibrated to data), also state the model version, the calibration data and the
validation data, and whether the invocation allows the model code to be run
(see Process-model results).

**Several claims.** If the invocation lists several claims, scope each one, and
lay the report out as set out before item 1 under Deliverables.

**Earlier reviews.** The invocation may name earlier reviews or reports on this
result, or say `earlier reviews: independent`.

- **Earlier reviews named (the default).** Do not open them until your findings
  are drafted: your first reads are the raw inputs and the code only, never the
  same batch as an earlier review. When the findings are drafted, write their
  titles as a short list in a message, then read each earlier review in full,
  with its resolution table, and tag every finding: **New**; **Repeats `<id>`**
  (say what this adds, or drop it); or **Contradicts `<id>`** (state both
  positions and the evidence for each).
- **`earlier reviews: independent`.** Do not open any earlier review or report on
  this result. Do not tag.

The first line of the report, always, is `Earlier reviews: read after the
findings were drafted.`, or `Earlier reviews: not read (independent).`, or
`Earlier reviews: none named.`
- **None named.** No tags.

**Re-derive independently, and never execute the existing script.** If an
existing script produced the claimed result, do not re-run it and call that
reproducing: it only confirms the script is deterministic, and it inherits any
bug or assumption in it. Write your own implementation from the raw inputs and
the stated method first. Only then compare your result with the script's
already-written output (its report and existing output files, read as they
stand) and with its code, read for logic and never run. Do not execute the
original script, even to compare: it can overwrite the project's own output files
in place. If the comparison genuinely needs code to run, run your own
reimplementation, never the original file, and never with its output path
unchanged.

**Data notes are input, not verification.** If the project has a
`data/DATA-NOTES.md`, read it for what each data file is (source, row order,
units, links between files, known problems). It records facts, not results, so
reading it does not compromise an independent re-derivation. Treat its
statements as claims to check: where the result depends on a stated fact, confirm
it against the data and report that check.

**Data status.** If the invocation says the data is taken as given (already
validated, or not in scope), do not check the accuracy of the data values: no
external searches, and no comparison with source literature, other datasets or
other reports. Everything else still applies: reproduce the result, review the
analysis, the exclusions and splits, the parameter provenance and the
alternative specifications. Keep only the internal consistency checks the result
depends on (row alignment, units as used, a stated link between two files), made
with the files supplied, and report any mismatch as a fact without judging the
data. State in the report that data accuracy was out of scope by instruction.
With no such instruction, the steps below apply as written.

## Steps

For a process-model result, do the Process-model results section as part of
these steps, before you write the report, and give its report item 7.

1. **Reproduce the reported outcome independently**, per Scoping. For a negative
   result, reproducing means confirming that the reported search was complete
   and each candidate failed the stated criterion, not that "no model found"
   sounds plausible. If it does not reproduce, stop and say so plainly; nothing
   below matters until it does, or until the discrepancy is understood and
   reported.

   **Then check what the reproduction tests, not only whether it passes.** A
   parameter fixed at a particular value (not fitted) can make part of the
   model cancel algebraically, so a passing fit can be true arithmetic while
   testing a weaker or different claim than the one asserted. Before calling
   that a weaker claim, check whether the collapsed form is a named, derived
   special case in the project's own theory (read the source derivation
   document, not only the code, and trace the fixed value back through it). If
   it is, say that only the theory's limiting-case prediction is being tested,
   not that the theory is untested. The concern that remains is which data
   points are treated as falling into that limiting case (see the
   classification circularity check in Step 2).
2. **Report the estimation sample as a fraction of the rows you were given.**
   Name what was dropped, how much, and whether anything left the sample
   entirely. Check whether any exclusion, filter or group split in the original
   work is data-driven and independently verifiable from the data under review,
   not just asserted.

   **Verifiable is not the same as independent of the variable being tested:
   check both separately.** A group split can be reproduced exactly from the data
   and still be built from the same dependent variable that a downstream check
   evaluates against (for example, by inverting a parameter from each row's own
   value of that variable). Name this **classification circularity** when it is
   present, distinct from a bare reused-parameter concern (Step 3): the question
   is whether group membership was decided with information independent of the
   outcome being tested.
3. **Trace any reused or imported parameter back through its own provenance
   chain**, however many hops it takes. A value carried over from a prior
   analysis was fitted under that analysis's sample and assumptions: check
   whether those still hold in this narrower or different context, not only
   whether the value reproduces where it came from. The chain can run several
   reports deep. Where the provenance can be checked, also check whether this
   run's acceptance criterion, evaluated on its own narrower data, would still
   favour the reused value over other candidates.
4. **Re-fit under at least two defensible alternative specifications.** Report
   every one, including any that shrink the estimate, widen it past zero or
   reverse its sign. Defensible means an alternative a reviewer would accept,
   not one you expect to agree with the original. Examples: a different
   covariate or predictor set, a different subsample restriction or inclusion
   criterion, a different functional form (linear, power-law, log-log), a
   different grouping or split rule, or a different treatment of an
   excluded or flagged data point.
5. **Name the single choice that most changes the answer**, and say whether the
   write-up mentions making it. When that choice is a continuous parameter (a
   threshold, a correction factor, a cutoff), sweep it numerically across a
   defensible range rather than only naming it: a materially different value may
   pass the same acceptance test better than the one used, and that finding is
   in the sweep, not in the disclosure check.
6. **Change nothing. You report; the author decides.** Never edit the data, the
   analysis script or the write-up under review.

## Process-model results

Apply this section as well as the Steps when the result is an output of a
process model. Steps 2 to 5 still apply.

The report then has a seventh section headed **Process-model checks** (see
Deliverables). It is required. It lists every check below as done, with its
numbers, or not done, with the reason. Do not leave a check out of the list.

- **Reproduction.** Re-implement the governing equations in a reduced form from
  the specification, with your own code, and compare with the model's
  already-written output. Where a reduced form cannot reproduce the output, test
  the model's own output against analytic solutions, limiting cases and
  conservation instead, and say that the full model was not reproduced.
- **Running the model.** Do not run the original model code. Run a copy only if
  the invocation says the model may be run: put the copy in the system temp
  folder, set every output path there, and state in the report that a copy was
  run.
- **Verification.** Conservation (mass or volume closes to the stated
  tolerance), dimensions and units, limiting cases with a known answer, and
  convergence in step size and resolution. Report each as a number.
- **Calibration and validation.** Name the calibration and validation data.
  Check that the validation data was not used to choose parameters, settings or
  the model form. Compare the skill with a trivial baseline (persistence,
  climatology or the initial state), on the validation data only.
- **Identifiability.** Generate synthetic data from the model with known
  parameters, at the real sampling dates and noise level, and fit it. Report the
  share of fits that recover each parameter within a stated factor, and any
  parameters that cancel or trade off against each other.
- **Misspecification.** For each parameter or exponent fixed without a test,
  free it, or fit data generated with a different value, and report the bias in
  the calibrated parameters and the change in fit. A bias that the fit statistic
  does not reveal is a finding.
- **Sensitivity.** Sweep the inputs and settings that the result depends on
  (forcing, datum, boundary and initial conditions, the model step), one at a
  time across a defensible range, with the sample size for each. Name the one
  that changes the result most (Step 5).
- **Equifinality and uncertainty.** Look for parameter sets that fit as well but
  predict differently. Compare the reported uncertainty with the spread you find.

## Deliverables

**Finish before you return.** Run scratch scripts in the foreground and wait for each one. Do not start a
background task. Return only when every check is done: the returned text is the complete report and your last
message, not an interim result.

The skill's subagent has no `Write` tool, deliberately, and must not write the
report file by shell either. Return the full report as the response text.
**Begin that text with a line `FILE: <deliverable path>`**, so the session that
receives it knows to save it (the global Subagents rule), and put this line
directly under it, with the subject and the absolute project root filled in (the
invoking session never sees this file, so the returned text must carry the
instruction):
`BEFORE SAVING, RUN the run control command in machine.md: start analysis-adversary-<subject> --root "<project-root>", then save this report into the folder it prints, as analysis-adversary-report.md. If it refuses, do not save the report anywhere; show the user the message.`

After the report, return every scratch script that supports a number in it as
text, each under its own line `FILE: <deliverable folder>/code/<script name>`
followed by the script in a code fence. Write each script so that the output
location is an argument or a relative path, so a rerun from the saved folder
works. Print p-values in scientific notation when they are below 1e-3, so a small value does not show as 0.0. The invoking session writes them to `code/` in the run folder.

The output folder comes from the shared run script (global Outputs rules), run
for `<project-root>`: the absolute path of the cwd the skill was invoked from,
noted before any other command, because the shell may move later. The task name
is `analysis-adversary-<subject>`. `<subject>` is the short name given in the
invocation for the result under review; if none is given, derive two to four
words from the scoped result and state them, so a review of the same result can
reuse the name (a different name starts a new task folder). Before Step 1, run
the run control command in `machine.md` as
`path analysis-adversary-<subject> --root "<project-root>"`. It writes nothing,
so it is allowed here. If it exits with an error (for example the folder would be
git-ignored), stop and return the message; do not work round it. If the script is
missing, stop and say so. The deliverable path is the folder it prints plus the
file name `analysis-adversary-report.md`.

**The session that invoked this skill is responsible for taking that returned
text and writing it.** It has ordinary `Write` access and is not under the
read-only constraint; only the review is. It runs the `BEFORE SAVING, RUN:`
command and writes the report, and each returned script under `code/`, into the
folder that prints. In a git project with
tracked outputs this is `outputs/analysis-adversary-<subject>/`, with its files
other than `.md` removed (overwrite the old report); otherwise it is a new
`outputs/analysis-adversary-<subject>-<DDMMYY>-run<N>/`. If that folder differs
from the `FILE:` line, use the printed folder and say so. In tracked mode, report
the run as pending review with the proposed tag from `run_info.txt`, and say so
if `start` warned that it replaced a pending run. Do not accept the run yourself:
when the user accepts, rejects or discards it, run `run_control.py accept`,
`reject` or `discard` for the task. Do not drop this handoff: save the returned
text before considering the task done.

**Known gap.** When the skill is started by a literal slash command at the top
level of a non-interactive `claude -p` session, the forked run's report comes
back as the command's output and no session is left to save it, so no file is
written. In that form, save the output yourself. The natural-language form saves
the file, because the invoking session follows the `FILE:` line. The interactive
slash form is untested.

With several claims, the report is a table of the claims and their status
(reproduced, not reproduced, not checked), then one block per claim headed
`Claim 1`, `Claim 2` and so on, each holding items 1 to 6 and, for a
process-model claim, item 7 under its own heading **Process-model checks**. The
items common to all claims (what could not be checked, scripts) come once at
the end.

The report, whether returned as text or saved, covers:

1. **Summary**: the claim under review (a fitted value or a negative result),
   whether it reproduced independently, whether the reproduction tests what it is
   reported to test (Step 1), and pass or fail against the acceptance criterion
   the original work stated (or "no stated criterion").
2. **Sample**: rows given and rows used, what was excluded and why, whether each
   exclusion or split is independently verifiable from the raw data, and
   separately whether it shows classification circularity.
3. **Provenance**: any reused or imported parameter, fit or coefficient, traced
   back through however many prior analyses it came from, and whether the
   assumptions and acceptance criterion behind it still hold here.
4. **Alternative specifications**: every one tried, with its own result and its
   own sample size, not only the ones that changed the answer.
5. **The single most consequential choice**, and whether the write-up disclosed
   making it.
6. **What could not be checked**, stated plainly. If the data was taken as given,
   say here that data accuracy was out of scope by instruction.
7. **Process-model checks** (required for a process-model result, under that
   heading): the verification numbers, the calibration and validation split,
   identifiability, misspecification and sensitivity results, each with its own
   sample size. Say which were not done and why.

## Checks

- Never edit the data, the analysis code or the write-up under review. Never
  execute the original script under review, even for comparison.
- The report states at least one number that the author's own write-up did not
  state.
- Every alternative specification is reported with its own sample size.
- A comparison made in words (no better than a guess, much larger, negligible)
  gives both numbers and the base they are measured on.
- With earlier reviews named, the findings were drafted before they were read and
  each is tagged; with `earlier reviews: independent`, none was opened.
- Every figure was computed by a script, and no background task was left running.
- Every script that supports a number is returned under a `FILE:` line, and its
  output location is an argument or a relative path.
- When uncertain, the report names a problem rather than issuing a clean bill of
  health, and it ends by naming what it could not check.
- The review ran in an Explore subagent (a forked execution, or an Agent call
  visible in the session log), or the report says at the top that it ran inline
  and why.
- If the invocation said to take the data as given, no data value was checked
  against an outside source, only internal consistency facts the result depends
  on were checked, and the report says so.
- A reused or imported fit, coefficient or group split not re-derived within the
  scope of the result is flagged explicitly, not treated as equivalent to one
  verified here, and traced through its whole provenance chain.
- A passing fit is checked for a fixed parameter that makes part of the model
  cancel, and the collapsed form is checked against the project's own theory
  before it is called a weaker or undisclosed claim.
- A group split is checked separately for independent verifiability and for
  classification circularity.
- A negative or no-model-found result is a reviewable claim in its own right,
  not skipped for lack of a single number to reproduce.
- For a process-model result, the report states whether the model was
  reproduced, tested against limits, or neither, and whether a copy of the code
  was run. Validation data is checked for independence from calibration, and skill
  is stated against a baseline.
- The subagent returns its report as text beginning with the `FILE:` line, and
  the invoking session saves it to the deliverable path before treating the task
  as done. When the review ran inline, the session saves its own report to the
  same path.
