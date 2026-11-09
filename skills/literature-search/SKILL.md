---
name: literature-search
description: Search the EndNote library, OpenAlex, arXiv, Semantic Scholar, Exa and Consensus for a search-term query or an open research question, dedupe across sources and return a structured candidate list with metadata, abstracts and local-PDF availability. It does not read full text or synthesize; the pdf skill reads the candidates you select.
context: fork
agent: general-purpose
background: true
---

# Literature search

This skill covers Discovery and Retrieval only, of the pipeline discussed
with the user (Discovery, Retrieval, Reading, Extraction, Synthesis,
Citation management, Knowledge storage). Reading and Extraction stay with
the existing `pdf` skill, applied afterward to whichever candidates are
actually selected. Synthesis, gap analysis, and review writing are
deliberately not a skill at all — they need open judgment over the
candidate set, not a fixed checklist, so they're done as direct agentic
reasoning that consumes this skill's report. Citation management stays with
EndNote and `citation-check`, unchanged.

It never creates, edits, or deletes an EndNote bibliography entry — the
same hard boundary `citation-check` observes. The default deliverable is a
report only. If asked for one (see Deliverables), it can also produce a
separate, clearly-labelled import-ready reference list — still never
imported automatically.

## Input

Accepts either a short search-term query, or an open research question in
natural language (e.g. "what mechanisms are proposed for changes in tidal
dynamics under sea-level rise, and which estuary types are under-studied?"),
preferred over a bare query when the user has one. For a research question,
the skill derives its own search terms before querying any source, and
**reports the derived terms plainly in the output** — not hidden — so a
mismatch between the question's actual intent and what got searched is
visible and correctable, rather than silently baked into the results.

If the invocation doesn't say which part of a question to prioritize (e.g.
a compound question bundling mechanism, evidence strength, and modelling
assumptions), search broadly across all of it rather than silently picking
one component — the point of this skill is coverage, not pre-judging which
part matters most.

Optional parameters:
- **Date range** — e.g. "last 15 years." Explicit only; default to no limit
  if not given, don't infer a window from context.
- **Source scope** — default is the EndNote library plus all five external
  sources below; a narrowing flag (e.g. `--sources=openalex,consensus`)
  restricts to a subset.
- **Result cap per source** — bounds cost/time on a broad query; ask if not
  given and the query looks broad (e.g. a multi-part research question with
  no date range). The EndNote library check is free and local, so this cap
  applies more loosely there — see below.

## Local source: your EndNote library

Run this first, always, regardless of the result cap or any narrowing
flag — it's read-only, local, and free (no network call, so it never needs
the confirmation gate below). Skipping it would mean re-discovering
externally what's already on hand.

**Search method — this is not like the other five sources.**
`mcp__endnote__search_references` does **literal contiguous-substring
matching** against title/author/abstract/keywords, not word/token or
relevance matching. Confirmed live: a full multi-clause derived query
(e.g. `"tidal inlet morphodynamics sediment availability channel
convergence North Sea"`) returned **zero** results even though clearly
relevant records exist in the library, while a short, real substring
(`"tidal inlet"`, two words) returned 30, several highly relevant. Do not
send the combined derived-term query as one string. Instead:
1. Break the derived search terms (or the bare query) into several short,
   individually meaningful substrings — 2–4 words each, phrases a real
   title or abstract is likely to contain verbatim (e.g. `"tidal inlet"`,
   `"sediment availability"`, `"Wadden Sea"` as separate calls, not one
   combined string).
2. Search each substring separately, union the results, dedupe by title.
3. A substring that returns zero is not proof of absence — it only means
   that exact contiguous phrase isn't in the library's title/author/
   abstract/keyword fields. Don't report "not in your library" from a
   single zero result the way you would for an external source's genuine
   no-match; try at least one alternative phrasing before concluding
   absence, and say plainly that this reflects EndNote's substring search,
   not a considered judgment that nothing relevant exists.

For each result, check `mcp__endnote__list_linked_files` and report
whether a local PDF already exists — this is the one thing this source
offers that none of the five external ones can: a direct answer to
"do I already have the full text for this." The `abstract_preview` field
returned by search often comes back empty even for records with a real
abstract in the full record; that's not itself informative — don't report
"no abstract" from `abstract_preview` alone.

Do not use the returned numeric `id` as a stable identifier outside this
run — `citation-check` already documents that EndNote record numbers
aren't stable across library re-imports. Within one run, resolving straight
from a fresh search to `list_linked_files`/`get_reference` on the same id
is fine; just don't cache the id for later reuse.

