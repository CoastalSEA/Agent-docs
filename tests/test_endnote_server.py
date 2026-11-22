r"""Tests of mcp/endnote/endnote_server.py on the synthetic library of tests/endnote_fixture.py.

Created using: $\text {Created using: }\ claude-opus-5-5-\text{v}5.5-\text {date: }211126$

The server needs the packages mcp and pypdf; the tests are skipped when they are not importable (as in CI).
The tool functions are called directly; no MCP session is started.
"""
import importlib.util
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import endnote_fixture as fx  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "mcp" / "endnote" / "endnote_server.py"
HAVE = importlib.util.find_spec("mcp") is not None and importlib.util.find_spec("pypdf") is not None


@unittest.skipUnless(HAVE, "the server packages mcp and pypdf are not importable")
class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.lib = fx.make_library(Path(cls.tmp.name))
        os.environ["ENDNOTE_LIBRARY_PATH"] = str(cls.lib)
        spec = importlib.util.spec_from_file_location("endnote_server_under_test", SERVER)
        cls.srv = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.srv)
        cls.srv.LIBRARY_PATH = str(cls.lib)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("ENDNOTE_LIBRARY_PATH", None)
        cls.tmp.cleanup()

    def test_search_leaves_out_the_trash_unless_asked(self):
        hits = self.srv.search_references("Heat transport")
        self.assertEqual([h["id"] for h in hits], [1])
        hits = self.srv.search_references("Heat transport", include_trash=True)
        self.assertEqual(sorted(h["id"] for h in hits), [1, 4])

    def test_exact_keyword_filter(self):
        self.assertEqual([h["id"] for h in self.srv.search_references(keyword="read:full")], [1])
        self.assertEqual(self.srv.search_references(keyword="read:f"), [])
        self.assertEqual([h["id"] for h in self.srv.search_references(keyword="*Ocean")], [1])

    def test_get_reference_gives_the_type_name_files_and_trash_flag(self):
        rec = self.srv.get_reference(2)
        self.assertEqual((rec["reference_type"], rec["reference_type_name"]), (7, "Book Section"))
        self.assertEqual(rec["files"], ["2222222222/Gamma1999_chapter.pdf"])
        self.assertFalse(rec["in_trash"])
        self.assertTrue(self.srv.get_reference(4)["in_trash"])

    def test_search_by_file_name(self):
        hits = self.srv.search_by_file_name("Alpha2001")
        self.assertEqual([(h["id"], h["file_path"]) for h in hits], [(1, "1111111111/Alpha2001_heat-transport.pdf")])

    def test_text_with_a_page_range_and_a_pdf_without_text(self):
        r = self.srv.read_linked_file_text(1, first_page=1, last_page=1)
        self.assertIn("Heat transport", r["text"])
        r = self.srv.read_linked_file_text(2)
        self.assertTrue(r["no_text_layer"])
        self.assertIn("OCR", r["message"])

    def test_a_locked_library_gives_the_per_library_message(self):
        holder = sqlite3.connect(str(self.lib), timeout=1)
        holder.execute("begin exclusive")
        try:
            r = self.srv.search_references("Heat")
        finally:
            holder.rollback()
            holder.close()
        self.assertIn("lock is per library", r[0]["error"])


if __name__ == "__main__":
    unittest.main()
