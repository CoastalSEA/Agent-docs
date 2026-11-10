---
name: proofread
description: Proofread a Word manuscript for environmental-science academic writing, on a copy and never the original, with Track Changes for spelling and grammar and Comments for flow, phrasing and tense. Also checks captions, cross-references, and that citations match the References list. It does not verify citations against sources (citation-check does).
context: fork
agent: general-purpose
background: true
---

# Proofread

Produces a reviewed copy of a Word (`.docx`) manuscript, saved alongside the original as `<name> - proofread.docx`. The original is never opened for writing: a hard boundary on this machine. All feedback lands in the copy as either a **Track Changes** edit or a **Comment**, per "What goes where"; nothing is a plain-text report.

This skill is scoped to writing quality and document mechanics. It does **not** check whether a citation is accurate or fabricated, or whether a cited source supports its claim: that is the separate `citation-check` skill. Say so once in the summary and do not attempt any part of it.

If the invocation does not say which part of the manuscript to check, ask rather than guess scope (whole document or a named section). Do not default silently to the whole document: a full spelling and grammar pass, a close read for flow, and the citation and figure checks all scale with length. State the agreed scope plainly in the summary.

## Style target

- **British spelling throughout.** Treat consistent British spelling as correct: never flag "characterised", "recognised", "colour" and similar as errors. A stray American spelling in an otherwise British document is itself an inconsistency: correct it with Track Changes.
- Apply the standing writing rules in `profile.md`: no contractions, plain words, short sentences, sentence case for titles and headings, dashes only inside compound modifiers and never as standalone punctuation.
- **Journal-specific calibration, optional.** If the invocation names a target journal (a `--journal "<name>"` argument, or a request such as "proofread this for JGR-Oceans"), fetch that journal's current author guidelines and check against them (structure, heading conventions, citation style, explicit style rules). If no journal is named, apply a generic environmental-science academic register; do not guess a journal from context.
  - Trust only a page that was fetched and read in this run, never a search snippet or a remembered description of a journal's usual style. Indexed guidance can be stale and can conflict with the live page.
  - Publisher pages can block automated fetches (HTTP 403). Treat a blocked fetch as a reported failure, fall back to the generic register and say the journal-specific lookup failed.
  - What loaded may be collection-level guidance shared by a publisher's journals, not journal-specific. Say which scope was obtained.
  - State in the summary the exact URLs fetched, which succeeded and which were blocked, and whether the rules applied are journal-specific or a publisher-collection fallback.

## Finding spelling and grammar issues

**Spelling.** Drive Microsoft Word through COM automation: `New-Object -ComObject Word.Application`, open the document read-only, read `doc.SpellingErrors`, close without saving, quit. This applies Word's own dictionary with exact character positions and is more reliable than reading for typos. **Every `SpellingErrors` hit is a candidate, not a correction.** Filter out proper nouns, place names, brand names (a name cited in the References section is almost certainly not a typo) and discipline vocabulary before proposing a Track Changes edit.

**British and American consistency.** Do not rely on Word's checker for this. A run can carry an explicit `en-US` language override, which makes Word accept American spelling inside it. Run an explicit variant-spelling scan (a wordlist of common `-ize`/`-ise`, `-or`/`-our` and `-er`/`-re` pairs) across all text, whatever the per-run language tags say.

**Grammar.** Word's `GrammaticalErrors` collection is not sensitive enough to trust as the only check. Treat grammar and flow as model judgment, reading the text directly.

## Mechanism

Use the `docx` skill's own editing workflow for the mechanical part. Do not reinvent XML handling.

