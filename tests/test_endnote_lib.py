r"""Tests of scripts/endnote_lib.py on a synthetic EndNote library (tests/endnote_fixture.py). No real library is used.

Created using: $\text {Created using: }\ claude-opus-5-5-\text{v}5.5-\text {date: }211126$
"""
import csv
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import endnote_fixture as fx  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "endnote_lib.py"
spec = importlib.util.spec_from_file_location("endnote_lib", SCRIPT)
el = importlib.util.module_from_spec(spec)
spec.loader.exec_module(el)


def rows(path, sql, args=()):
    c = el.connect(path)
    try:
        return c.execute(sql, args).fetchall()
    finally:
        c.close()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "proj"
        self.lib = fx.make_library(self.root)
        self.enl, self.data, self.sdb = el.paths(self.lib)

    def cli(self, *args, script=SCRIPT):
        return subprocess.run([sys.executable, "-I", str(script), *args, "--root", str(self.root)],
                              capture_output=True, text=True, encoding="utf-8")


class Reading(Base):
    def test_read_connection_refuses_a_write(self):
        c = el.connect(self.enl)
        with self.assertRaises(sqlite3.OperationalError):
            c.execute("update refs set title='x' where id=1")
        c.close()

    def test_read_refs_skips_the_trashed_entry(self):
        self.assertEqual([r["id"] for r in el.read_refs(self.lib)], [1, 2, 3])
        self.assertEqual(len(el.read_refs(self.lib, include_trash=True)), 4)
        self.assertEqual(el.read_refs(self.lib)[0]["files"], ["1111111111/Alpha2001_heat-transport.pdf"])

    def test_check_is_ok_and_types_list_the_types_in_use(self):
        self.assertEqual(el.check(self.lib), "ok")
        self.assertEqual([t for t, _, _ in el.types(self.lib)], [0, 7])

    def test_list_filters_on_an_exact_keyword(self):
        r = self.cli("list", "--lib", str(self.enl), "--keyword", "read:full")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(r.stdout.strip().splitlines()), 1)
        r = self.cli("list", "--lib", str(self.enl), "--keyword", "read:f")
        self.assertEqual(r.stdout.strip(), "")


class Guards(Base):
    def test_a_library_outside_sources_references_is_refused(self):
        other = Path(self.tmp.name) / "elsewhere"
        lib = fx.make_library(other)
        moved = Path(self.tmp.name) / "independent"
        shutil.move(str(lib.parent), str(moved))
        with self.assertRaisesRegex(el.LibraryError, "only a project library"):
            el.update_refs(moved / lib.name, self.root, {1: {"title": "x"}})

    def test_a_protected_path_is_refused_even_under_sources_references(self):
        config = Path(self.tmp.name) / "config"
        (config / "scripts").mkdir(parents=True)
        (config / "rules").mkdir()
        shutil.copy2(SCRIPT, config / "scripts" / SCRIPT.name)
        (config / "rules" / "protected-paths.txt").write_text(f"# test\n{self.enl}\n", encoding="utf-8")
        j = Path(self.tmp.name) / "u.json"
        j.write_text(json.dumps({"1": {"title": "x"}}), encoding="utf-8")
        r = self.cli("update", "--lib", str(self.enl), "--json", str(j), script=config / "scripts" / SCRIPT.name)
        self.assertEqual(r.returncode, 1)
        self.assertIn("protected path", r.stderr)
        self.assertEqual(rows(self.enl, "select title from refs where id=1")[0][0], "Heat transport in a model ocean")

    def test_a_locked_library_is_refused_with_a_message_naming_endnote(self):
        holder = sqlite3.connect(str(self.enl), timeout=1)
        holder.execute("begin exclusive")
        try:
            with self.assertRaisesRegex(el.LibraryError, "open in EndNote"):
                el.update_refs(self.lib, self.root, {1: {"title": "x"}})
        finally:
            holder.rollback()
            holder.close()
        self.assertFalse(el.backup_root(self.lib).exists())

    def test_a_column_outside_the_allow_list_is_refused(self):
        with self.assertRaisesRegex(el.LibraryError, "not editable"):
            el.update_refs(self.lib, self.root, {1: {"trash_state": 1}})

    def test_an_entry_type_not_in_use_needs_to_be_allowed(self):
        with self.assertRaisesRegex(el.LibraryError, "entry type 5"):
            el.update_refs(self.lib, self.root, {1: {"reference_type": 5}})
        el.update_refs(self.lib, self.root, {1: {"reference_type": 5}}, allow_types=[5])
        self.assertEqual(rows(self.enl, "select reference_type from refs where id=1")[0][0], 5)

    def test_no_function_deletes_an_entry(self):
        text = SCRIPT.read_text(encoding="utf-8").lower()
        self.assertNotRegex(text, r"delete\s+from")
        self.assertNotRegex(text, r"set\s+trash_state")


