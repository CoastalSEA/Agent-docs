# EndNote command-line tool review: outcome

Date: 2026-08-30

## Decision

The `endnote-cli` package (github.com/TCMzhoutong/endnote-cli) was compared with the local
`endnote_server.py`. The route chosen was to keep the local server, read-only only. No write
tool was added. The full comparison is in `endnote-mcp-spec.md`, section "endnote-cli review".

| | endnote-cli | Local `endnote_server.py` |
|---|---|---|
| Type | Third-party pip package, command line only, not MCP-native | Purpose-built MCP server |
| Write support | Yes. The only documented precondition is that EndNote is closed; the tool does not check it | None. Every connection opens the library with `mode=ro`, so a write fails at the driver |
| Maturity | 12 stars, 7 commits at review time | Tested end to end against the target library |
| Cost to adopt | Needs an MCP wrapper | Already built |

## Change made

The server was re-registered from project scope to user scope, so it is available in every
project on the machine:

```
claude mcp remove endnote -s local
claude mcp add endnote -s user -e ENDNOTE_LIBRARY_PATH="<path to library>.enl" -- \
  "<python>" "<repository>/mcp/endnote/endnote_server.py"
```

`claude mcp get endnote` reports the scope as user, and `claude mcp list` shows it connected.
The server code was not changed.

## Acceptance tests

- **Read entries:** `search_references` returned records with id, author, year, title,
  abstract preview and url.
- **Formatted copy:** `get_reference` returned the full bibliographic record for one entry.
- **Linked PDF:** `list_linked_files` found the attachment and `read_linked_file_text`
  extracted readable text from it.
- **Write blocked:** the server exposes no write tool (`search_references`, `get_reference`,
  `list_linked_files`, `read_linked_file_text` only), and each opens the library with
  `mode=ro`. A live update against the real library was blocked by the session permission
  classifier and was not worked around. Checksums on the library file and a linked PDF were
  unchanged before and after testing (see `endnote-mcp-spec.md`).
