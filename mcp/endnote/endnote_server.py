"""
EndNote MCP server: read-only access to an EndNote library for sourcing references.

Inputs:  an EndNote .enl library file. The path is required, in the
         ENDNOTE_LIBRARY_PATH environment variable; there is no default.
         Test history: docs/endnote-mcp-spec.md.
Outputs: MCP tools returning bibliographic records, search results, and text
         extracted from linked files (e.g. PDFs). No field is ever written back.
Model:   none (data access only). Built against docs/endnote-mcp-spec.md.
Package: mcp 2.1.1 (Python MCP SDK, MCPServer class), pypdf for PDF text extraction.
Date:    2026-08-28.
Changed: 2026-09-27. get_reference and search_references now return EndNote's
         DOI field (column electronic_resource_number) under the key "doi",
         exactly as stored. Created using: claude-opus-5-5-v5.5-date: 270926
Changed: 2026-11-08. ENDNOTE_LIBRARY_PATH is required; the built-in default path
         was removed. Created using: claude-sonnet-5-5-v5.5-date: 081126

Every database connection opens the .enl file with SQLite's mode=ro URI flag,
so a write attempt fails at the driver level rather than relying on this code
never issuing one. Linked files are opened for reading only.

Every tool checks up front that the library file can actually be opened.
EndNote holds an exclusive OS-level lock on a .enl file while it is open in
the application, which otherwise surfaces as an opaque driver error. That
check turns it into a clear, actionable message returned to the caller
instead. This server never tries to close EndNote itself.
"""
import os
import sqlite3
import urllib.parse
from pathlib import Path

from mcp.server.mcpserver import MCPServer

LIBRARY_PATH = os.environ.get("ENDNOTE_LIBRARY_PATH")
if not LIBRARY_PATH:
    raise SystemExit("ENDNOTE_LIBRARY_PATH is not set. Register the server with "
                     "-e ENDNOTE_LIBRARY_PATH=<path to the .enl file>.")

REF_FIELDS = [
    "id", "author", "year", "title", "abstract", "keywords", "url", "notes",
    "reference_type", "secondary_title", "volume", "number", "pages",
    "publisher", "isbn",
]

# Output key -> refs column, where the key differs from the column name.
# The DOI lives in EndNote's "Electronic Resource Number" field, not in url.
# Values are returned as stored: bare 10.x, https://doi.org/ links, doi:
# prefixes and non-DOI text all occur, so callers must normalise.
REF_COLUMNS = {"doi": "electronic_resource_number"}
REF_FIELDS.append("doi")

mcp = MCPServer("endnote")


class LibraryLockedError(RuntimeError):
    """The library file could not be opened, most likely because EndNote has it open."""


def _ro_connect(path: str) -> sqlite3.Connection:
    """Open the library read-only, failing fast with a clear message if it is locked."""
    uri = "file:" + urllib.parse.quote(path) + "?mode=ro"
    con = None
    try:
        con = sqlite3.connect(uri, uri=True)
        con.execute("select 1")
    except sqlite3.OperationalError as exc:
        if con is not None:
            con.close()
        raise LibraryLockedError(
            f"Cannot open the EndNote library at '{path}': {exc}. This library is "
            "most likely open in the EndNote application, which holds an exclusive "
            "lock on the file while it is open. Close the library in EndNote, then retry."
        ) from exc
    return con


def _pdf_root(library_path: str) -> Path:
    return Path(library_path).with_suffix(".Data") / "PDF"


@mcp.tool()
def search_references(query: str, limit: int = 20) -> list[dict]:
    """Search title, author, abstract, and keywords for a substring. Read-only."""
    try:
        con = _ro_connect(LIBRARY_PATH)
    except LibraryLockedError as exc:
        return [{"error": str(exc)}]
    try:
        cur = con.cursor()
        like = f"%{query}%"
        cur.execute(
            "select id, author, year, title, substr(abstract, 1, 300) as abstract_preview, url, "
            "electronic_resource_number as doi "
            "from refs where title like ? or author like ? or abstract like ? or keywords like ? "
            "order by year desc limit ?",
            (like, like, like, like, limit),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        con.close()


@mcp.tool()
def get_reference(ref_id: int) -> dict:
    """Return the full bibliographic record for one reference id. Read-only."""
    try:
        con = _ro_connect(LIBRARY_PATH)
    except LibraryLockedError as exc:
        return {"error": str(exc)}
    try:
        cur = con.cursor()
        cols = ",".join(f"{REF_COLUMNS[f]} as {f}" if f in REF_COLUMNS else f for f in REF_FIELDS)
        cur.execute(f"select {cols} from refs where id = ?", (ref_id,))
        row = cur.fetchone()
        if row is None:
            return {"error": f"no reference with id {ref_id}"}
        return dict(zip(REF_FIELDS, row))
    finally:
        con.close()


def _list_linked_files(ref_id: int) -> list[dict]:
    """Raises LibraryLockedError if the library cannot be opened; callers must catch it."""
    con = _ro_connect(LIBRARY_PATH)
    try:
        cur = con.cursor()
        cur.execute("select file_path, file_type, file_pos from file_res where refs_id = ?", (ref_id,))
        rows = cur.fetchall()
    finally:
        con.close()
    pdf_root = _pdf_root(LIBRARY_PATH)
    results = []
    for file_path, file_type, file_pos in rows:
        resolved = pdf_root / file_path
        results.append({
            "file_path": file_path,
            "file_type": file_type,
            "file_pos": file_pos,
            "resolved_path": str(resolved),
            "exists": resolved.exists(),
        })
    return results


@mcp.tool()
def list_linked_files(ref_id: int) -> list[dict]:
    """List linked file attachments recorded for a reference id. Read-only."""
    try:
        return _list_linked_files(ref_id)
    except LibraryLockedError as exc:
        return [{"error": str(exc)}]


@mcp.tool()
def read_linked_file_text(ref_id: int, file_index: int = 0, max_chars: int = 20000) -> dict:
    """Extract text from one of a reference's linked files (e.g. a PDF), read-only."""
    try:
        files = _list_linked_files(ref_id)
    except LibraryLockedError as exc:
        return {"error": str(exc)}
    if not files:
        return {"error": f"no linked files for reference id {ref_id}"}
    if file_index >= len(files):
        return {"error": f"file_index {file_index} out of range (0..{len(files) - 1})"}
    target = files[file_index]
    if not target["exists"]:
        return {"error": f"linked file not found on disk: {target['resolved_path']}"}
    path = target["resolved_path"]
    if path.lower().endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(path)
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    else:
        text = Path(path).read_text(errors="replace")
    return {
        "file_path": target["file_path"],
        "text": text[:max_chars],
        "truncated": len(text) > max_chars,
    }


if __name__ == "__main__":
    mcp.run()
