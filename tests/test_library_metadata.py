r"""Tests of the library-metadata scripts (skills/library-metadata/scripts/) on the synthetic library, without network.

Created using: $\text {Created using: }\ claude-opus-5-5-\text{v}5.5-\text {date: }231126$

Every service (arXiv, CrossRef, DataCite, OpenAlex) is replaced with recorded responses, and a test fails if a call
reaches the network. Tests that read PDF text need pypdf or pymupdf and are skipped without them.
"""
import contextlib
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
SICI = "10.1175/1520-0442(1993)006<0886:ETBOAA>2.0.CO;2"

ARTICLE = {"type": "journal-article", "title": ["A new paper on\n tidal <sub>flats</sub>"], "DOI": "10.9999/new.1",
           "author": [{"family": "Omega", "given": "Pat Q."}], "issued": {"date-parts": [[2015]]},
           "container-title": ["Journal of Tests"], "volume": "3", "issue": "2", "page": "1-9", "publisher": "Test Press"}
CHAPTER = {"type": "book-chapter", "title": ["4 Entropy in a box"], "DOI": "10.9999/ch.4",
           "author": [{"family": "Gamma", "given": "Dora"}], "issued": {"date-parts": [[None]]},
           "container-title": ["Series of Tests", "Book of Tests"], "publisher": "Test Press"}
DATACITE = {"doi": "10.5281/zenodo.123", "titles": [{"title": "A zenodo paper on dunes"}], "publicationYear": 2020,
            "creators": [{"familyName": "Sigma", "givenName": "Ray"}], "publisher": "Zenodo",
            "types": {"resourceTypeGeneral": "Text"}}
DATASET = {**DATACITE, "doi": "10.5281/zenodo.999", "titles": [{"title": "Dune heights"}],
           "types": {"resourceTypeGeneral": "Dataset"}}
ARXIV = {"author": "Alpha, Ann", "year": "2001", "title": "Heat transport in a model ocean", "secondary_title": "arXiv preprint",
         "volume": "", "number": "", "pages": "arXiv:2508.09353", "electronic_resource_number": "10.48550/arXiv.2508.09353",
         "publisher": "", "record_type": "preprint (arXiv)", "source": "arXiv"}
TYPES = {"journal-article": 0, "book-chapter": 7, "_evidence": "entries 1 and 2"}


@contextlib.contextmanager
def offline(crossref=None, datacite=None, openalex_work=None, arxiv=None, openalex=None, pdf_text=None):
    """Replace every service with recorded responses ({doi or id: record}); block the network."""
    def blocked(*a, **k):
        raise AssertionError(f"network call in a test: {a}")
    patches = [mock.patch.object(lm, "http_get", blocked),
               mock.patch.object(lm, "crossref", lambda d: (crossref or {}).get(lm.norm_doi(d))),
               mock.patch.object(lm, "datacite", lambda d: (datacite or {}).get(lm.norm_doi(d))),
               mock.patch.object(lm, "openalex_work", lambda d: (openalex_work or {}).get(lm.norm_doi(d))),
               mock.patch.object(lm, "arxiv", lambda i: (arxiv or {}).get(i)),
               mock.patch.object(lm, "openalex", lambda *a, **k: openalex or [])]
    if pdf_text is not None:
        patches.append(mock.patch.object(lm, "pdf_text", lambda *a, **k: pdf_text))
    with contextlib.ExitStack() as st:
        for p in patches:
            st.enter_context(p)
        yield


