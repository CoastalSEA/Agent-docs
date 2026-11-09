r"""Tests for the project scripts and deploy.py. Standard library only.

Run from the repository root:  python tests/test_scripts.py [-v]
Each test builds a throwaway project in a temporary folder (a git repository where needed), runs a
script as a separate process and checks the exit code, the files, the tags and the INDEX.md rows.
Nothing under the real ~/.claude is touched: deploy.py is run with --target set to a temporary folder.

Scripts covered: run_control.py, archive_control.py, check_records.py and deploy.py.
Inputs:  the scripts in this repository; the stub files under claude-md/project-template/.
Outputs: a unittest report on standard error; exit code 0 if every test passes.

Created using: $\text {Created using: }\ claude-sonnet-5-5-\text{v}1.0-\text {date: }081126$
"""
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "claude-md" / "project-template"
TODAY = dt.date.today().strftime("%d%m%y")


def find(name, *folders):
    for f in folders:
        p = REPO / f / name
        if p.exists():
            return p
    raise FileNotFoundError(name)


RUN_CONTROL = find("run_control.py", "scripts")
ARCHIVE = find("archive_control.py", "scripts", "claude-md/project-template/code")
CHECK = find("check_records.py", "scripts", "claude-md/project-template/records")
DEPLOY = REPO / "deploy.py"
ROTATE = find("rotate_records.py", "scripts")
STATUS = find("wrapup_status.py", "scripts")
HOOK = find("hook_push_check.py", "scripts")
GUARD = find("hook_guard.py", "scripts")
CONFIRM = find("hook_confirm.py", "scripts")
NL = chr(10)
CRLF = chr(13) + chr(10)

GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def run(script, *args, cwd=None):
    return subprocess.run([sys.executable, "-I", str(script), *args], capture_output=True, text=True,
                          cwd=cwd, env=GIT_ENV)


def git(root, *args):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, env=GIT_ENV)
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


def version_of(script):
    return re.search(r'^VERSION = "([^"]+)"', script.read_text(encoding="utf-8"), re.M).group(1)


class Project(unittest.TestCase):
    """A temporary project; a git repository with the INDEX.md stub unless `tracked` is False."""
    tracked = True

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "proj"
        (self.root / "outputs").mkdir(parents=True)
        if self.tracked:
            shutil.copy(TEMPLATE / "outputs" / "INDEX.md", self.root / "outputs" / "INDEX.md")
            git(self.root, "init", "-q", "-b", "main")
            git(self.root, "add", "-A")
            git(self.root, "commit", "-q", "-m", "init")

    def rc(self, *args):
        return run(RUN_CONTROL, *args, "--root", str(self.root))

    def start_and_write(self, task="demo", name="r.txt", text="one"):
        self.assertEqual(self.rc("start", task).returncode, 0)
        (self.root / "outputs" / task / name).write_text(text, encoding="utf-8")

    def accept(self, task="demo", question=None):
        args = ["accept", task] + ([question] if question else [])
        r = self.rc(*args)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        return r

    def index_rows(self):
        text = (self.root / "outputs" / "INDEX.md").read_text(encoding="utf-8")
        return [[c.strip() for c in ln.strip().strip("|").split("|")]
                for ln in text.splitlines() if ln.startswith("| `")]

    def tags(self):
        return git(self.root, "tag", "-l").split()


