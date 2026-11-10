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
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "tests" / "skills" / "run_fixtures.py"
spec = importlib.util.spec_from_file_location("run_fixtures", RUNNER)
rf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rf)
w_para, write_minimal_docx = rf.w_para, rf.write_minimal_docx


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
            "secret and was redacted.\n\n## Timeline\n\n- 2026-03-02 plot written\n- 2026-03-09 fit changed\n\nAdd --detailed for the checklist.")

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

    def test_short_form_checks(self):
        short = self.fx.checks_listed[11]
        self.write(self.GOOD)
        self.assertTrue(self.results()[short])
        self.write(self.GOOD + "\n## Prompt appendix\n")
        self.assertFalse(self.results()[short])
        self.write(self.GOOD.replace("--detailed", "more"))
        self.assertFalse(self.results()[short])
        self.write(self.GOOD + "".join(f"- 2026-03-{d:02d} event\n" for d in range(10, 30)))
        self.assertFalse(self.results()[short])

    def test_detailed_form_check(self):
        fx = rf.ProjectDisclosureDetailed()
        self.assertEqual(fx.checks_listed[:11], self.fx.checks_listed[:11])
        full = self.GOOD + "\n## Prompt appendix\n\nPlot the decay curve; log transform; Summarise the repository layout\n"
        self.write(full)
        res = {n: ok for n, ok, _ in fx.check(self.root, "The run is pending review.", self.fx.before)}
        self.assertTrue(all(res.values()), [n for n, ok in res.items() if not ok])
        self.write(self.GOOD)
        res = {n: ok for n, ok, _ in fx.check(self.root, "The run is pending review.", self.fx.before)}
        self.assertFalse(res[fx.checks_listed[11]])
        self.assertIn("--detailed", fx.prompt(self.root))

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


class AdversaryLogHelpers(Base):
    def test_first_use_times_reads_main_and_subagent_logs(self):
        root = (self.work / "P").resolve()
        root.mkdir()
        folder = self.home / "projects" / rf.project_key(root)

        def call(ts, path):
            return {"type": "assistant", "timestamp": ts, "message": {"content": [
                {"type": "tool_use", "name": "Read", "input": {"file_path": path}}]}}

        rf.jsonl(folder / "s1.jsonl", [call("2026-11-10T10:00:00Z", str(root / "docs" / "spec.md"))])
        rf.jsonl(folder / "s1" / "subagents" / "agent-a.jsonl", [
            call("2026-11-10T10:05:00Z", str(root / "docs" / "review.md")),
            call("2026-11-10T10:01:00Z", str(root / "docs" / "spec.md"))])
        found = rf.first_use_times(root, ["docs/spec.md", "review.md", "absent.md"])
        self.assertEqual(found["docs/spec.md"], "2026-11-10T10:00:00Z")
        self.assertEqual(found["review.md"], "2026-11-10T10:05:00Z")
        self.assertIsNone(found["absent.md"])

    def test_four_parts(self):
        full = "".join(f"**C{i}.** Challenge. Evidence here. Consequence here. What would settle it: x.\n" for i in (1, 2, 3))
        self.assertTrue(rf.four_parts(full)[0])
        self.assertFalse(rf.four_parts(full.replace("What would settle it", "Note", 1))[0])
        self.assertFalse(rf.four_parts("**C1.** only\n")[0])


