# Literature synthesis prompt template

For the Synthesis / gap analysis / review writing stage of the research
pipeline discussed alongside `citation-check`, `proofread`, and
`literature-search`. Deliberately **not** a skill: judging which mechanism
is best supported, where studies disagree, and what's under-studied needs
open reasoning over a specific body of evidence, not a fixed checklist. A
skill would either constrain that judgment or become so vague it added
nothing over reasoning directly.

**How to use this template.** Fill in the bracketed sections, then hand the filled document to a fresh general-purpose subagent (Agent tool, `subagent_type: general-purpose`, background: true). Use a fresh agent, not a context-fork—a fork drags in irrelevant conversation history; this task needs to reason cleanly over a stated question and evidence set alone. The subagent needs `Write` access for files; report-type `.md` output can be refused (see Handback). If the subagent needs mid-run authorization (External fetches, below), pre-authorize it explicitly in the filled brief.

---

## Task

[One sentence, imperative. E.g. "Synthesize the retrieved literature into
a theoretical account of why <phenomenon> varies across <cases or
study sites>, and identify which proposed mechanisms are best
supported and where the evidence disagrees."]

## Context

[Two or three sentences: what research question this serves, and what
already exists. Point at documents rather than summarizing them.]

## Inputs (any combination)

- **Literature-search output** — `<path to literature-search-report.md>`
  and, if produced, `<path to the .ris file>`. The normal path into this
  task.
- **Existing document** — `<path>` to a draft manuscript, notes, or prior
  review to extend or check against the retrieved evidence. If given,
  work on a **copy**, never the original — same hard boundary as
  `proofread`. State the copy's path in the output.
- **Existing reference list** — `<path>` to a `.ris`/EndNote export, or an
  EndNote search/group name, in place of or alongside literature-search's
  output.
- If none of the above exist yet, say so and stop rather than doing your
  own literature discovery — that's `literature-search`'s job, not this
  task's.

## Reading full text

For each candidate with a DOI/URL, in this order:

1. Check whether it's already in the EndNote library with a linked PDF (`mcp__endnote__search_references`, then `list_linked_files`/`read_linked_file_text`). **`search_references` does literal substring matching only**—search with the candidate's exact, full title as given in the source report, never paraphrased or truncated. If zero results look surprising, retry with a shorter, distinctive substring before concluding it's genuinely absent.
2. If not found, check for a local or downloadable copy; use the `pdf` skill.
3. If neither, fetch the open-access link (`WebFetch` or `mcp__exa__web_fetch_exa`).
4. If full text is unavailable, work from the abstract and **mark such claims as abstract-only**—never present them with full-text confidence.

Confirm full-text fetching once per run (same gate pattern as `citation-check` and `literature-search`), unless the filled brief pre-authorized it.

## Neutral framing

State the research question exactly as given, never rephrased toward a
hoped-for conclusion. If the person filling in this brief already has a
hypothesis, name it explicitly as *their* hypothesis to test — not as the
question itself — so the agent isn't nudged toward confirming it.

[The actual question goes here, verbatim.]

## What "reasoning openly" means here

- Identify the distinct mechanisms/explanations each source proposes, not
  just its topic.
- Note where sources agree, disagree, or simply haven't been tested
  against each other — don't silently resolve a disagreement by picking a
  side.
- Distinguish evidence basis per claim: field measurement, numerical
  model, idealized/theoretical argument, or a review's own synthesis of
  others' work are not equally strong evidence, and the difference must be
  stated, not flattened into one confident narrative.
- Name modelling assumptions that plausibly explain disagreement between
  studies (domain dimensionality, idealized vs. real bathymetry, which
  forcings are included) only when the sources themselves discuss this —
  don't invent an assumption a source doesn't state.
- Note what's under-studied or absent (a case type, a mechanism
  combination, a geographic setting) as a gap, distinct from a
  disagreement between studies that did look at it.
- Where two sources use the same term differently, or the same mechanism
  under different names, say so rather than silently merging or silently
  treating them as unrelated.

## Acceptance criteria

- [ ] Every claim in the output traces to a specific source (title/author/
      year) in the input set — never asserted free-floating.
- [ ] Full-text-confirmed and abstract-only claims are visibly
      distinguished.
- [ ] Disagreement between sources is reported as disagreement, not
      resolved silently.
- [ ] Gaps are named with the specific missing dimension (case type,
      mechanism, method), not just "more research is needed."
- [ ] Nothing in the EndNote library or any original document was created,
      edited, or deleted.
- [ ] Output saved at `<project-root>\outputs\literature-synthesis-
      <DDMMYY>-run<N>\`, per this project's standard convention (by the
      agent, or by the lead from text returned under `FILE:`; see Handback).

## Handback

**Handback.** The Write tool can refuse a report-type `.md` file from a subagent (server-side rule: names beginning report,
summary, findings or analysis; no opt-out). Try to save the deliverable at the path given. If the Write is refused, do not
work around it (no Bash or script write, and no renaming to get past the check). Return the complete, unshortened text in
the final message under the heading `FILE: <that path>`, and say which file this applies to. Do not say a file was refused
unless you attempted to write it. Save any data files, tables, figures and scripts yourself. The lead saves any file that was
returned as text and checks it against the saved outputs before relying on it.

## Out of scope

- Literature discovery — `literature-search`'s job. If the given evidence
  set looks obviously incomplete for the question, say so in the output
  rather than silently going and searching for more.
- Citation/source verification — `citation-check`'s job.
- Editing an existing manuscript in place — if extending a draft, output
  goes to a new file or a clearly separated new section, never overwriting
  the original silently.

## Definition of done

Ran end to end, output on disk at the stated path (saved by the lead if it was
returned as text), and a short summary of
what surprised you — especially any claim you couldn't source, any source
you couldn't get full text for, and any place the sources actively
disagreed.