class RunControlTracked(Project):
    def test_version_flag(self):
        r = run(RUN_CONTROL, "--version")
        self.assertEqual(r.stdout.strip(), f"run_control.py {version_of(RUN_CONTROL)}")

    def test_root_is_accepted_before_or_after_the_command(self):
        self.start_and_write()
        for args in (["--root", str(self.root), "check", "demo"], ["check", "demo", "--root", str(self.root)],
                     ["check", "--root", str(self.root), "demo"], ["check", "demo", f"--root={self.root}"]):
            r = run(RUN_CONTROL, *args)
            self.assertEqual(r.returncode, 0, (args, r.stderr))

    def test_path_changes_nothing(self):
        r = self.rc("path", "demo")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r.stdout.strip().endswith("demo"))
        self.assertFalse((self.root / "outputs" / "demo").exists())

    def test_start_writes_run_info(self):
        self.start_and_write()
        info = (self.root / "outputs" / "demo" / "run_info.txt").read_text(encoding="utf-8")
        self.assertIn("mode: tracked", info)
        self.assertIn(f"proposed tag: demo-{TODAY}-run1", info)
        self.assertRegex(info, r"run control version: \S+")

    def test_accept_tags_commits_and_indexes(self):
        self.start_and_write()
        self.accept(question="Does x hold?")
        tag = f"demo-{TODAY}-run1"
        self.assertIn(tag, self.tags())
        self.assertEqual(git(self.root, "cat-file", "-t", tag), "tag")  # annotated
        message = git(self.root, "tag", "-l", "--format=%(contents)", tag)
        self.assertEqual(message.splitlines()[0], "Does x hold?")
        self.assertIn("Run control version:", message)
        self.assertEqual(git(self.root, "status", "--porcelain"), "")
        rows = self.index_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0][0], rows[0][1], rows[0][2], rows[0][3]),
                         (f"`{tag}`", "`demo`", "Does x hold?", "current"))

    def test_second_run_supersedes_and_reuses_question(self):
        self.start_and_write()
        self.accept(question="Q?")
        self.start_and_write(text="two")
        self.accept()
        rows = self.index_rows()
        self.assertEqual([r[3] for r in rows], ["superseded", "current"])
        self.assertIn(f"demo-{TODAY}-run2", self.tags())
        self.assertEqual(rows[1][2], "Q?")

    def test_reject_tags_not_adopted(self):
        self.start_and_write()
        r = self.rc("reject", "demo", "Q?")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"demo-{TODAY}-run1-rejected", self.tags())
        self.assertEqual(self.index_rows()[0][3], "not adopted")

    def test_discard_restores_last_accepted_run(self):
        self.start_and_write(text="one")
        self.accept(question="Q?")
        self.start_and_write(text="two")
        self.assertEqual(self.rc("discard", "demo").returncode, 0)
        self.assertEqual((self.root / "outputs" / "demo" / "r.txt").read_text(encoding="utf-8"), "one")

    def test_guard_blocks_excluded_file_type(self):
        self.start_and_write()
        (self.root / "outputs" / "demo" / "paper.pdf").write_bytes(b"%PDF")
        r = self.rc("accept", "demo", "Q?")
        self.assertEqual(r.returncode, 1)
        self.assertIn("paper.pdf", r.stderr)
        self.assertEqual(self.tags(), [])

    def test_allow_passes_a_named_file_and_is_recorded(self):
        self.start_and_write()
        (self.root / "outputs" / "demo" / "paper.pdf").write_bytes(b"%PDF")
        r = self.rc("accept", "demo", "Q?", "--allow", "paper.pdf")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("paper.pdf", git(self.root, "tag", "-l", "--format=%(contents)", f"demo-{TODAY}-run1"))

    def test_rerun_keeps_md_removes_other_files_and_warns(self):
        self.start_and_write()
        (self.root / "outputs" / "demo" / "report.md").write_text("keep", encoding="utf-8")
        r = self.rc("start", "demo")
        self.assertIn("pending review", r.stderr)
        self.assertTrue((self.root / "outputs" / "demo" / "report.md").exists())
        self.assertFalse((self.root / "outputs" / "demo" / "r.txt").exists())

    def test_status_lists_pending_task(self):
        self.start_and_write()
        r = self.rc("status")
        self.assertEqual(r.returncode, 0)
        self.assertIn("demo", r.stdout)

    def test_task_name_is_reduced_to_safe_characters(self):
        r = self.rc("path", "a b/../c")
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("..", Path(r.stdout.strip()).name)


class RunControlRefusals(Project):
    """Cases where the script must stop with a message, change nothing and exit 1."""

    def assert_refused(self, r, text):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(text, r.stderr)

    def test_start_refuses_a_task_name_with_no_usable_characters(self):
        self.assert_refused(self.rc("start", "!!!"), "no usable characters")
        self.assertEqual([p.name for p in (self.root / "outputs").iterdir()], ["INDEX.md"])

    def test_start_and_path_refuse_a_git_ignored_task_folder(self):
        (self.root / ".gitignore").write_text("outputs/demo/\n", encoding="utf-8")
        for command in ("start", "path"):
            self.assert_refused(self.rc(command, "demo"), "git-ignored although outputs/ is not")
        self.assertFalse((self.root / "outputs" / "demo").exists())

    def test_accept_refuses_when_no_run_is_pending(self):
        self.assert_refused(self.rc("accept", "demo", "Q?"), "no run pending review")
        self.assertEqual(self.tags(), [])

    def test_accept_without_a_question_refuses_when_there_is_no_earlier_run(self):
        self.start_and_write()
        self.assert_refused(self.rc("accept", "demo"), "give the question")
        self.assertEqual(self.tags(), [])

    def test_a_refused_accept_leaves_the_pending_run_in_place(self):
        self.start_and_write()
        self.rc("accept", "demo")
        self.assertTrue((self.root / "outputs" / "demo" / "r.txt").exists())
        self.assertEqual(self.index_rows(), [])


class RunControlFolderMode(Project):
    tracked = False

    def test_each_start_makes_a_new_run_folder(self):
        for n in (1, 2):
            r = self.rc("start", "demo")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(r.stdout.strip().endswith(f"demo-{TODAY}-run{n}"))
        info = (self.root / "outputs" / f"demo-{TODAY}-run2" / "run_info.txt").read_text(encoding="utf-8")
        self.assertIn("mode: run folder", info)

    def test_accept_is_a_no_op(self):
        self.rc("start", "demo")
        r = self.rc("accept", "demo", "Q?")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Run folder mode", r.stdout)