class DocumentAdversaryFixture(Base):
    def setUp(self):
        super().setUp()
        self.fx = rf.DocumentAdversary()
        self.root = self.fx.build(self.work)
        self.times = {"docs/spec.md": "10:00", "docs/objective.md": "10:01", "review-v0.9.md": "10:30"}
        self._orig = rf.first_use_times
        rf.first_use_times = lambda root, needles: {n: self.times.get(n) for n in needles}
        self.addCleanup(setattr, rf, "first_use_times", self._orig)

    def write(self, text, script=None):
        folder = self.root / "outputs" / "document-adversary-decay-spec-101126-run1"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "document-adversary-report.md").write_text(text, encoding="utf-8")
        if script:
            (folder / "code").mkdir(exist_ok=True)
            (folder / "code" / script).write_text("print(1)", encoding="utf-8")

    REPLY = "Saved as document-adversary-report.md. The run is pending review."

    @staticmethod
    def challenge(n, severity, text):
        return (f"**C{n} ({severity}).** {text} Challenge stated. Evidence: the passage. Consequence: a wrong run. "
                f"*What would settle it:* a decision.\n\n")

    GOOD = (
        "# Report\n\n## Verdict\n\nThe specification does not meet R3.\n\n## Method\n\nThe earlier review was read after "
        "the challenges were drafted.\n\n## Challenges\n\n"
        + challenge.__func__(1, "major", "R3 asks for the uncertainty of k and the specification has none. New.")
        + challenge.__func__(2, "moderate", "At k = 0.30 per day the half-life is 2.31 days, not 3.5 days. Contradicts E3.")
        + challenge.__func__(3, "minor", "Ten samples of one per day cannot cover 20 days. New.")
        + challenge.__func__(4, "moderate", "The background is fixed at zero and not tested. Repeats E2; adds a fit with an offset.")
        + "The claim of 1 per cent recovery needs data: refer it to analysis-adversary.\n\n"
        "## Alternatives not ruled out\n\nPool the profiles.\n\n## Numbers the document did not state\n\nHalf-life 2.31 days.\n\n"
        "## Null results\n\nThe 0.0125 per hour conversion holds.\n\n## Not checked\n\nSource papers.\n")

    def results(self, reply=None):
        return {n: ok for n, ok, _ in self.fx.check(self.root, self.REPLY if reply is None else reply, self.fx.before)}

    def test_the_planted_faults_are_in_the_fixture(self):
        spec = (self.root / "docs" / "spec.md").read_text(encoding="utf-8")
        self.assertIn("half-life is 3.5 days", spec)
        self.assertAlmostEqual(math.log(2) / 0.30, 2.31, places=2)
        self.assertAlmostEqual(0.30 / 24, 0.0125)
        self.assertIn("Ten samples", spec)
        self.assertNotIn("uncertaint", spec.lower())
        self.assertIn("R3", (self.root / "docs" / "objective.md").read_text(encoding="utf-8"))
        earlier = (self.root / "docs" / "review-v0.9.md").read_text(encoding="utf-8")
        self.assertIn("E2", earlier)
        self.assertIn("3.5 days", earlier)
        self.assertIn("review-v0.9.md", self.fx.prompt(self.root))

    def test_a_good_report_passes_every_check(self):
        self.write(self.GOOD)
        results = self.results()
        self.assertTrue(all(results.values()), [n for n, ok in results.items() if not ok])

    def test_each_planted_problem_fails_its_check(self):
        cases = [
            (self.GOOD.replace("R3", "a requirement").replace("uncertainty", "error"), 1),
            (self.GOOD.replace("2.31", "a different value"), 2),
            (self.GOOD.replace("Ten samples", "The samples").replace("20 days", "the run"), 3),
            (self.GOOD.replace("background", "offset").replace("baseline", "offset"), 4),
            (self.GOOD.replace("analysis-adversary", "another skill"), 5),
            (self.GOOD.replace("What would settle it", "Note"), 6),
            (self.GOOD.replace("## Not checked", "## Other").replace("Source papers.", ""), 7),
            (self.GOOD + "\n**C5 (minor).** The 0.0125 per hour value is wrong.\n", 8),
            (self.GOOD.replace("after the challenges were drafted", "at the start"), 12),
            (self.GOOD.replace("Repeats E2", "New"), 13),
            (self.GOOD + "The sampling interval is not stated.\n", 13),
            (self.GOOD.replace("Contradicts E3", "New"), 14),
            (self.GOOD.replace("Consequence", "Result", 1), 15),
            (self.GOOD.replace("## Alternatives not ruled out", "## Other"), 16),
            (self.GOOD.replace("## Numbers the document did not state", "## Other"), 16),
            (self.GOOD + "The check is in scratch.py.\n", 17),
        ]
        for text, i in cases:
            self.write(text)
            self.assertFalse(self.results()[self.fx.checks_listed[i]], (i, self.fx.checks_listed[i]))

    def test_reading_order_and_saved_scripts(self):
        self.write(self.GOOD)
        self.times["review-v0.9.md"] = "09:00"
        self.assertFalse(self.results()[self.fx.checks_listed[11]])
        self.times["review-v0.9.md"] = None
        self.assertFalse(self.results()[self.fx.checks_listed[11]])
        self.times["review-v0.9.md"] = "10:30"
        self.write(self.GOOD + "The check is in scratch.py.\n", script="scratch.py")
        self.assertTrue(self.results()[self.fx.checks_listed[17]])

    def test_missing_report_changed_file_and_reply(self):
        self.assertFalse(self.results()[self.fx.checks_listed[0]])
        self.write(self.GOOD)
        self.assertFalse(self.results("The run is pending review.")[self.fx.checks_listed[10]])
        self.assertFalse(self.results("document-adversary-report.md saved and I accepted the run, pending no more")[self.fx.checks_listed[10]])
        (self.root / "docs" / "spec.md").write_text("changed", encoding="utf-8")
        self.assertFalse(self.results()[self.fx.checks_listed[9]])


class DocumentAdversaryIndependentFixture(DocumentAdversaryFixture):
    def setUp(self):
        super().setUp()
        self.fx = rf.DocumentAdversaryIndependent()
        self.root = self.fx.build(self.work / "ind")
        self.times = {}

    GOOD = DocumentAdversaryFixture.GOOD.replace("The earlier review was read after the challenges were drafted.",
                                                 "No earlier review was read: the review was independent.") \
        .replace(" Contradicts E3.", "").replace(" Repeats E2; adds a fit with an offset.", "")

    def test_the_planted_faults_are_in_the_fixture(self):
        self.assertIn("earlier reviews: independent", self.fx.prompt(self.root))

    def test_each_planted_problem_fails_its_check(self):
        self.write(self.GOOD)
        results = self.results()
        self.assertTrue(all(results.values()), [n for n, ok in results.items() if not ok])
        cases = [
            (self.GOOD.replace("No earlier review was read: the review was independent.", "Done."), 12),
            (self.GOOD + "C9 Repeats E2 (new text).\n", 13),
            (self.GOOD.replace("Consequence", "Result", 1), 14),
        ]
        for text, i in cases:
            self.write(text)
            self.assertFalse(self.results()[self.fx.checks_listed[i]], (i, self.fx.checks_listed[i]))
        self.write(self.GOOD)
        self.times["review-v0.9.md"] = "10:30"
        self.assertFalse(self.results()[self.fx.checks_listed[11]])

    def test_a_good_report_passes_every_check(self):
        self.write(self.GOOD)
        results = self.results()
        self.assertTrue(all(results.values()), [n for n, ok in results.items() if not ok])

    def test_reading_order_and_saved_scripts(self):
        self.assertEqual(len(self.fx.checks_listed), 15)

    def test_missing_report_changed_file_and_reply(self):
        self.assertFalse(self.results()[self.fx.checks_listed[0]])


