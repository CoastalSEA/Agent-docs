r"""Read and maintain a project EndNote library under `sources/references/` of a project.

Created using: $\text {Created using: }\ claude-opus-5-5-\text{v}5.5-\text {date: }211126$

A project library is a project source: agents add and correct its entries through this helper. Every other
library (an independent library, such as a personal one) is never written: a write is refused unless the library
lies inside `<root>/sources/references/`, and always refused for a path listed in the protected-paths file
(`<claude folder>/rules/protected-paths.txt`, read as `hook_guard.py` reads it).

Usage: endnote_lib.py <command> --lib <library .enl> [options] [--root <project root>]
       endnote_lib.py --version
  --root may stand anywhere in the command line; the default is the current folder. --lib is relative to the root.
  info                        counts (active, in the trash), agreement of the two files, journal modes, lock state,
                              backups and their total size
  list [--keyword K]          active entries: id, year, first author, title (K: exact keyword)
  types                       entry type integers in use, with a count and one example title each
  check                       integrity of the tables this helper writes, in both files, and their agreement
  backup                      copy the .enl file and Data/sdb/ to a timestamped backup folder
  restore <tag>               restore a backup (the present state is backed up first)
  update --json F             F: {"<id>": {"<column>": value}}
  add --json F [--pdf P]      F: {"<column>": value}; P: a PDF to copy into the library
  tag --csv F --prefixes P    F: columns id, keywords (separated by "; "); P: allowed prefixes, e.g. "read:,proj:"
  Write commands (restore, update, add, tag) take --source TEXT (the source of the values, logged),
  --log FOLDER (append each change to FOLDER/changes.csv) and --allow-type N (an entry type not yet in the library).
Inputs:  the library file and its <name>.Data/ folder; the JSON or CSV file of a write command.
Outputs: a report on standard output; writes change the library, make a backup in
         <library folder>/library-backups/<library name>/<DDMMYY-HHMMSS>/ and, with --log, append to changes.csv.
Exit:    0 on success; 1 for a refused write, a locked library or a failed check; 2 for an unusable path or input.
Version: see VERSION; `--version` prints it.

Rules kept by the code:
- Reads open the database read-only (mode=ro). read_refs returns active entries only (trash_state = 0).
- Gate: immediately before each write, the library must open for reading (assert_not_open). EndNote locks the
  file while the library is open, and the read then fails. When it fails the write is refused with a message
  naming EndNote; the caller stops and tells the user. There is no retry.
- One commit: Data/sdb/sdb.eni is attached to the connection of the .enl file and both are written in one
  transaction, which SQLite commits atomically when neither file is in WAL mode (refused otherwise). The integrity
  check runs inside the transaction, before the commit. On any failure the transaction is rolled back; if either
  file then differs from the backup, both are restored from it and the message says so. A PDF folder created by
  the failed call is removed; nothing else is removed.
- Editable columns come from EDITABLE. No function deletes an entry or removes a keyword (an update of keywords
  must keep every keyword already there), trash_state is never written, a PDF is
  copied (never moved or overwritten). Keywords already present are kept; new ones are appended after a
  carriage return. An entry type must already be in use in the library unless allowed by name.

Facts about the EndNote library format that this helper depends on, as used by EndNote 2025.4.1 (build 20759), the
version on which they were observed (TESTED_ENDNOTE; another version may differ). Evidence: (F) the synthetic library
of tests/test_endnote_lib.py, for the behaviour of this helper; (R) a round trip on a real project library on
211126 (entries written by the earlier project copy of this helper, then opened in EndNote and checked by the
user: entries, DOI links and a keyword search were correct), for the behaviour of EndNote.
1. The .enl file and Data/sdb/sdb.eni are SQLite databases with the same reference tables; the .enl file also
   holds the groups; Data/sdb/pdb.eni (the PDF text index) is not written. (R)
2. refs_ord, ref_props, ret_watch and tag_members are kept by triggers on refs, which call EN_MAKE_SORT_KEY;
   a stand-in is registered (author key: surname in upper case for ASCII letters, initials padded to three,
   one space, per author, cut at 255; year key: the year). Names with letters outside ASCII may sort differently
   from EndNote until Library, Recover Library is run. (F, R)
3. The collations ENCI_Base and ENCIN_Base get stand-ins; a whole-database integrity check then reports the term
   indexes as damaged, so only the tables written here are checked. (F, R)
4. A changed record gets a new stamp: ref_props.rec_stamp and the counter in misc (code 22, subcodes 0 and 1,
   bytes of the number) go up by one per record; record_last_updated and added_to_library are Unix seconds. (R)
5. Authors and keywords are one string, entries separated by a carriage return. (R)
6. Entry types are internal integers that differ from EndNote XML export numbers; the mapping is taken from the
   target library (command `types`). (R)
7. Attachments: file_res(refs_id, file_path, file_type=1, file_pos), file_path relative to <name>.Data/PDF/ as
   <ten digits>/<file name>, the name cut to 50 characters with .pdf. (R)
8. The term lists (table terms) and the PDF index are not updated: new authors, journals and keywords may not
   show in the term lists until Library, Recover Library is run. Searches use refs and are correct. (R)
9. While a library is open in EndNote, a read-only open of its .enl file fails; the lock is per library file. (R)
   sdb.eni stays readable while the library is open (observed 211126), so the check on the .enl file is the one
   that detects an open library. Not yet tested: EndNote opening a library during a write.
10. An entry moved to the trash keeps its row with trash_state = 1. (R)
"""
import csv
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import urllib.parse
from pathlib import Path

