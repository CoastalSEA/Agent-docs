r"""Tests of the library-metadata scripts (skills/library-metadata/scripts/) on the synthetic library, without network.

Created using: $\text {Created using: }\ claude-opus-5-5-\text{v}5.5-\text {date: }211126$

CrossRef and OpenAlex calls are replaced with canned records. Tests that read PDF text need pypdf or pymupdf and
are skipped without them.
"""
import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import endnote_fixture as fx  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skills" / "library-metadata" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import libmeta as lm  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(f"lm_{name}", SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


apply_mod, add_mod, lookup_mod = load("apply"), load("add"), load("lookup")
HAVE_PDF = bool(importlib.util.find_spec("pypdf") or importlib.util.find_spec("pymupdf"))
FILLER = ["The quick brown fox jumps over the lazy dog near the river bank today."] * 12

ARTICLE = {"type": "journal-article", "title": ["A new paper on\n tidal <sub>flats</sub>"], "DOI": "10.9999/new.1",
           "author": [{"family": "Omega", "given": "Pat Q."}], "issued": {"date-parts": [[2015]]},
           "container-title": ["Journal of Tests"], "volume": "3", "issue": "2", "page": "1-9", "publisher": "Test Press"}
CHAPTER = {"type": "book-chapter", "title": ["4 Entropy in a box"], "DOI": "10.9999/ch.4",
           "author": [{"family": "Gamma", "given": "Dora"}], "issued": {"date-parts": [[None]]},
           "container-title": ["Series of Tests", "Book of Tests"], "publisher": "Test Press"}
TYPES = {"journal-article": 0, "book-chapter": 7, "_evidence": "entries 1 and 2"}


class Matching(unittest.TestCase):
    def test_check_pdf(self):
        f = {"author": "Alpha, Ann", "title": "Heat transport in a model ocean", "year": "2001"}
        self.assertTrue(lm.check_pdf("Heat transport in a model ocean by Ann Alpha", f, (2000, 2008))[0])
        ok, _, why = lm.check_pdf("Heat transport in a model ocean by Ann Beta", f)
        self.assertFalse(ok)
        self.assertIn("first author not found on the pages read", why)
        self.assertIn("title words not found on the pages read", lm.check_pdf("Alpha on something else", f)[2])
        self.assertIn("record year outside the window", lm.check_pdf("Heat transport model ocean Alpha", f, (2005, 2010))[2])

    def test_fields_from_crossref(self):
        a = lm.fields_from_crossref(ARTICLE)
        self.assertEqual((a["title"], a["author"], a["year"], a["secondary_title"]),
                         ("A new paper on tidal flats", "Omega, Pat Q.", "2015", "Journal of Tests"))
        c = lm.fields_from_crossref(CHAPTER)
        self.assertEqual((c["title"], c["secondary_title"], c["year"]), ("Entropy in a box", "Book of Tests", ""))

    def test_entry_type_needs_the_types_file(self):
        self.assertEqual(lm.entry_type("book-chapter", TYPES), 7)
        self.assertEqual(lm.entry_type("journal-article", TYPES), 0)
        with self.assertRaises(SystemExit):
            lm.entry_type("book-chapter", {"journal-article": 0})


class Apply(unittest.TestCase):
    def test_rules(self):
        props = {"1": {**lm.fields_from_crossref(ARTICLE), "_evidence": "ok"},
                 "2": {"author": "Gamma, Dora", "year": "2001", "title": "A chapter", "record_type": "preprint (arXiv)",
                       "_evidence": "ok"},
                 "3": {**lm.fields_from_crossref(CHAPTER), "_evidence": "ok"}}
        current = {1: {"year": "2015"}, 2: {"year": "2000"}, 3: {"year": ""}}
        up = apply_mod.build_updates(props, current, TYPES, {"1": {"fields": {"pages": "1-19"}, "source": "PDF header"}})
        self.assertEqual(up[2]["year"], "2000")
        self.assertEqual(up[3]["reference_type"], 7)
        self.assertNotIn("year", up[3])
        self.assertEqual(up[1]["pages"], "1-19")
        self.assertIn("PDF header", up[1]["_source"])
        self.assertTrue(up[2]["_source"].startswith("arXiv"))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "proj"
        self.lib = fx.make_library(self.root)
        self.types = Path(self.tmp.name) / "types.json"
        self.types.write_text(json.dumps(TYPES), encoding="utf-8")
        self.el = lm.load_helper()

    def add(self, rows, records):
        f = Path(self.tmp.name) / "list.csv"
        cols = ["doi", "record", "title", "pdf", "linked", "year_fallback", "note"]
        with open(f, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in cols})
        with mock.patch.object(lm, "crossref", lambda doi: records.get(doi)):
            code = add_mod.main(["--root", str(self.root), "--lib", str(self.lib), "--list", str(f), "--types",
                                 str(self.types), "--log", "logs"])
        with open(self.root / "logs" / "added.csv", encoding="utf-8-sig") as fh:
            return code, list(csv.DictReader(fh))