class AnalysisAdversaryModelFixture(Base):
    def setUp(self):
        super().setUp()
        self.fx = rf.AnalysisAdversaryModel()
        self.root = self.fx.build(self.work)
        self.times = {"data/obs.csv": "10:00", "code/model.py": "10:01", "earlier-review.md": "10:30"}
        self._orig = rf.first_use_times
        rf.first_use_times = lambda root, needles: {n: self.times.get(n) for n in needles}
        self.addCleanup(setattr, rf, "first_use_times", self._orig)

    def write(self, text, script="repro.py", content="import sys\nout = sys.argv[1]\n"):
        folder = self.root / "outputs" / "analysis-adversary-relaxation-rate-101126-run1"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "analysis-adversary-report.md").write_text(text, encoding="utf-8")
        if script:
            (folder / "code").mkdir(exist_ok=True)
            (folder / "code" / script).write_text(content, encoding="utf-8")

    REPLY = "Saved as analysis-adversary-report.md. The run is pending review."
    GOOD = (
        "# Report\n\n| Claim | Status |\n|---|---|\n| 1 | reproduced |\n| 2 | not reproduced |\n\n"
        "The earlier review was read after the findings were drafted.\n\n"
        "## Claim 1\n\nThe reported 0.160 reproduces with the exponent fixed at 0.5. With the exponent freed the fit gives an "
        "exponent of 1.00 and lam = 0.100 per day. F2 Repeats the open finding; it adds the split detail. F1 Contradicts: the rate "
        "falls from 0.160 to 0.100.\n\n"
        "The calibration used all the data and no data were held out for validation. A persistence baseline was not stated.\n\n"
        "## Claim 2\n\nThe RMSE of 0.468 is 0.49 of the standard deviation of y (0.954).\n\n"
        "## 7. Process-model checks\n\nSensitivity swept.\n")

    def results(self, reply=None):
        return {n: ok for n, ok, _ in self.fx.check(self.root, self.REPLY if reply is None else reply, self.fx.before)}

    def test_the_planted_bias_is_in_the_fixture(self):
        out = subprocess.run([sys.executable, "-I", "code/model.py"], cwd=self.root, capture_output=True, text=True)
        self.assertIn("lam = 0.160", out.stdout)
        rows = [ln.split(",") for ln in (self.root / "data" / "obs.csv").read_text(encoding="utf-8").splitlines()[1:]]
        self.assertEqual(len(rows), self.fx.N)
        ys = [float(r[2]) for r in rows]
        mean = sum(ys) / len(ys)
        sd = math.sqrt(sum((v - mean) ** 2 for v in ys) / len(ys))
        self.assertAlmostEqual(sd, 0.954, delta=0.01)
        self.assertIn("earlier-review.md", self.fx.prompt(self.root))
        self.assertTrue((self.root / "docs" / "earlier-review.md").is_file())

    def test_a_good_report_passes_every_check(self):
        self.write(self.GOOD)
        results = self.results()
        self.assertTrue(all(results.values()), [n for n, ok in results.items() if not ok])

    def test_each_planted_problem_fails_its_check(self):
        cases = [
            (self.GOOD.replace("0.100", "0.160"), 1),
            (self.GOOD.replace("1.00", "0.75").replace("0.5", "a value"), 2),
            (self.GOOD.replace("all the data", "some data").replace("no data were held out", "a split was made"), 3),
            (self.GOOD.replace("persistence baseline", "comparison"), 4),
            (self.GOOD.replace("Process-model checks", "Other"), 5),
            (self.GOOD.replace("| 1 | reproduced |", "").replace("Claim 2", "Item"), 9),
            (self.GOOD.replace("after the findings were drafted", "at the start"), 11),
            (self.GOOD.replace("F2 Repeats", "F2"), 12),
            (self.GOOD.replace("F1 Contradicts", "F1"), 12),
            (self.GOOD.replace("(0.954)", "").replace("0.468", "the model RMSE"), 13),
        ]
        for text, i in cases:
            self.write(text)
            self.assertFalse(self.results()[self.fx.checks_listed[i]], (i, self.fx.checks_listed[i]))

    def test_order_and_scripts(self):
        self.write(self.GOOD)
        self.times["earlier-review.md"] = "09:00"
        self.assertFalse(self.results()[self.fx.checks_listed[10]])
        self.times["earlier-review.md"] = "10:30"
        self.write(self.GOOD, script="repro.py", content="print(1)\n")
        self.assertTrue(self.results()[self.fx.checks_listed[14]])
        self.write(self.GOOD, script="repro.py", content="open('C:\\\\Temp\\\\scratch\\\\out.csv', 'w')\n")
        self.assertFalse(self.results()[self.fx.checks_listed[14]])
        self.write(self.GOOD, script=None)
        self.assertFalse(self.results()[self.fx.checks_listed[14]])

    def test_missing_report_changed_file_and_reply(self):
        self.assertFalse(self.results()[self.fx.checks_listed[0]])
        self.write(self.GOOD)
        self.assertFalse(self.results("The run is pending review.")[self.fx.checks_listed[8]])
        (self.root / "draft.md").write_text("changed", encoding="utf-8")
        self.assertFalse(self.results()[self.fx.checks_listed[7]])