class Writing(Base):
    def test_update_changes_only_the_named_entry_and_raises_stamp_and_counter(self):
        before = {r["id"]: r for r in el.read_refs(self.lib, include_trash=True)}
        log = el.update_refs(self.lib, self.root, {3: {"author": "Zeta, Anna\rAlpha, B. C.", "year": "1998"}},
                             source="test")
        after = {r["id"]: r for r in el.read_refs(self.lib, include_trash=True)}
        self.assertEqual({r["field"] for r in log}, {"author", "year"})
        for i in before:
            if i != 3:
                self.assertEqual(before[i], after[i])
        for p in (self.enl, self.sdb):
            self.assertEqual(rows(p, "select ro_key_2, ro_key_3 from refs_ord where ro_id=3")[0], ("ZETA A   ALPHA BC  ", "1998"))
            self.assertEqual(rows(p, "select rec_stamp from ref_props where refs_id=3")[0][0], 11)
            self.assertEqual(rows(p, "select value from misc where code=22 order by subcode"), [(b"11",), (b"11",)])
        self.assertEqual(el.check(self.lib), "ok")

    def test_both_files_agree_after_a_write(self):
        el.update_refs(self.lib, self.root, {2: {"title": "A new title"}})
        q = "select id, title, record_last_updated from refs order by id"
        self.assertEqual(rows(self.enl, q), rows(self.sdb, q))

    def test_add_reference_with_and_without_a_pdf(self):
        pdf = Path(self.tmp.name) / "Epsilon 2020 (a test).pdf"
        fx.make_pdf(pdf, ["A test paper"])
        rid = el.add_reference(self.lib, self.root, {"title": "A test paper", "author": "Epsilon, Fay", "year": "2020",
                                                     "reference_type": 0}, pdf_path=pdf)
        refs = {r["id"]: r for r in el.read_refs(self.lib)}
        self.assertEqual(rid, 5)
        self.assertTrue((self.data / "PDF" / refs[rid]["files"][0]).is_file())
        self.assertTrue(refs[rid]["files"][0].endswith("/Epsilon2020atest.pdf"))
        self.assertTrue(pdf.is_file())
        for p in (self.enl, self.sdb):
            self.assertEqual(rows(p, "select ro_key_2 from refs_ord where ro_id=5")[0][0], "EPSILON F   ")
            self.assertEqual(rows(p, "select rec_stamp from ref_props where refs_id=5")[0][0], 11)
        rid2 = el.add_reference(self.lib, self.root, {"title": "No file", "year": "2021"})
        self.assertEqual(el.read_refs(self.lib)[-1]["files"], [])
        self.assertEqual(rid2, 6)
        self.assertEqual(el.check(self.lib), "ok")

    def test_keywords_are_appended_without_duplicates(self):
        el.add_keywords(self.lib, self.root, {1: ["read:full", "proj:ocean", "proj:ocean"], 3: ["read:none"]},
                        ["read:", "proj:"])
        kw = dict(rows(self.enl, "select id, keywords from refs where id in (1, 3)"))
        self.assertEqual(kw[1], "*Ocean\rread:full\rproj:ocean")
        self.assertEqual(kw[3], "read:none")
        with self.assertRaisesRegex(el.LibraryError, "outside the vocabulary"):
            el.add_keywords(self.lib, self.root, {1: ["topic:x"]}, ["read:", "proj:"])
        with self.assertRaisesRegex(el.LibraryError, "may not remove keywords"):
            el.update_refs(self.lib, self.root, {1: {"keywords": "read:full"}})
        el.update_refs(self.lib, self.root, {3: {"keywords": "read:none" + chr(13) + "proj:extra"}})

    def test_a_failure_in_sdb_leaves_both_files_and_removes_only_the_new_pdf_folder(self):
        c = sqlite3.connect(self.sdb)
        c.execute("CREATE TRIGGER fail BEFORE INSERT ON file_res BEGIN SELECT RAISE(ABORT, 'injected'); END")
        c.commit()
        c.close()
        digests = (el._digest(self.enl), el._digest(self.sdb))
        folders = sorted(p.name for p in (self.data / "PDF").iterdir())
        pdf = Path(self.tmp.name) / "x.pdf"
        fx.make_pdf(pdf, ["x"])
        with self.assertRaisesRegex(el.LibraryError, "rolled back"):
            el.add_reference(self.lib, self.root, {"title": "x"}, pdf_path=pdf)
        self.assertEqual((el._digest(self.enl), el._digest(self.sdb)), digests)
        self.assertEqual(sorted(p.name for p in (self.data / "PDF").iterdir()), folders)

    def test_a_failed_update_in_sdb_leaves_the_enl_file_unchanged(self):
        c = sqlite3.connect(self.sdb)
        c.execute("CREATE TRIGGER fail BEFORE UPDATE ON refs WHEN new.title = 'FAIL' BEGIN SELECT RAISE(ABORT, 'injected'); END")
        c.commit()
        c.close()
        with self.assertRaises(el.LibraryError):
            el.update_refs(self.lib, self.root, {1: {"title": "FAIL"}})
        self.assertEqual(rows(self.enl, "select title from refs where id=1")[0][0], "Heat transport in a model ocean")

    def test_backup_holds_both_files_and_restore_brings_them_back(self):
        folder = el.backup(self.lib)
        self.assertTrue((folder / self.enl.name).is_file() and (folder / "sdb" / "sdb.eni").is_file())
        el.update_refs(self.lib, self.root, {1: {"title": "Changed"}})
        el.restore(self.lib, self.root, folder.name)
        for p in (self.enl, self.sdb):
            self.assertEqual(rows(p, "select title from refs where id=1")[0][0], "Heat transport in a model ocean")
        self.assertGreaterEqual(len(list(el.backup_root(self.lib).iterdir())), 3)


