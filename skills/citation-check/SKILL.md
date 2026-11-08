---
name: citation-check
description: Verify every in-text citation in a Word manuscript that uses EndNote cite-while-write against the EndNote library, and against CrossRef/Semantic Scholar/OpenAlex/arXiv, flagging drift and fabrication without editing anything. With a "context" extension (--context, or a natural-language request like "citation check with context"), also verify each citing sentence's claim is supported by the cited source.
---

# Citation check

This skill checks the citations in a Word (`.docx`) manuscript that uses
EndNote cite-while-write (CWYW) field codes. It never edits the manuscript,
the EndNote library, or any bibliography entry — it only flags. Where a
check cannot be completed (no source text, no DOI, ambiguous match), it
reports that plainly rather than guessing.

The manuscript is supplied input data (a hard boundary on this machine): it
is opened read-only. The EndNote library is read only through the
`mcp__endnote__*` tools, which are read-only by construction. This skill
requires that MCP to be connected; if it isn't, stop and say so rather than
attempting to parse the library file directly.

## Two stages

**Stage 1 — citation integrity.** Always runs.

**Stage 2 — context validity extension.** Only runs when asked for, either
by a literal `--context` argument on invocation, or by an invocation that
uses the phrase "citation check" together with the word "context" (e.g.
"citation check with context"). These are the only two accepted trigger
forms — don't infer stage 2 from other phrasing (e.g. "check the citations
are used correctly" does *not* trigger it on its own). If the invocation
doesn't match either form, run stage 1 only and tell the user stage 2 is
available via `--context` — don't assume silently.

If the invocation doesn't say which part of the manuscript to check, ask
rather than guessing scope (whole document vs. a named section) — don't
silently default to the whole document, which could be long and costly to
verify externally.

## Extracting citations from the manuscript

A `.docx` is a zip archive; the CWYW field code lives in `word/document.xml`
as one or more `w:instrText` runs. Word frequently splits a single field's
instruction text across multiple adjacent runs — concatenate all
`w:instrText` content between a field's begin (`w:fldChar
w:fldCharType="begin"`) and end (`w:fldCharType="end"`) markers before
parsing, don't assume one run holds the whole field. The same paragraphs
also contain non-citation fields (`REF`, `SEQ` cross-references for figure/
table numbering) — filter to fields whose instruction text starts
`ADDIN EN.CITE` and skip everything else; don't treat every field in the
document as a citation.

Within the reassembled instruction text, the content looks like:

```
ADDIN EN.CITE <EndNote>...</EndNote>
```

Strip the `ADDIN EN.CITE` prefix and outer field braces, then parse the
remaining `<EndNote>...</EndNote>` block as XML. A single field can contain
more than one `<Cite>` element (a multi-source citation like
`(Smith, 2019; Jones et al., 2016)`) — process each `<Cite>` separately.

From each `<Cite>`, the fields that matter:

- `<RecNum>` / `<record><rec-number>` — the EndNote record id **at the time
  the field was last updated in Word**. Do not use this as the key to
  `mcp__endnote__get_reference`: rec-numbers are not stable across copies
  or re-imports of a library, and a stale rec-number resolves silently to
  a real but unrelated record rather than failing. Treat it as
  informational only (see resolution method below).
- `<record><foreign-keys><key guid="...">` — not usable: `get_reference`
  does not return a `guid` field to cross-check against.
- `<DisplayText>` — appears once per field, attached to the *first*
  `<Cite>` in a multi-citation field, not once per `<Cite>`. It's the
  combined rendered text for the whole field (e.g.
  `(Wallace, 1990; Scott and Jones, 2017)`), not per-source.
- The rest of `<record>` (`<contributors><authors>`, `<titles><title>`,
  `<periodical><full-title>` or `<secondary-title>` depending on
  `<ref-type>` — book chapters, theses, and conference papers use
  different field names than journal articles — `<pages>`, `<volume>`,
  `<number>`, `<dates><year>`, `<electronic-resource-num>` for the DOI,
  seen both bare (`10.1139/anc-2019-0002`) and as a full
  `https://doi.org/...` URL — normalize by stripping any
  `https://doi.org/` prefix before comparing or querying) is a **snapshot
  of the record as of when the field was last updated in Word**, not
  necessarily what the library holds now. That gap is exactly what the
  first stage-1 check below is for.

