---
name: proofread
description: Proofread a Word manuscript for environmental-science academic writing, on a copy and never the original, with Track Changes for spelling and grammar and Comments for flow, phrasing and tense. Also checks captions, cross-references, and that citations match the References list. It does not verify citations against sources (citation-check does).
context: fork
agent: general-purpose
background: true
---

# Proofread

Produces a reviewed copy of a Word (`.docx`) manuscript, saved alongside
the original as `<name> - proofread.docx`. The original is never opened
for writing — a hard boundary on this machine. All feedback lands in the
copy as either a **Track Changes** edit or a **Comment**, per the split
below; nothing is a plain-text report.

This skill is scoped to writing quality and document mechanics. It does
**not** check whether a citation is accurate or fabricated, or whether a
cited source actually supports its claim — that is the separate
`citation-check` skill, run independently. Say so once in the summary,
don't attempt any part of it here.

If the invocation doesn't say which part of the manuscript to check, ask
rather than guessing scope (whole document vs. a named section) — don't
silently default to the whole document, which can be long and costly to
proofread properly (a full Word spelling/grammar pass, a genuine close
read for flow, and the citation/figure checks all scale with length).
Whatever scope is agreed, state it plainly in the summary.

## Style target

- **British spelling throughout.** Treat consistent British spelling as
  correct — never flag "characterised," "recognised," "colour," etc. as
  errors. Where a document mixes variants (a stray American spelling in
  an otherwise British-spelled document), that inconsistency is itself
  worth correcting via Track Changes.
- Apply this machine's standing writing rules (from the global CLAUDE.md):
  no contractions, plain words, short sentences, sentence case for
  titles/headings, dashes only inside compound modifiers and never as
  standalone punctuation.
- **Journal-specific calibration, optional.** If the invocation names a
  target journal (a `--journal "<name>"` argument, or a natural-language
  request like "proofread this for JGR-Oceans"), fetch that journal's
  current author guidelines and check against them (structure, heading
  conventions, citation style, any explicit style rules the guidelines
  state). If no journal is named, apply a generic environmental-science
  academic register instead — don't guess a journal from context.

  **Tested live** (Proceedings of the ICE: Maritime Engineering, Emerald)
  and confirmed two real risks, not hypothetical ones:
  - **Publisher pages can block automated fetches outright.** Confirmed
    HTTP 403 on `emeraldgrouppublishing.com` and `icevirtuallibrary.com`;
    only `emerald.com/journals/author-guidance/...` succeeded. Treat a
    blocked fetch as a plain, reported failure — fall back to the generic
    register and say the journal-specific lookup failed, don't silently
    apply nothing or guess.
  - **Search-indexed guidance can be stale and can actively conflict with
    the current live page.** Confirmed directly: search results (from
    the now-blocked `icevirtuallibrary.com`) described Vancouver/numbered
    referencing and 3000–5000 word limits, while the live Emerald page
    that actually loaded states Harvard author-year style instead — a
    real discrepancy, plausibly from ICE Publishing's journals moving
    onto Emerald's platform with a house-style change. **Only trust a
    page that was actually fetched and read this run — never a search
    snippet or a remembered/cached description of what a journal's style
    "usually" is.**
  - What loaded may be **collection-level** guidance (shared across every
    journal in a publisher's group) rather than confirmed journal-specific
    detail — the specific journal's own homepage, where per-journal word
    counts typically live, can be exactly the page that's blocked. Say
    explicitly which scope was actually obtained (collection-wide vs.
    this journal specifically) rather than presenting one as the other.
  - State plainly in the summary: the exact URL(s) fetched, which
    succeeded and which were blocked, and whether what's being applied is
    journal-specific or a publisher-collection fallback.

## Finding spelling and grammar issues

**Spelling**: drive Microsoft Word itself via COM automation (confirmed
available and working on this machine — `New-Object -ComObject
Word.Application`, open the document read-only, read
`doc.SpellingErrors`, close without saving, quit). This uses the same
dictionary Word itself would apply, with exact character positions, and
is far more reliable than reading the document for typos by eye —
confirmed against the real test document: it found 31 candidates,
including a genuine catch ("Brechtschneider" for the standard
"Bretschneider" wave-spectrum model) alongside many legitimate technical
terms, place names, and brand names it simply doesn't recognise (its
dictionary is not a judge of domain correctness). **Every
`SpellingErrors` hit is a candidate, not an automatic correction** — filter
out proper nouns, place names, brand names (cross-check against names
already appearing in the References section — a name cited there is
almost certainly not a typo), and known technical/discipline vocabulary
before proposing anything as a Track Changes edit.

