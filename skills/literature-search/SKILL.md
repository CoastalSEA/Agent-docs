---
name: literature-search
description: Search the EndNote library, OpenAlex, arXiv, Semantic Scholar, Exa and Consensus for a search-term query or an open research question, dedupe across sources and return a structured candidate list with metadata, abstracts and local-PDF availability. It does not read full text or synthesize; the pdf skill reads the candidates you select.
context: fork
agent: general-purpose
background: true
---

# Literature search

This skill covers Discovery and Retrieval only. Reading and extraction stay with the `pdf` skill, applied afterwards to the candidates the user selects. Synthesis, gap analysis and review writing are deliberately not part of this skill: they need open judgment over the candidate set, not a fixed checklist, so they are done as direct reasoning that consumes this skill's report. Citation management stays with EndNote and `citation-check`.

It never creates, edits or deletes an EndNote bibliography entry: the same hard boundary `citation-check` observes. The default deliverable is a report only. If asked for one (see Deliverables), it can also produce a separate, clearly labelled import-ready reference list, which is never imported automatically.

## Input

Accepts a short search-term query, or an open research question in natural language (for example "what mechanisms are proposed for changes in tidal dynamics under sea-level rise, and which estuary types are under-studied?"), which is preferred over a bare query when the user has one. For a research question, derive your own search terms before querying any source, and **report the derived terms plainly in the output**, so that a mismatch between the question's intent and what was searched is visible and correctable.

If the invocation does not say which part of a question to prioritise (for example a compound question that bundles mechanism, evidence strength and modelling assumptions), search broadly across all of it. The point of this skill is coverage, not pre-judging which part matters most.

Optional parameters:

- **Date range**, for example "last 15 years". Explicit only: with none given, apply no limit, and do not infer a window from context.
- **Source scope**: the default is the EndNote library plus all five external sources below; a narrowing flag (for example `--sources=openalex,consensus`) restricts it to a subset.
- **Result cap per source**: bounds cost and time on a broad query. Ask if it is not given and the query looks broad (for example a multi-part research question with no date range). The EndNote library check is free and local, so the cap applies more loosely there.

## Local source: your EndNote library

Run this first, always, whatever the result cap or narrowing flag. It is read-only, local and free (no network call, so it never needs the confirmation gate below). Skipping it would mean re-discovering externally what is already on hand.

**Search method: this is not like the other five sources.** `mcp__endnote__search_references` does **literal contiguous-substring matching** against title, author, abstract and keywords. It does not match words or rank by relevance. A full multi-clause derived query returns zero results even when relevant records exist, while a short real substring returns many. Do not send the combined derived-term query as one string. Instead:

1. Break the derived search terms (or the bare query) into several short, individually meaningful substrings of 2 to 4 words, phrases that a real title or abstract is likely to contain verbatim (for example `"tidal inlet"`, `"sediment availability"` and `"Wadden Sea"` as separate calls).
2. Search each substring separately, union the results, and dedupe by title.
3. A substring that returns zero is not proof of absence: it means only that the exact contiguous phrase is not in the library's title, author, abstract and keyword fields. Do not report "not in your library" from a single zero result the way you would for an external source's genuine no-match. Try at least one alternative phrasing before concluding absence, and say plainly that this reflects EndNote's substring search, not a considered judgment that nothing relevant exists.

For each result, check `mcp__endnote__list_linked_files` and report whether a local PDF already exists. This is the one thing this source offers that no external one can: a direct answer to "do I already have the full text for this". The `abstract_preview` field returned by search is often empty even for records with a real abstract, so do not report "no abstract" from it alone.

Do not use the returned numeric `id` as a stable identifier outside this run: EndNote record numbers are not stable across library re-imports (see `citation-check`). Within one run, going straight from a fresh search to `list_linked_files` or `get_reference` on the same id is fine; do not cache the id for later reuse.

## External sources and what each is for

