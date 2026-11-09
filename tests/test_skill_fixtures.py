r"""Tests for the skill fixture runner (tests/skills/run_fixtures.py) that need no model calls.

Created using: $\text {Created using: }\ claude-sonnet-5-5-\text{v}5.5-\text {date: }091126$

The runner itself starts Claude Code sessions and is run by hand. These tests check what does not need a model:
the fixtures build what they say, the planted fault is really in the fixture, and each check passes on a good
result and fails on a result that has the planted problem.
"""
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "tests" / "skills" / "run_fixtures.py"
spec = importlib.util.spec_from_file_location("run_fixtures", RUNNER)
rf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rf)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "claude"
        self.home.mkdir()
        self.saved_home = rf.CLAUDE_HOME
        rf.CLAUDE_HOME = self.home
        self.addCleanup(setattr, rf, "CLAUDE_HOME", self.saved_home)
        self.work = Path(self.tmp.name) / "work"
        self.work.mkdir()


class Runner(unittest.TestCase):
    def test_version_list_and_unknown_fixture(self):
        r = subprocess.run([sys.executable, "-I", str(RUNNER), "--version"], capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), f"run_fixtures.py {rf.VERSION}")
        r = subprocess.run([sys.executable, "-I", str(RUNNER), "--list"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("project-disclosure", r.stdout)
        self.assertIn("analysis-adversary", r.stdout)
        r = subprocess.run([sys.executable, "-I", str(RUNNER), "nope"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_helpers(self):
        self.assertEqual(rf.project_key(Path.cwd()), rf.project_key(str(Path.cwd())))
        self.assertTrue(rf.has_date("held on 2 March 2026", "2026-03-02"))
        self.assertTrue(rf.has_date("02/03/2026", "2026-03-02"))
        self.assertFalse(rf.has_date("03/03/2026", "2026-03-02"))


class ProjectDisclosureFixture(Base):
    def setUp(self):
        super().setUp()
        self.fx = rf.ProjectDisclosure()
        self.root = self.fx.build(self.work)

    def write(self, text):
        folder = self.root / "outputs" / "project-disclosure-Alpha-091126-run1"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "run_info.txt").write_text("task: x", encoding="utf-8")
        (folder / "AI-DISCLOSURE.md").write_text(text, encoding="utf-8")

    GOOD = ("Sessions: Plot the decay curve (2026-03-02, claude-sonnet-5-5, permission mode default); log transform "
            "(2026-03-09, claude-opus-5-5, auto then default, analysis subfolder; Write notes.md attempted, refused); "
            "Summarise the repository layout (2026-03-16, permission mode MISSING for the subagent). A prompt held a "
            "secret and was redacted.")

    def results(self, reply="The run is pending review."):
        return {n: ok for n, ok, _ in self.fx.check(self.root, reply, self.fx.before)}

    def test_the_synthetic_logs_exist_with_the_planted_features(self):
        projects = self.home / "projects"
        folders = {p.name for p in projects.iterdir()}
        self.assertEqual(folders, {rf.project_key(self.root), rf.project_key(self.fx.sub), rf.project_key(self.fx.decoy)})
        logs = list((projects / rf.project_key(self.root)).glob("*.jsonl"))
        self.assertEqual(len(logs), 2)
        first = [json.loads(ln) for ln in logs[0].read_text(encoding="utf-8").splitlines()]
        self.assertEqual(first[0]["type"], "user")
        self.assertEqual(Path(first[0]["cwd"]), self.root)
        modes = {json.loads(ln).get("permissionMode") for f in (projects / rf.project_key(self.fx.sub)).glob("*.jsonl")
                 for ln in f.read_text(encoding="utf-8").splitlines()} - {None}
        self.assertEqual(modes, {"auto", "default"})
        self.assertTrue(list((projects / rf.project_key(self.root)).glob("*/subagents/agent-a1.jsonl")))
        self.assertTrue(list((projects / rf.project_key(self.root)).glob("*/subagents/agent-a1.meta.json")))
        self.assertEqual(sorted(self.fx.log_folders(self.root)), sorted(folders))

    def test_a_good_disclosure_passes_every_check(self):
        self.write(self.GOOD)
        results = self.results()
        self.assertTrue(all(results.values()), [n for n, ok in results.items() if not ok])

    def test_each_planted_problem_fails_its_check(self):
        cases = [
            (self.GOOD + " DECOYMARKER", self.fx.checks_listed[2]),
            (self.GOOD + " key " + self.fx.SECRET, self.fx.checks_listed[5]),
            (self.GOOD.replace("attempted", "done"), self.fx.checks_listed[6]),
            (self.GOOD + " A human stayed in the loop.", self.fx.checks_listed[8]),
            (self.GOOD.replace("claude-opus-5-5", "an Opus model"), self.fx.checks_listed[3]),
            (self.GOOD.replace("MISSING", "default"), self.fx.checks_listed[4]),
            (self.GOOD.replace("analysis", "work"), self.fx.checks_listed[7]),
        ]
        for text, check in cases:
            self.write(text)
            self.assertFalse(self.results()[check], check)

    def test_missing_file_extra_file_and_reply(self):
        self.assertFalse(self.results()[self.fx.checks_listed[0]])
        self.write(self.GOOD)
        (self.root / "outputs" / "project-disclosure-Alpha-091126-run1" / "helper.py").write_text("x", encoding="utf-8")
        self.assertFalse(self.results()[self.fx.checks_listed[0]])
        self.assertFalse(self.results("I accepted the run.")[self.fx.checks_listed[9]])

    def test_a_changed_project_file_is_caught(self):
        self.write(self.GOOD)
        (self.root / "data" / "decay.csv").write_text("changed", encoding="utf-8")
        self.assertFalse(self.results()[self.fx.checks_listed[10]])


class AnalysisAdversaryFixture(Base):
    def setUp(self):
        super().setUp()
        self.fx = rf.AnalysisAdversary()
        self.root = self.fx.build(self.work)

    def fit(self, log):
        rows = [ln.split(",") for ln in (self.root / "data" / "decay.csv").read_text(encoding="utf-8").splitlines()[1:]]
        t = [float(a) for a, _ in rows]
        y = [log(float(b)) for _, b in rows]
        n = len(t)
        mt, my = sum(t) / n, sum(y) / n
        return -sum((a - mt) * (b - my) for a, b in zip(t, y)) / sum((a - mt) ** 2 for a in t)

    def test_the_planted_fault_is_in_the_fixture(self):
        self.assertAlmostEqual(self.fit(math.log), 0.30, delta=0.01)
        self.assertAlmostEqual(self.fit(math.log10), 0.130, delta=0.005)
        out = subprocess.run([sys.executable, "-I", "code/fit_decay.py"], cwd=self.root, capture_output=True, text=True)
        self.assertIn("k = 0.130", out.stdout)

    def write(self, text):
        folder = self.root / "outputs" / "analysis-adversary-decay-rate-091126-run1"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "analysis-adversary-report.md").write_text(text, encoding="utf-8")

    GOOD = ("The reported k = 0.130 does not reproduce. An independent fit on the natural logarithm gives k = 0.301. "
            "The script fits log10(y), so its slope is smaller by the factor ln 10.")

    def results(self):
        return {n: ok for n, ok, _ in self.fx.check(self.root, "", self.fx.before)}

    def test_a_good_report_passes_and_each_fault_fails_its_check(self):
        self.write(self.GOOD)
        results = self.results()
        self.assertTrue(all(results.values()), [n for n, ok in results.items() if not ok])
        cases = [
            (self.GOOD.replace("0.301", "0.130"), self.fx.checks_listed[1]),
            ("The result reproduces: k = 0.301 matches.", self.fx.checks_listed[2]),
            (self.GOOD.replace("natural logarithm", "method").replace("log10(y)", "y").replace("ln 10", "ten"),
             self.fx.checks_listed[3]),
        ]
        for text, check in cases:
            self.write(text)
            self.assertFalse(self.results()[check], check)

    def test_no_report_fails_and_a_changed_file_is_caught(self):
        self.assertFalse(self.results()[self.fx.checks_listed[0]])
        self.write(self.GOOD)
        (self.root / "draft.md").write_text("edited", encoding="utf-8")
        self.assertFalse(self.results()[self.fx.checks_listed[5]])

    def test_running_the_script_under_review_is_detected(self):
        self.write(self.GOOD)
        self.assertTrue(self.results()[self.fx.checks_listed[4]])
        logs = self.home / "projects" / rf.project_key(self.root)
        logs.mkdir(parents=True)
        entry = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "python code/fit_decay.py"}}]}}
        (logs / "s.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")
        self.assertFalse(self.results()[self.fx.checks_listed[4]])
        entry["message"]["content"][0]["input"]["command"] = "cat code/fit_decay.py"
        (logs / "s.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")
        self.assertTrue(self.results()[self.fx.checks_listed[4]])