class CommandLine(Base):
    def test_update_with_a_log_and_info(self):
        j = Path(self.tmp.name) / "u.json"
        j.write_text(json.dumps({"3": {"volume": "12"}}), encoding="utf-8")
        r = self.cli("update", "--lib", "sources/references/Test Library.enl", "--json", str(j), "--log", "logs/t",
                     "--source", "CrossRef")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.root / "logs" / "t" / "changes.csv", encoding="utf-8-sig") as fh:
            log = list(csv.DictReader(fh))
        self.assertEqual((log[0]["ref_id"], log[0]["field"], log[0]["after"], log[0]["source"]), ("3", "volume", "12", "CrossRef"))
        r = self.cli("info", "--lib", str(self.enl))
        self.assertIn("active: 3", r.stdout)
        self.assertIn("backups: 1", r.stdout)

    def test_tag_from_a_csv(self):
        f = Path(self.tmp.name) / "k.csv"
        f.write_text("id,keywords\n2,read:partial; proj:entropy\n", encoding="utf-8")
        r = self.cli("tag", "--lib", str(self.enl), "--csv", str(f), "--prefixes", "read:,proj:")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(rows(self.enl, "select keywords from refs where id=2")[0][0], "read:partial\rproj:entropy")

    def test_a_missing_library_gives_exit_2(self):
        r = self.cli("info", "--lib", "sources/references/None.enl")
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