**British/American spelling consistency**: don't rely on Word's own
checker for this specifically. Confirmed on the real document: its
default language is `en-GB` (`styles.xml` `docDefaults`), but 41 runs
carry an explicit `en-US` override, which makes Word accept American
spelling as correct within those runs — an inconsistency Word's own
checker cannot itself catch. Run an explicit variant-spelling scan
(a wordlist of common `-ize`/`-ise`, `-or`/`-our`, `-er`/`-re`, etc. pairs)
across all text regardless of per-run language tags.

**Grammar**: Word's own `GrammaticalErrors` collection returned zero
hits on a real pass over this document — either genuinely clean or (more
likely) not sensitive enough to trust as the sole check. Treat grammar
and flow as model judgment, reading the text directly, not as something
Word's checker verifies for you.

## Mechanism

Use the `docx` skill's own editing workflow for the mechanical part —
don't reinvent XML handling this skill already documents. **Confirmed
working end to end** on this machine, real edit through to a Word-opened,
inspected result (not just a dry read of the docx skill's own docs):

- `merge_runs.py` and `comment.py` (and the validator) depend on
  `defusedxml` and `lxml`, neither installed on this machine by default —
  confirmed by hitting `ModuleNotFoundError` on all three before
  installing both packages (`pip install --break-system-packages
  defusedxml lxml`). Check they're importable before relying on these
  scripts; if not, that's a one-time environment setup, not something to
  work around by hand-rolling the XML.
- Unpack, run `merge_runs.py` so fragmented runs are findable. It does
  **not** merge every run spanning a phrase — runs with differing
  `rPr` (even trivial formatting differences) stay separate, confirmed on
  a real caption ("Figure" / " " / "1" stayed three separate runs). A
  Track Changes edit or comment anchor spanning multiple adjacent runs
  needs each run's own `rPr` matched exactly when splitting/wrapping —
  don't assume the phrase you want to touch is a single run after
  merging.
- **Track Changes**: wrap the correction in `<w:ins>`/`<w:del>` (author
  `"Claude"`, current date, each with its own unique `w:id` — confirmed
  two edits in the same document need distinct ids, not the same pair
  reused). When the target text sits inside a longer run, split that run
  at the target's boundaries, keeping any sibling content (e.g. a
  `<w:fldChar>` in the same run) in its own untouched run rather than
  disturbing it.
- **Comments**: use `comment.py` against the *unpacked directory* (not
  the `.docx` directly, when you're also editing `document.xml` — saves
  an unzip/rezip cycle, and is what was actually tested). It prints the
  exact `commentRangeStart`/`commentRangeEnd`/`commentReference` markers
  to place — these must be **direct children of `w:p`, never inside
  `w:r`**, confirmed by following its own printed instructions.
- **When a run has content after the target text but before its own
  `</w:r>`** (e.g. the target sentence is followed, later in the same
  run, by a `SEQ`/`REF` field for a figure number) — confirmed on a real
  paragraph: naively taking only the first `<w:t>...</w:t>` in the run
  and discarding everything after it silently deletes that trailing
  content. The schema validator does catch this specific failure (it
  compares document text with tracked changes resolved against the
  original) — but **don't rely on catching it after the fact**: always
  capture everything between the end of the target text and the run's
  real closing `</w:r>` and re-emit it, unmodified, in a continuing run.