class Matching(unittest.TestCase):
    def test_check_pdf(self):
        f = {"author": "Alpha, Ann", "title": "Heat transport in a model ocean", "year": "2001"}
        self.assertTrue(lm.check_pdf("Heat transport in a model ocean by Ann Alpha", f, (2000, 2008))[0])
        ok, _, why = lm.check_pdf("Heat transport in a model ocean by Ann Beta", f)
        self.assertFalse(ok)
        self.assertIn("first author not found on the pages read", why)
        self.assertIn("title words not found on the pages read", lm.check_pdf("Alpha on something else", f)[2])
        self.assertIn("record year outside the window", lm.check_pdf("Heat transport model ocean Alpha", f, (2005, 2010))[2])

    def test_fields_from_crossref_clean_titles_and_keep_the_doi(self):
        a = lm.fields_from_crossref({**ARTICLE, "title": ["Rising CO<sub>2</sub> and\n tidal flats"], "DOI": SICI})
        self.assertEqual((a["title"], a["author"], a["year"], a["secondary_title"]),
                         ("Rising CO2 and tidal flats", "Omega, Pat Q.", "2015", "Journal of Tests"))
        self.assertEqual(a["electronic_resource_number"], SICI)
        self.assertEqual(a["source"], "CrossRef")
        c = lm.fields_from_crossref(CHAPTER)
        self.assertEqual((c["title"], c["secondary_title"], c["year"]), ("Entropy in a box", "Book of Tests", ""))

    def test_doi_forms(self):
        self.assertEqual(lm.norm_doi(" https://doi.org/" + SICI), SICI.lower())
        self.assertEqual(lm.doi_text("doi:" + SICI), SICI)
        self.assertEqual(lm.arxiv_id_from_doi("10.48550/ARXIV.2508.09353"), "2508.09353")
        self.assertIsNone(lm.arxiv_id_from_doi("10.5281/zenodo.123"))

    def test_record_for_doi_searches_widely_in_order(self):
        with offline(datacite={"10.5281/zenodo.123": DATACITE}):
            f, searched = lm.record_for_doi("10.5281/zenodo.123")
        self.assertEqual((f["source"], f["author"], f["year"], f["record_type"]), ("DataCite", "Sigma, Ray", "2020", "text"))
        self.assertEqual(searched, ["CrossRef by DOI", "DataCite by DOI"])
        with offline(arxiv={"2508.09353": ARXIV}):
            f, searched = lm.record_for_doi("10.48550/arXiv.2508.09353")
        self.assertEqual((f["source"], searched), ("arXiv", ["arXiv by DOI"]))
        work = {"doi": "https://doi.org/10.1/x", "title": "An OpenAlex work", "publication_year": 2019, "type": "article",
                "authorships": [{"author": {"display_name": "Kim Lee"}}], "biblio": {"first_page": "1", "last_page": "5"}}
        with offline(openalex_work={"10.1/x": work}):
            f, searched = lm.record_for_doi("10.1/x")
        self.assertEqual((f["source"], f["author"], f["pages"], f["electronic_resource_number"]), ("OpenAlex", "Lee, Kim", "1-5", "10.1/x"))
        with offline():
            f, searched = lm.record_for_doi("10.1/none")
        self.assertIsNone(f)
        self.assertEqual(searched, ["CrossRef by DOI", "DataCite by DOI", "OpenAlex by DOI"])

    def test_entry_type_and_type_check(self):
        self.assertEqual(lm.entry_type("book-chapter", TYPES), 7)
        self.assertEqual(lm.entry_type("journal-article", TYPES), 0)
        with self.assertRaises(SystemExit):
            lm.entry_type("book-chapter", {"journal-article": 0})
        self.assertFalse(lm.needs_type_check("journal-article"))
        self.assertTrue(lm.needs_type_check("dataset"))
        self.assertTrue(lm.needs_type_check("book"))
        self.assertTrue(lm.needs_type_check("peer-review"))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "proj"
        self.lib = fx.make_library(self.root)
        self.types = Path(self.tmp.name) / "types.json"
        self.types.write_text(json.dumps(TYPES), encoding="utf-8")
        self.el = lm.load_helper()

    def set_doi(self, ref_id, doi):
        self.el.update_refs(self.lib, self.root, {ref_id: {"electronic_resource_number": doi}})

    def log(self):
        f = self.root / "logs" / "changes.csv"
        if not f.exists():
            return []
        with open(f, encoding="utf-8-sig") as fh:
            return list(csv.DictReader(fh))

    def add(self, rows, **services):
        f = Path(self.tmp.name) / "list.csv"
        cols = ["doi", "record", "title", "pdf", "linked", "year_fallback", "note"]
        with open(f, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in cols})
        with offline(**services):
            code = add_mod.main(["--root", str(self.root), "--lib", str(self.lib), "--list", str(f), "--types",
                                 str(self.types), "--log", "logs"])
        with open(self.root / "logs" / "added.csv", encoding="utf-8-sig") as fh:
            return code, list(csv.DictReader(fh))