class AnalysisAdversaryIndependentFixture(Base):
    def setUp(self):
        super().setUp()
        self.fx = rf.AnalysisAdversaryIndependent()
        self.root = self.fx.build(self.work)
        self.times = {}
        self._orig = rf.first_use_times
        rf.first_use_times = lambda root, needles: {n: self.times.get(n) for n in needles}
        self.addCleanup(setattr, rf, "first_use_times", self._orig)

    def write(self, text):
        folder = self.root / "outputs" / "analysis-adversary-relaxation-rate-101126-run1"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "analysis-adversary-report.md").write_text(text, encoding="utf-8")

    GOOD = ("# Report\n\nNo earlier review was read: the review was independent.\n\n"
            "The reported 0.160 reproduces with the exponent fixed at 0.5. With the exponent freed the fit gives an exponent of "
            "1.00 and lam = 0.100 per day. The calibration used all the data and no data were held out for validation. A "
            "persistence baseline was not stated.\n\n## 7. Process-model checks\n\nSensitivity swept.\n")

    def results(self):
        return {n: ok for n, ok, _ in self.fx.check(self.root, "Saved as analysis-adversary-report.md; pending review.",
                                                    self.fx.before)}

    def test_good_and_each_fault(self):
        self.assertIn("earlier reviews: independent", self.fx.prompt(self.root))
        self.write(self.GOOD)
        results = self.results()
        self.assertTrue(all(results.values()), [n for n, ok in results.items() if not ok])
        self.write(self.GOOD.replace("No earlier review was read: the review was independent.", "Done."))
        self.assertFalse(self.results()[self.fx.checks_listed[10]])
        self.write(self.GOOD + "F2 Repeats the open finding.\n")
        self.assertFalse(self.results()[self.fx.checks_listed[11]])
        self.write(self.GOOD)
        self.times["earlier-review.md"] = "10:00"
        self.assertFalse(self.results()[self.fx.checks_listed[9]])


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

    def results(self, reply="The validator was not run. Citation accuracy is not checked here; see citation-check."):
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
        self.assertFalse(self.results("The validator ran.")[self.fx.checks_listed[7]])
        self.assertFalse(self.results("Citation-check covers citations.")[self.fx.checks_listed[9]])
        (self.root / "Estuary Notes.docx").write_bytes(b"changed")
        self.assertFalse(self.results()[self.fx.checks_listed[1]])

    def test_word_failure_is_reported(self):
        self.corrected()
        rf.word_run = lambda script, timeout=180: (1, "the file is corrupt")
        self.assertFalse(self.results()[self.fx.checks_listed[8]])

    def test_the_fixture_is_skipped_without_word(self):
        saved = rf.word_available
        rf.word_available = lambda: False
        self.addCleanup(setattr, rf, "word_available", saved)
        with self.assertRaises(rf.Skip):
            rf.Proofread().build(self.work / "x")

    def test_the_fixture_builds_its_own_document_with_each_fault_once(self):
        saved = rf.word_available
        rf.word_available = lambda: True
        self.addCleanup(setattr, rf, "word_available", saved)
        fx = rf.Proofread()
        (self.work / "gen").mkdir()
        root = fx.build(self.work / "gen")
        self.assertEqual(root.name, "Notes")
        paragraphs = rf.doc_text(root / "Estuary Notes.docx")
        self.assertEqual(paragraphs[0], fx.planted[0])
        for old, new in rf.Proofread.PLANTS:
            self.assertIn(new, paragraphs[0])
            self.assertNotIn(old, paragraphs[0])
            self.assertEqual(rf.Proofread.PROSE.count(old), 1, old)
        self.assertTrue(paragraphs[0].startswith("Macrotidal estuaries"))
        self.assertIn("seperate", paragraphs[1])
        self.assertEqual(len(paragraphs), 5)
        for word in rf.Proofread.MUST_NOT_REMAIN:
            self.assertNotIn(word, rf.Proofread.PROSE)

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

    def test_the_manuscript_is_well_formed_xml(self):
        ET.fromstring(zipfile.ZipFile(self.fx.manuscript).read("word/document.xml"))

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