## Resolving a field citation to a current library record

Because rec-number can't be trusted, resolve every `<Cite>` by content,
not by id:

1. Call `mcp__endnote__search_references` with the `<title>` text (or a
   distinctive substring of it — titles in this library run long and are
   usually unique on their own).
2. Among the results, match on title first; if more than one candidate
   shares a near-identical title (e.g. the same author's multi-part works,
   "...Part 1" vs "...Part 2" of the same series), disambiguate with year
   and author surname before accepting a match. Never accept a match on
   author+year alone when title match is weak — report **ambiguous, not
   resolved** instead of guessing.
   - Two candidates can tie on title, year, *and* author (the library can
     hold genuine duplicate entries for the same work — one confirmed
     case had id 1264 matching the field's publisher/ISBN/keywords
     exactly while a separate id 6166 matched the field's own DOI via its
     `url` instead, with neither candidate matching on both). If
     secondary evidence (DOI, publisher, ISBN, keywords) points at
     *different* candidates rather than converging on one, don't pick a
     winner — report **ambiguous**, name both ids, state which specific
     fields matched which candidate, and note this as a likely duplicate
     library entry rather than a citation problem.
3. Call `mcp__endnote__get_reference` on the resolved id to get full
   current fields for the stage-1 comparison below.
4. If the resolved id differs from the field's own rec-number, record that
   difference explicitly (it is evidence the library was renumbered or
   re-imported since the citation was last inserted) — this is a finding
   in its own right, separate from whether the content still matches.
5. If no reasonable title match is found at all, flag as **unresolved** —
   don't fall back to a weaker match to avoid an empty result.