class Apply(Base):
    def run_apply(self, props):
        d = Path(self.tmp.name) / "props"
        d.mkdir(exist_ok=True)
        (d / "proposals.json").write_text(json.dumps(props), encoding="utf-8")
        with offline():
            return apply_mod.main(["--root", str(self.root), "--lib", str(self.lib), "--proposals", str(d), "--types",
                                   str(self.types), "--log", "logs"])

    def test_a_sici_doi_reaches_the_library_unchanged(self):
        props = {"3": {**lm.fields_from_crossref({**ARTICLE, "DOI": SICI, "title": ["Lapse rates without a file"],
                                                  "author": [{"family": "Delta", "given": "Eve"}]}), "_evidence": "ok"}}
        self.set_doi(3, "")
        self.assertEqual(self.run_apply(props), 0)
        self.assertEqual({r["id"]: r for r in self.el.read_refs(self.lib)}[3]["electronic_resource_number"], SICI)

    def test_an_equivalent_recorded_doi_keeps_its_form(self):
        self.set_doi(3, "https://doi.org/" + SICI)
        props = {"3": {**lm.fields_from_crossref({**ARTICLE, "DOI": SICI.lower(), "title": ["Lapse rates without a file"],
                                                  "author": [{"family": "Delta", "given": "Eve"}]}), "_evidence": "ok"}}
        self.run_apply(props)
        self.assertEqual({r["id"]: r for r in self.el.read_refs(self.lib)}[3]["electronic_resource_number"], "https://doi.org/" + SICI)
        self.assertFalse([r for r in self.log() if r["field"] == "electronic_resource_number" and r["ref_id"] == "3"])

    def test_a_different_recorded_doi_is_flagged_and_nothing_written(self):
        before = {r["id"]: r for r in self.el.read_refs(self.lib)}[1]
        props = {"1": {**lm.fields_from_crossref({**ARTICLE, "DOI": "10.9999/other"}), "_evidence": "ok"}}
        self.run_apply(props)
        self.assertEqual({r["id"]: r for r in self.el.read_refs(self.lib)}[1], before)
        self.assertIn("flagged", [r["after"] for r in self.log() if r["action"] == "check"][0])

    def test_only_changed_fields_are_logged_with_one_summary_row_per_entry(self):
        same = {"author": "Gamma, Dora", "year": "1999", "title": "A chapter on entropy", "secondary_title": "Book of Tests",
                "record_type": "book-chapter", "source": "CrossRef", "_evidence": "ok"}
        changed = {"author": "Delta, Eve", "year": "2010", "title": "Lapse rates without a file", "volume": "12",
                   "electronic_resource_number": "10.1234/test.3", "record_type": "journal-article", "source": "CrossRef",
                   "_evidence": "ok"}
        self.run_apply({"2": same, "3": changed})
        rows = self.log()
        fields = [(r["ref_id"], r["field"]) for r in rows if r["action"] == "update"]
        self.assertEqual(fields, [("3", "volume")])
        checks = {r["ref_id"]: r["after"] for r in rows if r["action"] == "check"}
        self.assertEqual(set(checks), {"2", "3"})
        self.assertIn("fields changed: 0", checks["2"])
        self.assertIn("fields changed: 1", checks["3"])

    def test_the_arxiv_year_rule_is_named(self):
        props = {"3": {**ARXIV, "author": "Delta, Eve", "title": "Lapse rates without a file", "year": "2011",
                       "electronic_resource_number": "", "_evidence": "ok"}}
        self.run_apply(props)
        self.assertEqual({r["id"]: r for r in self.el.read_refs(self.lib)}[3]["year"], "2010")
        self.assertIn("entry year 2010 kept (arXiv year 2011", [r["after"] for r in self.log() if r["action"] == "check"][0])