class Archive(Project):
    def ac(self, *args):
        return run(ARCHIVE, *args, "--root", str(self.root))

    def accepted_run(self):
        self.start_and_write()
        self.accept(question="Q?")

    def test_version_flag_and_tag_message(self):
        self.assertEqual(run(ARCHIVE, "--version").stdout.strip(), f"archive_control.py {version_of(ARCHIVE)}")
        self.accepted_run()
        self.ac("archive", "demo")
        message = git(self.root, "tag", "-l", "--format=%(contents)", f"archive-demo-{TODAY}")
        self.assertIn(f"Archive control version: {version_of(ARCHIVE)}", message)

    def test_root_is_accepted_before_the_command(self):
        self.accepted_run()
        r = run(ARCHIVE, "--root", str(self.root), "list")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_archive_removes_folder_tags_and_marks_row(self):
        self.accepted_run()
        r = self.ac("archive", "demo")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertFalse((self.root / "outputs" / "demo").exists())
        self.assertIn(f"archive-demo-{TODAY}", self.tags())
        row = self.index_rows()[0]
        self.assertEqual((row[3], row[4]), ("archived", f"`archive-demo-{TODAY}`"))
        self.assertEqual(git(self.root, "status", "--porcelain"), "")
        self.assertIn("1 archived", self.ac("list").stdout)

    def test_restore_brings_folder_back_as_current(self):
        self.accepted_run()
        self.ac("archive", "demo")
        r = self.ac("restore", "demo")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.root / "outputs" / "demo" / "r.txt").read_text(encoding="utf-8"), "one")
        self.assertEqual(self.index_rows()[0][3], "current")

    def test_archive_refuses_uncommitted_changes(self):
        self.accepted_run()
        (self.root / "outputs" / "demo" / "r.txt").write_text("changed", encoding="utf-8")
        r = self.ac("archive", "demo")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("uncommitted", r.stderr)
        self.assertTrue((self.root / "outputs" / "demo").exists())

    def test_archive_refuses_a_task_without_a_current_row(self):
        self.start_and_write()
        r = self.rc("reject", "demo", "Q?")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.ac("archive", "demo")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("current", r.stderr)


