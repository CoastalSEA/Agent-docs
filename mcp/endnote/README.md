# endnote

MCP server providing read-only access to an EndNote library: search references, retrieve
full records, list linked files, and extract text from linked PDFs.

- `endnote_server.py` — the server code
- `docs/endnote-mcp-spec.md` — the spec (allowed/prohibited/approval/verification, schema
  grounding, implementation and test status)
- `docs/endnote-mcp-prompt.md` — the prompt used to generate the spec
- `docs/endnote-cli-review.md` — comparison against the third-party `endnote-cli` alternative,
  and the acceptance-test results from bringing this server online at user (global) scope