class Add(Base):
    def test_rows_without_a_pdf(self):
        code, log = self.add([{"doi": "10.9999/new.1", "note": "from record R1"},
                              {"doi": "10.9999/ch.4", "year_fallback": "2005", "note": "year of the book"},
                              {"doi": "10.1234/test.1"},
                              {"doi": "10.9999/new.1x", "title": "Something quite different"},
                              {"doi": "10.9999/none"},
                              {"doi": "10.5281/zenodo.123"},
                              {"doi": "10.5281/zenodo.999"}],
                             crossref={"10.9999/new.1": ARTICLE, "10.9999/ch.4": CHAPTER, "10.9999/new.1x": ARTICLE},
                             datacite={"10.5281/zenodo.123": DATACITE, "10.5281/zenodo.999": DATASET})
        self.assertEqual(code, 0)
        self.assertEqual([r["new_id"] for r in log], ["5", "6", "", "", "", "7", ""])
        self.assertIn("already in the library as entry 1", log[2]["check_or_reason"])
        self.assertIn("title similarity", log[3]["check_or_reason"])
        self.assertIn("searched: CrossRef by DOI, DataCite by DOI, OpenAlex by DOI", log[4]["check_or_reason"])
        self.assertIn("record type dataset (DataCite)", log[6]["check_or_reason"])
        refs = {r["id"]: r for r in self.el.read_refs(self.lib)}
        self.assertEqual((refs[5]["notes"], refs[5]["reference_type"]), ("from record R1", 0))
        self.assertEqual((refs[6]["reference_type"], refs[6]["year"], refs[6]["secondary_title"]), (7, "2005", "Book of Tests"))
        self.assertEqual((refs[7]["author"], refs[7]["electronic_resource_number"]), ("Sigma, Ray", "10.5281/zenodo.123"))
        self.assertIn("year_fallback", log[1]["check_or_reason"])
        self.assertTrue(any(r["source"].startswith("DataCite 10.5281/zenodo.123") for r in self.log()))

    def test_a_doi_recorded_with_a_prefix_is_a_duplicate(self):
        self.set_doi(3, "https://doi.org/10.9999/NEW.1")
        code, log = self.add([{"doi": "10.9999/new.1"}], crossref={"10.9999/new.1": ARTICLE})
        self.assertIn("already in the library as entry 3", log[0]["check_or_reason"])

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
                             crossref={"10.9999/new.1": ARTICLE, "10.9999/new.2": other, "10.9999/new.3": third})
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
            with offline():
                code = add_mod.main(["--root", str(self.root), "--lib", str(self.lib), "--list", str(f), "--types",
                                     str(self.types), "--log", "logs"])
        finally:
            holder.rollback()
            holder.close()
        self.assertEqual(code, 1)