VERSION = "1.0"
TESTED_ENDNOTE = "EndNote 2025.4.1 (build 20759)"
EDITABLE = ("reference_type", "author", "year", "title", "secondary_title", "volume", "number", "pages", "publisher",
            "electronic_resource_number", "url", "keywords", "abstract", "notes", "place_published", "date",
            "secondary_author", "isbn")
CHECKED_TABLES = ("refs", "refs_ord", "ref_props", "file_res", "misc", "ret_watch")
SCHEMAS = ("main", "sdb")


class LibraryError(RuntimeError):
    """A refused write or an unusable library; the message says why."""


# ---------- paths and guards ----------

def paths(lib):
    """(.enl file, <name>.Data folder, Data/sdb/sdb.eni) of a library."""
    enl = Path(lib).resolve()
    data = enl.with_name(enl.stem + ".Data")
    return enl, data, data / "sdb" / "sdb.eni"


def _norm(p):
    return os.path.normcase(str(Path(p).resolve())).replace("\\", "/").rstrip("/")


def _inside(p, base):
    p, base = _norm(p), _norm(base)
    return p == base or p.startswith(base + "/")


def protected_paths():
    """Paths listed in <claude folder>/rules/protected-paths.txt (the folder above this script's folder)."""
    f = Path(__file__).resolve().parent.parent / "rules" / "protected-paths.txt"
    if not f.is_file():
        return []
    return [ln.strip() for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]


def check_location(lib, root):
    """Refuse a write to any library that is not a project library of this root, or that is protected."""
    enl, data, sdb = paths(lib)
    base = Path(root).resolve() / "sources" / "references"
    for p in protected_paths():
        if _inside(enl, p) or _inside(data, p):
            raise LibraryError(f"{enl} is a protected path (protected-paths.txt): it is never written")
    if not _inside(enl, base):
        raise LibraryError(f"{enl} is not inside {base}: only a project library under sources/references/ "
                           "is written; an independent library is read only")
    if enl.suffix.lower() != ".enl" or not enl.is_file() or not sdb.is_file():
        raise LibraryError(f"{enl} is not an EndNote library with {sdb}")


def _uri(path, mode):
    return "file:" + urllib.parse.quote(Path(path).resolve().as_posix(), safe="/:") + f"?mode={mode}"