class CheckRecords(Project):
    """check_records.py on a copy of the full-template stubs."""

    def setUp(self):
        super().setUp()
        for rel in ("data/DATA-NOTES.md", "records/DECISIONS.md", "records/HANDOFF.md", "products/PRODUCTS.md"):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(TEMPLATE / rel, self.root / rel)
        self.memory = Path(self.tmp.name) / "memory"
        self.memory.mkdir()
        (self.memory / "MEMORY.md").write_text("", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "records")

    def check(self):
        return run(CHECK, str(self.root), "--memory", str(self.memory))

    def test_version_flag_and_report_name_it(self):
        self.assertEqual(run(CHECK, "--version").stdout.strip(), f"check_records.py {version_of(CHECK)}")
        self.assertIn(f"check_records.py {version_of(CHECK)}", self.check().stdout)

    def test_root_option_works_like_the_positional_root(self):
        r = run(CHECK, "--root", str(self.root), "--memory", str(self.memory))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_clean_project_passes(self):
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_data_file_without_note_fails(self):
        (self.root / "data").mkdir(exist_ok=True)
        (self.root / "data" / "obs.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("obs.csv", r.stdout)

    def test_decision_citing_a_missing_path_fails(self):
        with (self.root / "records" / "DECISIONS.md").open("a", encoding="utf-8") as f:
            f.write("| 010126 | d | r | `nowhere/missing_file.py` |\n")
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing_file.py", r.stdout)

    def test_run_tag_without_index_row_fails(self):
        self.start_and_write()
        self.accept(question="Q?")
        idx = self.root / "outputs" / "INDEX.md"
        idx.write_text("\n".join(
            ln for ln in idx.read_text(encoding="utf-8").splitlines() if not ln.startswith("| `")) + "\n",
            encoding="utf-8")
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn(f"demo-{TODAY}-run1", r.stdout)

    def test_accepted_run_passes(self):
        self.start_and_write()
        self.accept(question="Q?")
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_archived_run_passes(self):
        self.start_and_write()
        self.accept(question="Q?")
        self.assertEqual(run(ARCHIVE, "archive", "demo", "--root", str(self.root)).returncode, 0)
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_pending_run_is_flagged_not_failed(self):
        self.start_and_write()
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("pending", r.stdout.lower())


def decision_rows(first, last, size=60):
    """Decision-log rows numbered first to last (the number is the six-digit date field)."""
    return [f"| {i:06d} | decision {i} " + "x" * size + " | reason | evidence |" for i in range(first, last + 1)]


class RotateRecords(Project):
    HEAD = ["# Decisions", "", "Header text.", "", "| Date | Decision | Reason | Evidence |", "|---|---|---|---|"]

    def write_log(self, rows, nl=NL):
        (self.root / "records").mkdir(exist_ok=True)
        text = nl.join(self.HEAD + rows) + nl
        with open(self.root / "records" / "DECISIONS.md", "w", encoding="utf-8", newline="") as f:
            f.write(text)

    def rows(self, name):
        text = (self.root / "records" / name).read_text(encoding="utf-8")
        return [ln for ln in text.splitlines() if ln.startswith("| 0")]

    def rot(self, *args):
        return run(ROTATE, "--root", str(self.root), *args)

    def test_version_flag(self):
        self.assertEqual(run(ROTATE, "--version").stdout.strip(), f"rotate_records.py {version_of(ROTATE)}")

    def test_dry_run_changes_nothing(self):
        self.write_log(decision_rows(1, 120))
        before = (self.root / "records" / "DECISIONS.md").read_bytes()
        r = self.rot()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Moving 20 rows", r.stdout)
        self.assertEqual((self.root / "records" / "DECISIONS.md").read_bytes(), before)
        self.assertFalse((self.root / "records" / "DECISIONS-archive.md").exists())

    def test_apply_moves_the_oldest_rows_and_loses_none(self):
        original = decision_rows(1, 120)
        self.write_log(original)
        self.assertEqual(self.rot("--apply").returncode, 0)
        self.assertEqual(self.rows("DECISIONS.md"), original[20:])
        self.assertEqual(self.rows("DECISIONS-archive.md"), original[:20])
        active = (self.root / "records" / "DECISIONS.md").read_text(encoding="utf-8")
        self.assertTrue(active.startswith(NL.join(self.HEAD)))
        self.assertIn("# Decisions archive", (self.root / "records" / "DECISIONS-archive.md").read_text(encoding="utf-8"))

    def test_a_second_run_does_nothing_and_a_later_run_appends_in_order(self):
        original = decision_rows(1, 120)
        self.write_log(original)
        self.rot("--apply")
        self.assertIn("nothing to move", self.rot("--apply").stdout)
        more = decision_rows(121, 125)
        self.write_log(original[20:] + more)
        self.assertEqual(self.rot("--apply").returncode, 0)
        self.assertEqual(self.rows("DECISIONS-archive.md"), original[:25])
        self.assertEqual(len(self.rows("DECISIONS.md")), 100)

    def test_max_lines_option(self):
        original = decision_rows(1, 30)
        self.write_log(original)
        self.rot("--apply", "--max-lines", "10")
        self.assertEqual(self.rows("DECISIONS.md"), original[20:])
        self.assertEqual(len(self.rows("DECISIONS-archive.md")), 20)

    def test_line_endings_are_kept(self):
        self.write_log(decision_rows(1, 105), nl=CRLF)
        self.rot("--apply")
        for name in ("DECISIONS.md", "DECISIONS-archive.md"):
            data = (self.root / "records" / name).read_bytes()
            self.assertEqual(data.count(CRLF.encode()), data.count(NL.encode()), name)

    def test_missing_log_is_refused(self):
        r = self.rot()
        self.assertEqual(r.returncode, 1)
        self.assertIn("not found", r.stderr)


class WrapupStatus(Project):
    """The handoff is stale when a changed file is newer than it."""

    def setUp(self):
        super().setUp()
        (self.root / "records").mkdir()
        self.work = self.root / "work.txt"
        self.work.write_text("one", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "work")
        self.handoff = self.root / "records" / "HANDOFF.md"

    def st(self, *args):
        return run(STATUS, "--root", str(self.root), *args)

    def times(self, work_age, handoff_age):
        """Write the work file and the handoff, then set their ages in seconds before now."""
        import time
        now = time.time()
        self.handoff.write_text("handoff", encoding="utf-8")
        self.work.write_text("two", encoding="utf-8")
        os.utime(self.work, (now - work_age, now - work_age))
        os.utime(self.handoff, (now - handoff_age, now - handoff_age))

    def test_version_flag(self):
        self.assertEqual(run(STATUS, "--version").stdout.strip(), f"wrapup_status.py {version_of(STATUS)}")

    def test_missing_handoff_is_stale(self):
        r = self.st()
        self.assertEqual(r.returncode, 1)
        self.assertIn("Handoff: missing", r.stdout)

    def test_handoff_written_after_the_changes_is_current(self):
        self.times(work_age=100, handoff_age=10)
        r = self.st()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("Status: CURRENT", r.stdout)

    def test_a_change_after_the_handoff_makes_it_stale(self):
        self.times(work_age=10, handoff_age=100)
        r = self.st()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("work.txt", r.stdout)
        self.assertIn("STALE", r.stdout)

    def test_an_unpushed_commit_counts_and_a_pushed_one_does_not(self):
        origin = Path(self.tmp.name) / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True, env=GIT_ENV)
        git(self.root, "remote", "add", "origin", str(origin))
        git(self.root, "push", "-q", "-u", "origin", "main")
        self.times(work_age=10, handoff_age=100)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "more work")
        self.assertEqual(self.st().returncode, 1, "an unpushed commit with a newer file is stale")
        git(self.root, "push", "-q")
        self.assertEqual(self.st().returncode, 0, "after the push nothing is changed")

    def test_quiet_prints_only_the_status_line(self):
        self.times(work_age=100, handoff_age=10)
        self.assertEqual(self.st("--quiet").stdout.strip().splitlines(), ["Status: CURRENT"])

    def test_counts_decision_lines_added_since_the_last_commit(self):
        rows = decision_rows(1, 3)
        (self.root / "records" / "DECISIONS.md").write_text(NL.join(rows[:1]) + NL, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "log")
        (self.root / "records" / "DECISIONS.md").write_text(NL.join(rows) + NL, encoding="utf-8")
        self.times(work_age=100, handoff_age=10)
        self.assertIn("Decision lines added since the last commit: 2", self.st().stdout)

    def test_a_folder_that_is_not_a_repository(self):
        plain = Path(self.tmp.name) / "plain"
        (plain / "records").mkdir(parents=True)
        self.assertEqual(run(STATUS, "--root", str(plain)).returncode, 1)
        (plain / "records" / "HANDOFF.md").write_text("x", encoding="utf-8")
        r = run(STATUS, "--root", str(plain))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("Not a git repository", r.stdout)


