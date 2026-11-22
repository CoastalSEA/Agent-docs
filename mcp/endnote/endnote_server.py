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
Changed: 2026-11-21. Entries in the trash are left out unless include_trash is set;
         search_references takes an exact keyword filter; get_reference returns the
         entry type name and the linked files; search_by_file_name finds entries by
         the name of a linked file; read_linked_file_text takes a page range and says
         when a PDF has no text layer. One registration serves one library: a project
         library is served by a second registration (see README.md).
         Created using: claude-opus-5-5-v5.5-date: 211126

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

# Entry type names for the internal integers, as observed in a project library of EndNote 20 on 211126
# (one entry of each kind checked). The integers differ from those of EndNote XML export. Other integers
# are returned without a name.
TYPE_NAMES = {0: "Journal Article", 1: "Book", 2: "Thesis", 7: "Book Section", 10: "Report"}

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
            "most likely open in the EndNote application, which locks the file of each "
            "open library (the lock is per library: other libraries stay readable). A "
            "library open in EndNote cannot be read. Close it in EndNote, then retry."
        ) from exc
    return con


def _pdf_root(library_path: str) -> Path:
    return Path(library_path).with_suffix(".Data") / "PDF"


def _keywords(value: str) -> list[str]:
    return [k.strip() for k in (value or "").split("\r") if k.strip()]


@mcp.tool()
def search_references(query: str = "", limit: int = 20, keyword: str = "",
                      include_trash: bool = False) -> list[dict]:
    """Search title, author, abstract, and keywords for a substring. keyword keeps only entries
    holding that exact keyword (for example read:full). Entries in the trash are left out unless
    include_trash is set. Read-only."""
    try:
        con = _ro_connect(LIBRARY_PATH)
    except LibraryLockedError as exc:
        return [{"error": str(exc)}]
    try:
        cur = con.cursor()
        like = f"%{query}%"
        trash = "" if include_trash else "trash_state = 0 and "
        cur.execute(
            "select id, author, year, title, substr(abstract, 1, 300) as abstract_preview, url, "
            "electronic_resource_number as doi, keywords, trash_state "
            f"from refs where {trash}(title like ? or author like ? or abstract like ? or keywords like ?) "
            "order by year desc",
            (like, like, like, like),
        )
        cols = [d[0] for d in cur.description]
        out = []
        for row in cur.fetchall():
            rec = dict(zip(cols, row))
            if keyword and keyword.strip() not in _keywords(rec["keywords"]):
                continue
            rec.pop("keywords")
            if not include_trash:
                rec.pop("trash_state")
            out.append(rec)
            if len(out) >= limit:
                break
        return out
    finally:
        con.close()


@mcp.tool()
def search_by_file_name(name: str, limit: int = 20, include_trash: bool = False) -> list[dict]:
    """Find entries whose linked file path contains name (older notes cite papers by file name). Read-only."""
    try:
        con = _ro_connect(LIBRARY_PATH)
    except LibraryLockedError as exc:
        return [{"error": str(exc)}]
    try:
        trash = "" if include_trash else "and r.trash_state = 0 "
        cur = con.execute(
            "select r.id, r.author, r.year, r.title, f.file_path from refs r join file_res f on f.refs_id = r.id "
            f"where f.file_path like ? {trash}order by r.id limit ?", (f"%{name}%", limit))
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
        cur.execute(f"select {cols}, trash_state from refs where id = ?", (ref_id,))
        row = cur.fetchone()
        if row is None:
            return {"error": f"no reference with id {ref_id}"}
        rec = dict(zip(REF_FIELDS + ["trash_state"], row))
        rec["in_trash"] = bool(rec.pop("trash_state"))
        rec["reference_type_name"] = TYPE_NAMES.get(rec["reference_type"])
    finally:
        con.close()
    try:
        rec["files"] = [f["file_path"] for f in _list_linked_files(ref_id)]
    except LibraryLockedError as exc:
        rec["files"] = {"error": str(exc)}
    return rec


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
def read_linked_file_text(ref_id: int, file_index: int = 0, max_chars: int = 20000,
                          first_page: int = 1, last_page: int = 0) -> dict:
    """Extract text from one of a reference's linked files (e.g. a PDF), read-only.
    first_page and last_page (1-based, 0 for the last page) limit the pages read from a PDF."""
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
        pages = reader.pages[max(first_page, 1) - 1:(last_page or len(reader.pages))]
        text = "\n".join((page.extract_text() or "") for page in pages)
        if not text.strip():
            return {"file_path": target["file_path"], "text": "", "truncated": False, "pages": len(reader.pages),
                    "no_text_layer": True,
                    "message": "The PDF has no text layer in the pages read (probably a scan). Use the OCR "
                               "step of the library-metadata skill; this server does no OCR."}
    else:
        text = Path(path).read_text(errors="replace")
    return {
        "file_path": target["file_path"],
        "text": text[:max_chars],
        "truncated": len(text) > max_chars,
    }


if __name__ == "__main__":
    mcp.run()
