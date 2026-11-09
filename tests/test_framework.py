r"""Consistency tests for the framework files in this repository. Standard library only.

Run from the repository root:  python -m unittest discover -s tests   (or: python tests/test_framework.py)
Checks that the shared files hold no machine-specific text, that the project template copy equals its
master, that every skill's frontmatter parses, that the user-file forms carry their marker lines, that every
script has a version, and that deploy.py installs every script and skill. Reads files only; writes nothing.

Created using: $\text {Created using: }\ claude-sonnet-5-5-\text{v}1.0-\text {date: }081126$
"""
import importlib.util
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".py", ".sh", ".json", ".txt", ".yml", ".yaml"}

# Files that may name this machine or the user: the tests that hold the patterns, and local notes.
PERSONAL_OK = ("tests/", "working_docs/", "outputs/")
# Generic patterns: a user-profile path, an e-mail address. Anything specific to one user (a name, a library, a folder)
# goes in tests/personal_patterns.local.txt, one regular expression per line. That file is git-ignored.
PERSONAL = [
    r"[A-Za-z]:[\\/]Users[\\/](?![<%$\{.]|user\b|username\b|you\b|name\b)[^\\/\s`\"']+",
    r"/(?:Users|home)/(?![<$\{.]|user\b|username\b|you\b|name\b|runner\b)[A-Za-z][^/\s`\"']*",
    r"[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com)[A-Za-z0-9-]+\.[A-Za-z]{2,}",
]
LOCAL = REPO / "tests" / "personal_patterns.local.txt"
if LOCAL.exists():
    PERSONAL += [ln.strip() for ln in LOCAL.read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.startswith("#")]