- **Use one consistent, safety-checked splitting routine for every
  comment/edit in a run, not ad-hoc one-off code per case.** Confirmed
  directly: four comments, each individually verified working, and even
  a 2-of-4 combination verified working, still produced a file Word's
  own opener rejected as corrupted when combined via inconsistent
  one-off code paths — despite passing the schema validator cleanly. A
  clean rewrite using a single shared function fixed it, without ever
  isolating the exact wrong line. **Schema validation passing is not
  sufficient proof of correctness — Word enforces stricter internal
  consistency than the XSD captures.** The Word-COM-open check below is
  therefore mandatory before treating any multi-comment or multi-edit
  run as done, not an optional final nicety.
- **Re-zipping**: this machine's Git Bash has no `zip` command — confirmed
  (`zip: command not found`). Use Python's `zipfile` module directly
  (`ZIP_DEFLATED`, walk the unpacked directory, write each file with a
  forward-slash relative path) rather than assuming the shell `zip`
  command from the docx skill's own docs is available.
- **Validate** with `validate.py --author "Claude" --original <source>`
  before treating any edit as done — confirmed it catches paragraph-count
  drift and un-tracked changes. On this machine its own output needs
  `PYTHONIOENCODING=utf-8` set first, or it crashes trying to print a
  Unicode arrow to the default Windows console encoding — a console
  quirk, not a validation failure.
- **Verify the result**: the docx skill's own documented verification
  step (LibreOffice render to PDF, then image inspection) **does not work
  on this machine** — `soffice` is not installed, confirmed by search.
  Microsoft Word itself is installed and reachable via COM automation
  (already established for spelling — see above), so use that instead:
  open the produced file read-only, check `doc.Revisions.Count` and
  `doc.Comments.Count` match what was intended, check each revision's
  `Author`/`Type`/`Range.Text` and each comment's `Scope.Text`, and
  confirm the file opened without triggering a repair prompt (a sign of
  XML corruption). Confirmed working this way end to end: a real
  two-instance spelling correction and a real anchored comment, both
  round-tripped through unpack → edit → re-zip → validate → Word-open,
  and both came back exactly as intended.
- Pandoc (`pandoc -t markdown file.docx`, the docx skill's suggested way
  to read content) is **not installed on this machine** either —
  confirmed. Extract text directly from `word/document.xml` instead (the
  same approach used throughout this skill for citations, captions, and
  cross-references) rather than assuming pandoc is available.

## What goes where

**Track Changes** — objectively correctable issues: spelling errors
(against the British-spelling target), grammatical errors (subject-verb
agreement, article use, punctuation), and non-British spelling variants
found in an otherwise British-spelled document. These get a direct
proposed correction, not just a flag.

**Comments** — anything requiring the author's own judgment rather than
a single correct fix: flow, phrasing, word choice, and two specific
consistency checks:
- **Active/passive voice inconsistency** — flag where the document
  switches between voices without an apparent reason (not a mandate for
  either voice; both are legitimate in this field).
- **Verb tense inconsistency** — flag where comparable content (e.g.
  within Methods, or within Results) mixes past and present tense without
  reason.

Keep each individual comment short — generally one to two sentences,
stating the issue and, if brief, a suggested direction, not a full
rewrite — and **never exceeding 50 words** (Word's own
`Range.Words.Count` per comment). This is a hard per-comment cap, checked
per comment as you add it, not an average to stay near.

**The budget is a ceiling on the *number* of comments, not their combined
length.** Compute it once per document:

```
x_max = max(5, floor(0.005 × prose_word_count))
```

— i.e. up to one comment per 200 prose words, with a floor of 5 comments
so a short document isn't blocked from any feedback at all, even where
5 × 50 words exceeds the document's own length. There is no separate
total-word ceiling beyond `x_max` comments at up to 50 words each; stop
adding comments once `x_max` is reached, prioritizing the clearest, most
useful issues over surfacing every minor stylistic preference. "Prose
word count" excludes the References section (citation entries carry no
flow to comment on) — locate it the same way the Citations vs. References
check does (the heading, then to the end of that field/section) and count
only what precedes it, plus anything after it that isn't
References/Appendix material.