class Add(Base):
    def test_rows_without_a_pdf(self):
        code, log = self.add([{"doi": "10.9999/new.1", "note": "from record R1"},
                              {"doi": "10.9999/ch.4", "year_fallback": "2005", "note": "year of the book"},
                              {"doi": "10.1234/test.1"},
                              {"doi": "10.9999/new.1x", "title": "Something quite different"},
                              {"doi": "10.9999/none"}],
                             {"10.9999/new.1": ARTICLE, "10.9999/ch.4": CHAPTER, "10.9999/new.1x": ARTICLE,
                              "10.1234/test.1": {**ARTICLE, "DOI": "10.1234/test.1", "title": ["Heat transport in a model ocean"]}})
        self.assertEqual(code, 0)
        self.assertEqual([r["new_id"] for r in log], ["5", "6", "", "", ""])
        self.assertIn("already in the library as entry 1", log[2]["check_or_reason"])
        self.assertIn("title similarity", log[3]["check_or_reason"])
        self.assertIn("CrossRef has no record", log[4]["check_or_reason"])
        refs = {r["id"]: r for r in self.el.read_refs(self.lib)}
        self.assertEqual((refs[5]["notes"], refs[5]["reference_type"]), ("from record R1", 0))
        self.assertEqual((refs[6]["reference_type"], refs[6]["year"], refs[6]["secondary_title"]), (7, "2005", "Book of Tests"))
        self.assertIn("year_fallback", log[1]["check_or_reason"])
        with open(self.root / "logs" / "changes.csv", encoding="utf-8-sig") as fh:
            self.assertTrue(any("CrossRef 10.9999/new.1" in r["source"] for r in csv.DictReader(fh)))

    @unittest.skipUnless(HAVE_PDF, "needs pypdf or pymupdf")
    def test_pdf_checks(self):
        good = Path(self.tmp.name) / "good.pdf"
        fx.make_pdf(good, ["A new paper on tidal flats", "Pat Omega"] + FILLER)
        scan = Path(self.tmp.name) / "scan.pdf"
        fx.make_pdf(scan, None)
        other = {**ARTICLE, "DOI": "10.9999/new.2", "title": ["A second paper on dunes"]}
        third = {**ARTICLE, "DOI": "10.9999/new.3", "title": ["A third paper on marshes"]}
        code, log = self.add([{"doi": "10.9999/new.1", "pdf": f"file:{good}"},
                              {"doi": "10.9999/new.2", "pdf": f"file:{scan}"},
                              {"doi": "10.9999/new.3", "pdf": f"file:{scan}", "linked": "yes"}],
                             {"10.9999/new.1": ARTICLE, "10.9999/new.2": other, "10.9999/new.3": third})
        self.assertEqual([r["new_id"] for r in log], ["5", "", "6"])
        self.assertIn("not linked", log[1]["check_or_reason"])
        self.assertIn("accepted: linked", log[2]["check_or_reason"])
        refs = {r["id"]: r for r in self.el.read_refs(self.lib)}
        self.assertTrue(refs[5]["files"][0].endswith("/Omega2015_a-new-paper-on-tidal-flats.pdf"))
        self.assertTrue(good.is_file())

    def test_a_locked_library_is_refused(self):
        import sqlite3
        holder = sqlite3.connect(str(self.lib), timeout=1)
        holder.execute("begin exclusive")
        try:
            f = Path(self.tmp.name) / "l.csv"
            f.write_text("doi\n10.9999/new.1\n", encoding="utf-8")
            code = add_mod.main(["--root", str(self.root), "--lib", str(self.lib), "--list", str(f), "--types",
                                 str(self.types), "--log", "logs"])
        finally:
            holder.rollback()
            holder.close()
        self.assertEqual(code, 1)


class Lookup(Base):
    def test_verified_and_flagged(self):
        record = {**ARTICLE, "DOI": "10.1234/test.1", "title": ["Heat transport in a model ocean"],
                  "author": [{"family": "Alpha", "given": "Ann"}], "issued": {"date-parts": [[2001]]}}
        text = "Heat transport in a model ocean\nAnn Alpha and Carl Beta\n" + " ".join(FILLER)
        out = Path(self.tmp.name) / "out"
        with mock.patch.object(lm, "crossref", lambda doi: record if doi == "10.1234/test.1" else None), \
                mock.patch.object(lm, "pdf_text", lambda *a, **k: text), \
                mock.patch.object(lm, "openalex", lambda *a, **k: []):
            code = lookup_mod.main(["--root", str(self.root), "--lib", str(self.lib), "--out", str(out), "--ids", "1,3"])
        self.assertEqual(code, 0)
        with open(out / "proposals.csv", encoding="utf-8-sig") as fh:
            rows = {r["ref_id"]: r for r in csv.DictReader(fh)}
        self.assertEqual(rows["1"]["status"], "verified")
        self.assertEqual(rows["3"]["status"], "flag")
        self.assertIn("no linked PDF", rows["3"]["reasons"])
        props = json.loads((out / "proposals.json").read_text(encoding="utf-8"))
        self.assertEqual(list(props), ["1"])
        self.assertEqual(self.el.read_refs(self.lib)[0]["title"], "Heat transport in a model ocean")


if __name__ == "__main__":
    unittest.main()