class CheckRecordsSize(CheckRecords):
    """Checks 12 and 13: the size of DECISIONS.md."""

    def add_rows(self, rows):
        with (self.root / "records" / "DECISIONS.md").open("a", encoding="utf-8", newline="") as f:
            f.write(NL.join(rows) + NL)

    def row(self, date, size):
        return f"| {date} | " + "x" * size + " | reason | evidence |"

    def test_a_row_over_800_is_a_flag_not_a_failure(self):
        self.add_rows([self.row("101126", 850)])
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertRegex(r.stdout, r"12\. DECISIONS.md rows: 1, average \d+ characters \(target 500 or less\); 1 flagged over 800, 0 failed")

    def test_a_new_row_over_1000_is_a_failure(self):
        self.add_rows([self.row("091126", 1100)])
        r = self.check()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("(failure)", r.stdout)

    def test_an_old_row_over_1000_is_only_a_flag(self):
        self.add_rows([self.row("080126", 1100), self.row("081126", 1100)])
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("2 flagged over 800, 0 failed", r.stdout)

    def test_too_many_rows_are_flagged_with_the_remedy(self):
        self.add_rows([self.row("010126", 40) for _ in range(12)])
        r = run(CHECK, str(self.root), "--memory", str(self.memory), "--max-lines", "10")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("12 rows (limit 10)", r.stdout)
        self.assertIn("rotate_records.py", r.stdout)

    def test_a_short_log_has_no_size_flags(self):
        self.add_rows([self.row("010126", 100)])
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("rotate_records.py", r.stdout)

    def test_the_rotation_script_clears_the_row_count_flag(self):
        self.add_rows([self.row("010126", 40) for _ in range(12)])
        self.assertEqual(run(ROTATE, "--root", str(self.root), "--apply", "--max-lines", "10").returncode, 0)
        r = run(CHECK, str(self.root), "--memory", str(self.memory), "--max-lines", "10")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("rotate_records.py", r.stdout)