class ProofreadStructureFixture(Base):
    def setUp(self):
        super().setUp()
        self.saved = (rf.require_word, rf.word_run)
        rf.require_word = lambda: None
        rf.word_run = lambda script, timeout=180: (0, "revisions=4")
        self.addCleanup(lambda: (setattr(rf, "require_word", self.saved[0]), setattr(rf, "word_run", self.saved[1])))
        self.fx = rf.ProofreadStructure()
        (self.work / "tmp").mkdir()
        self.root = self.fx.build(self.work / "tmp", None)
        self.c = self.fx.checks_listed

    GOOD_REPLY = ("Scope: the whole document. validate.py was not run, because the docx scripts were not found. "
                  "Figure 2 has a caption that nothing refers to. The text refers to Figure 3, which has no caption. "
                  "Brown (2015) has no entry in the References. The entry for Zeta, 2010 is an orphan: nothing cites it. "
                  "The other citations (Smith 2019, Jones and Lee 2021, Kirby et al. 2000) match. "
                  "Citation accuracy is not checked here; use citation-check.")

    def make_copy(self, authors="Claude", text=None, comments=(), previous=True):
        """Write the proofread copy and the renamed previous copy as a good run would."""
        text = self.fx.original_text if text is None else text
        # one tracked change in the first paragraph: rejecting it gives back "Introduction", accepting it adds a full stop
        paras = [w_para(f'<w:del w:id="1" w:author="{authors}" w:date="x"><w:r><w:delText>Introduction</w:delText></w:r></w:del>'
                        f'<w:ins w:id="2" w:author="{authors}" w:date="x"><w:r><w:t>Introduction.</w:t></w:r></w:ins>')]
        paras += [w_para(t) for t in text[1:]]
        path = self.root / "Structure Notes - proofread.docx"
        write_minimal_docx(path, paras)
        if comments:
            body = "".join(f'<w:comment w:id="{i}" w:author="Claude"><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:comment>'
                           for i, c in enumerate(comments))
            with zipfile.ZipFile(path, "a") as z:
                z.writestr("word/comments.xml", '<w:comments xmlns:w="x">' + body + "</w:comments>")
        if previous:
            (self.root / "Structure Notes - proofread (previous run).docx").write_bytes(self.fx.marker_bytes)
        return path

    def results(self, reply=None):
        return {n: ok for n, ok, _ in self.fx.check(self.root, self.GOOD_REPLY if reply is None else reply, self.fx.before)}

    def test_the_manuscript_is_well_formed_xml(self):
        ET.fromstring(zipfile.ZipFile(self.fx.manuscript).read("word/document.xml"))

    def test_the_manuscript_holds_the_planted_features(self):
        with zipfile.ZipFile(self.fx.manuscript) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        self.assertEqual(xml.count("SEQ Figure"), 2)
        self.assertEqual(xml.count("SEQ Table"), 1)
        self.assertEqual(xml.count("REF _Ref100000001"), 1)
        self.assertEqual(xml.count("ADDIN EN.CITE"), 1)
        paragraphs = rf.doc_paragraphs(xml)
        begin = next(i for i, p in enumerate(paragraphs) if "ADDIN EN.REFLIST" in p)
        end = max(i for i, p in enumerate(paragraphs) if 'fldCharType="end"' in p)
        self.assertGreater(end - begin, 2, "the References field spans several paragraphs")
        text = " ".join(self.fx.original_text)
        for needle in ("Brown (2015)", "Kirby et al. (2000)", "Figure 3", "Zeta Q, 2010", "Smith, 2019"):
            self.assertIn(needle, text)
        self.assertEqual(rf.tree_hashes(self.root), self.fx.before)
        self.assertEqual(len(self.fx.checks_listed), 14)

    def test_a_good_run_passes_every_check(self):
        self.make_copy()
        results = self.results()
        self.assertTrue(all(results.values()), [n for n, ok in results.items() if not ok])

    def test_each_planted_problem_fails_its_check(self):
        c = self.c
        self.make_copy()
        cases = [
            (self.GOOD_REPLY.replace("Figure 2 has a caption that nothing refers to.", "Figure 2 is fine."), c[5]),
            (self.GOOD_REPLY.replace("which has no caption", "which is shown"), c[6]),
            (self.GOOD_REPLY.replace("Brown (2015) has no entry in the References.", "All citations have entries."), c[7]),
            (self.GOOD_REPLY.replace("is an orphan: nothing cites it", "is fine"), c[8]),
            (self.GOOD_REPLY + " Smith 2019 has no entry in the References.", c[9]),
            (self.GOOD_REPLY.replace("validate.py was not run, because the docx scripts were not found.", "Done."), c[11]),
            (self.GOOD_REPLY.replace("use citation-check", "done"), c[12]),
        ]
        for reply, check in cases:
            self.assertFalse(self.results(reply)[check], check)

    def test_a_flag_in_a_comment_counts_and_a_clause_boundary_separates_findings(self):
        self.make_copy(comments=["Figure 2 is never referred to in the text."])
        results = self.results("validator not run. Brown (2015) has no entry; Zeta is an orphan; Figure 3 has no caption. "
                               "Smith and Jones and Kirby match. See citation-check.")
        self.assertTrue(results[self.c[5]], "found in a comment")
        self.assertTrue(results[self.c[9]], "a finding about Brown does not count against Smith")

    def test_copy_rename_original_tracking_authors_comments_and_word(self):
        c = self.c
        self.make_copy(previous=False)
        self.assertFalse(self.results()[c[2]])
        self.make_copy(authors="Someone")
        self.assertFalse(self.results()[c[4]])
        self.make_copy(text=self.fx.original_text[:-1])
        self.assertFalse(self.results()[c[3]], "text that does not come back on reject-all")
        self.make_copy(comments=["x"] * 6)
        self.assertFalse(self.results()[c[10]])
        self.make_copy(comments=["word " * 51])
        self.assertFalse(self.results()[c[10]])
        self.make_copy()
        rf.word_run = lambda script, timeout=180: (1, "corrupt")
        self.assertFalse(self.results()[c[13]])
        (self.root / "Structure Notes.docx").write_bytes(b"changed")
        self.assertFalse(self.results()[c[1]])

    def test_no_new_copy_fails_the_content_checks(self):
        (self.root / "Structure Notes - proofread.docx").write_bytes(self.fx.marker_bytes)
        results = self.results()
        self.assertFalse(results[self.c[0]])
        self.assertFalse(results[self.c[3]])
        self.assertFalse(results[self.c[13]])

    def test_the_fixture_is_skipped_without_word(self):
        rf.require_word = self.saved[0]
        saved = rf.word_available
        rf.word_available = lambda: False
        try:
            with self.assertRaises(rf.Skip):
                rf.ProofreadStructure().build(self.work / "q", None)
        finally:
            rf.word_available = saved


class DocxSkillReport(Base):
    def test_the_runner_reports_the_docx_skill_rows_for_the_live_folder(self):
        rows = rf.docx_skill_rows()
        self.assertTrue(rows)
        self.assertTrue(all(kind in ("OK", "WARN", "FAIL") for kind, _ in rows))
        self.assertTrue(rf.Proofread.uses_docx_skill and rf.ProofreadStructure.uses_docx_skill)
        self.assertFalse(rf.CitationCheck.uses_docx_skill)