**Calibrated against a real full-document pass** (~8,850-word paper,
prose portion excluding References ~8,200 words, giving `x_max = 41`
under this formula): a genuinely defensible read — every candidate
individually checkable against the actual text, nothing invented to fill
space — produced 4 comments totalling 164 words. That run never came
close to either this ceiling or the earlier 2%-of-total-words ceiling it
was originally calibrated against, so it confirms both are more than
sufficient for a real proofread pass on that document, not which of the
two is "correct" — there is no real-run evidence yet that `x_max` itself
ever binds in practice; treat it as a backstop against a runaway number
of comments, not a target to approach. Two categories the checklist asks
for (active/passive and verb-tense inconsistency) were deliberately
**not** used in that calibration run: the document's mix of tenses/voices
followed a coherent, conventional pattern (passive for methods, present
for stated results, past for what was done) rather than an arbitrary
switch, and inventing an inconsistency finding to fill the budget would
be fabricating a result the text doesn't support. **Don't pad the budget
with weak findings — using fewer than `x_max` comments is a legitimate
outcome, not a failure to hit a target.**

## Parsing rule that applies to every check below: track fields across the whole document, not per paragraph

A Word field's `begin`/`separate`/`end` markers do not have to sit in the
same paragraph — confirmed on a real document: the entire References
section is a *single* `ADDIN EN.REFLIST` field whose `begin` is in the
paragraph right after the "References" heading and whose matching `end`
is 23 paragraphs later, with every reference entry in between rendered as
plain-looking `<w:t>` runs and no field markers of their own in that
paragraph. Track field nesting depth by walking the document body in
document order, continuously, from the top — **never reset the tracking
state at a paragraph boundary**, or every entry after the first gets
silently misclassified as plain text. Paragraph boundaries *within* a
field's result region still separate individual entries (one paragraph =
one reference entry, one caption, etc.) — only the state-tracking itself
must span paragraphs, not the meaning of a paragraph break.

## Figures and tables

Word inserts native captions as `SEQ Figure`/`SEQ Table` fields, and
cross-references them elsewhere with `REF _Ref... \h` fields pointing at
bookmarks. But a cross-reference can also be plain typed text with no
field at all — confirmed on a real document: the same paragraph contains
both a properly field-linked `REF` to "Figure 2" and a manually typed
"Figure 1" (no field markers whatsoever) referring back to an earlier
caption. The typed one won't auto-update if figure numbering changes
later — that fragility is itself worth a Comment, not just a parsing
inconvenience.

For each figure/table:

1. Confirm it has a caption (a `SEQ Figure`/`SEQ Table` field, format seen
   in practice as `Figure <n> – <caption text>` with an en dash).
2. Confirm it is cross-referenced somewhere in the prose, by **either**
   a `REF` field resolving to that caption's bookmark **or** a plain-text
   mention matching the pattern `Figure`/`Table` + the caption's number.
3. Flag: a caption with no cross-reference of either kind anywhere in the
   text; a cross-reference whose target can't be resolved to any caption;
   and, separately, a plain-text cross-reference where a proper field
   would be more robust (Comment, not Track Changes — it's a
   recommendation, not an error).

## Citations vs. References section

Reusing the EndNote CWYW field-parsing already established for
citation-check (`ADDIN EN.CITE` fields in `word/document.xml`), extended
for this skill's own requirement that citations can be plain text too:

1. Extract every in-text citation, from **both** `ADDIN EN.CITE` fields
   (citation-check's method — still works unchanged for a numbered
   citation style; see below) **and** plain-text citations that sit
   outside any field. Confirmed on a real document: the same source can
   appear both ways for different mentions in the same document, and both
   need catching.

   Plain-text detection needs two passes, not one monolithic pattern — a
   single naive author-year regex was tried and **failed** on real
   in-document text (`(Wallace, 1990; Scott and Jones, 2017)` and
   `(Scott et al., 2020)` both matched nothing):
   - **Parenthetical form**: find a parenthetical group containing a
     4-digit year, then split its *inner* content on `;` — a single
     parenthetical commonly holds more than one citation — then match
     each segment against `Surname[,][ and Surname2 | et al.], Year`.
   - **Narrative form**: `Surname[ and Surname2 | et al.] (Year)` outside
     any parentheses (e.g. "Fitzgerald (1988)", "Abernethy and Gilbert
     (1975)").
   - Both were tested against every real citation instance found in the
     document and matched correctly once split this way; a single
     combined regex did not.

2. Locate the References section (the heading, then the single
   `ADDIN EN.REFLIST` field that follows it — confirmed format on a real
   document: one field spanning the whole list, one paragraph per entry).
   Two entry formats seen, both real:
   - **Author-year style**: `Surname Initials [and Surname2 Initials...],
     Year, Title, ...`, list alphabetical by lead author.
   - **Numbered style** (e.g. Nature): each entry begins with its
     citation number as literal text with no separating space (e.g.
     `1Wallace, H. Sealevel...`), list ordered by first appearance in the
     text, not alphabetical. The in-text `ADDIN EN.CITE` fields are
     unchanged by this style switch — same embedded author/title/year
     metadata as author-year style, only the *rendered* result differs
     (a number, or `Author <number>` for a narrative-style cite like
     "Fitzgerald 5"). Match a numbered in-text citation to its entry by
     **both** the number **and** a lead-author/year cross-check against
     the field's own embedded metadata — don't trust the rendered number
     alone, since it's just a label the field produced, not an
     independent identifier.
   - Extract each entry's lead author surname(s) and year for matching —
     don't require an exact full-string match, since an in-text citation
     with 3+ authors typically abbreviates to "First et al., Year" while
     the References entry lists everyone.
3. A third, simpler case also confirmed: a document with **no** citation
   or reference-list fields at all (every field "unlinked" to plain text).
   Here every in-text citation is plain-text-only (both forms above still
   apply) and the References section is plain paragraphs with no field to
   track — the cross-paragraph field-tracking rule doesn't come into play
   because there's no field, which is the simpler, not the harder, case.
4. Flag any in-text citation (field or plain-text) whose surname+year
   doesn't match any References entry.
5. Flag any References entry never matched by an in-text citation (an
   orphan) — requested explicitly, distinct from citation-check's remit.

This check is about internal consistency only (does every citation have
an entry, and vice versa) — it does not verify that any entry is accurate
or that any citation is used correctly in context. Point to citation-check
for that, once, in the summary.

## Deliverables

`<original-name> - proofread.docx`, saved in the same folder as the
original manuscript (not the `/outputs` convention — this is a document
meant to be opened directly in Word, not a task-output report). If that
path already exists, don't silently overwrite it — a prior run's
revisions and comments are real work, not scratch. Rename the existing
file to `<original-name> - proofread (previous run).docx` (confirmed
naming, real behaviour from a fresh test) before writing the new output,
and say so plainly in the summary so the user can check whether the
prior run's findings need retaining or merging.

Produce a short summary in the chat response, not inside the document —
the document's own comments are for substantive editorial feedback only,
not a meta-report about the run. Cover: counts of Track Changes edits and
Comments made (with the comment count used vs. `x_max`), the journal
guideline lookup result if one ran (including any blocked or
stale-vs-live discrepancy found), any unresolved figure/table or
citation-matching issues, and the standing note that citation
source-verification is out of scope here.

## Checks

- Never write to the original file.
- Never flag correct British spelling as an error.
- Track Changes only for objectively correctable issues; Comments for
  anything requiring the author's judgment.
- A "Not located" or similar hedge only applies when a check genuinely
  could not be completed (e.g. a source or guideline page couldn't be
  fetched) — don't use it to avoid a real finding the data supports.
- No characterization beyond what's found — report the inconsistency or
  gap, not a judgment about the writing's overall quality.
- State plainly when a journal-guideline fetch happened and what it found;
  don't apply journal-specific rules without saying so.
- Don't pad the comment budget with weak or invented findings — an
  unused budget is a legitimate outcome.