class Deploy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.target = Path(self.tmp.name) / "claude"

    def dep(self, *args):
        return run(DEPLOY, *args, "--target", str(self.target))

    def test_status_on_empty_target_exits_1(self):
        r = self.dep("status")
        self.assertEqual(r.returncode, 1)
        self.assertIn("MISSING", r.stdout)

    def test_apply_needs_yes_without_a_terminal(self):
        r = subprocess.run([sys.executable, "-I", str(DEPLOY), "apply", "--target", str(self.target)],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 1)
        self.assertFalse(self.target.exists() and any(self.target.iterdir()))

    def test_apply_copies_then_status_is_in_sync(self):
        self.assertEqual(self.dep("apply", "--yes").returncode, 0)
        self.assertEqual(self.dep("status").returncode, 0)
        self.assertTrue((self.target / "CLAUDE.md").exists())
        self.assertTrue((self.target / "scripts" / "run_control.py").exists())

    def test_apply_backs_up_a_changed_live_file(self):
        self.dep("apply", "--yes")
        live = self.target / "CLAUDE.md"
        live.write_text(live.read_text(encoding="utf-8") + "local edit\n", encoding="utf-8")
        self.assertEqual(self.dep("apply", "--yes").returncode, 0)
        backups = list((self.target / "backups").glob("deploy-*/CLAUDE.md"))
        self.assertEqual(len(backups), 1)
        self.assertIn("local edit", backups[0].read_text(encoding="utf-8"))
        self.assertNotIn("local edit", live.read_text(encoding="utf-8"))

    def test_init_needs_yes_without_a_terminal_and_creates_nothing(self):
        r = subprocess.run([sys.executable, "-I", str(DEPLOY), "init", "--target", str(self.target)],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 1)
        self.assertFalse((self.target / "rules").exists())

    def test_init_creates_both_files_and_doctor_passes_after_apply(self):
        self.assertEqual(self.dep("init", "--yes").returncode, 0)
        for name, marker in (("machine.md", "machine-file-v1"), ("profile.md", "profile-file-v1")):
            self.assertIn(f"Marker: {marker}", (self.target / "rules" / name).read_text(encoding="utf-8"))
        self.assertEqual(self.dep("apply", "--yes").returncode, 0)
        r = self.dep("doctor")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_init_never_overwrites_an_existing_file(self):
        rules = self.target / "rules"
        rules.mkdir(parents=True)
        (rules / "profile.md").write_text("my own rules", encoding="utf-8")
        self.assertEqual(self.dep("init", "--yes").returncode, 0)
        self.assertEqual((rules / "profile.md").read_text(encoding="utf-8"), "my own rules")
        self.assertTrue((rules / "machine.md").exists())
        self.assertIn("Nothing to create", self.dep("init", "--yes").stdout)

    def test_help_prints_the_deployment_section(self):
        r = self.dep("help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("First-time setup", r.stdout)
        self.assertIn("deploy.py init", r.stdout)

    def test_doctor_reports_missing_user_files(self):
        r = self.dep("doctor")
        self.assertEqual(r.returncode, 1)
        self.assertIn("MISSING", r.stdout)

    def test_doctor_accepts_filled_files_and_flags_a_missing_path(self):
        rules = self.target / "rules"
        rules.mkdir(parents=True)
        (rules / "profile.md").write_text("Marker: profile-file-v1\n\nrule\n", encoding="utf-8")
        ghost = Path(self.tmp.name) / "no_such" / "python.exe"
        (rules / "machine.md").write_text(f'Marker: machine-file-v1\n\n- Python: `"{ghost}"`\n', encoding="utf-8")
        r = self.dep("doctor")
        self.assertEqual(r.returncode, 1)
        self.assertIn("NOT FOUND", r.stdout)


class HookPushCheck(Project):
    """The push hook blocks `git push` (exit 2) only while the handoff is stale."""

    def setUp(self):
        super().setUp()
        (self.root / "records").mkdir()
        self.work = self.root / "work.txt"
        self.work.write_text("one", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "work")
        self.handoff = self.root / "records" / "HANDOFF.md"

    def times(self, work_age, handoff_age):
        import time
        now = time.time()
        self.handoff.write_text("handoff", encoding="utf-8")
        self.work.write_text("two", encoding="utf-8")
        os.utime(self.work, (now - work_age, now - work_age))
        os.utime(self.handoff, (now - handoff_age, now - handoff_age))

    def hook(self, command, tool="Bash", cwd=None):
        call = json.dumps({"tool_name": tool, "tool_input": {"command": command}, "cwd": str(cwd or self.root)})
        return subprocess.run([sys.executable, "-I", str(HOOK)], input=call, capture_output=True, text=True)

    def test_stale_handoff_blocks_a_push(self):
        self.times(work_age=10, handoff_age=100)
        r = self.hook("git push origin main")
        self.assertEqual(r.returncode, 2)
        self.assertIn("checkpoint", r.stderr)

    def test_current_handoff_allows_a_push(self):
        self.times(work_age=100, handoff_age=10)
        self.assertEqual(self.hook("git push").returncode, 0)

    def test_other_commands_and_tools_are_not_checked(self):
        self.times(work_age=10, handoff_age=100)
        self.assertEqual(self.hook("git commit -m x").returncode, 0)
        self.assertEqual(self.hook("echo git pushing").returncode, 0)
        self.assertEqual(self.hook("git push", tool="Read").returncode, 0)

    def test_a_folder_without_records_is_not_checked(self):
        plain = Path(self.tmp.name) / "plain"
        plain.mkdir()
        self.assertEqual(self.hook("git push", cwd=plain).returncode, 0)

    def test_bad_input_fails_open(self):
        r = subprocess.run([sys.executable, "-I", str(HOOK)], input="not json", capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)

    def test_version_flag(self):
        self.assertEqual(run(HOOK, "--version").stdout.strip(), f"hook_push_check.py {version_of(HOOK)}")


class HookGuard(Project):
    """hook_guard.py blocks writes to data/ and to listed paths, and nothing else."""

    def hook(self, tool, cwd=None, **args):
        call = json.dumps({"tool_name": tool, "tool_input": args, "cwd": str(cwd or self.root)})
        return subprocess.run([sys.executable, "-I", str(GUARD)], input=call, capture_output=True, text=True)

    def blocked(self, tool, **args):
        return self.hook(tool, **args).returncode == 2

    def test_version_flag(self):
        self.assertEqual(run(GUARD, "--version").stdout.strip(), f"hook_guard.py {version_of(GUARD)}")

    def test_file_tools_are_blocked_under_data(self):
        for tool in ("Write", "Edit", "MultiEdit"):
            self.assertTrue(self.blocked(tool, file_path=str(self.root / "data" / "a.csv")), tool)
        self.assertTrue(self.blocked("Write", file_path="data/sub/b.csv"))
        self.assertTrue(self.blocked("NotebookEdit", notebook_path=str(self.root / "data" / "n.ipynb")))

    def test_file_tools_elsewhere_and_exempt_files_are_allowed(self):
        self.assertFalse(self.blocked("Write", file_path=str(self.root / "outputs" / "demo" / "a.csv")))
        self.assertFalse(self.blocked("Write", file_path=str(self.root / "code" / "data" / "x.py")))
        self.assertFalse(self.blocked("Write", file_path=str(self.root / "data" / "DATA-NOTES.md")))
        self.assertFalse(self.blocked("Write", file_path=str(self.root / "data" / "sub" / "README.md")))
        self.assertTrue(self.blocked("Write", file_path=str(self.root / "data" / "sub" / "DATA-NOTES.md")))
        self.assertFalse(self.blocked("Read", file_path=str(self.root / "data" / "a.csv")))

    def test_bash_writes_to_data_are_blocked(self):
        for cmd in ("echo x > data/a.csv", "echo x >> data/a.csv", "rm data/a.csv", "rm -rf ./data",
                    "mv data/a.csv outputs/", "sed -i s/a/b/ data/a.csv", "cp outputs/x.csv data/a.csv",
                    "ls; rm data/a.csv", 'Set-Content -Path "data/a.csv" -Value x', "tee data/a.csv"):
            self.assertTrue(self.blocked("Bash", command=cmd), cmd)
        self.assertTrue(self.blocked("Bash", command=f"rm {self.root.as_posix()}/data/a.csv"))
        self.assertTrue(self.blocked("Bash", command="rm " + str(self.root / "data" / "a.csv")))

    def test_bash_reads_and_other_folders_are_allowed(self):
        for cmd in ("cat data/a.csv", "head -3 data/a.csv > outputs/x.txt", "cp data/a.csv outputs/a.csv",
                    "rm outputs/data/a.csv", "ls data", "git status", "rm -rf build"):
            self.assertFalse(self.blocked("Bash", command=cmd), cmd)

    def test_listed_paths_are_protected(self):
        # the config file sits next to the scripts folder: rules/protected-paths.txt
        scripts = Path(self.tmp.name) / "claude" / "scripts"
        scripts.mkdir(parents=True)
        shutil.copy(GUARD, scripts / "hook_guard.py")
        (scripts.parent / "rules").mkdir()
        lib = Path(self.tmp.name) / "lib" / "My.enl"
        (scripts.parent / "rules" / "protected-paths.txt").write_text(
            "# library" + chr(10) + lib.parent.as_posix() + chr(10), encoding="utf-8")

        def go(tool, **args):
            call = json.dumps({"tool_name": tool, "tool_input": args, "cwd": str(self.root)})
            return subprocess.run([sys.executable, "-I", str(scripts / "hook_guard.py")], input=call,
                                  capture_output=True, text=True).returncode
        self.assertEqual(go("Write", file_path=str(lib)), 2)
        self.assertEqual(go("Bash", command=f"rm {lib.as_posix()}"), 2)
        self.assertEqual(go("Bash", command=f"cat {lib.as_posix()}"), 0)
        self.assertEqual(go("Write", file_path=str(self.root / "x.txt")), 0)

    def test_the_off_switch_and_bad_input_fail_open(self):
        call = json.dumps({"tool_name": "Write", "tool_input": {"file_path": "data/a.csv"}, "cwd": str(self.root)})
        env = dict(os.environ, CLAUDE_HOOK_GUARD="off")
        r = subprocess.run([sys.executable, "-I", str(GUARD)], input=call, capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0)
        r = subprocess.run([sys.executable, "-I", str(GUARD)], input="not json", capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)


class HookConfirm(unittest.TestCase):
    def hook(self, command, tool="Bash"):
        call = json.dumps({"tool_name": tool, "tool_input": {"command": command}})
        return subprocess.run([sys.executable, "-I", str(CONFIRM)], input=call, capture_output=True, text=True)

    def asks(self, command, **kw):
        r = self.hook(command, **kw)
        self.assertEqual(r.returncode, 0)
        return bool(r.stdout.strip()) and json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "ask"

    def test_version_flag(self):
        self.assertEqual(run(CONFIRM, "--version").stdout.strip(), f"hook_confirm.py {version_of(CONFIRM)}")

    def test_the_users_decisions_ask(self):
        for cmd in ('python rc/run_control.py accept demo "Q?" --root p', "python run_control.py reject demo",
                    "python run_control.py --root p discard demo", "python archive_control.py archive demo",
                    "python archive_control.py restore demo --root p", "ls && python run_control.py accept demo"):
            self.assertTrue(self.asks(cmd), cmd)

    def test_other_calls_do_not_ask(self):
        for cmd in ("python run_control.py start demo", "python run_control.py check demo",
                    "python run_control.py status", "python archive_control.py list", "git status"):
            self.assertFalse(self.asks(cmd), cmd)
        self.assertFalse(self.asks("python run_control.py accept demo", tool="Read"))

    def test_bad_input_is_allowed(self):
        r = subprocess.run([sys.executable, "-I", str(CONFIRM)], input="x", capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout), (0, ""))


