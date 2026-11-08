# Reanalysis triage prompt template

A follow-on step after `analysis-adversary` runs: reads the source report
and the adversarial-review report together and recommends, per finding,
whether it warrants reanalysis, a caveat added to the existing report, or
further investigation — with reasoning shown. Deliberately **not** a
skill, for the same reason `literature-synthesis-template.md` isn't:
judging whether a finding is material enough to warrant redoing an
analysis depends on context (what the report is used for, how much the
finding actually moves the conclusion, what reanalysis would cost) that a
fixed checklist can't anticipate case to case.

**This step is advisory, not a decision-maker.** It recommends; never edits the source report, adversarial report, or underlying analysis. Never re-run analysis scripts—`analysis-adversary` found this can silently overwrite output files. If assessing a finding requires new computation beyond what's in the two reports, that need itself warrants reanalysis or further investigation—say so as the recommendation, don't quietly do it.

**How to use this template.** Fill in the bracketed sections, then hand the filled document to a fresh general-purpose subagent (Agent tool, `subagent_type: general-purpose`). Report-type `.md` output can be refused (see Handback), so the lead may need to save it. Use a fresh agent, not a context-fork, for reusability.

---

## Task

[One sentence, imperative. E.g. "Triage the findings in the
analysis-adversary report against the Smtl-Prism two-tier result and
recommend, per finding, whether reanalysis, a caveat, or further
investigation is warranted."]

## Context

[Two or three sentences: what the source report is for, and what
prompted the adversarial review — a routine check, or a specific concern.
Point at the two documents rather than summarizing them.]

## Inputs

- **Source report** — `<path>`, the original reported result.
- **Adversarial report** — `<path>`, `analysis-adversary`'s findings
  against it.
- Optionally, if a finding's materiality can't be assessed from the two
  reports alone: the raw data and analysis code the adversarial report
  itself already read — for reference, not for re-running (see above).
- Optionally, the project's `data\DATA-NOTES.md`, if one exists: a map of
  the data files (source, row order, units, links between files, known
  problems). It records facts about the data, not results, so reading it
  does not bias the triage. It is a reference, not a check made here:
  where a finding's materiality depends on a fact stated there, say that
  the fact is taken from DATA-NOTES.md.

## Neutral framing

State the actual question — which findings, if any, warrant reanalysis —
without assuming the answer either way. An adversarial report finding real
issues does not itself mean reanalysis is warranted (some findings are
disclosure gaps, not result-changing ones); a clean-looking adversarial
report does not itself mean no action is needed (re-read for anything
downplayed). Treat every finding in the adversarial report as worth a
materiality judgment, not just the ones flagged as most consequential
there — a report's own "most consequential choice" section is about what
most changes the *number*, not necessarily what most changes whether the
*conclusion* is trustworthy.

## What triage means here

**Granularity.** Follow the adversarial report's own section/finding
structure as the default unit of triage — don't invent a finer or coarser
split. Split further only when one sentence there genuinely bundles two
separable claims a reader could disagree about independently.

**Confirmations vs. issues.** An adversarial report often confirms things (number reproduces, split is data-driven, no rows dropped) alongside flagged issues. Confirmations don't need full per-finding treatment—list them briefly as a group ("N items confirmed: ..."). Reserve full triage for flagged concerns, discrepancies, or undisclosed choices.

For each actual issue the adversarial report raises, separately:

1. **Restate the finding** in one or two sentences — what it says, not
   what it implies. If the finding characterizes what a result does or
   doesn't demonstrate (rather than a pure arithmetic/reproduction check),
   and a directly relevant primary source is readily available (a theory
   or method document the task itself cites), check the characterization
   against it before restating — see the Out of scope section for the
   boundary this sits inside.
2. **Assess materiality**, choosing one:
   - **No action** — doesn't affect the reported conclusion in any way
     that matters for how the source report is used.
   - **Caveat** — real, but doesn't change the number or the pass/fail
     status; the existing report should disclose it, not be redone. Say
     what the caveat should say.
   - **Reanalysis warranted** — likely changes the reported number, pass/fail status, or the substantive claim (a result can pass numerically while the claim it supports is undermined; don't triage on pass/fail alone). Say what would need to change.
   - **Further investigation needed** — the finding raises a real question
     the two reports can't resolve on their own (e.g. a reused value's own
     justification lives in a different report not read here). Name
     specifically what needs checking and where, rather than defaulting to
     "reanalysis" for lack of a cleaner answer.
3. **Note interactions between findings** — two findings that are each
   individually minor can be jointly material (e.g. a marginal-pass result
   plus an undisclosed sensitivity to a nearby parameter choice); say so
   rather than triaging every finding in isolation.

## Deliverable

Save to `<project-root>\outputs\reanalysis-triage-<DDMMYY>-run<N>\
reanalysis-triage-report.md`, where `<project-root>` is the cwd this was
invoked from.

**Handback.** The Write tool can refuse a report-type `.md` file from a subagent (server-side rule: names beginning report,
summary, findings or analysis; no opt-out). Try to save the deliverable at the path given. If the Write is refused, do not
work around it (no Bash or script write, and no renaming to get past the check). Return the complete, unshortened text in
the final message under the heading `FILE: <that path>`, and say which file this applies to. Do not say a file was refused
unless you attempted to write it. Save any data files, tables, figures and scripts yourself. The lead saves any file that was
returned as text and checks it against the saved outputs before relying on it.

1. **Summary** — overall recommendation in one paragraph: does anything
   here warrant reanalysis, and how urgently.
2. **Per-finding triage** — the restated finding, materiality category,
   and reasoning, for every finding in the adversarial report, in the
   order that report gave them.
3. **If reanalysis is warranted for one or more findings**: a drafted
   task brief for that reanalysis (same convention as
   `prompts/blank-prompt-template.md`) — Task, Context, Inputs, Neutral framing,
   Acceptance criteria, Out of scope, Definition of done — ready to hand
   to whoever will actually run it. **Drafted, not run** — this step
   prepares the next step, it doesn't perform it.
4. **If a caveat is warranted for one or more findings**: the exact
   caveat text recommended for each, ready to add to the source report —
   again, drafted for the author to add, not added by this step.
5. **If further investigation is warranted for one or more findings**: for
   each, name concretely what to check and where (a specific file, a
   specific prior report, a specific piece of code's own logic) — inline,
   not a formal task brief, since what's missing here is information to
   decide with, not yet a defined piece of analysis work to run.

## Acceptance criteria

- Every issue the adversarial report raises gets its own materiality
  judgment — none silently dropped. Confirmations may be grouped briefly
  (see Granularity above) but are still accounted for, not omitted.
- No finding is triaged on pass/fail status alone without considering
  whether the underlying claim survives.
- A "reanalysis warranted" or "further investigation" recommendation says
  concretely what would need to change or be checked, not just that
  something should happen.
- Nothing in the source report, the adversarial report, or the underlying
  analysis is edited, and no analysis script is executed.

## Out of scope

- Performing the reanalysis itself — that's a separate, later step, using
  the task brief this one drafts.
- Adding the recommended caveat to the source report directly — drafted
  here, added by the author.
- Raising the accuracy of the data as a finding, when the adversarial
  report says the data was taken as given by instruction. Note that
  statement in the summary, treat data accuracy as not assessed, and do
  not triage it. A mismatch the report states as a fact (for example a row
  order or unit that differs from DATA-NOTES.md) is still triaged like any
  other finding.
- Re-running or re-deriving the adversarial report's own computations —
  that's `analysis-adversary`'s job, already done, and this step doesn't
  redo the reproduction, the alternative-specification sweep, or the
  provenance trace.

**Not out of scope, and confirmed to matter**: checking an adversarial finding's *characterization* against a directly relevant primary source already in the project (a theory/method document the task itself cites) when materiality turns on characterization accuracy. This is a narrow, targeted check against a specific named source, not a re-audit of computations. If resolving a characterization question requires redoing analysis rather than reading a document, that need itself becomes a "further investigation" finding.

## Definition of done

Ran end to end, output on disk at the stated path (saved by the lead if it was
returned as text), and a short summary of
the overall recommendation — plus anywhere you were genuinely unsure
whether a finding was material, flagged as such rather than resolved by
guessing.