- **OpenAlex**: broad academic index and the primary discovery source. No authentication for basic use. **Do not add the `mailto=` polite-pool parameter**: it sends the user's email to OpenAlex on every call, which the user has declined. Run on the default unauthenticated rate limit. Abstracts come back as an `abstract_inverted_index` (word to list of positions), not plain text: reconstruct the abstract by placing each word at its listed positions, and do not report it as unavailable.
- **arXiv**: preprints; Atom/XML responses that need parsing. Coverage is sparse for environmental and coastal-science topics. **Always use a quoted phrase search** (for example `ti:"exact phrase"`), never an unquoted multi-word query: arXiv ORs the terms and returns false positives from unrelated fields.
- **Semantic Scholar**: secondary academic index and abstract source. It rate-limits aggressively when unauthenticated (see `citation-check`): treat a 429 as its own outcome, not checked, never "not found".
- **Consensus**: an already-connected MCP, a semantic search over 400M+ papers (Semantic Scholar, OpenAlex, PubMed) with its own filters (study design, journal quartile, medical mode, years). Use `mcp__claude_ai_Consensus__search` with the `query` alone and no filters, unless the user asks for one. **Ask for breadth in one call**: for a broad search set `page_size` to 100 (300 only when the user wants as many papers as possible) instead of splitting the topic into several narrow searches. Each 100 papers counts as one search against the monthly allowance, and the tool description states what the plan allows. Each paper comes back with its title and Consensus link (keep the link exactly as given), authors, year, citation count, journal and abstract. DOI, study design and a preprint flag come only on a paid plan: without a DOI, de-duplicate Consensus results by title, author surname and year. A 100-paper result is about 200,000 characters and the harness saves it to a file: pull out the fields with a script in the scratch folder, and do not read the whole result into the context. Direct Semantic Scholar and arXiv calls stay in scope alongside it, because cross-source agreement on a result is itself a useful signal. The monthly allowance can already be used up: treat that as any other source failure, report it plainly and do not retry in a loop. Some results end with a sign-up, upgrade or usage message: copy it word for word into the Summary of the report and into your reply, and never write one yourself.
- **Exa**: general web and document search, for sources the four academic and preprint indices do not cover (reports, datasets, repositories) and for ordinary web-hosted copies of peer-reviewed papers. **Do not assume an Exa result is grey literature because of its source**: Exa returns peer-reviewed articles too. Assess each result on its own terms (published venue, DOI, journal name) and label it peer-reviewed or grey literature in the output row. Connected as an MCP server at user scope. `mcp__exa__web_search_exa` takes `query` (a semantically rich description of the ideal page, not bare keywords) and `objective` (what to prioritise, exclude and pull out), plus optional `numResults`; it returns highlight snippets, often without a full author list or DOI. `mcp__exa__web_fetch_exa` takes `urls` (batchable) and reads a page's full content: use it on a promising result when the snippet lacks fields you need. A snippet's author or venue field can be incomplete or conflict with the page itself. When that happens, resolve it independently with an OpenAlex title search (`filter=title.search:`) and do not pick one of the two conflicting names.

