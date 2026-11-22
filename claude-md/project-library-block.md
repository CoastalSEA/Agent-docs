## Project library

- The project library is `sources/references/[name].enl`. Read it through the MCP registration `endnote-project`; add and correct entries only through `endnote_lib.py` (in `machine.md`) with `--lib "sources/references/[name].enl" --log [log folder] --source "<source of the values>"`.
- Downloaded papers go into the library, not into loose files; this replaces the naming rule for downloaded references above. A paper cited in older notes by file name is found in the library by file name or by title and author.
- When the helper refuses because the library is open in EndNote, stop and tell the user.
- Keywords: `read:full`, `read:partial` and `read:none` for reading depth (from the reading records, never from an abstract), and `proj:<topic>` for project topics. Select papers by keyword, not by EndNote group.