def connect(path, write=False):
    """SQLite connection with the stand-ins for the EndNote collations and sort-key function; read-only unless write."""
    c = sqlite3.connect(_uri(path, "rw" if write else "ro"), uri=True, timeout=1, isolation_level=None)
    for name in ("ENCI_Base", "ENCIN_Base"):
        c.create_collation(name, lambda a, b: (a.casefold() > b.casefold()) - (a.casefold() < b.casefold()))
    c.create_function("EN_MAKE_SORT_KEY", 3, sort_key)
    return c


def assert_not_open(path):
    """Refuse when the file cannot be opened for reading: EndNote locks the library file while it is open."""
    try:
        c = sqlite3.connect(_uri(path, "ro"), uri=True, timeout=1)
        try:
            c.execute("select count(*) from sqlite_master").fetchone()
        finally:
            c.close()
    except sqlite3.OperationalError as e:
        raise LibraryError(f"{Path(path).name} cannot be opened ({e}): the library is probably open in EndNote. "
                           "Close it in EndNote; nothing was written") from e


def _journal_mode(path):
    c = connect(path)
    try:
        return c.execute("pragma journal_mode").fetchone()[0].lower()
    finally:
        c.close()


# ---------- reading ----------

def author_sort_key(authors):
    """Sort key of refs_ord.ro_key_2: per author the surname in upper case (ASCII letters), initials padded to three."""
    def up(s):
        return "".join(ch.upper() if "a" <= ch <= "z" else ch for ch in s)

    def initials(first):
        return "".join("-".join(p[0].upper() for p in tok.split("-") if p)
                       for tok in re.split(r"[\s.]+", first.strip()) if tok)
    key = ""
    for a in (authors or "").split("\r"):
        if a.strip():
            last, _, first = a.partition(",")
            key += up(last.strip()) + " " + initials(first).ljust(3) + " "
    return key[:255]


def sort_key(value, column, mode):
    """Stand-in for EN_MAKE_SORT_KEY: column 2 is the author key, other columns the value itself."""
    return author_sort_key(value or "") if column == 2 else (value or "")


def read_refs(lib, include_trash=False):
    """References as dictionaries (read-only), each with its linked file paths under 'files'."""
    enl, _, _ = paths(lib)
    c = connect(enl)
    try:
        c.row_factory = sqlite3.Row
        where = "" if include_trash else " where trash_state=0"
        refs = [dict(r) for r in c.execute(f"select * from refs{where} order by id")]
        files = {}
        for r in c.execute("select refs_id, file_path from file_res order by refs_id, file_pos"):
            files.setdefault(r[0], []).append(r[1])
    finally:
        c.close()
    for r in refs:
        r["files"] = files.get(r["id"], [])
    return refs


def keywords_of(value):
    return [k for k in (value or "").split("\r") if k.strip()]


def types(lib):
    """[(type integer, count, example title)] for every entry type in use, active entries first."""
    enl, _, _ = paths(lib)
    c = connect(enl)
    try:
        return c.execute("select reference_type, count(*), (select title from refs r2 where r2.reference_type="
                         "r.reference_type order by trash_state, id limit 1) from refs r group by reference_type "
                         "order by reference_type").fetchall()
    finally:
        c.close()


def _summary(c, schema):
    return c.execute(f"select count(*), coalesce(max(id), 0), coalesce(sum(trash_state), 0) from {schema}.refs").fetchone()


def _check_schema(c, schema):
    for t in CHECKED_TABLES:
        r = c.execute(f"pragma {schema}.integrity_check({t})").fetchone()[0]
        if r != "ok":
            return f"{schema}.{t}: {r}"
    return "ok"


def check(lib):
    """'ok', or the first problem: integrity of the written tables in both files, then their agreement."""
    enl, _, sdb = paths(lib)
    c = connect(enl)
    try:
        c.execute("attach database ? as sdb", (_uri(sdb, "ro"),))
        for s in SCHEMAS:
            r = _check_schema(c, s)
            if r != "ok":
                return r
        a, b = _summary(c, "main"), _summary(c, "sdb")
        if a != b:
            return f"the .enl file and sdb.eni disagree (records, last id, in trash): {a} and {b}"
        return "ok"
    finally:
        c.close()


