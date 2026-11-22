r"""A synthetic EndNote 20 library for the tests of scripts/endnote_lib.py and the EndNote server.

Created using: $\text {Created using: }\ claude-opus-5-5-\text{v}5.5-\text {date: }211126$

Inputs:  a folder (a temporary project root).
Outputs: <root>/sources/references/Test Library.enl and Test Library.Data/ (sdb/sdb.eni, sdb/pdb.eni, PDF/), built
         with the table definitions and triggers of a real EndNote 20 library (refs, refs_ord, ref_props, ret_watch,
         tag_members, file_res, misc, and a terms table with the collation ENCI_Base). Invented records only:
         id 1 journal article with keywords and a PDF with text; id 2 book section with a PDF without text;
         id 3 journal article without a PDF; id 4 a journal article in the trash. sdb.eni is a copy of the .enl file.
"""
import shutil
import sqlite3
from pathlib import Path

COLUMNS = ("reference_type", "author", "year", "title", "secondary_title", "volume", "number", "pages", "publisher",
           "keywords", "abstract", "notes", "url", "electronic_resource_number", "accession_number", "database_provider",
           "place_published", "date", "secondary_author", "isbn")

DDL = [
    "CREATE TABLE refs(id INTEGER PRIMARY KEY AUTOINCREMENT,trash_state INTEGER NOT NULL DEFAULT 0,"
    "reference_type INTEGER NOT NULL DEFAULT 0," + ",".join(f'{c} TEXT NOT NULL DEFAULT ""' for c in COLUMNS[1:])
    + ",added_to_library INTEGER NOT NULL DEFAULT 0,record_last_updated INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE refs_ord(ro_trash_state INTEGER, ro_key_2 TEXT COLLATE ENCIN_Base, ro_key_3 TEXT COLLATE ENCIN_Base, "
    "ro_id INTEGER PRIMARY KEY)",
    "CREATE INDEX refs_ord_keys_index ON refs_ord(ro_trash_state, ro_key_2, ro_key_3, ro_id)",
    "CREATE TABLE ref_props (refs_id INTEGER PRIMARY KEY, rec_stamp INTEGER NOT NULL DEFAULT 0 )",
    "CREATE TABLE ret_watch (refs_id INTEGER PRIMARY KEY, retwatch_status INTEGER NOT NULL DEFAULT 0, clean_doi TEXT NOT "
    "NULL COLLATE NOCASE DEFAULT '', clean_version INTEGER NOT NULL DEFAULT 1)",
    "CREATE VIRTUAL TABLE tag_members USING fts5(tag_ids, tokenize = 'ascii', detail=none)",
    "CREATE TABLE file_res (refs_id INTEGER NOT NULL, file_path TEXT NOT NULL DEFAULT '', file_type INTEGER NOT NULL, "
    "file_pos INTEGER NOT NULL)",
    "CREATE UNIQUE INDEX fileres_path_index ON file_res(file_path) WHERE file_type = 1 OR file_type = 4",
    "CREATE UNIQUE INDEX fileres_refsidpos_index ON file_res (refs_id, file_pos)",
    "CREATE TABLE misc( code INTEGER UNSIGNED NOT NULL, subcode INTEGER UNSIGNED NOT NULL, value BLOB NOT NULL, "
    "PRIMARY KEY (code, subcode))",
    "CREATE TABLE terms (term_id INTEGER PRIMARY KEY, term TEXT COLLATE ENCI_Base)",
    "CREATE INDEX terms_index ON terms(term)",
    "CREATE TRIGGER refs__ref_props_AI AFTER INSERT ON refs BEGIN INSERT INTO ref_props (refs_id) VALUES (new.id); END",
    "CREATE TRIGGER refs__ref_props_AD AFTER DELETE ON refs BEGIN DELETE FROM ref_props WHERE refs_id = old.id; END",
    "CREATE TRIGGER refs__refs_ord_AI AFTER INSERT ON refs BEGIN INSERT INTO refs_ord (ro_trash_state, ro_key_2, ro_key_3, "
    "ro_id) VALUES (new.trash_state, EN_MAKE_SORT_KEY(new.author,2,12), EN_MAKE_SORT_KEY(new.year,3,12), new.id); END",
    "CREATE TRIGGER refs__refs_ord_AU AFTER UPDATE ON refs BEGIN DELETE FROM refs_ord WHERE ro_id = old.id; INSERT INTO "
    "refs_ord (ro_trash_state, ro_key_2, ro_key_3, ro_id) VALUES (new.trash_state, EN_MAKE_SORT_KEY(new.author,2,12), "
    "EN_MAKE_SORT_KEY(new.year,3,12), new.id); END",
    "CREATE TRIGGER refs__refs_ord_AD AFTER DELETE ON refs BEGIN DELETE FROM refs_ord WHERE ro_id = old.id; END",
    "CREATE TRIGGER refs__ret_watch_AI AFTER INSERT ON refs BEGIN INSERT INTO ret_watch (refs_id) VALUES (new.id); END",
    "CREATE TRIGGER refs__ret_watch_AU AFTER UPDATE ON refs BEGIN UPDATE ret_watch SET retwatch_status = 0, clean_doi = '' "
    "WHERE (refs_id = new.id) AND (old.electronic_resource_number != new.electronic_resource_number OR "
    "old.accession_number != new.accession_number OR old.database_provider != new.database_provider); END",
    "CREATE TRIGGER refs__ret_watch_AD AFTER DELETE ON refs BEGIN DELETE FROM ret_watch WHERE refs_id = old.id; END",
    "CREATE TRIGGER refs__tag_members_AI AFTER INSERT ON refs BEGIN INSERT INTO tag_members (rowid, tag_ids) VALUES "
    "(new.id, ' '); END",
    "CREATE TRIGGER refs__tag_members_AD AFTER DELETE ON refs BEGIN DELETE FROM tag_members WHERE rowid = old.id; END",
]