## External sources and what each is for

- **OpenAlex** — broad academic index, primary discovery source. No auth
  for basic use. **Do not add the `mailto=` polite-pool parameter** — that
  sends the user's email to OpenAlex on every call, which the user has
  declined. Run on the default unauthenticated rate limit. Abstracts come
  back as an `abstract_inverted_index` (word → list of positions), not
  plain text — reconstruct it by placing each word at its listed
  positions, rather than reporting the abstract as unavailable.
- **arXiv** — preprints; Atom/XML responses, needs parsing. Coverage is
  confirmed sparse for environmental/coastal-science topics (tested
  directly in the `citation-check` OpenAlex/arXiv extension work — a real
  coastal-engineering title returned zero via quoted search, and an
  unquoted multi-term query ORs terms and surfaces false positives from
  unrelated fields like astrophysics). **Always use a quoted phrase search**
  (e.g. `ti:"exact phrase"`), never an unquoted multi-word query.
- **Semantic Scholar** — secondary academic index and abstract source.
  Rate-limits aggressively unauthenticated (documented in `citation-check`)
  — treat 429s as their own outcome, not-checked, never "not found."
- **Consensus** — already-connected MCP, covers Semantic Scholar, PubMed,
  Scopus, and arXiv in one call with its own quality filters (study type,
  journal tier, medical mode, etc.), but is capped at one page of results
  on the free tier (the user's understanding: 10 results free / 20 Pro) —
  this is why direct Semantic Scholar and arXiv calls stay in scope
  alongside it rather than being dropped as redundant: a capped-page
  overlap tool doesn't substitute for uncapped direct queries, and
  cross-source agreement on a result is itself a useful signal. The free
  tier also has a **monthly search quota** separate from the per-page cap
  (confirmed live: "used all 30 searches this month, resets on the 1st") —
  a run can find it already exhausted for the month with no queries left
  at all; treat that the same as any other source failure, report plainly,
  don't retry in a loop.
- **Exa** — general web/document search, useful here for sources the four
  academic/preprint indices above don't cover: reports, datasets,
  repositories, and also ordinary web-hosted copies of peer-reviewed
  papers. **Do not assume an Exa result is grey literature by virtue of
  the source** — confirmed live: a real run returned two genuinely
  peer-reviewed journal articles via Exa. Assess each result on its own
  terms (published venue, DOI, journal name) and label it what it actually
  is — peer-reviewed or grey literature — in the output row itself, not by
  blanket rule. Connected as an MCP server at user scope (`claude mcp add
  --transport http exa https://mcp.exa.ai/mcp --scope user`), running on
  its free/anonymous tier. If the free tier proves too rate-limited in
  real testing, upgrading to an API key is a connection-config change, not
  a rewrite of this skill.
  **Confirmed tools** (a newly-added MCP server's tools only appear in a
  session started after the connection was made — not the session that
  added it, same restriction as a skill edited mid-session): `mcp__exa__
  web_search_exa` takes `query` (a semantically rich description of the
  ideal page, not bare keywords) and `objective` (what to prioritize,
  exclude, and pull out), plus optional `numResults`. It returns highlight
  snippets, often without a full author list or DOI. `mcp__exa__
  web_fetch_exa` takes `urls` (batchable) and reads a page's full content —
  use it on a promising result's URL when `web_search_exa`'s snippet is
  missing fields you need. Confirmed live: a snippet's author/venue field
  can be incomplete or inconsistent with the page itself (a Cambridge Core
  result showed a different lead author in the structured metadata than in
  the rendered byline) — when that happens, resolve it independently via
  an OpenAlex title search (`filter=title.search:`) rather than picking
  one of the two conflicting names, the same technique used elsewhere in
  this skill and in `citation-check`.

Before any of these five run, confirm once per run with the user — same
pattern as `citation-check`'s external-verification gate — since a query
(which may describe unpublished or sensitive research directions) goes to
up to five external services. State plainly what will be sent and to which
services, proceed only on a yes. This gate does not cover the EndNote
library check above — that never leaves the machine, so it runs
unconditionally and doesn't wait on this confirmation.

## Deduplication

Reuses `citation-check`'s resolution discipline: match by DOI first where
more than one source returns one for the same work; otherwise fall back to
title + author-surname + year match. Never merge two results on a weak
title match alone — a title search can surface a different, merely
topically-similar work (confirmed pattern in `citation-check`'s CrossRef
testing). Where evidence doesn't converge cleanly on one candidate, report
as **possible duplicate, unresolved** and name both, rather than silently
picking one.

## What to extract per result

- Title, authors, year, venue/journal (or preprint server), DOI where
  available.
- Source(s) that returned it — a result found by more than one source is
  itself a signal worth keeping, not just deduping away silently.
- Abstract, if returned by the source.
- Open-access link, if OpenAlex exposes one — linked, not fetched (full
  text is out of scope; see above).
- For every result, whether it's peer-reviewed or grey literature —
  assessed per result (venue, DOI, journal name), never assumed from
  which source returned it (see Exa note above).
- **Already in your EndNote library, and whether a local PDF is linked** —
  for every result, not just ones the EndNote search itself surfaced (a
  result an external source returns can still already be in the library;
  cross-check by title/DOI against what the EndNote pass found rather than
  only flagging the EndNote source's own hits).

## Deliverables

The output folder comes from the shared run script (global Outputs rules),
run for `<project-root>`: the absolute path of the cwd the skill was
invoked from, noted before any other command, because the shell may move
later. The task
name is `literature-search-<subject>`. `<subject>` is the short name given
in the invocation; if none is given, derive two to four words from the
query or question and report them plainly, so a rerun of the same search
can pass the same name (a different name starts a new task folder).

- Before any search, run
  the run control command in `machine.md`, as `path literature-search-<subject> --root "<project-root>"`.
  It changes nothing. If it exits with an error (for example the folder
  would be git-ignored), stop and report the
  message; do not work round it. If the script is missing, stop and say so.
- When the report is ready, run the same command with `start` in place of
  `path`, and write into the folder it prints. In a git project with
  tracked outputs this is `outputs/literature-search-<subject>/`, with
  its files other than `.md` removed (overwrite the old report); otherwise it is a new `outputs/literature-search-<subject>-<DDMMYY>-run<N>/`.
  The script writes `run_info.txt` there.
- In tracked mode, report the run as pending review and give the proposed
  tag from `run_info.txt`. If `start` warned that it replaced a pending run,
  say so. Do not accept the run yourself: when the user accepts, rejects or
  discards it, run the same command with `accept`, `reject` or `discard` in
  place of `path`.

The report file itself is always named `literature-search-report.md` — fixed,
not invented per run, so repeated runs are predictable to find.

1. **Summary** — the query or derived search terms actually used, sources
   queried, hit counts per source, duplicates resolved, any source that
   returned zero results or failed (rate-limited, timed out) — reported
   plainly, not silently dropped.
2. **Candidate list** — one row per deduplicated result: fields above.
3. **Import-ready reference list** — only if asked for (on invocation, or a
   natural-language request like "with an import list"), same opt-in
   pattern as `citation-check`'s `--context` extension. A separate file,
   `literature-search-import.ris`, in **RIS format** — EndNote's own manual
   import filter is "Reference Manager (RIS)" (File > Import), so this is
   the format that actually imports without the user reformatting it by
   hand. One record per deduplicated candidate:
   - `TY` — `JOUR` for a journal article, `GEN` for anything whose type is
     unclear (don't guess a specific type from a title alone).
   - `AU` — one line per author, surname first (`Surname, Forename`).
   - `TI` — title. `PY` — year. `JO`/`JF` — venue/journal. `DO` — DOI.
     `UR` — open-access link if any. `AB` — abstract if retrieved.
   - `ER` — blank line, ends each record.
   Never auto-imported — the user brings the `.ris` file into EndNote
   themselves via File > Import.

## Checks

- Never create, edit, or delete an EndNote bibliography entry.
- Never make an external call without the once-per-run confirmation.
- Never send the user's email or other personal identifiers to an external
  source unless explicitly asked to for that run.
- Report zero-hit and failed sources as plainly as successful ones,
  including a source that has run out of its monthly quota, not just one
  that returned zero matches.
- Assess and label every result as peer-reviewed or grey literature on its
  own merits — never assume grey literature from source alone (Exa returns
  both).
- Never report "not in your EndNote library" from a single zero-result
  substring search — that reflects the search method, not a considered
  absence (see Local source section above).
- Always report local-PDF availability per result, not just for results
  the EndNote pass itself returned.
- Report the derived search terms plainly whenever the input was a research
  question, not a bare query.
- This skill does not judge relevance, quality, or evidentiary strength of
  any result — that's the separate synthesis step's job, not this one's.