class Lookup(Base):
    TEXT = "Heat transport in a model ocean\nAnn Alpha and Carl Beta\n" + " ".join(FILLER)
    RECORD = {**ARTICLE, "DOI": "10.1234/test.1", "title": ["Heat transport in a model ocean"],
              "author": [{"family": "Alpha", "given": "Ann"}], "issued": {"date-parts": [[2001]]}}

    def run_lookup(self, ids, **services):
        out = Path(self.tmp.name) / "out"
        with offline(pdf_text=self.TEXT, **services):
            code = lookup_mod.main(["--root", str(self.root), "--lib", str(self.lib), "--out", str(out), "--ids", ids])
        self.assertEqual(code, 0)
        with open(out / "proposals.csv", encoding="utf-8-sig") as fh:
            rows = {r["ref_id"]: r for r in csv.DictReader(fh)}
        return rows, json.loads((out / "proposals.json").read_text(encoding="utf-8"))

    def test_verified_and_flagged(self):
        rows, props = self.run_lookup("1,3", crossref={"10.1234/test.1": self.RECORD})
        self.assertEqual(rows["1"]["status"], "verified")
        self.assertEqual(rows["1"]["searched"], "CrossRef by DOI")
        self.assertEqual(rows["3"]["status"], "flag")
        self.assertIn("no linked PDF", rows["3"]["reasons"])
        self.assertEqual(list(props), ["1"])
        self.assertEqual(self.el.read_refs(self.lib)[0]["title"], "Heat transport in a model ocean")

    def test_an_arxiv_doi_is_verified_from_arxiv_with_the_year_noted(self):
        self.set_doi(1, "10.48550/arXiv.2508.09353")
        self.el.update_refs(self.lib, self.root, {1: {"year": "2002"}})
        rows, props = self.run_lookup("1", arxiv={"2508.09353": ARXIV})
        self.assertEqual((rows["1"]["status"], rows["1"]["record_source"], rows["1"]["searched"]), ("verified", "arXiv", "arXiv by DOI"))
        self.assertIn("arXiv year 2001, entry year 2002; apply.py keeps the entry year", rows["1"]["notes"])

    def test_an_unknown_doi_goes_on_to_the_title_search_and_names_the_sources(self):
        self.set_doi(1, "10.5281/zenodo.404")
        rows, _ = self.run_lookup("1")
        self.assertEqual(rows["1"]["status"], "flag")
        self.assertIn("no record found (searched: CrossRef by DOI, DataCite by DOI, OpenAlex by DOI, OpenAlex by title)",
                      rows["1"]["reasons"])
        self.assertNotIn("arXiv", rows["1"]["reasons"])

    def test_a_record_found_by_title_with_another_doi_is_flagged(self):
        self.set_doi(1, "10.5281/zenodo.404")
        cand = [{"doi": "https://doi.org/10.1234/real", "title": "Heat transport in a model ocean"}]
        rows, props = self.run_lookup("1", openalex=cand, crossref={"10.1234/real": {**self.RECORD, "DOI": "10.1234/real"}})
        self.assertEqual(rows["1"]["status"], "flag")
        self.assertIn("has DOI 10.1234/real; the entry holds 10.5281/zenodo.404", rows["1"]["reasons"])
        self.assertEqual(props, {})

    def test_duplicates_flag_active_entries_and_note_trashed_ones(self):
        self.set_doi(4, "https://doi.org/10.1234/TEST.1")
        rows, _ = self.run_lookup("1", crossref={"10.1234/test.1": self.RECORD})
        self.assertEqual(rows["1"]["status"], "verified")
        self.assertIn("a copy with the same DOI is in the trash (entry 4)", rows["1"]["notes"])
        self.set_doi(3, "10.1234/test.1")
        rows, _ = self.run_lookup("1", crossref={"10.1234/test.1": self.RECORD})
        self.assertEqual(rows["1"]["status"], "flag")
        self.assertIn("active entry 3 holds the same DOI", rows["1"]["reasons"])


class Helper(Base):
    def test_unchanged_fields_are_not_written_stamped_or_logged(self):
        stamp = lambda: self.el.connect(self.lib).execute("select value from misc where code=22 and subcode=0").fetchone()[0]
        before = stamp()
        rows = self.el.update_refs(self.lib, self.root, {1: {"title": "Heat transport in a model ocean", "year": "2001"}},
                                   log_dir=self.root / "logs")
        self.assertEqual((rows, stamp(), self.log()), ([], before, []))
        self.assertFalse(self.el.backup_root(self.lib).exists())
        rows = self.el.update_refs(self.lib, self.root, {1: {"title": "Heat transport in a model ocean", "year": "2002"}},
                                   log_dir=self.root / "logs")
        self.assertEqual([r["field"] for r in rows], ["year"])
        self.assertEqual([r["field"] for r in self.log()], ["year"])


if __name__ == "__main__":
    unittest.main()