# ---------- backup and restore ----------

def backup_root(lib):
    enl, _, _ = paths(lib)
    return enl.parent / "library-backups" / enl.stem


def backup(lib):
    """Copy the .enl file and Data/sdb/ to library-backups/<name>/<DDMMYY-HHMMSS>/ and return that folder."""
    enl, data, _ = paths(lib)
    stamp = time.strftime("%d%m%y-%H%M%S")
    dest, n = backup_root(lib) / stamp, 1
    while dest.exists():
        n += 1
        dest = backup_root(lib) / f"{stamp}-{n}"
    (dest / "sdb").mkdir(parents=True)
    shutil.copy2(enl, dest / enl.name)
    for f in (data / "sdb").iterdir():
        if f.is_file():
            shutil.copy2(f, dest / "sdb" / f.name)
    return dest


def _copy_back(lib, folder):
    enl, data, _ = paths(lib)
    shutil.copy2(folder / enl.name, enl)
    for f in (folder / "sdb").iterdir():
        shutil.copy2(f, data / "sdb" / f.name)


def _digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def restore(lib, root, tag, log_dir=None, source=""):
    """Restore the backup <tag>; the present state is backed up first. Returns the folder of that new backup."""
    check_location(lib, root)
    folder = backup_root(lib) / tag
    enl, _, sdb = paths(lib)
    if not (folder / enl.name).is_file():
        raise LibraryError(f"no backup {folder}")
    assert_not_open(enl)
    assert_not_open(sdb)
    before = backup(lib)
    _copy_back(lib, folder)
    _log(log_dir, enl, [{"action": "restore", "id": "", "field": "", "before": before.name, "after": tag}], source)
    return before


# ---------- writing ----------

