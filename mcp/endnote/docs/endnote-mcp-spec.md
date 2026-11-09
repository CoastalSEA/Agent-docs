---
name: endnote-mcp
description: MCP server that sources references from an EndNote library, read-only
---
# MCP server specification: EndNote

## system

EndNote. Current target library: `<path>/<target library>.enl` and its companion folder `<path>/<target library>.Data/`. The server was first built and tested against the first test library, `<path>/<test library>.enl`, then switched to the target library on 2026-08-28 at the user's request; the implementation (`mcp_servers\endnote_server.py`) selects the library from the `ENDNOTE_LIBRARY_PATH` environment variable, defaulting to the target library.

Working constraint confirmed during testing: EndNote holds an exclusive OS-level lock on a `.enl` file while it is open in the application, and the read-only SQLite connection fails (`unable to open database file`) while that lock is held. The library must be closed in EndNote before this server can read it. This was first hit as an opaque error during a real reference-check run (three subagents each independently spent tool calls diagnosing the same generic `Error executing tool` failure before the cause — EndNote being open — was found). An upfront check for this was added afterward; see **Library-lock detection** below.

## interface

MCP server. Exposes read-only tools over the EndNote library so a calling agent can pull reference data into a conversation without opening the EndNote application.

## purpose

Source references from the database: return bibliographic records, abstracts, and the text of linked files (for example PDFs) so they can be used as source material in an analysis or a citation search.

## allowed

- Read bibliographic fields from the library (title, author, year, abstract, keywords, url, notes, reference type, and the other fields listed in the schema below).
- Read the abstract field as source text.
- Read the content of a linked file (for example a PDF) as source text, by opening the file in read-only mode and extracting its text. The file itself is never altered.

## prohibited