class SyntheticLibraryHelpers(Base):
    def test_a_pdf_is_valid_and_its_text_can_be_read(self):
        path = self.work / "t.pdf"
        rf.make_pdf(path, ["First line (with brackets)", "Second line"])
        self.assertTrue(path.read_bytes().startswith(b"%PDF-1.4"))
        try:
            from pypdf import PdfReader
        except ImportError:
            self.skipTest("pypdf is not installed here")
        text = "\n".join(page.extract_text() for page in PdfReader(str(path)).pages)
        self.assertIn("First line (with brackets)", text)
        self.assertIn("Second line", text)

    def test_the_enl_file_is_the_database_and_the_pdf_is_linked(self):
        import sqlite3
        lib = rf.SyntheticLibrary()
        path = lib.make_library(self.work, [{"author": "A, B", "year": "2000", "title": "T", "electronic_resource_number": "10.1/x"}],
                                pdfs={1: ("A2000.pdf", ["text"])})
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        self.assertEqual(con.execute("select title, electronic_resource_number from refs where id = 1").fetchone(), ("T", "10.1/x"))
        self.assertEqual(con.execute("select refs_id, file_path from file_res").fetchall(), [(1, "A2000.pdf")])
        con.close()
        self.assertTrue((path.with_suffix(".Data") / "PDF" / "A2000.pdf").is_file())
        self.assertEqual(sorted(lib._library_hashes()), ["PDF/A2000.pdf", "Synthetic.enl"])
        self.assertTrue(json.loads(lib.mcp_config.read_text(encoding="utf-8"))["mcpServers"]["endnote"]["env"]["ENDNOTE_LIBRARY_PATH"])

    def test_short_author_forms_and_missing_packages(self):
        self.assertEqual(rf.short_author({"author": "Marlow, T\rOkoro, E"}), "Marlow and Okoro")
        self.assertEqual(rf.short_author({"author": "Quill, R"}), "Quill")
        self.assertEqual(rf.short_author({"author": "A, B\rC, D\rE, F"}), "A et al.")
        self.assertEqual(rf.short_author({"author": "A, B\rC, D\rE, F", "display": "Custom"}), "Custom")
        with self.assertRaises(rf.Skip):
            rf.require_server_packages("no_such_package_for_the_fixture")

    def test_verdict_lines_and_tool_calls(self):
        lines = ["| tidal pumping | Overstated |", "| mouth | Not supported |", "| spring tides | Supported |"]
        self.assertTrue(rf.verdict_line(lines, "tidal pumping", "overstated"))
        self.assertFalse(rf.verdict_line(lines, "mouth", rf.NOT_SUPPORTED), "'Not supported' is not Supported")
        self.assertTrue(rf.verdict_line(lines, "spring", rf.NOT_SUPPORTED))
        self.assertFalse(rf.verdict_line(lines, "spring", "supported", exclude="spring"))
        write_transcript(self.home, self.work, [tool_call("WebFetch", url="https://a.example/x", note=["y"])])
        self.assertEqual(rf.tool_calls(self.work), [("WebFetch", "https://a.example/x y")])