def _log(log_dir, enl, rows, source):
    if not log_dir or not rows:
        return
    d = Path(log_dir)
    d.mkdir(parents=True, exist_ok=True)
    f = d / "changes.csv"
    new = not f.exists()
    with open(f, "a", newline="", encoding="utf-8-sig" if new else "utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["time", "library", "action", "ref_id", "field", "before", "after", "source"])
        now = time.strftime("%d%m%y %H:%M:%S")
        for r in rows:
            w.writerow([now, enl.name, r["action"], r["id"], r["field"], str(r["before"]).replace("\r", " | "),
                        str(r["after"]).replace("\r", " | "), r.get("source") or source])


def _check_fields(fields, known_types, allow_types):
    bad = set(fields) - set(EDITABLE)
    if bad:
        raise LibraryError(f"columns not editable here: {sorted(bad)}")
    if "reference_type" in fields:
        t = int(fields["reference_type"])
        if t not in known_types and t not in set(allow_types or ()):
            raise LibraryError(f"entry type {t} is not in use in this library (command types); "
                               "allow it with --allow-type only with evidence of its meaning")


def _stamp(c, schema, ref_id):
    cur = int(c.execute(f"select value from {schema}.misc where code=22 and subcode=0").fetchone()[0])
    c.execute(f"update {schema}.ref_props set rec_stamp=? where refs_id=?", (cur + 1, ref_id))
    for sub in (0, 1):
        c.execute(f"update {schema}.misc set value=? where code=22 and subcode=?", (str(cur + 1).encode(), sub))


def _write(lib, root, work, log_dir=None, source="", pdf_folder=None):
    """Run work(c, schema, now) for both files in one transaction after the guards and a backup."""
    check_location(lib, root)
    enl, _, sdb = paths(lib)
    assert_not_open(enl)
    assert_not_open(sdb)
    for p in (enl, sdb):
        if _journal_mode(p) == "wal":
            raise LibraryError(f"{p.name} is in WAL mode, in which the two files cannot be committed together")
    folder = backup(lib)
    c = connect(enl, write=True)
    log, ok = [], False
    try:
        c.execute("attach database ? as sdb", (_uri(sdb, "rw"),))
        c.execute("begin immediate")
        for s in SCHEMAS:
            r = _check_schema(c, s)
            if r != "ok":
                raise LibraryError(f"integrity check failed before writing: {r}")
        if _summary(c, "main") != _summary(c, "sdb"):
            raise LibraryError("the .enl file and sdb.eni disagree before writing; run Library, Recover Library in EndNote")
        now = int(time.time())
        for s in SCHEMAS:
            rows = work(c, s, now)
            if s == "main":
                log = rows
        for s in SCHEMAS:
            r = _check_schema(c, s)
            if r != "ok":
                raise LibraryError(f"integrity check failed after writing: {r}")
        if _summary(c, "main") != _summary(c, "sdb"):
            raise LibraryError("the .enl file and sdb.eni disagree after writing")
        c.execute("commit")
        ok = True
    except Exception as e:
        try:
            c.execute("rollback")
        except sqlite3.Error:
            pass
        c.close()
        msg = f"write failed, rolled back ({e})"
        if _digest(enl) != _digest(folder / enl.name) or _digest(sdb) != _digest(folder / "sdb" / sdb.name):
            _copy_back(lib, folder)
            msg += f"; both files restored from {folder}"
        if pdf_folder is not None and pdf_folder.exists():
            shutil.rmtree(pdf_folder)
            msg += f"; removed the PDF folder created by this call ({pdf_folder.name})"
        raise LibraryError(msg) from e
    finally:
        if ok:
            c.close()
    _log(log_dir, enl, log, source)
    return log


def _guard(lib, root):
    """The location guard and the lock check on both files; run before any read that precedes a write."""
    check_location(lib, root)
    _, _, sdb = paths(lib)
    assert_not_open(paths(lib)[0])
    assert_not_open(sdb)


guard = _guard  # public name for callers that read before they write (the library-metadata scripts)


def _known_types(lib):
    return {t for t, _, _ in types(lib)}


def update_refs(lib, root, updates, log_dir=None, source="", allow_types=()):
    """updates: {ref_id: {column: value}}. Returns the change log [{action, id, field, before, after}]."""
    _guard(lib, root)
    updates = {int(k): dict(v) for k, v in updates.items()}
    sources = {i: f.pop("_source", "") for i, f in updates.items()}
    known = _known_types(lib)
    for fields in updates.values():
        _check_fields(fields, known, allow_types)

    def work(c, s, now):
        rows = []
        for ref_id, fields in updates.items():
            if not fields:
                continue
            cols = list(fields)
            cur = c.execute(f"select {','.join(cols)} from {s}.refs where id=?", (ref_id,)).fetchone()
            if cur is None:
                raise LibraryError(f"no entry {ref_id}")
            if "keywords" in fields:
                old = {k.strip() for k in keywords_of(cur[cols.index("keywords")])}
                lost = sorted(old - {k.strip() for k in keywords_of(fields["keywords"])})
                if lost:
                    raise LibraryError(f"an update may not remove keywords (entry {ref_id}: {lost}); the user edits "
                                       "keywords in EndNote")
            c.execute(f"update {s}.refs set {', '.join(k + '=?' for k in cols)}, record_last_updated=? where id=?",
                      list(fields.values()) + [now, ref_id])
            _stamp(c, s, ref_id)
            rows += [{"action": "update", "id": ref_id, "field": k, "before": b, "after": fields[k],
                      "source": sources.get(ref_id, "")} for k, b in zip(cols, cur)]
        return rows
    return _write(lib, root, work, log_dir, source)


def clean_name(name):
    return re.sub(r"[^A-Za-z0-9_.\-]", "", Path(name).stem)[:46] + ".pdf"


def add_reference(lib, root, fields, pdf_path=None, log_dir=None, source="", allow_types=()):
    """Add one entry, with an optional PDF copied into Data/PDF/<ten digits>/. Returns the new id."""
    _guard(lib, root)
    fields = dict(fields)
    _check_fields(fields, _known_types(lib), allow_types)
    _, data, _ = paths(lib)
    rel, folder = None, None
    if pdf_path:
        src = Path(pdf_path)
        if not src.is_file():
            raise LibraryError(f"no PDF {src}")
        n = int(time.time() * 1000) % 10**10
        while (data / "PDF" / f"{n:010d}").exists():
            n = (n + 1) % 10**10
        folder = data / "PDF" / f"{n:010d}"
        folder.mkdir(parents=True)
        rel = f"{folder.name}/{clean_name(src.name)}"
        shutil.copy2(src, data / "PDF" / rel)
    new = {}

    def work(c, s, now):
        cols = list(fields) + ["added_to_library", "record_last_updated"]
        vals = list(fields.values()) + [now, now]
        if s == "main":
            cur = c.execute(f"insert into main.refs ({','.join(cols)}) values ({','.join('?' * len(cols))})", vals)
            new["id"] = cur.lastrowid
        else:
            c.execute(f"insert into sdb.refs (id,{','.join(cols)}) values ({','.join('?' * (len(cols) + 1))})",
                      [new["id"]] + vals)
        _stamp(c, s, new["id"])
        if rel:
            c.execute(f"insert into {s}.file_res (refs_id, file_path, file_type, file_pos) values (?,?,1,0)",
                      (new["id"], rel))
        rows = [{"action": "add", "id": new["id"], "field": k, "before": "", "after": v} for k, v in fields.items()]
        if rel:
            rows.append({"action": "add", "id": new["id"], "field": "pdf", "before": str(pdf_path), "after": rel})
        return rows
    try:
        _write(lib, root, work, log_dir, source, pdf_folder=folder)
    except LibraryError:
        if folder is not None and folder.exists():
            shutil.rmtree(folder)
        raise
    return new["id"]


def add_keywords(lib, root, table, prefixes, log_dir=None, source=""):
    """table: {ref_id: [keyword, ...]}. Appends the keywords not yet present; every one must start with a prefix."""
    _guard(lib, root)
    prefixes = tuple(p for p in prefixes if p)
    if not prefixes:
        raise LibraryError("give the allowed keyword prefixes")
    for rid, kws in table.items():
        bad = [k for k in kws if not k.startswith(prefixes)]
        if bad:
            raise LibraryError(f"keywords outside the vocabulary {prefixes} for entry {rid}: {bad}")
    current = {r["id"]: r for r in read_refs(lib, include_trash=True)}
    updates = {}
    for rid, kws in table.items():
        rid = int(rid)
        if rid not in current:
            raise LibraryError(f"no entry {rid}")
        have = keywords_of(current[rid]["keywords"])
        seen = {k.strip().lstrip("*") for k in have}
        add = []
        for k in kws:
            if k not in seen:
                add.append(k)
                seen.add(k)
        if add:
            updates[rid] = {"keywords": "\r".join(have + add)}
    if not updates:
        return []
    return update_refs(lib, root, updates, log_dir, source)


def info(lib):
    enl, data, sdb = paths(lib)
    out = {"library": str(enl), "format_facts_observed_with": TESTED_ENDNOTE}
    for name, p in (("enl", enl), ("sdb", sdb)):
        try:
            assert_not_open(p)
            out[f"{name}_lock"] = "readable"
            out[f"{name}_journal_mode"] = _journal_mode(p)
        except LibraryError as e:
            out[f"{name}_lock"] = str(e)
    if out["enl_lock"] == "readable":
        refs = read_refs(lib, include_trash=True)
        out["active"] = sum(1 for r in refs if not r["trash_state"])
        out["in_trash"] = sum(1 for r in refs if r["trash_state"])
        out["check"] = check(lib) if out["sdb_lock"] == "readable" else "not run (sdb.eni locked)"
    b = backup_root(lib)
    folders = [p for p in b.iterdir() if p.is_dir()] if b.is_dir() else []
    out["backups"] = len(folders)
    out["backup_size_mb"] = round(sum(f.stat().st_size for p in folders for f in p.rglob("*") if f.is_file()) / 1e6, 1)
    return out


# ---------- command line ----------

def split_root(argv):
    root, rest, i = None, [], 0
    while i < len(argv):
        if argv[i] == "--root" and i + 1 < len(argv):
            root, i = argv[i + 1], i + 2
        elif argv[i].startswith("--root="):
            root, i = argv[i].split("=", 1)[1], i + 1
        else:
            rest.append(argv[i])
            i += 1
    return root, rest


def main(argv):
    import argparse
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    root_arg, rest = split_root(argv)
    ap = argparse.ArgumentParser(prog="endnote_lib.py", description="Read and maintain a project EndNote library.")
    ap.add_argument("--version", action="version", version=f"endnote_lib.py {VERSION}")
    ap.add_argument("command", choices=("info", "list", "types", "check", "backup", "restore", "update", "add", "tag"))
    ap.add_argument("tag_name", nargs="?", help="restore: the backup folder name")
    ap.add_argument("--lib", required=True)
    ap.add_argument("--json")
    ap.add_argument("--csv")
    ap.add_argument("--pdf")
    ap.add_argument("--prefixes", default="")
    ap.add_argument("--keyword")
    ap.add_argument("--source", default="")
    ap.add_argument("--log")
    ap.add_argument("--allow-type", type=int, action="append", default=[])
    a = ap.parse_args(rest)
    root = Path(root_arg).resolve() if root_arg else Path.cwd().resolve()
    lib = Path(a.lib) if Path(a.lib).is_absolute() else root / a.lib
    log = (Path(a.log) if Path(a.log).is_absolute() else root / a.log) if a.log else None
    if not paths(lib)[0].is_file():
        print(f"No library {lib}", file=sys.stderr)
        return 2
    try:
        if a.command == "info":
            for k, v in info(lib).items():
                print(f"{k}: {v}")
        elif a.command == "list":
            for r in read_refs(lib):
                if a.keyword and a.keyword not in [k.strip() for k in keywords_of(r["keywords"])]:
                    continue
                first = r["author"].split("\r")[0].split(",")[0]
                print(f"{r['id']}\t{r['year']}\t{first}\t{r['title']}")
        elif a.command == "types":
            for t, n, title in types(lib):
                print(f"{t}\t{n}\t{title}")
        elif a.command == "check":
            r = check(lib)
            print(r)
            return 0 if r == "ok" else 1
        elif a.command == "backup":
            check_location(lib, root)
            print(backup(lib))
        elif a.command == "restore":
            if not a.tag_name:
                print("restore needs the backup folder name", file=sys.stderr)
                return 2
            print(f"restored {a.tag_name}; the state before is in {restore(lib, root, a.tag_name, log, a.source)}")
        elif a.command in ("update", "add"):
            if not a.json:
                print(f"{a.command} needs --json", file=sys.stderr)
                return 2
            data = json.loads(Path(a.json).read_text(encoding="utf-8"))
            if a.command == "update":
                rows = update_refs(lib, root, data, log, a.source, a.allow_type)
                print(f"fields written: {len(rows)}")
            else:
                print(f"added entry {add_reference(lib, root, data, a.pdf, log, a.source, a.allow_type)}")
        elif a.command == "tag":
            if not a.csv:
                print("tag needs --csv", file=sys.stderr)
                return 2
            table = {}
            with open(a.csv, encoding="utf-8-sig") as fh:
                for r in csv.DictReader(fh):
                    table.setdefault(int(r["id"]), []).extend(k.strip() for k in r["keywords"].split(";") if k.strip())
            rows = add_keywords(lib, root, table, a.prefixes.split(","), log, a.source)
            print(f"entries changed: {len(rows)}")
    except LibraryError as e:
        print(f"Refused: {e}", file=sys.stderr)
        return 1
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"Unusable input: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