def tracked_files():
    r = subprocess.run(["git", "-C", str(REPO), "ls-files"], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return [REPO / ln for ln in r.stdout.splitlines() if (REPO / ln).is_file()]
    return [p for p in REPO.rglob("*") if p.is_file() and ".git" not in p.parts]


def read(p):
    return p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def rel(p):
    return p.relative_to(REPO).as_posix()


def load_deploy():
    spec = importlib.util.spec_from_file_location("deploy", REPO / "deploy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SharedFiles(unittest.TestCase):
    def test_no_machine_specific_text_in_shared_files(self):
        pat = re.compile("|".join(PERSONAL))
        hits = []
        for p in tracked_files():
            r = rel(p)
            if p.suffix.lower() not in TEXT_SUFFIXES or r.startswith(PERSONAL_OK):
                continue
            for n, line in enumerate(read(p).split("\n"), 1):
                if pat.search(line):
                    hits.append(f"{r}:{n}: {line.strip()[:100]}")
        self.assertEqual(hits, [], "machine-specific text in shared files:\n" + "\n".join(hits))

    def test_public_decision_log_has_no_quotes_or_session_citations(self):
        log = REPO / "records" / "DECISIONS.md"
        if not log.exists():
            self.skipTest("no records/DECISIONS.md")
        text = read(log)
        self.assertNotRegex(text, r"user: ", "user quotes belong in the private log")
        self.assertNotRegex(text, r"log [0-9a-f]{8}", "session-log citations belong in the private log")

    def test_project_template_copy_equals_its_master(self):
        master = REPO / "claude-md" / "project-CLAUDE.md"
        copy = REPO / "claude-md" / "project-template" / "CLAUDE.md"
        self.assertEqual(read(master), read(copy), "run deploy.py apply to regenerate the copy")

    def test_project_templates_name_no_removed_paths(self):
        banned = ["start_run(", "records/check_records.py", "code/archive_control.py", "code/run_control.py"]
        files = [p for p in (REPO / "claude-md").rglob("*.md")
                 if "global-CLAUDE" not in p.name and "user-files" not in p.parts and p.name != "README.md"]
        hits = [f"{rel(p)}: {b}" for p in files for b in banned if b in read(p)]
        self.assertEqual(hits, [])

    def test_project_templates_and_global_rules_use_forward_slashes(self):
        files = [p for p in (REPO / "claude-md").rglob("*.md") if "user-files" not in p.parts]
        hits = []
        for p in files:
            for n, line in enumerate(read(p).split("\n"), 1):
                if re.search(r"[A-Za-z0-9_>)]\\[A-Za-z0-9_<`.]", line):
                    hits.append(f"{rel(p)}:{n}: {line.strip()[:80]}")
        self.assertEqual(hits, [], "backslash paths in shared templates:\n" + "\n".join(hits))

    def test_user_file_forms_carry_their_marker_lines(self):
        deploy = load_deploy()
        for name, marker in deploy.MARKERS.items():
            form = REPO / "claude-md" / "user-files" / (name[:-3] + ".example.md")
            self.assertIn(f"Marker: {marker}", read(form), form.name)

    def test_global_rules_point_to_both_user_files(self):
        text = read(REPO / "claude-md" / "global-CLAUDE.md")
        for name in ("machine.md", "profile.md"):
            self.assertIn(name, text)


class Readme(unittest.TestCase):
    def listed_in_structure(self):
        text = read(REPO / "README.md")
        nl, fence = chr(10), chr(96) * 3
        head = text.index("## Structure")
        start = text.index(nl, text.index(fence, head)) + 1
        end = text.index(fence, start)
        return {ln.split()[0].rstrip("/") for ln in text[start:end].split(nl) if ln.strip()}

    def test_structure_list_matches_the_top_level_folders(self):
        tracked = {rel(p).split("/")[0] for p in tracked_files() if "/" in rel(p)}
        folders = {n for n in tracked if not n.startswith(".")}
        listed = self.listed_in_structure()
        self.assertEqual(sorted(folders - listed), [], "folders missing from the README Structure list")
        missing = [n for n in listed if not (REPO / n).exists()]
        self.assertEqual(missing, [], "README Structure lists names that do not exist")


class InitOutput(unittest.TestCase):
    """The text that `deploy.py init` writes must follow the blank forms."""

    def facts(self, windows):
        return {"windows": windows, "bash_form": windows, "os": "Windows 11" if windows else "Linux",
                "shells": "Git Bash (the Bash tool) and PowerShell 5.1" if windows else "bash", "home": "/home/u",
                "python": Path("/usr/bin/python3"), "plain_python": "no (not on PATH)",
                "pip": "in any environment (no externally-managed marker was found)", "tools": []}

    def headings(self, text):
        return [ln for ln in text.split(chr(10)) if ln.startswith("#")]

    def test_machine_text_has_the_marker_and_headings_of_the_form(self):
        deploy = load_deploy()
        form = read(REPO / "claude-md" / "user-files" / "machine.example.md")
        for windows in (False, True):
            text = deploy.render_machine(self.facts(windows), Path("/s/scripts"), Path("/r"), Path("/c"), today="010101")
            self.assertIn("Marker: machine-file-v1", text)
            self.assertNotIn("Copy this form to", text)
            self.assertEqual([h for h in self.headings(form) if h in self.headings(text)], self.headings(text))
            self.assertIn("run_control.py", text)

    def test_windows_text_gives_both_shell_forms(self):
        deploy = load_deploy()
        text = deploy.render_machine(self.facts(True), Path("C:/s/scripts"), Path("C:/r"), Path("C:/c"), today="010101")
        self.assertIn("Bash `", text)
        self.assertIn("PowerShell `", text)

    def test_profile_text_has_the_marker_and_headings_of_the_form(self):
        deploy = load_deploy()
        form = read(REPO / "claude-md" / "user-files" / "profile.example.md")
        text = deploy.render_profile(today="010101")
        self.assertIn("Marker: profile-file-v1", text)
        self.assertNotIn("Copy this form to", text)
        self.assertEqual(self.headings(text), self.headings(form))


class Skills(unittest.TestCase):
    def test_every_skill_frontmatter_parses(self):
        skills = sorted((REPO / "skills").glob("*/SKILL.md"))
        self.assertTrue(skills)
        r = subprocess.run([sys.executable, "-I", str(REPO / "skills" / "check_frontmatter.py"),
                            *map(str, skills)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_descriptions_are_within_the_limit(self):
        skills = sorted((REPO / "skills").glob("*/SKILL.md"))
        r = subprocess.run([sys.executable, "-I", str(REPO / "skills" / "check_frontmatter.py"),
                            *map(str, skills)], capture_output=True, text=True)
        self.assertNotIn("warning", r.stdout)

    def test_a_long_description_gives_a_warning_and_not_a_failure(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            f = Path(d) / "SKILL.md"
            f.write_text("---\nname: x\ndescription: " + "word " * 80 + "\n---\nbody\n", encoding="utf-8")
            r = subprocess.run([sys.executable, "-I", str(REPO / "skills" / "check_frontmatter.py"), str(f)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("warning: description is", r.stdout)

    def test_skills_name_machine_md_not_a_literal_command(self):
        for p in (REPO / "skills").glob("*/SKILL.md"):
            self.assertNotRegex(read(p), r"python3?\.\d+\.exe", rel(p))


class Scripts(unittest.TestCase):
    def test_every_script_has_a_version_and_the_flag(self):
        for p in sorted((REPO / "scripts").glob("*.py")):
            version = re.search(r'^VERSION = "([^"]+)"', read(p), re.M)
            self.assertIsNotNone(version, f"{p.name} has no VERSION")
            r = subprocess.run([sys.executable, "-I", str(p), "--version"], capture_output=True, text=True)
            self.assertEqual(r.stdout.strip(), f"{p.name} {version.group(1)}")


class Deploy(unittest.TestCase):
    def setUp(self):
        self.deploy = load_deploy()
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.items = self.deploy.items(Path(self.tmp.name))

    def sources(self):
        return {src for _, src, _ in self.items}

    def test_deploy_installs_every_script_and_global_rules(self):
        for p in (REPO / "scripts").glob("*.py"):
            self.assertIn(p, self.sources(), p.name)
        self.assertIn(REPO / "claude-md" / "global-CLAUDE.md", self.sources())

    def test_deploy_installs_every_skill_file_except_docs(self):
        for skill in (REPO / "skills").glob("*/SKILL.md"):
            for f in skill.parent.rglob("*"):
                if f.is_file() and "__pycache__" not in f.parts:
                    in_docs = "docs" in f.relative_to(skill.parent).parts[:-1]
                    self.assertEqual(f in self.sources(), not in_docs, rel(f))


if __name__ == "__main__":
    unittest.main()