RECORDS = [
    {"reference_type": 0, "author": "Alpha, Ann B.\rBeta, Carl", "year": "2001", "title": "Heat transport in a model ocean",
     "secondary_title": "Journal of Tests", "keywords": "*Ocean\rread:full", "electronic_resource_number": "10.1234/test.1"},
    {"reference_type": 7, "author": "Gamma, Dora", "year": "1999", "title": "A chapter on entropy",
     "secondary_title": "Book of Tests"},
    {"reference_type": 0, "author": "Delta, Eve", "year": "2010", "title": "Lapse rates without a file",
     "electronic_resource_number": "10.1234/test.3"},
    {"reference_type": 0, "author": "Alpha, Ann B.", "year": "2001", "title": "Heat transport in a model ocean",
     "trash_state": 1},
]
PDFS = {1: ("1111111111/Alpha2001_heat-transport.pdf", ["Heat transport in a model ocean", "Ann Alpha and Carl Beta"]),
        2: ("2222222222/Gamma1999_chapter.pdf", None)}


def make_pdf(path, lines, font_size=9):
    """A minimal one-page PDF whose text is the given lines (ASCII only); lines None gives a page without text."""
    def esc(s):
        return s.replace(chr(92), chr(92) * 2).replace("(", chr(92) + "(").replace(")", chr(92) + ")")
    content = ("" if lines is None else
               f"BT /F1 {font_size} Tf {font_size + 4} TL 60 740 Td\n" + "".join(f"({esc(ln)}) Tj T*\n" for ln in lines) + "ET")
    objects = ["<< /Type /Catalog /Pages 2 0 R >>",
               "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
               f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode("ascii")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii")
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode("ascii")
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(out)


def _sort_key(value, column, mode):
    if column != 2:
        return value or ""
    key = ""
    for a in (value or "").split("\r"):
        last, _, first = a.partition(",")
        key += last.strip().upper() + " " + "".join(t[0].upper() for t in first.replace(".", " ").split()).ljust(3) + " "
    return key[:255]


def make_library(root, name="Test Library"):
    """Build the library under <root>/sources/references/ and return the path of the .enl file."""
    base = Path(root) / "sources" / "references"
    data = base / f"{name}.Data"
    (data / "sdb").mkdir(parents=True)
    enl = base / f"{name}.enl"
    con = sqlite3.connect(enl)
    for n in ("ENCI_Base", "ENCIN_Base"):
        con.create_collation(n, lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
    con.create_function("EN_MAKE_SORT_KEY", 3, _sort_key)
    for stmt in DDL:
        con.execute(stmt)
    con.execute("INSERT INTO misc VALUES (22, 0, ?), (22, 1, ?)", (b"10", b"10"))
    con.execute("INSERT INTO terms (term) VALUES ('Ocean'), ('entropy')")
    for i, rec in enumerate(RECORDS, 1):
        cols = list(rec)
        con.execute(f"INSERT INTO refs ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", [rec[c] for c in cols])
        con.execute("UPDATE ref_props SET rec_stamp=? WHERE refs_id=?", (i, i))
    for ref_id, (rel, lines) in PDFS.items():
        make_pdf(data / "PDF" / rel, lines)
        con.execute("INSERT INTO file_res (refs_id, file_path, file_type, file_pos) VALUES (?, ?, 1, 0)", (ref_id, rel))
    con.commit()
    con.close()
    shutil.copy2(enl, data / "sdb" / "sdb.eni")
    (data / "sdb" / "pdb.eni").write_bytes(b"")
    return enl