Field notes so the comparison logic doesn't choke on real records:
`get_reference`'s `author` field is one string with authors separated by
`\r`, not a list or semicolon-delimited string — split on `\r`. The DOI
comes from the `doi` key (EndNote's Electronic Resource Number field),
returned exactly as stored. Normalize it before comparing or querying:
trim leading and trailing whitespace (stored values can carry a trailing
space), then strip any `https://doi.org/`, `http://dx.doi.org/` or `doi:`
prefix. A
value that still does not start with `10.` (e.g. an ISBN typed into the
field, a publisher link, or a malformed prefix such as `19.`) is not a
usable DOI — report it as found, as a data finding, never as "DOI
missing". Only if `doi` is empty, check `url` for a `doi.org` link and
say the DOI was taken from `url`. Report "no DOI" only when both are
empty. Many records (e.g. privately published or thesis sources) have no
DOI at all, which is expected, not an error. `reference_type` comes back as a
bare integer code with no name mapping available from the MCP — report the
raw code as-is rather than inventing a label for it.

## Stage 1 — citation integrity

For every unique `<Cite>` actually cited in the manuscript, deduped by
title (not by rec-number — see above) before doing any lookups:

1. **Resolve.** Follow the resolution method above. Report **resolved**
   (with any rec-number drift noted), **ambiguous** (multiple close title
   candidates), or **unresolved** (no reasonable match) per reference.
2. **Field vs. current library record**, for anything resolved. Compare
   the resolved record's fields against the snapshot embedded in the field
   code. Flag any mismatch (title, authors, year, journal/secondary-title,
   volume/pages, DOI) by name — this is the "citation inserted correctly
   but the library record has since changed" case.
3. **External verification, once confirmed.** Before making any external
   call, ask the user once per run to confirm — not once per reference or
   per API call — since this sends each cited record's title/author/
   year/DOI to CrossRef and Semantic Scholar. State plainly what will be
   sent and to which services, then proceed only on a yes.
   - If the current library record has a DOI, look it up on CrossRef
     (`https://api.crossref.org/works/{doi}`, no key required). Compare
     title/authors/year/journal. A DOI that returns "Resource not found"
     is **not automatically wrong** — some legitimate DOIs (e.g.
     ResearchGate-prefix `10.13140/...`) are registered outside CrossRef's
     coverage and 404 cleanly. Report this as **DOI not indexed in
     CrossRef**, distinct from a fabricated or malformed DOI (e.g. wrong
     checksum, non-existent prefix).
   - If there's no DOI, DOI lookup came back not-indexed, or CrossRef has
     nothing, search by title on CrossRef and/or Semantic Scholar and
     match on title similarity plus author surname overlap plus year. A
     weak or absent match is reported as **not verified**, not as
     **wrong** — an index gap (older, niche, or non-academic-press
     sources are often absent from these indices) is not evidence of
     fabrication. A title search's top hit can be a different, merely
     topically-similar work (confirmed: a Barcock & Collins 1991 search
     surfaced an unrelated 2006 paper on the same harbour) — require
     author-surname overlap before accepting it, don't take the top hit
     on title alone.
   - For conference proceedings specifically, a year difference between
     the library record and CrossRef can be legitimate — CrossRef often
     indexes by print/online publication date, which can trail the
     conference year the library recorded by a year or more (confirmed:
     a 2017 conference paper indexed by CrossRef under 2018). Report this
     as a **year discrepancy (conference year vs. indexed year)** note,
     not as a mismatch finding, when title/authors/publisher otherwise
     match strongly.
   - Semantic Scholar's unauthenticated tier rate-limits aggressively in
     practice (HTTP 429 observed on the second call in immediate
     sequence, well inside its documented allowance). Treat a 429 as its
     own outcome, **not checked — rate-limited**, never as "not found."
     Don't retry in a tight loop; if it recurs across most calls in a run,
     say so once in the summary rather than repeating the same note per
     reference, and treat Semantic Scholar as a best-effort secondary
     check, not one the run depends on completing.
   - Semantic Scholar is also the fallback source for an abstract, used in
     stage 2 when there's no linked PDF (same rate-limit caveat applies).
   - Also check OpenAlex (`https://api.openalex.org/works/doi:{doi}` for a
     DOI, no key required). OpenAlex indexes some sources CrossRef doesn't —
     confirmed: a ResearchGate-prefix DOI (`10.13140/...`) that 404s on
     CrossRef resolved cleanly on OpenAlex with matching title, author, and
     year. Treat an OpenAlex hit on a CrossRef-404'd DOI as a genuine
     independent verification, not a lesser one.
   - For an OpenAlex **title** search (no DOI, or DOI not found), use
     `https://api.openalex.org/works?filter=title.search:{title}`, not the
     bare `?search=` parameter. `?search=` does full-text relevance
     matching across the whole work, not just the title, and returns
     confident-looking non-zero results for clearly unrelated papers
     (confirmed: searching `Barcock Collins tidal inlet` this way surfaced
     an unrelated gravel-bed-clogging paper with no author overlap).
     `filter=title.search:` restricts the match to the title field itself
     and correctly returns zero results for sources OpenAlex genuinely
     doesn't index, rather than a misleading low-relevance hit. Same
     matching rule as CrossRef: require author-surname overlap, don't
     accept on title alone; a genuine index gap is reported as **not
     verified**, not wrong.
   - Also check arXiv (`https://export.arxiv.org/api/query?search_query=
     ti:"{title}"&max_results=5`, no key required, Atom/XML response —
     parse it, don't expect JSON). The title **must** be double-quoted
     inside `ti:"..."` — an unquoted, multi-word `all:` or `ti:` query is
     OR'd term-by-term by arXiv's parser and returns large numbers of
     confidently-labelled but completely unrelated results (confirmed:
     an unquoted `all:tidal inlet morphodynamics` query returned 15,966
     results, top hits about galactic tidal streams, not coastal
     inlets — a false-positive trap, not a real match). This is a
     coastal/environmental-science library; arXiv skews physics, maths,
     CS, and quantitative biology, and confirmed testing against a
     genuinely cited paper in this library (Scott, Harris & Jones 2020,
     "...Example Harbour...") returned zero results with a correctly
     quoted title search. Treat a zero-result arXiv check as an expected
     index gap for this discipline, not a finding, and don't spend more
     than one query per reference confirming it.
   - Only add `&mailto=` (OpenAlex) or any similar per-user identifier to
     these queries if the user has explicitly said to — the once-per-run
     confirmation covers sending citation metadata externally, not sending
     the user's own identity alongside it.

## Stage 2 — context validity extension

Only when requested (see above). For every citation *instance* in the
manuscript (not deduplicated — the same source can be cited for different
claims in different places, and each needs its own verdict):

1. Extract the sentence (or clause) the citation is attached to — the
   actual claim being made.
2. Get source text for that reference, in this order:
   - `mcp__endnote__list_linked_files` / `read_linked_file_text` — a PDF
     already linked in the library, read locally, no external call.
   - If nothing is linked, and stage 1's external-verification consent
     already covers this run, fall back to the Semantic Scholar abstract,
     or an open-access link via OpenAlex/Unpaywall if one exists — still
     under the same once-per-run confirmation, don't ask again mid-run.
   - If no source text is obtainable at all, verdict the instance
     **unable to verify — no source text available** rather than skipping
     it silently.
3. Compare the claim against the source text and assign one verdict per
   instance: **Supported**, **Overstated**, **Contradicted**, **Not
   located** (source text obtained but the claim isn't in it), or
   **Unable to verify**.
   - A single citing sentence can bundle more than one factual component
     (e.g. "the focus has been on the west spit extension and breaching"
     names two things). Verdict each component separately rather than
     forcing one verdict onto a compound claim.
   - Call `read_linked_file_text` with a generous `max_chars` (well above
     a typical article's length, e.g. 150 000+) rather than relying on the
     20 000 default — the tool itself has no fixed document-length cap
     and will return the whole file if asked for enough. If the result is
     too large to inline, the harness (not the EndNote tool) redirects it
     to a file on disk with its own read-in-chunks instructions — follow
     those and read the full file rather than treating that as a dead
     end. Only when `truncated: true` comes back (the source genuinely
     exceeds even a generous `max_chars`) is the read partial.
   - If the read is partial (`truncated: true`), the verdict is
     provisional on the portion actually read — say so explicitly.
     **Never assign Contradicted on a partial read** — a claim not found
     in the portion read is at most **Not located (in the text read)**,
     since an unread remainder could still contain it. Once the full
     document has been read (`truncated: false`, whether inline or via
     the harness's spilled file), a "not found" result is definitive, not
     provisional — say so.

## Deliverables

The output folder comes from the shared run script (global Outputs rules),
run for `<project-root>`: the absolute path of the cwd the skill was
invoked from (don't ask for it or guess it), noted before any other
command, because the shell may move later. The task name is `citation-check-<manuscript>`, where
`<manuscript>` is the manuscript file name without its extension.

- Before stage 1, run
  the run control command in `machine.md`, as `path citation-check-<manuscript> --root "<project-root>"`.
  It changes nothing. If it exits with an error (for example the folder
  would be git-ignored), stop and report the
  message; do not work round it. If the script is missing, stop and say so.
- When the report is ready, run the same command with `start` in place of
  `path`, and write into the folder it prints. In a git project with
  tracked outputs this is `outputs/citation-check-<manuscript>/`, with
  its files other than `.md` removed (overwrite the old report); otherwise it is a new `outputs/citation-check-<manuscript>-<DDMMYY>-run<N>/`.
  The script writes `run_info.txt` there.
- In tracked mode, report the run as pending review and give the proposed
  tag from `run_info.txt`. If `start` warned that it replaced a pending run,
  say so. Do not accept the run yourself: when the user accepts, rejects or
  discards it, run the same command with `accept`, `reject` or `discard` in
  place of `path`.

Produce a single report, `citation-check-report.md`:

1. **Summary** — counts: references cited, resolved / unresolved,
   field-vs-library mismatches, externally verified / not verified /
   flagged, and (if stage 2 ran) instances per verdict.
2. **Stage 1 findings** — one row per unique reference with an issue:
   rec-number, in-text display text, what was checked, what was found.
   References with no issues are counted in the summary, not listed row
   by row.
3. **Stage 2 findings** (if run) — one row per flagged instance: location
   in the manuscript (surrounding sentence), rec-number, verdict, and the
   specific discrepancy between claim and source.

## Checks

- Never edit the manuscript, the EndNote library, or any bibliography
  entry. Flag; do not fix.
- Never make an external call (CrossRef, Semantic Scholar, OpenAlex, arXiv,
  Unpaywall) without the once-per-run confirmation described above.
- Distinguish **not verified** (couldn't confirm, index gap, DOI outside
  CrossRef's coverage, rate-limited, no source text) from **wrong**
  (confirmed mismatch) — don't conflate them in either the findings or
  the summary counts.
- Report every check that ran and its result, including passes — not just
  the failures — so the summary counts are traceable to the findings list.
- No characterization beyond what the comparison supports — report the
  mismatch, not a judgment about the author or the library's quality.

## Known limitations

- EndNote CWYW field `rec-number`/`guid` are not usable as stable
  identifiers against whatever library copy is currently connected;
  resolution is by title/author/year match instead, which can be
  ambiguous for near-duplicate titles (multi-part series from one author).
- `get_reference` exposes no guid field. Its `doi` key is the raw stored
  value and needs the normalization above.
- CrossRef and Semantic Scholar do not index everything — a "not
  verified" result there is common for niche, older, or non-CrossRef-
  registered (e.g. ResearchGate-prefix DOI) sources and is not itself
  evidence of a problem.
- Semantic Scholar's unauthenticated API rate-limits quickly; treat it as
  best-effort, not a required check.
- OpenAlex's `?search=` parameter does full-text relevance matching, not a
  title match, and will return non-zero, unrelated results for a source it
  doesn't actually index — always use `filter=title.search:` for a title
  check, never the bare `search` parameter.
- arXiv's query parser ORs unquoted multi-word terms, returning large
  numbers of unrelated results (confirmed: a coastal-engineering query
  matched astrophysics papers on galactic tidal streams) — always quote
  the title inside `ti:"..."`.
- For a coastal/environmental-science library, arXiv coverage is expected
  to be sparse to zero (confirmed against a real cited reference in this
  library) — arXiv's core disciplines are physics, maths, CS, and
  quantitative biology. A zero-result arXiv check is the expected outcome
  for most references here, not evidence of a problem.
- `read_linked_file_text` itself has no fixed document-length cap — ask
  for a generous `max_chars` rather than the 20 000 default. A too-large
  result gets redirected by the harness to a file on disk instead of
  being inlined; read that file rather than assuming the source is
  unreadable. Only a genuine `truncated: true` at a generous `max_chars`
  means a partial read, and only then are stage-2 verdicts capped at "Not
  located," never "Contradicted."
- The field code's `<ref-type name="...">` numeric code and
  `get_reference`'s `reference_type` code are not confirmed to share the
  same numbering — a code mismatch between them (observed: field code 32
  "Thesis" vs. current record's `reference_type` 2) may just be a
  namespace difference, not a real re-typing of the record. Report it as
  a flagged, unresolved difference, not a conclusion either way.