def make_docx(path, paragraphs_xml):
    """A minimal .docx whose body holds the given paragraph XML strings."""
    import zipfile
    body = "".join(paragraphs_xml)
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
           'wordprocessingml/2006/main"><w:body>' + body + "</w:body></w:document>")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", doc)
    return path


def para(*runs):
    return "<w:p>" + "".join(runs) + "</w:p>"


def run_t(text):
    return f'<w:r><w:t xml:space="preserve">{text}</w:t></w:r>'


def ins(text, author="Claude"):
    return f'<w:ins w:id="1" w:author="{author}" w:date="2026-11-09T00:00:00Z">{run_t(text)}</w:ins>'


def dele(text, author="Claude"):
    return (f'<w:del w:id="2" w:author="{author}" w:date="2026-11-09T00:00:00Z"><w:r><w:delText xml:space="preserve">'
            f'{text}</w:delText></w:r></w:del>')


class TrackedChangeText(unittest.TestCase):
    def test_accept_and_reject_read_the_tracked_changes(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            f = make_docx(Path(d) / "a.docx", [para(run_t("It is "), dele("sedement"), ins("sediment"), run_t(" here."))])
            self.assertEqual(rf.doc_text(f, "accept"), ["It is sediment here."])
            self.assertEqual(rf.doc_text(f, "reject"), ["It is sedement here."])
            self.assertEqual(rf.doc_text(f), ["It is sediment here."])

    def test_a_paragraph_mark_insertion_and_field_instructions_do_not_confuse_it(self):
        mark = '<w:pPr><w:rPr><w:ins w:id="9" w:author="Claude" w:date="x"/></w:rPr></w:pPr>'
        instr = '<w:r><w:instrText xml:space="preserve"> ADDIN X </w:instrText></w:r>'
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            f = make_docx(Path(d) / "a.docx", [para(mark, run_t("Keep "), instr, dele("old"), ins("new"))])
            self.assertEqual(rf.doc_text(f, "reject"), ["Keep old"])
            self.assertEqual(rf.doc_text(f, "accept"), ["Keep new"])


class ProofreadFixture(Base):
    def setUp(self):
        super().setUp()
        self.fx = rf.Proofread()
        self.root = (self.work / "Notes")
        self.root.mkdir()
        planted = [para(run_t("The " + " ".join(w for _, w in rf.Proofread.PLANTS))), para(run_t("Poem line one")),
                   para(run_t("Poem line two"))]
        make_docx(self.root / "Estuary Notes.docx", planted)
        self.fx.root = self.root
        self.fx.planted = rf.doc_text(self.root / "Estuary Notes.docx")
        self.fx.before = rf.tree_hashes(self.root)
        self.saved_run = rf.word_run
        rf.word_run = lambda script, timeout=180: (0, "revisions=12 comments=1")
        self.addCleanup(setattr, rf, "word_run", self.saved_run)

    def corrected(self, comments=(), author="Claude", fix=True, extra_change=False, break_tracking=False):
        first = []
        for old, new in rf.Proofread.PLANTS:
            wrong, right = new, old
            first += [dele(wrong, author), ins(right if fix else wrong, author), run_t(" ")]
        if break_tracking:
            first[0] = run_t("silently changed ")
        paras = [para(*[run_t("The ")] + first), para(run_t("Poem line one")),
                 para(run_t("Poem line two") if not extra_change else ins("Poem line 2"))]
        path = make_docx(self.root / "Estuary Notes - proofread.docx", paras)
        if comments:
            import zipfile
            body = "".join(f'<w:comment w:id="{i}" w:author="Claude"><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:comment>'
                           for i, c in enumerate(comments))
            with zipfile.ZipFile(path, "a") as z:
                z.writestr("word/comments.xml", "<w:comments xmlns:w=\"x\">" + body + "</w:comments>")
        return path

    def results(self, reply="Citation accuracy is not checked here; see citation-check."):
        return {n: ok for n, ok, _ in self.fx.check(self.root, reply, self.fx.before)}

    def test_a_good_proofread_passes_every_check(self):
        self.corrected(comments=["Short comment about flow."])
        results = self.results()
        self.assertTrue(all(results.values()), [n for n, ok in results.items() if not ok])

    def test_each_planted_problem_fails_its_check(self):
        c = self.fx.checks_listed
        cases = [
            (dict(fix=False), c[3]),
            (dict(author="Someone"), c[4]),
            (dict(extra_change=True), c[5]),
            (dict(break_tracking=True), c[2]),
            (dict(comments=["x"] * 6), c[6]),
            (dict(comments=["word " * 51]), c[6]),
        ]
        for kwargs, check in cases:
            self.corrected(**kwargs)
            self.assertFalse(self.results()[check], (kwargs, check))

    def test_missing_copy_changed_original_and_reply(self):
        self.assertFalse(self.results()[self.fx.checks_listed[0]])
        self.corrected()
        self.assertFalse(self.results("Done.")[self.fx.checks_listed[7]])
        (self.root / "Estuary Notes.docx").write_bytes(b"changed")
        self.assertFalse(self.results()[self.fx.checks_listed[1]])

    def test_word_failure_is_reported(self):
        self.corrected()
        rf.word_run = lambda script, timeout=180: (1, "the file is corrupt")
        self.assertFalse(self.results()[self.fx.checks_listed[8]])

    def test_the_fixture_is_skipped_without_its_source(self):
        class Args:
            estuary_doc = str(self.work / "missing.doc")
        with self.assertRaises(rf.Skip):
            rf.Proofread().build(self.work / "x", Args())

    def test_every_plant_is_a_distinct_fault_the_check_can_see(self):
        for old, new in rf.Proofread.PLANTS:
            self.assertNotEqual(old, new)
        for word in rf.Proofread.MUST_NOT_REMAIN:
            self.assertTrue(any(word in new for _, new in rf.Proofread.PLANTS), word)
        for word in rf.Proofread.MUST_REMAIN:
            self.assertTrue(any(word in old for old, _ in rf.Proofread.PLANTS), word)


class CitationCheckFixture(Base):
    def setUp(self):
        super().setUp()
        import sqlite3
        self.lib = self.work / "Test Library.enl"
        self.lib.write_bytes(b"enl")
        data = self.work / "Test Library.Data" / "sdb"
        data.mkdir(parents=True)
        con = sqlite3.connect(data / "sdb.eni")
        con.execute("create table refs (id integer primary key, author text, year text, title text, number text, reference_type integer)")
        con.executemany("insert into refs values (?,?,?,?,?,?)", [
            (1, "World Economic Forum,", "2023", "Global Risks Report 2023", "May 2025", 16),
            (2, "IPCC", "2023", "AR6 Synthesis Report: Climate Change 2023", "", 16),
            (3, "WorldPop", "2025", "Open Spatial Demographic Data and Research", "", 16)])
        con.commit()
        con.close()

        class Args:
            test_library = str(self.lib)
        self.fx = rf.CitationCheck()
        (self.work / "tmp").mkdir()
        self.root = self.fx.build(self.work / "tmp", Args())

    def fields(self):
        import zipfile
        import xml.etree.ElementTree as ET
        xml = zipfile.ZipFile(self.fx.manuscript).read("word/document.xml").decode("utf-8")
        found = []
        for m in re.finditer(r'fldCharType="begin"/>(.*?)fldCharType="end"/>', xml, re.S):
            instr = html_unescape("".join(re.findall(r"<w:instrText[^>]*>([^<]*)</w:instrText>", m.group(1))))
            self.assertTrue(instr.strip().startswith("ADDIN EN.CITE"))
            tree = ET.fromstring(instr.strip()[len("ADDIN EN.CITE"):])
            cite = tree.find("Cite")
            found.append((cite.findtext("RecNum"), cite.findtext("Year"), cite.find("record/titles").findtext("title")))
        return found

    def test_the_manuscript_holds_the_planted_fields(self):
        fields = self.fields()
        self.assertEqual(len(fields), 4)
        self.assertEqual(fields[0], ("1", "2023", "Global Risks Report 2023"))
        self.assertEqual(fields[1][0], "52")
        self.assertEqual(fields[2][1], "2024")
        self.assertEqual(fields[3][0], "99")
        self.assertIn("--strict-mcp-config", self.fx.extra_args(self.root))
        config = json.loads(self.fx.mcp_config.read_text(encoding="utf-8"))
        self.assertEqual(config["mcpServers"]["endnote"]["env"]["ENDNOTE_LIBRARY_PATH"], str(self.lib.resolve()))

    GOOD = ("""# Citation check

| Reference | Finding |
|---|---|
| IPCC 2023 AR6 | resolved; the field rec-number 52 differs from the library record 2 |
| WorldPop 2024 | year mismatch: field 2024, library 2025 |
| Harrington and Osei 2021, Adaptive Planning Horizons | unresolved: no title match in the library |

World Economic Forum 2023 was resolved with no issue. External verification was not done: not verified.
""")

    def write(self, text):
        folder = self.root / "outputs" / "citation-check-manuscript-091126-run1"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "citation-check-report.md").write_text(text, encoding="utf-8")

    def results(self):
        return {n: ok for n, ok, _ in self.fx.check(self.root, "", self.fx.before)}

    def test_a_good_report_passes_and_each_fault_fails_its_check(self):
        self.write(self.GOOD)
        results = self.results()
        self.assertTrue(all(results.values()), [n for n, ok in results.items() if not ok])
        c = self.fx.checks_listed
        cases = [
            (self.GOOD.replace("unresolved", "resolved"), c[1]),
            (self.GOOD.replace("2024", "x"), c[2]),
            (self.GOOD.replace("52", "n"), c[3]),
            (self.GOOD + "\nWorld Economic Forum 2023: year mismatch\n", c[4]),
            (self.GOOD.replace("External verification was not done: not verified.", ""), c[6]),
        ]
        for text, check in cases:
            self.write(text)
            self.assertFalse(self.results()[check], check)

    def test_an_external_call_or_a_changed_library_is_caught(self):
        self.write(self.GOOD)
        logs = self.home / "projects" / rf.project_key(self.root)
        logs.mkdir(parents=True)
        entry = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "WebFetch", "input": {"url": "https://api.crossref.org/works/10.1/x"}}]}}
        (logs / "s.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")
        self.assertFalse(self.results()[self.fx.checks_listed[5]])
        (logs / "s.jsonl").unlink()
        self.assertTrue(self.results()[self.fx.checks_listed[5]])
        self.lib.write_bytes(b"changed")
        self.assertFalse(self.results()[self.fx.checks_listed[7]])

    def test_the_fixture_is_skipped_without_a_library(self):
        class Args:
            test_library = None
        saved = os.environ.pop("FIXTURE_ENDNOTE_LIBRARY", None)
        try:
            with self.assertRaises(rf.Skip):
                rf.CitationCheck().build(self.work / "y", Args())
        finally:
            if saved:
                os.environ["FIXTURE_ENDNOTE_LIBRARY"] = saved