- **Locate the `docx` skill scripts first.** Run `check_docx_skill.py --find` (the form is in `machine.md`; it takes no `--root`). It prints the folder that holds `comment.py`, `merge_runs.py` and `office/validate.py`; call the scripts from there. If it prints nothing or fails, search `~/.claude/skills` and the Claude plugin folders for `docx/scripts/office/validate.py`. If the scripts are still not found, say so in the summary (for example "validator not run: docx skill scripts not found") and rely on the Word check alone. Do not skip the validator silently.
- `merge_runs.py`, `comment.py` and the validator need `defusedxml` and `lxml`. Check that both import before relying on the scripts; if not, install them once (see `machine.md` for how packages are installed) rather than hand-rolling the XML.
- Unpack, then run `merge_runs.py` so fragmented runs are findable. It does not merge runs whose `rPr` differs, even trivially. An edit or comment anchor that spans several runs needs each run's own `rPr` matched when splitting or wrapping.
- **Track Changes:** wrap the correction in `<w:ins>`/`<w:del>` (author `"Claude"`, current date, a unique `w:id` for each). When the target sits inside a longer run, split the run at the target's boundaries and keep sibling content (for example a `<w:fldChar>`) in its own untouched run.
- **Comments:** use `comment.py` against the unpacked directory, not the `.docx`. Place the `commentRangeStart`, `commentRangeEnd` and `commentReference` markers it prints as direct children of `w:p`, never inside `w:r`.
- When a run has content after the target text and before its own `</w:r>` (for example a `SEQ` or `REF` field), capture everything after the target up to the real closing `</w:r>` and re-emit it unmodified in a continuing run. Taking only the first `<w:t>` silently deletes the trailing content. Do not rely on the validator to catch this afterwards.
- Use **one shared, safety-checked splitting routine** for every comment and edit, not one-off code per case. Inconsistent one-off code has produced a file that Word rejected as corrupted while the schema validator passed.
- **Re-zip** with Python's `zipfile` (`ZIP_DEFLATED`, walk the unpacked directory, write each file with a forward-slash relative path). Git Bash has no `zip` command.
- **Validate** with `office/validate.py --author "Claude" --original <source>` (from the folder found above) before treating any edit as done. It catches paragraph-count drift and untracked changes. Set `PYTHONIOENCODING=utf-8` first, or it crashes printing a Unicode arrow on the Windows console.
- **Verify with Word.** LibreOffice (`soffice`) and pandoc are not installed. Open the produced file read-only through COM; check that `doc.Revisions.Count` and `doc.Comments.Count` match what was intended, each revision's `Author`, `Type` and `Range.Text`, and each comment's `Scope.Text`; confirm that the file opened without a repair prompt (a sign of XML corruption). Schema validation passing is not sufficient: Word enforces stricter consistency than the XSD. This check is mandatory before any multi-comment or multi-edit run is done.
- Read text straight from `word/document.xml`.

## What goes where

**Track Changes** are for objectively correctable issues: spelling errors (against the British target), grammatical errors (subject-verb agreement, article use, punctuation) and non-British variants in an otherwise British document. Each gets a direct proposed correction, not just a flag.

**Comments** are for anything that needs the author's judgment: flow, phrasing, word choice, and two consistency checks.
- **Active and passive voice:** flag a switch between voices without an apparent reason. Neither voice is mandated; both are legitimate in this field.
- **Verb tense:** flag comparable content (for example within Methods, or within Results) that mixes past and present tense without reason.

