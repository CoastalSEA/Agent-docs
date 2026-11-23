---
name: library-metadata
description: Maintain the project EndNote library under sources/references (find verified metadata for entries from their PDFs, add papers by DOI with or without a PDF, append keywords), writing only through endnote_lib.py. Not for an independent or personal library.
---

# Library metadata

This skill maintains the project library named in the "Project library" block of the project `CLAUDE.md`. The project root is the folder the skill was invoked from. It corrects entries, adds papers and appends keywords, and writes only through the shared helper `endnote_lib.py` (command form in `machine.md`). The helper refuses any library outside `sources/references/` of the project and any protected path; an independent library (a personal one, for example) is read only, through `mcp__endnote__*`. The scripts of this skill are in `<claude folder>/skills/library-metadata/scripts/`; run them with the Python in `machine.md`, with `--root "<project root>"`.

## Finding the library

- Read the "Project library" block: the library path, the log folder and the MCP registration (`endnote-project`).
- Run `endnote_lib.py info --lib "<library>"` first. When the library is open in EndNote the helper refuses: stop and tell the user to close it. Do not retry.
- If the project has no such block, or `info` reports no library at that path, stop, write nothing, and say so. Name the setup: create the library in `sources/references/`, add the block with `project.py init --library`, and register `endnote-project` (Agent-docs README, section "A project EndNote library").
- Entry types differ per library. If `<log folder>/entry_types.json` does not exist, run `endnote_lib.py types`, find the integers for a journal article and a book chapter from the example titles, and write `{"journal-article": <int>, "book-chapter": <int>, "_evidence": "<entry ids and titles used>"}`. If the examples do not settle it, ask the user.

## Before sending anything off the machine

Ask the user once per invocation, naming what is sent (titles read from PDFs, DOIs) and where (arXiv, CrossRef, DataCite and OpenAlex). Without a yes, do only the local steps. The scripts send the OpenAlex key as described in `machine.md` and send no e-mail address.

## Tasks

1. **Correct entries.** Run `lookup.py --lib "<library>" --out "<log folder>/<task>" --untitled` (or `--ids`). It writes `proposals.csv` and `proposals.json` and writes nothing to the library. A DOI is looked up on arXiv (an arXiv DOI), CrossRef, DataCite and OpenAlex before the title search; each row names the services searched. Report the flags (an entry sharing its DOI with another active entry, a record found by title with a different DOI, a record type to set by hand) and the notes (a copy in the trash, an arXiv year that differs from the entry year) to the user; do not resolve them.
   - For an entry flagged because its file name or recorded title is wrong, read the first page with `mcp__endnote-project__read_linked_file_text` (`first_page=1`, `last_page=1`), put the printed title in a CSV with columns `id, query`, and run `lookup.py` again with `--queries`.
   - For an entry flagged for no text layer, run `ocr_pdf.py` with the interpreter of the OCR environment and the Tesseract path in `machine.md`, with the same `--out`, then run `lookup.py` again.
   - Run `apply.py --lib "<library>" --proposals "<log folder>/<task>" --types "<log folder>/entry_types.json" --log "<log folder>"`. It writes the verified entries only. Use `--overrides` only for values printed on the PDF itself, with that as the source.
2. **Add papers.** Write a CSV with `doi` and, as known, `record`, `title`, `pdf`, `linked`, `year_fallback` and `note` (see the header of `add.py`), then run `add.py --lib "<library>" --list <csv> --types "<log folder>/entry_types.json" --log "<log folder>"`. A PDF comes from an open-access address (`url:`) or a local file (`file:`). For a paper held in an independent library, take the file path from `mcp__endnote__list_linked_files` (`resolved_path`): the file is only read and copied. Set `linked` to `yes` only for such a file.
3. **Append keywords.** Write a CSV with `id, keywords` and run `endnote_lib.py tag --lib "<library>" --csv <csv> --prefixes "<prefixes in the block>" --log "<log folder>" --source "<records used>"`. Reading depth comes from the project's reading records only, never from an abstract. Match a record to an entry by DOI, then by title with first author and year; a record that names several papers counts for each; duplicate entries get the same keywords; the deepest reading depth wins. Which keywords to propose is project specific: take them from the project records.

## Deliverables

All files go in the log folder named in the block, under fixed names. Library changes are not run controlled.

- `changes.csv`: every changed field written by the helper (entry, field, before, after, source), and one `check` row per entry handled by `apply.py` with its result (verified with the number of fields changed, or flagged with the reason).
- `added.csv`: every row of an `add.py` list, with the new id or the reason it was not added.
- `<task>/proposals.csv` and `<task>/proposals.json`, `<task>/ocr/`, and `entry_types.json`.

In the reply, report: entries written and fields changed, entries flagged with their reasons, rows not added with their reasons, any refusal by the helper, and the backup folder (`endnote_lib.py info` gives the count and size). Remind the user that new authors, journals and keywords may not appear in EndNote's term lists until Library, Recover Library is run.

## Checks

- Write nothing for a flagged entry or a row that failed a check. Do not fill a gap with a plausible value; report it as missing and say what would settle it.
- A DOI that CrossRef does not find is not proof of a wrong DOI; report it as not found in CrossRef.
- A paper whose copy is in the trash is reported, not added.
- Never delete an entry or a PDF, never remove a keyword, and never write to a library other than the one in the block. When the helper refuses, report the refusal; do not work around it.
- Name the checks that failed as well as the ones that passed.