class CitationCheckContextFixture(Base):
    def setUp(self):
        super().setUp()
        self.saved = rf.require_server_packages
        rf.require_server_packages = lambda *names: None
        self.addCleanup(setattr, rf, "require_server_packages", self.saved)
        self.fx = rf.CitationCheckContext()
        (self.work / "tmp").mkdir()
        self.root = self.fx.build(self.work / "tmp", None)
        self.c = self.fx.checks_listed

    GOOD = """# Citation check

| Sentence | Verdict | Note |
|---|---|---|
| Peak suspended sediment concentration occurred during spring tides | Supported | in the results |
| Tidal pumping is the main cause of the up-estuary increase in sediment concentration | Overstated | the source says the data suggest it contributes |
| Concentration increased towards the mouth of the estuary at all three stations | Contradicted | the source says towards the head |
| The bed sediment of the estuary is mainly fine sand | Not located | the source did not measure bed sediment |
| River discharge controlled the concentration, and the peak occurred during spring tides | discharge: Contradicted; spring tides: Supported | two components |
| Wave climate is dominant in the outer estuary (Quill, 2015) | Unable to verify: no source text available | nothing linked |

External verification was not done.
"""

    def write(self, text):
        folder = self.root / "outputs" / "citation-check-manuscript-101126-run1"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "citation-check-report.md").write_text(text, encoding="utf-8")

    def read_call(self, max_chars=150000):
        write_transcript(self.home, self.root, [tool_call("mcp__endnote__read_linked_file_text", ref_id=1, max_chars=max_chars)])

    def results(self):
        return {n: ok for n, ok, _ in self.fx.check(self.root, "", self.fx.before)}

    def test_the_inputs_are_what_the_checks_assume(self):
        self.assertEqual(self.fx.RECORDS[0]["year"], "2018")
        text = " ".join(self.fx.SOURCE)
        for fact in ("Peak concentration occurred during spring tides", "towards the head", "no relationship between concentration and river discharge",
                     "suggest that tidal pumping contributes", "did not measure bed sediment"):
            self.assertIn(fact, text)
        ET.fromstring(zipfile.ZipFile(self.fx.manuscript).read("word/document.xml"))
        self.assertEqual(len(rf.doc_text(self.fx.manuscript)), 1 + len(self.fx.CLAIMS))
        self.assertEqual(len(self.fx.checks_listed), 10)

    def test_a_good_report_passes_every_check(self):
        self.write(self.GOOD)
        self.read_call()
        results = self.results()
        self.assertTrue(all(results.values()), [n for n, ok in results.items() if not ok])

    def test_each_wrong_verdict_fails_its_check(self):
        self.read_call()
        cases = [
            (self.GOOD.replace("| Supported | in the results", "| Contradicted | in the results"), self.c[1]),
            (self.GOOD.replace("Overstated", "Supported"), self.c[2]),
            (self.GOOD.replace("| Contradicted | the source says towards the head", "| Supported | the source says towards the head"), self.c[3]),
            (self.GOOD.replace("Not located", "Contradicted"), self.c[4]),
            (self.GOOD.replace("discharge: Contradicted; spring tides: Supported", "Contradicted"), self.c[5]),
            (self.GOOD.replace("Unable to verify: no source text available", "Supported"), self.c[6]),
        ]
        for text, check in cases:
            self.write(text)
            self.assertFalse(self.results()[check], check)

    def test_a_split_compound_sentence_passes_and_prompt_words_in_the_skill_call_are_not_calls(self):
        both = "| River discharge controlled the concentration, and the peak occurred during spring tides | discharge: Contradicted; spring tides: Supported | two components |"
        split = self.GOOD.replace(both, '| 5a "River discharge controlled the concentration ..." | Contradicted | no relationship |\n'
                                        '| 5b "... and the peak occurred during spring tides" | Supported | stated |')
        self.assertNotEqual(split, self.GOOD)
        self.write(split)
        self.read_call()
        self.assertTrue(self.results()[self.c[5]], "one row for each half is a verdict for each component")
        self.write(split.replace("| Supported | stated |", "| Contradicted | stated |"))
        self.assertFalse(self.results()[self.c[5]], "the second half is not Supported")
        self.write(split)
        write_transcript(self.home, self.root, [
            tool_call("Skill", skill="citation-check", args="make no call to CrossRef, OpenAlex, arXiv, Unpaywall or https://x.example"),
            tool_call("mcp__endnote__read_linked_file_text", ref_id=1, max_chars=150000)])
        self.assertTrue(self.results()[self.c[8]], "the Skill call only repeats the prompt")
        write_transcript(self.home, self.root, [tool_call("Bash", command="curl https://api.crossref.org/works/x")])
        self.assertFalse(self.results()[self.c[8]])

    def test_a_small_max_chars_an_external_call_and_a_changed_library_are_caught(self):
        self.write(self.GOOD)
        self.read_call(max_chars=20000)
        self.assertFalse(self.results()[self.c[7]])
        self.read_call()
        self.assertTrue(self.results()[self.c[7]])
        write_transcript(self.home, self.root, [tool_call("WebFetch", url="https://api.crossref.org/works/10.1/x")])
        self.assertFalse(self.results()[self.c[8]])
        write_transcript(self.home, self.root, [tool_call("mcp__endnote__read_linked_file_text", ref_id=1, max_chars=150000)])
        self.assertTrue(self.results()[self.c[8]], "the local EndNote tools are not external calls")
        (self.fx.library.with_suffix(".Data") / "PDF" / "Marlow2018.pdf").write_bytes(b"changed")
        self.assertFalse(self.results()[self.c[9]])