class RunControlDataCheck(Project):
    def setUp(self):
        super().setUp()
        (self.root / "data").mkdir()
        self.csv = self.root / "data" / "a.csv"
        self.csv.write_text("1,2", encoding="utf-8")

    def test_unchanged_data_passes_and_state_is_recorded(self):
        self.start_and_write()
        info = (self.root / "outputs" / "demo" / "run_info.txt").read_text(encoding="utf-8")
        self.assertRegex(info, r"data state at start: 1[|][0-9a-f]{16}[|]\d+")
        self.assertIn("Data check: pass", self.rc("check", "demo").stdout)
        self.accept(question="Q?")

    def test_changed_data_fails_check_and_refuses_accept(self):
        self.start_and_write()
        self.csv.write_text("1,2,3,4", encoding="utf-8")
        later = self.csv.stat().st_mtime + 100
        os.utime(self.csv, (later, later))
        r = self.rc("check", "demo")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("a.csv", r.stdout)
        r = self.rc("accept", "demo", "Q?")
        self.assertEqual(r.returncode, 1)
        self.assertIn("data/ changed", r.stderr)
        self.assertNotIn(f"demo-{TODAY}-run1", git(self.root, "tag", "-l"))

    def test_data_changed_ok_passes_it(self):
        self.start_and_write()
        self.csv.write_text("changed", encoding="utf-8")
        self.assertEqual(self.rc("accept", "demo", "Q?", "--data-changed-ok").returncode, 0)

    def test_a_removed_file_is_a_change(self):
        self.start_and_write()
        self.csv.unlink()
        self.assertIn("1 files then, 0 now", self.rc("check", "demo").stdout)

    def test_notes_and_readme_changes_are_ignored_and_no_data_folder_is_skipped(self):
        self.start_and_write()
        (self.root / "data" / "DATA-NOTES.md").write_text("notes", encoding="utf-8")
        (self.root / "data" / "README.md").write_text("r", encoding="utf-8")
        self.assertEqual(self.rc("check", "demo").returncode, 0)
        shutil.rmtree(self.root / "data")
        self.start_and_write(task="other")
        info = (self.root / "outputs" / "other" / "run_info.txt").read_text(encoding="utf-8")
        self.assertNotIn("data state", info)


