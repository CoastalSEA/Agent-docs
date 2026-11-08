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


if __name__ == "__main__":
    unittest.main()
