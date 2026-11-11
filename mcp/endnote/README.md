# endnote

MCP server providing read-only access to an EndNote library: search references, retrieve
full records, list linked files, and extract text from linked PDFs.

- `endnote_server.py` — the server code
- `docs/endnote-mcp-spec.md` — the spec (allowed/prohibited/approval/verification, schema
  grounding, implementation and test status)
- `docs/endnote-mcp-prompt.md` — the prompt used to generate the spec
- `docs/endnote-cli-review.md` — comparison against the third-party `endnote-cli` alternative,
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