class DeployHooks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.target = Path(self.tmp.name) / "claude"

    def dep(self, *args):
        return run(DEPLOY, *args, "--target", str(self.target))

    def settings(self):
        return json.loads((self.target / "settings.json").read_text(encoding="utf-8"))

    def test_hooks_merges_keeps_settings_and_is_idempotent(self):
        self.target.mkdir()
        (self.target / "settings.json").write_text(json.dumps({"theme": "x"}), encoding="utf-8")
        self.assertEqual(self.dep("hooks", "--yes").returncode, 0)
        cfg = self.settings()
        self.assertEqual(cfg["theme"], "x")
        groups = cfg["hooks"]["PreToolUse"]
        self.assertEqual(len(groups), 3)
        commands = [g["hooks"][0]["command"] for g in groups]
        for name in ("hook_push_check.py", "hook_guard.py", "hook_confirm.py"):
            self.assertEqual(sum(name in c for c in commands), 1, name)
        self.assertIn("Write", next(g for g in groups if "hook_guard" in g["hooks"][0]["command"])["matcher"])
        self.assertTrue(list((self.target / "backups").glob("hooks-*/settings.json")))
        self.assertIn("already installed", self.dep("hooks", "--yes").stdout)
        self.assertEqual(len(self.settings()["hooks"]["PreToolUse"]), 3)

    def test_hooks_uses_the_python_named_in_machine_md(self):
        (self.target / "rules").mkdir(parents=True)
        fake = Path(self.tmp.name) / "launcher" / "py.exe"
        fake.parent.mkdir()
        fake.write_text("x", encoding="utf-8")
        (self.target / "rules" / "machine.md").write_text(
            "- Python: Bash `\"" + fake.as_posix() + "\"`. Plain python is not used." + chr(10), encoding="utf-8")
        self.assertEqual(self.dep("hooks", "--yes").returncode, 0)
        for g in self.settings()["hooks"]["PreToolUse"]:
            command = g["hooks"][0]["command"]
            self.assertTrue(command.startswith('"' + fake.as_posix() + '"'), command)

    def test_hooks_needs_yes_without_a_terminal(self):
        r = subprocess.run([sys.executable, "-I", str(DEPLOY), "hooks", "--target", str(self.target)],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 1)
        self.assertFalse((self.target / "settings.json").exists())


if __name__ == "__main__":
    unittest.main()