Before any of these five run, confirm once per run with the user (the same pattern as `citation-check`'s external-verification gate), because a query, which may describe unpublished or sensitive research directions, goes to up to five external services. State plainly what will be sent and to which services, and proceed only on a yes. This gate does not cover the EndNote library check above: that never leaves the machine, so it runs unconditionally and does not wait on this confirmation.

## Deduplication

Reuse `citation-check`'s resolution discipline: match by DOI first where more than one source returns one for the same work; otherwise fall back to title plus author surname plus year. Never merge two results on a weak title match alone: a title search can surface a different, merely topically similar work. Where the evidence does not converge on one candidate, report **possible duplicate, unresolved**, name both, and do not pick one silently.

## What to extract per result

- Title, authors, year, venue or journal (or preprint server), and DOI where available.
- The source(s) that returned it. A result found by more than one source is itself a signal worth keeping, not just deduplicating away.
- The abstract, if the source returned one.
- An open-access link, if OpenAlex exposes one: linked, not fetched (full text is out of scope).
- Whether it is peer-reviewed or grey literature, assessed per result (venue, DOI, journal name), never assumed from the source that returned it.
- **Whether it is already in your EndNote library, and whether a local PDF is linked**, for every result and not only the ones the EndNote search itself surfaced. A result an external source returns can already be in the library: cross-check by title or DOI against what the EndNote pass found.

## Deliverables

The output folder comes from the shared run script (global Outputs rules), run for `<project-root>`: the absolute path of the cwd the skill was invoked from, noted before any other command, because the shell may move later. The task name is `literature-search-<subject>`. `<subject>` is the short name given in the invocation; if none is given, derive two to four words from the query or question and report them plainly, so that a rerun of the same search can pass the same name (a different name starts a new task folder).

- Before any search, run the run control command in `machine.md`, as `path literature-search-<subject> --root "<project-root>"`. It changes nothing. If it exits with an error (for example the folder would be git-ignored), stop and report the message; do not work round it. If the script is missing, stop and say so.
- When the report is ready, run the same command with `start` in place of `path`, and write into the folder it prints. In a git project with tracked outputs this is `outputs/literature-search-<subject>/`, with its files other than `.md` removed (overwrite the old report); otherwise it is a new `outputs/literature-search-<subject>-<DDMMYY>-run<N>/`. The script writes `run_info.txt` there.
- In tracked mode, report the run as pending review and give the proposed tag from `run_info.txt`. If `start` warned that it replaced a pending run, say so. Do not accept the run yourself: when the user accepts, rejects or discards it, run the same command with `accept`, `reject` or `discard` in place of `path`.

The report file is always named `literature-search-report.md`: fixed, not invented per run, so repeated runs are predictable to find.

1. **Summary**: the query or derived search terms actually used, the sources queried, hit counts per source, duplicates resolved, and any source that returned zero results or failed (rate-limited, timed out), reported plainly and not silently dropped.
2. **Candidate list**: one row per deduplicated result, with the fields above.
3. **Import-ready reference list**: only if asked for (on invocation, or in a natural-language request such as "with an import list"), the same opt-in pattern as `citation-check`'s `--context` extension. A separate file, `literature-search-import.ris`, in **RIS format**, which EndNote's own manual import filter ("Reference Manager (RIS)", File > Import) reads without the user reformatting it. One record per deduplicated candidate:
   - `TY`: `JOUR` for a journal article, `GEN` for anything whose type is unclear (do not guess a specific type from a title alone).
   - `AU`: one line per author, surname first (`Surname, Forename`).
   - `TI` title, `PY` year, `JO` or `JF` venue or journal, `DO` DOI, `UR` open-access link if any, `AB` abstract if retrieved.
   - `ER`: a blank line that ends each record.

   Never auto-imported: the user brings the `.ris` file into EndNote through File > Import.

## Checks

- Never create, edit or delete an EndNote bibliography entry.
- Never make an external call without the once-per-run confirmation.
- Never send the user's email or other personal identifiers to an external source unless explicitly asked to for that run.
- Report zero-hit and failed sources as plainly as successful ones, including a source that has run out of its monthly quota, not just one that returned zero matches.
- Copy any Consensus sign-up, upgrade or usage message word for word; never write one of your own.
- Assess and label every result as peer-reviewed or grey literature on its own merits. Never assume grey literature from the source alone (Exa returns both).
- Never report "not in your EndNote library" from a single zero-result substring search: that reflects the search method, not a considered absence (see the Local source section).
- Always report local-PDF availability per result, not just for results the EndNote pass itself returned.
- Report the derived search terms plainly whenever the input was a research question, not a bare query.
- This skill does not judge the relevance, quality or evidentiary strength of any result: that is the separate synthesis step's job.