def html_unescape(text):
    import html
    return html.unescape(text)


def make_library(work, titles):
    """A fake EndNote library: an .enl file and the .Data/sdb/sdb.eni database with the given titles."""
    import sqlite3
    lib = Path(work) / "Test Library.enl"
    lib.write_bytes(b"enl")
    data = Path(work) / "Test Library.Data" / "sdb"
    data.mkdir(parents=True)
    con = sqlite3.connect(data / "sdb.eni")
    con.execute("create table refs (id integer primary key, author text, year text, title text, number text, "
                "reference_type integer)")
    con.executemany("insert into refs values (?,?,?,?,?,?)", [(i + 1, "A", "2025", t, "", 16) for i, t in enumerate(titles)])
    con.commit()
    con.close()
    return lib


def write_transcript(home, root, entries):
    logs = home / "projects" / rf.project_key(root)
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "s.jsonl").write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


def tool_call(name, **inputs):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inputs}]}}


class LiteratureSearchFixture(Base):
    def setUp(self):
        super().setUp()
        self.lib = make_library(self.work, ["Global Risks Report", "Theatre in Education", "Serious game",
                                            "Open Spatial Demographic Data and Research", "AR6 Synthesis Report"])

        class Args:
            test_library = str(self.lib)
        self.fx = rf.LiteratureSearch()
        (self.work / "tmp").mkdir()
        self.root = self.fx.build(self.work / "tmp", Args())

    GOOD = ("# Literature search\n\nDerived search terms: theatre, serious game.\n\n"
            "Sources: EndNote library, 2 hits. No external source was queried (OpenAlex not queried).\n\n"
            "| Title | Local PDF |\n|---|---|\n| Theatre in Education | no PDF linked |\n| Serious game | no PDF linked |\n")

    def write(self, text):
        folder = self.root / "outputs" / "literature-search-public-engagement-091126-run1"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "literature-search-report.md").write_text(text, encoding="utf-8")

    def results(self, reply="The run is pending review."):
        return {n: ok for n, ok, _ in self.fx.check(self.root, reply, self.fx.before)}

    def test_a_good_report_passes_and_each_fault_fails_its_check(self):
        self.write(self.GOOD)
        results = self.results()
        self.assertTrue(all(results.values()), [n for n, ok in results.items() if not ok])
        c = self.fx.checks_listed
        cases = [
            (self.GOOD.replace("Theatre in Education", "x"), c[2]),
            (self.GOOD + "| Open Spatial Demographic Data and Research | none |\n", c[3]),
            (self.GOOD.replace("Derived search terms: theatre, serious game.", "Terms used."), c[1]),
            (self.GOOD.replace("No external source was queried (OpenAlex not queried).", "Done."), c[5]),
        ]
        for text, check in cases:
            self.write(text)
            self.assertFalse(self.results()[check], check)
        self.write(self.GOOD)
        self.assertFalse(self.results("Done.")[c[8]])

    def test_an_external_call_or_a_changed_library_is_caught(self):
        self.write(self.GOOD)
        write_transcript(self.home, self.root, [tool_call("WebFetch", url="https://api.openalex.org/works?search=x")])
        self.assertFalse(self.results()[self.fx.checks_listed[6]])
        write_transcript(self.home, self.root, [tool_call("Bash", command="ls")])
        self.assertTrue(self.results()[self.fx.checks_listed[6]])
        self.lib.write_bytes(b"changed")
        self.assertFalse(self.results()[self.fx.checks_listed[7]])

    def test_the_fixture_is_skipped_without_the_records_it_expects(self):
        other = self.work / "other"
        other.mkdir()
        lib = make_library(other, ["Something else"])

        class Args:
            test_library = str(lib)
        with self.assertRaises(rf.Skip):
            rf.LiteratureSearch().build(self.work / "z", Args())