class CitationCheckExternalFixture(Base):
    def setUp(self):
        super().setUp()
        self.saved = rf.require_server_packages
        rf.require_server_packages = lambda *names: None
        self.addCleanup(setattr, rf, "require_server_packages", self.saved)

        class Args:
            external = True
        self.Args = Args
        self.fx = rf.CitationCheckExternal()
        (self.work / "tmp").mkdir()
        self.root = self.fx.build(self.work / "tmp", Args())
        self.c = self.fx.checks_listed

    GOOD = """# Citation check

| Reference | Finding |
|---|---|
| Watson and Crick 1953 | resolved; verified on CrossRef by DOI: title, authors, year and journal agree |
| Shannon 1949 | year mismatch: the library says 1949 and CrossRef says 1948 |
| LeCun et al. 2015, Deep learning | no DOI; verified by a title search on CrossRef (authors LeCun, Bengio and Hinton, year 2015) |
| Harrington and Osei 2021 | DOI 10.9999/jcr.2021.0099 not found on CrossRef; the title searches gave no author match; not verified |
"""
    CALLS = [tool_call("WebFetch", url="https://api.crossref.org/works/10.1038/171737a0"),
             tool_call("WebFetch", url="https://api.crossref.org/works?query.title=Deep+learning&query.author=LeCun"),
             tool_call("WebFetch", url="https://api.openalex.org/works?filter=title.search:Deep%20learning"),
             tool_call("WebFetch", url='https://export.arxiv.org/api/query?search_query=ti:"Deep learning"&max_results=5')]

    def write(self, text):
        folder = self.root / "outputs" / "citation-check-manuscript-101126-run1"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "citation-check-report.md").write_text(text, encoding="utf-8")

    def calls(self, *extra, drop=()):
        entries = [c for i, c in enumerate(self.CALLS) if i not in drop] + list(extra)
        write_transcript(self.home, self.root, entries)

    def results(self):
        return {n: ok for n, ok, _ in self.fx.check(self.root, "", self.fx.before)}

    def test_it_is_skipped_unless_external_is_given_and_the_inputs_are_what_the_checks_assume(self):
        class NoExternal:
            external = False
        with self.assertRaises(rf.Skip):
            rf.CitationCheckExternal().build(self.work / "q", NoExternal())
        self.assertEqual(self.fx.RECORDS[1]["year"], "1949", "the planted wrong year")
        self.assertEqual(self.fx.RECORDS[3]["electronic_resource_number"][:7], "10.9999", "a prefix that does not exist")
        ET.fromstring(zipfile.ZipFile(self.fx.manuscript).read("word/document.xml"))
        self.assertEqual(len(self.fx.checks_listed), 10)

    def test_a_good_result_passes_every_check(self):
        self.write(self.GOOD)
        self.calls()
        results = self.results()
        self.assertTrue(all(results.values()), [n for n, ok in results.items() if not ok])

    def test_each_planted_problem_fails_its_check(self):
        self.calls()
        c = self.c
        cases = [
            (self.GOOD.replace("1948", "an earlier year"), c[2]),
            (self.GOOD + "| Watson and Crick 1953 | title mismatch on CrossRef |\n", c[3]),
            (self.GOOD.replace("verified by a title search", "not verified by a title search"), c[4]),
            (self.GOOD.replace("not verified", "verified"), c[5]),
        ]
        for text, check in cases:
            self.write(text)
            self.assertFalse(self.results()[check], check)

    def test_scripted_queries_count_and_prompt_words_in_the_skill_call_do_not(self):
        self.write(self.GOOD)
        quote = chr(92) + '"'
        script = ('URLS = ["https://api.crossref.org/works/{doi}", "https://api.openalex.org/works?filter=title.search:{t}", '
                  '"https://export.arxiv.org/api/query?search_query=ti:' + quote + '{t}' + quote + '&max_results=5"]\n'
                  'DOIS = ["10.1038/171737a0"]')
        write_transcript(self.home, self.root, [
            tool_call("Skill", skill="citation-check", args="not Semantic Scholar, Unpaywall, Exa; no mailto= parameter"),
            tool_call("Write", file_path="q.py", content=script)])
        results = self.results()
        for index in (1, 6, 7, 8):
            self.assertTrue(results[self.c[index]], self.c[index])
        write_transcript(self.home, self.root, [tool_call("Write", file_path="q.py", content=script + "\nX = 'https://api.unpaywall.org/v2/x'")])
        self.assertFalse(self.results()[self.c[6]], "a real Unpaywall address in a script")

    def test_a_script_that_keeps_the_base_address_and_the_query_apart_is_judged_on_the_query(self):
        self.write(self.GOOD)
        base = 'ARXIV = "https://export.arxiv.org/api/query"\nOA = "https://api.openalex.org/works"\nCR = "https://api.crossref.org/works/"\nDOI = "10.1038/171737a0"\n'
        good = base + 'q = ARXIV + "?search_query=ti:%22" + t + "%22&max_results=5"\nr = OA + "?filter=title.search:" + t\n'
        write_transcript(self.home, self.root, [tool_call("Bash", command=good)])
        results = self.results()
        for index in (1, 7, 8):
            self.assertTrue(results[self.c[index]], self.c[index])
        write_transcript(self.home, self.root, [tool_call("Bash", command=base + 'q = ARXIV + "?search_query=ti:" + t + "&max_results=5"\n')])
        self.assertFalse(self.results()[self.c[8]], "an unquoted query built apart from the address")
        write_transcript(self.home, self.root, [tool_call("Bash", command=base + 'r = OA + "?search=" + t\n')])
        self.assertFalse(self.results()[self.c[7]], "a bare search parameter built apart from the address")
        write_transcript(self.home, self.root, [tool_call("Bash", command=base)])
        self.assertFalse(self.results()[self.c[8]], "no arXiv query at all")

    def test_the_lecun_row_may_say_match_on_title_but_not_no_match(self):
        self.calls()
        c = self.c
        match_row = "| LeCun et al. 2015 | no DOI; title search found the same work: match on title, authors, year and journal |"
        self.write(self.GOOD.replace([ln for ln in self.GOOD.splitlines() if "LeCun" in ln][0], match_row))
        self.assertTrue(self.results()[c[4]])
        for wording in ("no match on title in CrossRef", "title search: ambiguous between two works", "not a match"):
            self.write(self.GOOD.replace([ln for ln in self.GOOD.splitlines() if "LeCun" in ln][0], f"| LeCun et al. 2015 | {wording} |"))
            self.assertFalse(self.results()[c[4]], wording)

    def test_the_calls_are_checked_for_services_search_form_and_quoting(self):
        self.write(self.GOOD)
        c = self.c
        self.calls(drop=(0,))
        self.assertFalse(self.results()[c[1]], "no CrossRef DOI call")
        self.calls(tool_call("WebFetch", url="https://api.semanticscholar.org/graph/v1/paper/search?query=x"))
        self.assertFalse(self.results()[c[6]])
        self.calls(tool_call("WebFetch", url="https://api.crossref.org/works/10.1/x?mailto=a@b.c"))
        self.assertFalse(self.results()[c[6]])
        self.calls(tool_call("WebFetch", url="https://api.openalex.org/works?search=tidal+inlet"))
        self.assertFalse(self.results()[c[7]], "the bare search parameter")
        self.calls(drop=(2,))
        self.assertFalse(self.results()[c[7]], "no OpenAlex call at all")
        self.calls(tool_call("WebFetch", url="https://export.arxiv.org/api/query?search_query=ti:Deep learning&max_results=5"))
        self.assertFalse(self.results()[c[8]], "an unquoted arXiv title")
        self.calls(drop=(3,))
        self.assertFalse(self.results()[c[8]], "no arXiv call at all")
        self.calls(tool_call("WebFetch", url="https://export.arxiv.org/api/query?search_query=ti:%22Deep+learning%22"))
        self.assertTrue(self.results()[c[8]], "a percent-encoded quote is still a quote")
        self.fx.library.write_bytes(b"changed")
        self.assertFalse(self.results()[c[9]])


if __name__ == "__main__":
    unittest.main()
