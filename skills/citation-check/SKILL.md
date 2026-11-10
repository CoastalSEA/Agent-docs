---
name: citation-check
description: Verify every in-text citation in a Word manuscript that uses EndNote cite-while-write against the EndNote library and against CrossRef, Semantic Scholar, OpenAlex and arXiv, flagging drift and fabrication without editing anything. Add --context (or ask for a citation check with context) to also check each citing sentence against its source.
---

# Citation check

This skill checks the citations in a Word (`.docx`) manuscript that uses EndNote cite-while-write (CWYW) field codes. It never edits the manuscript, the EndNote library, or any bibliography entry: it only flags. Where a check cannot be completed (no source text, no DOI, ambiguous match), it reports that plainly and does not guess.

The manuscript is supplied input data (a hard boundary on this machine): open it read-only. Read the EndNote library only through the `mcp__endnote__*` tools, which are read-only by construction. This skill requires that MCP to be connected; if it is not, stop and say so. Do not parse the library file directly.

## Two stages

**Stage 1, citation integrity.** Always runs.

**Stage 2, context validity extension.** Runs only when asked for: a literal `--context` argument, or an invocation that uses the phrase "citation check" together with the word "context" (for example "citation check with context"). These are the only two accepted trigger forms. Do not infer stage 2 from other phrasing (for example "check the citations are used correctly" does not trigger it). Otherwise run stage 1 only and tell the user that stage 2 is available with `--context`.

If the invocation does not say which part of the manuscript to check, ask rather than guess scope (whole document or a named section). Do not default silently to the whole document, which could be long and costly to verify externally.

## Extracting citations from the manuscript

A `.docx` is a zip archive. The CWYW field code lives in `word/document.xml` as one or more `w:instrText` runs. Word often splits one field's instruction text across adjacent runs: concatenate all `w:instrText` content between a field's begin (`w:fldChar w:fldCharType="begin"`) and end (`w:fldCharType="end"`) markers before parsing. The same paragraphs also hold non-citation fields (`REF` and `SEQ` for figure and table numbers): keep only fields whose instruction text starts `ADDIN EN.CITE`.

The reassembled instruction text has the form `ADDIN EN.CITE <EndNote>...</EndNote>`. Strip the prefix and outer field braces, then parse the `<EndNote>...</EndNote>` block as XML. One field can hold several `<Cite>` elements (a multi-source citation such as `(Smith, 2019; Jones et al., 2016)`): process each `<Cite>` separately.

From each `<Cite>`:

- `<RecNum>` / `<record><rec-number>`: the EndNote record id when the field was last updated in Word. Do not use it as the key for `mcp__endnote__get_reference`. Rec-numbers are not stable across copies or re-imports of a library, and a stale one resolves silently to a real but unrelated record. Treat it as informational only.
- `<record><foreign-keys><key guid="...">`: not usable. `get_reference` returns no `guid` to cross-check against.
- `<DisplayText>`: appears once per field, on the first `<Cite>` of a multi-citation field. It is the combined rendered text for the whole field (for example `(Wallace, 1990; Scott and Jones, 2017)`), not per source.
- The rest of `<record>`: `<contributors><authors>`, `<titles><title>`, `<periodical><full-title>` or `<secondary-title>` (book chapters, theses and conference papers use different field names than journal articles), `<pages>`, `<volume>`, `<number>`, `<dates><year>`, and `<electronic-resource-num>` for the DOI (bare, or as a full `https://doi.org/...` URL: strip that prefix before comparing or querying). This is a **snapshot of the record when the field was last updated in Word**, not necessarily what the library holds now. That gap is what the first Stage 1 check tests.

## Resolving a field citation to a current library record

Resolve every `<Cite>` by content, not by id:

1. Call `mcp__endnote__search_references` with the `<title>` text or a distinctive substring of it (titles are usually unique on their own).
2. Match on title first. If several candidates share a near-identical title (for example "...Part 1" and "...Part 2" of one series), disambiguate with year and author surname. Never accept a match on author and year alone when the title match is weak: report **ambiguous, not resolved**.
   - Two candidates can tie on title, year and author, because the library can hold genuine duplicate entries for one work. If secondary evidence (DOI, publisher, ISBN, keywords) points at different candidates and does not converge on one, do not pick a winner. Report **ambiguous**, name both ids, say which fields matched which candidate, and note it as a likely duplicate library entry, not a citation problem.
3. Call `mcp__endnote__get_reference` on the resolved id for the full current fields.
4. If the resolved id differs from the field's own rec-number, record that difference explicitly. It shows the library was renumbered or re-imported since the citation was inserted, and it is a finding separate from whether the content still matches.
5. If no reasonable title match is found, flag as **unresolved**. Do not fall back to a weaker match to avoid an empty result.