class LiteratureSearchExternalFixture(Base):
    def setUp(self):
        super().setUp()
        self.lib = make_library(self.work, ["One"])

        class Args:
            test_library = str(self.lib)
            external = True
        self.Args = Args
        self.fx = rf.LiteratureSearchExternal()
        (self.work / "tmp").mkdir()
        self.root = self.fx.build(self.work / "tmp", Args())

    def report(self, n=6, dup=False):
        rows = [f"| Title {i} | Author {i} | {2000 + i} | Journal | 10.1000/abc{i if not (dup and i == 1) else 0} | "
                f"{'peer-reviewed' if i % 2 else 'grey literature'} | OpenAlex |" for i in range(n)]
        return "# Report\n\nOpenAlex: 10 hits.\n\n| Title | Authors | Year | Venue | DOI | Type | Source |\n|---|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n"

    def ris(self, n=6):
        return "\n\n".join(f"TY  - JOUR\nAU  - Surname, Forename\nTI  - Title {i}\nPY  - {2000 + i}\nER  - " for i in range(n)) + "\n"

    def write(self, report, ris):
        folder = self.root / "outputs" / "literature-search-tidal-inlets-091126-run1"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "literature-search-report.md").write_text(report, encoding="utf-8")
        target = folder / "literature-search-import.ris"
        if ris is not None:
            target.write_text(ris, encoding="utf-8")
        else:
            target.unlink(missing_ok=True)

    def results(self):
        return {n: ok for n, ok, _ in self.fx.check(self.root, "", self.fx.before)}

    def sections(self, n=6):
        blocks = [f"### {i + 1}. Title {i}\n\n- Authors: A\n- Year: {2000 + i}\n- DOI: 10.1000/s{i}\n- Type: "
                  f"{'peer-reviewed' if i % 2 else 'grey literature'}\n" for i in range(n)]
        return "# Report\n\nOpenAlex: 10 hits.\n\n## 2. Candidate list\n\n" + "\n".join(blocks)

    def test_numbered_sections_count_as_candidates(self):
        self.write(self.sections(), self.ris())
        results = self.results()
        self.assertTrue(all(results.values()), [n for n, ok in results.items() if not ok])
        self.write(self.sections(n=3), self.ris(n=3))
        self.assertFalse(self.results()[self.fx.checks_listed[2]])
        self.write(self.sections().replace("peer-reviewed", "article"), self.ris())
        self.assertFalse(self.results()[self.fx.checks_listed[2]])
        self.write(self.sections(), self.ris(n=4))
        self.assertFalse(self.results()[self.fx.checks_listed[5]])

    def test_it_is_skipped_unless_external_is_given(self):
        class NoExternal(self.Args):
            external = False
        with self.assertRaises(rf.Skip):
            rf.LiteratureSearchExternal().build(self.work / "q", NoExternal())

    def test_a_good_result_passes_and_each_fault_fails_its_check(self):
        self.write(self.report(), self.ris())
        results = self.results()
        self.assertTrue(all(results.values()), [n for n, ok in results.items() if not ok])
        c = self.fx.checks_listed
        cases = [
            (self.report(n=3), self.ris(n=3), c[2]),
            (self.report(dup=True), self.ris(), c[3]),
            (self.report(), self.ris().replace("ER  - ", "", 1), c[4]),
            (self.report(), self.ris().replace("Surname, Forename", "Forename Surname"), c[4]),
            (self.report(), self.ris(n=5), c[5]),
            (self.report().replace("OpenAlex: 10 hits.", "Done."), self.ris(), c[1]),
        ]
        for report, ris, check in cases:
            self.write(report, ris)
            self.assertFalse(self.results()[check], check)
        self.write(self.report(), None)
        self.assertFalse(self.results()[c[4]])

    def test_mailto_and_other_services_are_caught_but_openalex_alone_is_fine(self):
        self.write(self.report(), self.ris())
        write_transcript(self.home, self.root, [tool_call("WebFetch", url="https://api.openalex.org/works?search=x")])
        results = self.results()
        self.assertTrue(results[self.fx.checks_listed[6]] and results[self.fx.checks_listed[7]])
        write_transcript(self.home, self.root, [tool_call("WebFetch", url="https://api.openalex.org/works?mailto=a@b.c")])
        self.assertFalse(self.results()[self.fx.checks_listed[6]])
        write_transcript(self.home, self.root, [tool_call("WebFetch", url="https://api.crossref.org/works/10.1/x")])
        self.assertFalse(self.results()[self.fx.checks_listed[7]])
        write_transcript(self.home, self.root, [tool_call("mcp__exa__web_search_exa", query="x")])
        self.assertFalse(self.results()[self.fx.checks_listed[7]])


if __name__ == "__main__":
    unittest.main()