Keep each comment short, generally one or two sentences stating the issue and, if brief, a suggested direction, never a full rewrite. A comment never exceeds **50 words** (Word's `Range.Words.Count`), checked per comment as it is added.

**The budget is a ceiling on the number of comments, not on their combined length.** Compute it once per document:

```
x_max = max(5, floor(0.005 × prose_word_count))
```

That is up to one comment per 200 prose words, with a floor of 5 so a short document is not denied feedback. There is no separate total-word ceiling. Stop adding comments at `x_max`, prioritising the clearest and most useful issues. "Prose word count" excludes the References section (locate it as the Citations vs. References check does: the heading, then to the end of that field or section) and counts what precedes it plus anything after it that is not References or Appendix material.

Do not pad the budget with weak or invented findings. Using fewer than `x_max` comments is a legitimate outcome, and a coherent conventional pattern of tense and voice (passive for methods, present for stated results, past for what was done) is not an inconsistency to report.

## Parsing rule for every check below: track fields across the whole document

A field's `begin`, `separate` and `end` markers do not have to sit in the same paragraph. The entire References section can be one `ADDIN EN.REFLIST` field that begins right after the heading and ends many paragraphs later, with every entry in between as plain-looking `<w:t>` runs. Track field nesting depth by walking the body in document order, continuously from the top, and **never reset the state at a paragraph boundary**, or every entry after the first is misclassified as plain text. Paragraph breaks inside a field's result region still separate individual entries (one paragraph is one reference entry or one caption); only the state tracking spans paragraphs.

## Figures and tables

Word inserts native captions as `SEQ Figure`/`SEQ Table` fields and cross-references them with `REF _Ref... \h` fields that point at bookmarks. A cross-reference can also be plain typed text with no field, and one paragraph can hold both kinds. A typed reference will not update if the numbering changes, and that fragility is itself worth a Comment.

For each figure and table:

1. Confirm it has a caption (a `SEQ Figure`/`SEQ Table` field, usually `Figure <n> – <caption text>` with an en dash).
2. Confirm it is cross-referenced in the prose by **either** a `REF` field that resolves to that caption's bookmark **or** a plain-text mention of `Figure`/`Table` plus the caption's number.
3. Flag: a caption with no cross-reference of either kind; a cross-reference whose target resolves to no caption; and, separately, a plain-text cross-reference where a field would be more robust (a Comment, not Track Changes: it is a recommendation, not an error).

## Citations vs. References section

This reuses the EndNote cite-while-write parsing of `citation-check` (`ADDIN EN.CITE` fields in `word/document.xml`), extended because citations can also be plain text.

1. Extract every in-text citation from **both** `ADDIN EN.CITE` fields and plain-text citations outside any field. The same source can appear both ways in one document, and both need catching. Plain-text detection needs two passes; one combined author-year pattern fails on real text such as `(Wallace, 1990; Scott and Jones, 2017)` and `(Scott et al., 2020)`:
   - **Parenthetical form:** find a parenthetical group that contains a 4-digit year, split its inner content on `;` (one group often holds several citations), then match each segment against `Surname[,][ and Surname2 | et al.], Year`.
   - **Narrative form:** `Surname[ and Surname2 | et al.] (Year)` outside parentheses, for example "Fitzgerald (1988)" or "Abernethy and Gilbert (1975)".
2. Locate the References section: the heading, then the `ADDIN EN.REFLIST` field that follows (one field for the whole list, one paragraph per entry). Two entry formats occur:
   - **Author-year:** `Surname Initials [and Surname2 Initials...], Year, Title, ...`, alphabetical by lead author.
   - **Numbered** (for example Nature): each entry begins with its citation number as literal text with no separating space (`1Wallace, H. Sealevel...`), ordered by first appearance. The in-text `ADDIN EN.CITE` fields are unchanged by the style switch and carry the same embedded author, title and year; only the rendered result differs (a number, or `Author <number>` for a narrative cite). Match a numbered citation to its entry by **both** the number **and** a lead-author and year cross-check against the field's embedded metadata. The rendered number is only a label.
   - Extract each entry's lead author surname(s) and year for matching. Do not require an exact full-string match: an in-text citation with three or more authors usually abbreviates to "First et al., Year" while the entry lists everyone.
3. A document can have no citation or reference-list fields at all (every field unlinked to plain text). Then every in-text citation is plain text (both forms above apply), the References section is plain paragraphs, and there is no field to track.
4. Flag any in-text citation, field or plain text, whose surname and year match no References entry.
5. Flag any References entry that no in-text citation matches (an orphan). This was requested explicitly and is distinct from `citation-check`'s remit.

This check is about internal consistency only: does every citation have an entry, and does every entry have a citation. It does not verify that an entry is accurate or that a citation is used correctly. Point to `citation-check` for that, once, in the summary.

## Deliverables

`<original-name> - proofread.docx`, saved in the same folder as the original manuscript (not the `outputs/` convention: this document is meant to be opened in Word, not read as a task-output report). If that path already exists, do not overwrite it silently, because a prior run's revisions and comments are real work. Rename the existing file to `<original-name> - proofread (previous run).docx` before writing the new output, and say so in the summary so the user can check whether the earlier findings need keeping or merging.

Give a short summary in the chat response, not inside the document: the document's comments are for substantive editorial feedback only, not a report on the run. Use these seven lines, in this order, and write "none" or "not run" rather than leaving one out:

1. Scope.
2. Track Changes edits: the count, and what changed.
3. Comments: the count against `x_max`.
4. Journal guidelines: the URLs fetched and what each returned (including a blocked fetch or a stale-versus-live discrepancy), or "no journal named".
5. Figure, table and citation-matching issues: unresolved cross-references, captions that nothing refers to, citations with no References entry, entries that nothing cites, or "none".
6. Verification: the validator (ran and passed, or not run and why), the Word check, and any other check that did not run and why.
7. Out of scope: citation source-verification is not done here; use `citation-check`.

## Checks

- Never write to the original file.
- Never flag correct British spelling as an error.
- Track Changes only for objectively correctable issues; Comments for anything that needs the author's judgment.
- A "Not located" or similar hedge applies only when a check genuinely could not be completed (for example a guideline page could not be fetched). Do not use it to avoid a finding the data supports.
- No characterisation beyond what is found: report the inconsistency or gap, not a judgment about the writing's overall quality.
- State plainly when a journal-guideline fetch happened and what it found; do not apply journal-specific rules without saying so.
- Do not pad the comment budget with weak or invented findings. An unused budget is a legitimate outcome.
