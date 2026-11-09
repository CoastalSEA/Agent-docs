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


if __name__ == "__main__":
    unittest.main()