- No write, update, insert, or delete against either database file (`<test library>.enl` or the files in `<test library>.Data\sdb\`).
- No move, rename, delete, or content edit of a linked file. A linked file is opened for reading only, and the handle is closed without modification.
- No writing back into the EndNote library from this server under any circumstance, including tagging, rating, or note fields.

Enforcement, not just policy: every database connection must open the `.enl` file with the SQLite URI flag `mode=ro` (for example `file:<path>?mode=ro` in Python's `sqlite3`, `uri=True`). This makes a write attempt fail at the driver level rather than relying on the server's own code to never issue one. Do not open the file in the default read-write mode and rely on the tool layer to avoid writing.

## approval

A reference is only used as a source once it is confirmed to match the context of the search that produced it. The server does not decide relevance on the caller's behalf — it returns candidate records for the query terms given, and the calling agent (or the person) must check each candidate's title, abstract, and year against the actual research question before treating it as a source. A record matching the search string is not the same as a record matching the search's intent; do not skip this check because a query returned few results.

## verification

Before any reference is cited or its content used, its full preview (title, author, year, abstract, and, if a linked file was pulled, the extracted text) must be opened together with the other candidates and actually read, item by item — not sampled, not assumed from the title alone. This applies even when the server returns a short result set.

---

## Schema grounding

Both libraries were inspected and queried read-only (`mode=ro`, no writes made). The test library first, on 2026-08-28; the target library the same day after switching. Checksums and modification times on both `.enl` files, and on a linked PDF read during testing, were confirmed unchanged before and after. Findings:

- The `.enl` file itself is a SQLite 3 database (EndNote's newer single-file format, schema version 4, confirmed via `file` and by listing `sqlite_master`). There is no separate `.enlp`/`rdb` companion database to open for this version — only `.enl` for records and a `.Data\sdb\` folder holding `sdb.eni` / `pdb.eni`.
- Relevant tables and columns found in `refs`: `id`, `author`, `year`, `title`, `abstract`, `keywords`, `url`, `notes`, `reference_type` (integer code), `pages`, `volume`, `number`, `secondary_title`, `publisher`, `isbn`, `electronic_resource_number` (the DOI field; returned as `doi` since 270926), plus several `custom_1`–`custom_7` fields whose meaning is library-specific and not derivable from the schema alone. the target library additionally has `sact` and `sync` tables not present in the test library, most likely related to EndNote's online-sync feature; these were not examined and are not exposed by any tool.
- Linked files are recorded in `file_res` (`refs_id`, `file_path`, `file_type`, `file_pos`). The test library has zero rows here (its 14 records are all web/report citations with a `url` field but no attachment). The target library has 6020 records in `refs` and 3838 rows in `file_res`, so this path is now exercised against real attachments.
- `file_path` values are relative to the library's `.Data\PDF\` folder, one subfolder per attachment keyed by a 10-digit id, e.g. `file_res` row `(30, '<id>/<file>.pdf', 1, 0)` resolves to `<target library>.Data\PDF\<id>\<file>.pdf` — confirmed to exist and to extract cleanly with `pypdf`. This resolution rule is now confirmed, not assumed.
- `reference_type` is an integer that maps to a type name (e.g. web page, journal article) via EndNote's style/type table, which is not present in the `.enl` file itself. This mapping was not resolved here; treat `reference_type` as an opaque code unless a type table is located, rather than guessing the mapping.

## Implementation and test status

Implemented at `mcp_servers\endnote_server.py` using the Python `mcp` SDK (v2.1.1, `MCPServer` class — the package renamed `FastMCP` to `MCPServer` between v1 and v2) and `pypdf` for text extraction. Four tools: `search_references`, `get_reference`, `list_linked_files`, `read_linked_file_text`.

Tested as direct function calls and as a full MCP protocol round trip (stdio transport, a real `ClientSession` calling `initialize`, `list_tools`, and `call_tool`) against both the test library and the target library, including a real PDF extraction. Confirmed live in a session as `mcp__endnote__search_references`, `mcp__endnote__get_reference`, `mcp__endnote__list_linked_files`, `mcp__endnote__read_linked_file_text`, and exercised end to end via the `check-references` skill against a real Word document with embedded EndNote citation field codes.

Originally registered at **local scope** (`claude mcp add --scope local`, private to this project). On 2026-08-30, following the `endnote-cli` review below, re-registered at **user scope** (`claude mcp remove endnote -s local` then `claude mcp add endnote -s user ...`), so it is now available in every project on this machine, stored in the user-level section of `~/.claude.json` rather than the project-scoped section. Still not in a repo-tracked `.mcp.json`, so it stays private to this machine/account and is not shared via git.

## endnote-cli review (2026-08-30)

Per `endnote_cli_mcp.md`, the third-party `endnote-cli` package (github.com/TCMzhoutong/endnote-cli) was reviewed as an alternative to this server. It offers write support (notes, keywords, ratings, labels, custom fields), export formats (BibTeX, RIS, JSON, CSV, XML), and journal auto-tagging that this server does not have. It is a CLI, not an MCP server, so adopting it would still require writing an MCP wrapper.

Its write path was checked specifically against this spec's write-gating requirement: its only documented precondition for a write is "EndNote must be closed," checked nowhere in the tool itself — no file-lock check, no consent flag, no confirmation prompt. It also writes to two files per edit (`.enl` and EndNote's internal mirror `sdb.eni`) to keep them in sync, a larger risk surface than this server's design. Getting the lock-check and consent-gate guarantees this spec requires around endnote-cli would mean building that enforcement from scratch anyway, on top of a young, lightly-maintained package (12 stars, 7 commits at review time).

Decision, confirmed by the user: keep this server, read-only only. No write tools were added. This server's existing `mode=ro`-at-the-driver-level design already satisfies the read/write requirements in **allowed** and **prohibited** above without further changes.

Operational note: an MCP stdio server subprocess is spawned once and kept alive for a session; it does not hot-reload. After editing `endnote_server.py`, a new Claude Code session is needed before the running tool reflects the change — confirmed when the library-lock fix below only took effect after a session restart, even though direct testing of the script showed the fix working immediately.

## Library-lock detection

Added 2026-08-28, after the EndNote-lock constraint above was hit blindly by three parallel subagents during a real check, each independently burning tool calls to diagnose the same opaque failure. `_ro_connect` now runs a probe query (`select 1`) immediately after opening the connection and catches `sqlite3.OperationalError` from either the connect or the probe, raising a `LibraryLockedError` with a specific, actionable message naming EndNote as the likely cause and instructing the caller to close the library and retry. All four tools catch this and return it as a normal result (`{"error": ...}`, or `[{"error": ...}]` for the two list-returning tools) rather than letting an exception propagate — the MCP framework was otherwise swallowing exception detail and returning a bare `Error executing tool` to the client, which is what caused the earlier wasted diagnosis.

This is detection and reporting only. The server does not attempt to close EndNote, kill its process, or otherwise act on a live application — that would be a different, and out-of-scope, kind of action for a read-only reference server. A human (or the calling agent relaying the message to a human) closes the library; the tool call is simply retried afterward.

Implication for use: this cannot become an interactive OS-level prompt appearing on screen mid-call — an MCP tool result is not a UI dialog. What it provides is a fast, clear failure instead of a slow, confusing one, surfaced through whatever is calling the tool.

## Open items requiring a choice

- Whether the server should expose a single `search_references(query)` tool that searches across all text fields, or separate tools per field (title/author/abstract/keyword search). Not decided here; flagging it as a design choice for whoever implements this spec.
- Whether PDF text extraction happens inside the MCP server process or is delegated to a separate extraction tool the calling agent already has. Not decided here.
- How to handle the `custom_1`–`custom_7` fields, whose meaning is set per-library in EndNote's preferences and was not recoverable from the database alone. Flag their raw content rather than guessing a label for them.
