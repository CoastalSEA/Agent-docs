# endnote

MCP server providing read-only access to an EndNote library: search references, retrieve
full records, list linked files, find entries by the name of a linked file, and extract text from linked PDFs.
Entries in the trash are left out unless a tool is asked to include them.

- `endnote_server.py`: the server code
- `docs/endnote-mcp-spec.md`: the spec (allowed/prohibited/approval/verification, schema
  grounding, implementation and test status)
- `docs/endnote-mcp-prompt.md`: the prompt used to generate the spec
- `docs/endnote-cli-review.md`: comparison against the third-party `endnote-cli` alternative,
  and the acceptance-test results from bringing this server online at user (global) scope

## Setup

The server needs Python 3 with the `mcp` and `pypdf` packages (`pypdf` reads the text of linked PDFs). Install them into the interpreter that will run the server:

```
<python> -m pip install mcp pypdf
```

Register the server at user scope, with the path of your library. Run the command from a shell that keeps the `--` (Git Bash or a Unix shell; PowerShell 5.1 drops it and the registration fails):

```
claude mcp add endnote -s user -e ENDNOTE_LIBRARY_PATH="<path to the .enl file>" -- <python> "<path to this folder>/endnote_server.py"
```

Then start a new session, because a server added during a session loads only in the next one. `claude mcp get endnote` should show `Connected`, and one `search_references` call confirms that the tools work. The spec was tested with `mcp` 2.1.1; 2.3.0 starts and answers `search_references`. Do not run the check from the repository root: the `mcp/` folder here can be imported in place of the `mcp` package.

## Project library

A project that keeps its papers in a project library under `sources/references/` (see `claude-md/project-library-block.md`) gets a second registration of the same server for that library. The user-scope `endnote` registration, which serves the independent library, is left as it is. Register at local scope from the project root, so the path stays out of the project repository:

```
claude mcp add endnote-project -s local -e ENDNOTE_LIBRARY_PATH="<project root>/sources/references/<name>.enl" -- <python> "<path to this folder>/endnote_server.py"
```

A session in that project then has both: `mcp__endnote__*` reads the independent library and `mcp__endnote-project__*` reads the project library. `citation-check` and `literature-search` use the project registration when the project `CLAUDE.md` names it. Start a new session after registering, and after any change to the server code: a running server is not reloaded.

The server stays read only for both. Entries of the project library are added and corrected only through `scripts/endnote_lib.py` (see `scripts/README.md`), which refuses to write to any library outside `sources/references/` of the project and to any protected path.

- `search_references` takes `keyword` for an exact keyword (for example `read:full`; a substring search on `read:full` is loose) and `include_trash`.
- `get_reference` returns the entry type name with the integer (for the integers observed: 0 Journal Article, 1 Book, 2 Thesis, 7 Book Section, 10 Report; others without a name), whether the entry is in the trash, and its linked files.
- `search_by_file_name` finds entries by the name of a linked file, for notes that cite papers by file name.
- `read_linked_file_text` takes `first_page` and `last_page`, and says when a PDF has no text layer. The server does no OCR; the `library-metadata` skill has an OCR step.
- A library open in EndNote cannot be read; the lock is per library file, so the other library stays readable.