Field notes for the comparison:

- `get_reference`'s `author` field is one string with authors separated by `\r`: split on `\r`.
- The DOI comes from the `doi` key (EndNote's Electronic Resource Number field), as stored. Normalise it before comparing or querying: trim whitespace (stored values can carry a trailing space), then strip any `https://doi.org/`, `http://dx.doi.org/` or `doi:` prefix.
- A value that still does not start with `10.` (an ISBN typed into the field, a publisher link, a malformed prefix such as `19.`) is not a usable DOI. Report it as found, as a data finding, never as "DOI missing".
- Only if `doi` is empty, check `url` for a `doi.org` link and say the DOI was taken from `url`. Report "no DOI" only when both are empty. Many records (privately published sources, theses) have no DOI at all, which is expected, not an error.
- `reference_type` is a bare integer code with no name mapping from the MCP: report the raw code and do not invent a label.

## Stage 1: citation integrity

For every unique `<Cite>` actually cited, deduplicated by title (not by rec-number) before any lookup:

1. **Resolve**, following the method above. Report **resolved** (with any rec-number drift noted), **ambiguous** (several close title candidates) or **unresolved** (no reasonable match) for each reference.
2. **Field against current library record**, for anything resolved. Compare the resolved record with the snapshot in the field code. Flag any mismatch by name (title, authors, year, journal or secondary title, volume or pages, DOI): the "citation inserted correctly, library record since changed" case.
3. **External verification, once confirmed.** Before any external call, ask the user once per run to confirm (not once per reference or per call), because this sends each cited record's title, author, year and DOI to CrossRef and Semantic Scholar. State plainly what will be sent and to which services, and proceed only on a yes.
   - If the current library record has a DOI, look it up on CrossRef (`https://api.crossref.org/works/{doi}`, no key). Compare title, authors, year and journal. A DOI that returns "Resource not found" is **not automatically wrong**: some legitimate DOIs (for example ResearchGate-prefix `10.13140/...`) are registered outside CrossRef and return 404. Report **DOI not indexed in CrossRef**, distinct from a fabricated or malformed DOI (wrong checksum, non-existent prefix).
   - With no DOI, a not-indexed DOI, or nothing from CrossRef, search by title on CrossRef and/or Semantic Scholar and match on title similarity plus author-surname overlap plus year. A weak or absent match is **not verified**, not **wrong**: older, niche and non-academic-press sources are often absent from these indices. A title search's top hit can be a different, merely topically similar work, so require author-surname overlap and never take the top hit on title alone.
   - For conference proceedings, a year difference between the library record and CrossRef can be legitimate: CrossRef often indexes by print or online date, which can trail the conference year. Report it as a **year discrepancy (conference year vs. indexed year)** note, not a mismatch, when title, authors and publisher otherwise match strongly.
   - Semantic Scholar's unauthenticated tier rate-limits aggressively (HTTP 429 can come on the second call in immediate sequence). Treat a 429 as its own outcome, **not checked: rate-limited**, never as "not found". Do not retry in a tight loop. If it recurs on most calls, say so once in the summary. Treat Semantic Scholar as a best-effort secondary check, and as the fallback source for an abstract in stage 2 (same caveat).
   - Also check OpenAlex (`https://api.openalex.org/works/doi:{doi}` for a DOI, no key). It indexes some sources CrossRef does not: a ResearchGate-prefix DOI that returns 404 on CrossRef can resolve on OpenAlex. Treat an OpenAlex hit on a CrossRef-404 DOI as genuine independent verification.
   - For an OpenAlex title search, use `https://api.openalex.org/works?filter=title.search:{title}`, never the bare `?search=` parameter. `?search=` matches full text across the whole work and returns confident-looking results for unrelated papers; `filter=title.search:` matches the title field and returns zero for sources OpenAlex does not index. The same rule applies as for CrossRef: require author-surname overlap, and report a genuine index gap as **not verified**, not wrong.
   - Also check arXiv (`https://export.arxiv.org/api/query?search_query=ti:"{title}"&max_results=5`, no key, Atom/XML: parse it). The title **must** be double-quoted inside `ti:"..."`: an unquoted multi-word query is OR'd term by term and returns many confident but unrelated results. This is a coastal and environmental-science library and arXiv skews to physics, maths, computer science and quantitative biology, so a zero-result arXiv check is an expected index gap, not a finding. Use one query per reference.
   - Add `&mailto=` (OpenAlex) or any similar per-user identifier only if the user has explicitly said to: the once-per-run confirmation covers sending citation metadata, not the user's identity.

## Stage 2: context validity extension

Only when requested (see above). For every citation *instance* in the manuscript (not deduplicated: the same source can be cited for different claims, and each needs its own verdict):

1. Extract the sentence (or clause) the citation is attached to: the claim being made.
2. Get source text for that reference, in this order:
   - `mcp__endnote__list_linked_files` / `read_linked_file_text`: a PDF already linked in the library, read locally, no external call.
   - If nothing is linked and stage 1's external-verification consent already covers this run, fall back to the Semantic Scholar abstract, or an open-access link via OpenAlex or Unpaywall if one exists, under the same once-per-run confirmation (do not ask again).
   - If no source text is obtainable, verdict **unable to verify: no source text available**. Do not skip the instance silently.
3. Compare the claim with the source text and assign one verdict per instance: **Supported**, **Overstated**, **Contradicted**, **Not located** (source text obtained but the claim is not in it), or **Unable to verify**.
   - A citing sentence can bundle several factual components (for example "the focus has been on the west spit extension and breaching"). Verdict each component separately.
   - Call `read_linked_file_text` with a generous `max_chars` (well above a typical article, for example 150 000 or more), not the 20 000 default: the tool has no fixed length cap. If the result is too large to inline, the harness redirects it to a file on disk with its own read-in-chunks instructions: follow them and read the full file. Only `truncated: true` (the source exceeds even a generous `max_chars`) means a partial read.
   - If the read is partial, the verdict is provisional on the portion read: say so. **Never assign Contradicted on a partial read.** A claim not found in the portion read is at most **Not located (in the text read)**, since the unread remainder could contain it. After a full read (`truncated: false`, inline or via the spilled file) a "not found" result is definitive: say so.

## Deliverables

The output folder comes from the shared run script (global Outputs rules), run for `<project-root>`: the absolute path of the cwd the skill was invoked from (do not ask for it or guess it), noted before any other command, because the shell may move later. The task name is `citation-check-<manuscript>`, where `<manuscript>` is the manuscript file name without its extension.

- Before stage 1, run the run control command in `machine.md`, as `path citation-check-<manuscript> --root "<project-root>"`. It changes nothing. If it exits with an error (for example the folder would be git-ignored), stop and report the message; do not work round it. If the script is missing, stop and say so.
- When the report is ready, run the same command with `start` in place of `path`, and write into the folder it prints. In a git project with tracked outputs this is `outputs/citation-check-<manuscript>/`, with its files other than `.md` removed (overwrite the old report); otherwise it is a new `outputs/citation-check-<manuscript>-<DDMMYY>-run<N>/`. The script writes `run_info.txt` there.
- In tracked mode, report the run as pending review and give the proposed tag from `run_info.txt`. If `start` warned that it replaced a pending run, say so. Do not accept the run yourself: when the user accepts, rejects or discards it, run the same command with `accept`, `reject` or `discard` in place of `path`.

Produce a single report, `citation-check-report.md`:

1. **Summary**: counts of references cited, resolved and unresolved, field-against-library mismatches, externally verified, not verified and flagged, and (if stage 2 ran) instances per verdict.
2. **Stage 1 findings**: one row per unique reference with an issue: rec-number, in-text display text, what was checked, what was found. References with no issues are counted in the summary, not listed row by row.
3. **Stage 2 findings** (if run): one row per flagged instance: location in the manuscript (surrounding sentence), rec-number, verdict, and the specific discrepancy between claim and source.

## Checks

- Never edit the manuscript, the EndNote library, or any bibliography entry. Flag; do not fix.
- Never make an external call (CrossRef, Semantic Scholar, OpenAlex, arXiv, Unpaywall) without the once-per-run confirmation described above.
- Distinguish **not verified** (could not confirm, index gap, DOI outside CrossRef's coverage, rate-limited, no source text) from **wrong** (confirmed mismatch). Do not conflate them in the findings or in the summary counts.
- Report every check that ran and its result, including passes, not just the failures, so the summary counts are traceable to the findings list.
- No characterisation beyond what the comparison supports: report the mismatch, not a judgment about the author or the library's quality.

## Known limitation

The field code's `<ref-type name="...">` numeric code and `get_reference`'s `reference_type` code are not confirmed to share the same numbering. A mismatch between them (for example field code 32 "Thesis" against a record `reference_type` of 2) may be a namespace difference, not a real re-typing of the record. Report it as a flagged, unresolved difference, not a conclusion either way.
