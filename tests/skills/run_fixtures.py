r"""Run a skill on a fixture with a fresh headless Claude Code session and check what it produced.

Created using: $\text {Created using: }\ claude-sonnet-5-5-\text{v}5.5-\text {date: }091126$

Each fixture builds a small synthetic project with a known correct answer, starts `claude -p` in it with a
plain request that names the skill, then checks the files the session wrote and the session transcript.
The checks look for planted facts and for things that must not happen. They do not compare wording.

This script makes model calls, so it is run on demand and never from the unit tests or CI. It uses the live
Claude configuration (the installed skills, the run control script and `machine.md`), so it tests what is
deployed. The project-disclosure fixture writes synthetic session logs into `~/.claude/projects/` under
folder names made from the temporary project path, and removes them afterwards.

Usage: python tests/skills/run_fixtures.py [skill ...] [--list] [--keep] [--timeout SECONDS]
                                           [--claude PATH] [--permission-mode MODE] [--out DIR]
                                           [--estuary-doc PATH] [--test-library PATH] [--external]
  skill      project-disclosure, analysis-adversary, proofread, citation-check, literature-search,
             literature-search-external (default: all that can run)
  --list     print the fixtures and their checks, and run nothing
  --keep     keep the temporary project and its logs
  --timeout  seconds allowed for each session (default: 900, or 1800 for proofread and citation-check)
  --estuary-doc PATH   the source .doc for the proofread fixture (default working_docs/Estuary Notes.doc);
             the fixture needs Microsoft Word and is skipped without it
  --test-library PATH  the .enl file of the test EndNote library for the citation-check and literature-search
             fixtures (or set FIXTURE_ENDNOTE_LIBRARY); a fixture is skipped without it
  --external  also run literature-search-external, which sends a query to OpenAlex (skipped otherwise)
  --claude   the claude command (default: the one on PATH)
  --permission-mode  the mode for the sessions (default auto, as in interactive use; a headless session
             started in the default mode cannot get approval for run control or Python commands)
  --out      folder for the results (default: working_docs/skill-runs under the repository)
Inputs:  the live Claude configuration; `claude` on PATH.
Outputs: <out>/<skill>-<DDMMYY-HHMM>/ with reply.txt, the saved deliverable and checks.json; a table on standard output.
Exit:    0 if every check of every fixture that ran passed (a skipped fixture is not a failure); 1 otherwise.
Version: see VERSION; `--version` prints it.
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

VERSION = "1.2"
REPO = Path(__file__).resolve().parents[2]
CLAUDE_HOME = Path.home() / ".claude"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def project_key(path):
    """The folder name Claude Code uses under ~/.claude/projects for a working directory."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(Path(path).resolve()))


def date_forms(iso):
    """The usual ways to write a date such as 2026-03-02."""
    y, m, d = (int(x) for x in iso.split("-"))
    name = MONTHS[m - 1]
    return [f"{y:04d}-{m:02d}-{d:02d}", f"{d:02d}/{m:02d}/{y}", f"{d:02d}-{m:02d}-{y}", f"{d} {name} {y}",
            f"{d:02d} {name} {y}", f"{name} {d}, {y}", f"{d:02d}{m:02d}{y % 100:02d}", f"{y:04d}/{m:02d}/{d:02d}",
            f"{d} {name[:3]} {y}", f"{d:02d} {name[:3]} {y}"]


def has_date(text, iso):
    return any(form in text for form in date_forms(iso))


def tree_hashes(root, skip=("outputs",)):
    """{relative path: sha1} for every file under root except the folders named in skip."""
    found = {}
    for f in sorted(Path(root).rglob("*")):
        if f.is_file() and f.relative_to(root).parts[0] not in skip:
            found[f.relative_to(root).as_posix()] = hashlib.sha1(f.read_bytes()).hexdigest()
    return found


def jsonl(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


class Fixture:
    name = ""
    checks_listed = ()
    timeout = 900
    max_turns = 30

    def extra_args(self, root):
        """Extra arguments for the claude command."""
        return []

    def build(self, tmp, args=None):
        """Create the project under tmp; return its root."""
        raise NotImplementedError

    def prompt(self, root):
        raise NotImplementedError

    def check(self, root, reply, before):
        """Return [(check name, passed, detail)]."""
        raise NotImplementedError

    def log_folders(self, root):
        """Folders under ~/.claude/projects that this fixture owns, to remove afterwards."""
        return [project_key(root)]

    def result_text(self, root, name):
        """The text of the first file called `name` under root/outputs, or None."""
        found = sorted((root / "outputs").rglob(name)) if (root / "outputs").is_dir() else []
        return found[0].read_text(encoding="utf-8", errors="replace") if found else None


# ---------------------------------------------------------------------------------------------------------
class ProjectDisclosure(Fixture):
    name = "project-disclosure"
    SECRET = "sk-ant-FIXTURE0123456789abcdef"
    S1_DATE, S2_DATE, S3_DATE, DECOY_DATE = "2026-03-02", "2026-03-09", "2026-03-16", "2026-03-20"
    checks_listed = (
        "AI-DISCLOSURE.md is written and is the only file in the output folder",
        "the three fixture sessions are found (their prompts and dates appear)",
        "the decoy session in the sibling folder Alpha-Old is left out",
        "both logged model ids are reported",
        "permission modes auto and default are both reported; the subagent mode is MISSING",
        "the secret in a prompt is not reproduced and a redaction is noted",
        "the refused Write is marked as attempted",
        "the subfolder is named as part of the scope",
        "no conclusion about human oversight is drawn",
        "the reply reports the run as pending and does not accept it",
        "the project files are unchanged",
    )

    def build(self, tmp, args=None):
        self.base = Path(tmp)
        root = self.base / "Alpha"
        (root / "analysis").mkdir(parents=True)
        (root / "data").mkdir()
        (root / "data" / "decay.csv").write_text("t,y\n0,100\n1,74\n2,55\n", encoding="utf-8")
        self.root = root.resolve()
        self.sub = self.root / "analysis"
        self.decoy = (self.base / "Alpha-Old").resolve()
        self.decoy.mkdir()
        self.s1, self.s2, self.s3, self.s4 = (str(uuid.uuid4()) for _ in range(4))
        projects = CLAUDE_HOME / "projects"
        self._session(projects / project_key(self.root), self.s1, self.root, "claude-sonnet-5-5", self.S1_DATE, [
            ("default", "Plot the decay curve in data/decay.csv", [
                ("Read", {"file_path": str(self.root / "data" / "decay.csv")}, "t,y", False),
                ("Write", {"file_path": str(self.root / "plot.py"), "content": "print(1)"}, "File created", False),
                ("Bash", {"command": "python plot.py"}, "1", False)])])
        self._session(projects / project_key(self.sub), self.s2, self.sub, "claude-opus-5-5", self.S2_DATE, [
            ("auto", "Fit the decay with a log transform", [
                ("Edit", {"file_path": str(self.sub / "fit.py"), "old_string": "a", "new_string": "b"}, "Edited", False)]),
            ("default", f"Use my key {self.SECRET} for the upload step", [
                ("Write", {"file_path": str(self.sub / "notes.md"), "content": "x"}, "Permission denied", True)])])
        self._session(projects / project_key(self.root), self.s3, self.root, "claude-sonnet-5-5", self.S3_DATE, [
            ("default", "Summarise the repository layout", [])])
        agent = projects / project_key(self.root) / self.s3 / "subagents"
        sid = "agent-a1"
        jsonl(agent / f"{sid}.jsonl", [
            self._user(self.root, self.s3, self.S3_DATE + "T10:01:00.000Z", "look at the data files", None),
            self._assistant(self.s3, "claude-sonnet-5-5", self.S3_DATE + "T10:01:05.000Z",
                            [self._use("toolu_sub1", "Read", {"file_path": str(self.root / "data" / "decay.csv")})]),
            self._result(self.root, self.s3, self.S3_DATE + "T10:01:06.000Z", "toolu_sub1", "t,y", False)])
        (agent / f"{sid}.meta.json").write_text(json.dumps({"agentType": "Explore", "description": "look around"}),
                                                encoding="utf-8")
        self._session(projects / project_key(self.decoy), self.s4, self.decoy, "claude-sonnet-5-5", self.DECOY_DATE, [
            ("default", "DECOYMARKER prompt from a sibling folder", [])])
        self.before = tree_hashes(self.root)
        return self.root

    def log_folders(self, root):
        return [project_key(self.root), project_key(self.sub), project_key(self.decoy)]

    @staticmethod
    def _use(tid, name, args):
        return {"type": "tool_use", "id": tid, "name": name, "input": args}

    def _user(self, cwd, sid, ts, text, mode):
        e = {"parentUuid": None, "isSidechain": False, "type": "user", "message": {"role": "user", "content": text},
             "uuid": str(uuid.uuid4()), "timestamp": ts, "userType": "external", "entrypoint": "cli", "cwd": str(cwd),
             "sessionId": sid, "version": "2.1.321"}
        if mode:
            e["permissionMode"] = mode
        return e

    def _assistant(self, sid, model, ts, content):
        return {"parentUuid": None, "isSidechain": False, "type": "assistant", "uuid": str(uuid.uuid4()),
                "timestamp": ts, "sessionId": sid,
                "message": {"model": model, "id": "msg_" + uuid.uuid4().hex[:12], "type": "message",
                            "role": "assistant", "content": content, "stop_reason": "tool_use"}}

    def _result(self, cwd, sid, ts, tid, text, is_error):
        return {"parentUuid": None, "isSidechain": False, "type": "user", "uuid": str(uuid.uuid4()), "timestamp": ts,
                "userType": "external", "entrypoint": "cli", "cwd": str(cwd), "sessionId": sid, "version": "2.1.321",
                "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": text,
                                                         "is_error": is_error}]}}

    def _session(self, folder, sid, cwd, model, day, turns):
        entries, minute, n = [], 0, 0
        for mode, prompt, calls in turns:
            minute += 1
            ts = f"{day}T09:{minute:02d}:00.000Z"
            entries.append(self._user(cwd, sid, ts, prompt, mode))
            for name, args, result, is_error in calls:
                n += 1
                tid = f"toolu_{sid[:6]}{n}"
                entries.append(self._assistant(sid, model, f"{day}T09:{minute:02d}:10.000Z", [self._use(tid, name, args)]))
                entries.append(self._result(cwd, sid, f"{day}T09:{minute:02d}:11.000Z", tid, result, is_error))
            entries.append(self._assistant(sid, model, f"{day}T09:{minute:02d}:30.000Z", [{"type": "text", "text": "Done."}]))
        jsonl(folder / f"{sid}.jsonl", entries)

    def prompt(self, root):
        return ("Use the project-disclosure skill to draft the AI-use disclosure for this project. Do not ask me "
                "questions. When the skill has returned, tell me where the file was written and whether the run is "
                "pending review.")

    def check(self, root, reply, before):
        text = self.result_text(root, "AI-DISCLOSURE.md")
        out = []

        def add(name, ok, detail=""):
            out.append((name, bool(ok), detail))

        folder = next(iter(sorted((root / "outputs").glob("project-disclosure-Alpha*"))), None) if (root / "outputs").is_dir() else None
        files = sorted(p.name for p in folder.iterdir()) if folder else []
        only = [f for f in files if f != "run_info.txt"] == ["AI-DISCLOSURE.md"]
        add(self.checks_listed[0], text is not None and only, f"files in {folder.name if folder else 'no folder'}: {files}")
        t = text or ""
        low = t.lower()
        found = ["Plot the decay curve" in t or has_date(t, self.S1_DATE),
                 "log transform" in t or has_date(t, self.S2_DATE),
                 "Summarise the repository layout" in t or has_date(t, self.S3_DATE)]
        add(self.checks_listed[1], all(found), f"sessions found: {found}")
        add(self.checks_listed[2], "DECOYMARKER" not in t and not has_date(t, self.DECOY_DATE))
        add(self.checks_listed[3], "claude-opus-5-5" in t and "claude-sonnet-5-5" in t)
        add(self.checks_listed[4], re.search(r"\bauto\b", low) and re.search(r"\bdefault\b", low) and "MISSING" in t)
        add(self.checks_listed[5], self.SECRET not in t and "redact" in low)
        add(self.checks_listed[6], "attempted" in low and "notes.md" in t)
        add(self.checks_listed[7], "analysis" in low)
        bad = [p for p in ("human stayed in the loop", "closely supervised", "human oversight", "human in the loop")
               if p in low]
        add(self.checks_listed[8], not bad, f"phrases found: {bad}")
        rl = reply.lower()
        add(self.checks_listed[9], "pending" in rl and "accepted the run" not in rl)
        add(self.checks_listed[10], tree_hashes(root) == before)
        return out


# ---------------------------------------------------------------------------------------------------------
class AnalysisAdversary(Fixture):
    name = "analysis-adversary"
    TRUE_K = 0.30
    REPORTED_K = 0.130
    checks_listed = (
        "a report analysis-adversary-report.md is saved in an output folder of the task",
        "the report gives an independent estimate of k close to 0.30",
        "the report says the reported 0.130 does not reproduce",
        "the report names the logarithm base as the likely cause",
        "the script under review was not run",
        "the project files are unchanged",
    )

    SCRIPT = '''"""Fit y = A exp(-k t) to data/decay.csv by least squares on the logarithm of y; print k."""
import csv
import math

rows = list(csv.DictReader(open("data/decay.csv", newline="")))
t = [float(r["t"]) for r in rows]
y = [math.log10(float(r["y"])) for r in rows]
n = len(t)
mt, my = sum(t) / n, sum(y) / n
slope = sum((a - mt) * (b - my) for a, b in zip(t, y)) / sum((a - mt) ** 2 for a in t)
print(f"k = {-slope:.3f} per day")
'''

    def build(self, tmp, args=None):
        import math
        import random
        root = (Path(tmp) / "Decay").resolve()
        (root / "data").mkdir(parents=True)
        (root / "code").mkdir()
        rng = random.Random(42)
        lines = ["t,y"] + [f"{t},{100 * math.exp(-self.TRUE_K * t) * (1 + 0.02 * rng.gauss(0, 1)):.4f}" for t in range(0, 21)]
        (root / "data" / "decay.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (root / "code" / "fit_decay.py").write_text(self.SCRIPT, encoding="utf-8")
        (root / "draft.md").write_text("# Decay\n\nThe fitted decay rate is k = 0.130 per day (code/fit_decay.py on data/decay.csv).\n",
                                       encoding="utf-8")
        self.root = root
        self.before = tree_hashes(root)
        return root

    def prompt(self, root):
        return (f"Use the analysis-adversary skill to try to break this result: the fitted decay rate k = 0.130 per day "
                f"in draft.md. Subject: decay-rate. Raw input: data/decay.csv. Code: code/fit_decay.py. Project root: "
                f"{root}. When the skill has returned, save its report as the skill instructs and tell me the path.")

    def check(self, root, reply, before):
        import glob
        text = self.result_text(root, "analysis-adversary-report.md")
        t = text or ""
        out = []

        def add(name, ok, detail=""):
            out.append((name, bool(ok), detail))

        add(self.checks_listed[0], text is not None)
        add(self.checks_listed[1], re.search(r"\b0\.(29|30|31)\d*", t) is not None)
        reproduces = re.search(r"(not|n't|fail\w*)\W+(\w+\W+){0,4}reproduc|does not (match|agree)|mismatch|discrepan|"
                               r"incorrect|wrong", t, re.I)
        add(self.checks_listed[2], reproduces is not None)
        add(self.checks_listed[3], re.search(r"log10|base[- ]10|common log|decimal log|natural log|base[- ]e\b|\bln\b", t, re.I) is not None)
        ran = []
        for f in glob.glob(str(CLAUDE_HOME / "projects" / project_key(root) / "**" / "*.jsonl"), recursive=True):
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    for m in re.finditer(r'"command":\s*"((?:[^"\\]|\\.)*)"', line):
                        if re.search(r"(python\S*|\bpy)\s+(-\S+\s+)*\S*fit_decay\.py", m.group(1).replace("\\\\", "/")):
                            ran.append(m.group(1)[:100])
        add(self.checks_listed[4], not ran, f"commands that ran it: {ran[:2]}")
        add(self.checks_listed[5], tree_hashes(root) == before)
        return out


class Skip(Exception):
    """Raised by a fixture whose source material or tools are not available here."""


def doc_paragraphs(xml):
    return re.findall(r"<w:p[ >].*?</w:p>", xml, re.S)


def paragraph_text(p, mode):
    """Text of one paragraph as plain text, with tracked changes accepted ('accept') or rejected ('reject')."""
    if mode == "accept":
        p = re.sub(r"<w:del\b[^>]*[^/]>.*?</w:del>", "", p, flags=re.S)
    elif mode == "reject":
        p = re.sub(r"<w:ins\b[^>]*[^/]>.*?</w:ins>", "", p, flags=re.S)
    return html.unescape("".join(re.findall(r"<w:(?:t|delText)[^>]*>([^<]*)</w:(?:t|delText)>", p)))


def doc_text(path, mode="accept"):
    """[paragraph text] of a .docx with tracked changes accepted or rejected."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    return [re.sub(r"\s+", " ", paragraph_text(p, mode)).strip() for p in doc_paragraphs(xml)]


def word_available():
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "try { $w = New-Object -ComObject Word.Application; $w.Quit(); 'yes' } catch { 'no' }"],
                       capture_output=True, text=True, timeout=120)
    return "yes" in (r.stdout or "")


def word_run(script, timeout=180):
    """Run a PowerShell script that drives Word; return (exit code, output)."""
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as f:
        f.write(script)
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", f.name],
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    finally:
        Path(f.name).unlink(missing_ok=True)


class TestLibrary:
    """Shared by the fixtures that read the test EndNote library through a second, read-only server."""

    def locate_library(self, args):
        lib = getattr(args, "test_library", None) or os.environ.get("FIXTURE_ENDNOTE_LIBRARY")
        if not lib or not Path(lib).is_file():
            raise Skip("no test EndNote library (give --test-library or set FIXTURE_ENDNOTE_LIBRARY)")
        lib = Path(lib).resolve()
        sdb = lib.with_name(lib.stem + ".Data") / "sdb" / "sdb.eni"
        if not (REPO / "mcp" / "endnote" / "endnote_server.py").is_file() or not sdb.is_file():
            raise Skip("the EndNote server or the library database is missing")
        self.library = lib
        return lib, sdb

    def write_mcp_config(self, tmp):
        self.mcp_config = Path(tmp) / "mcp.json"
        self.mcp_config.write_text(json.dumps({"mcpServers": {"endnote": {
            "command": sys.executable, "args": [str(REPO / "mcp" / "endnote" / "endnote_server.py")],
            "env": {"ENDNOTE_LIBRARY_PATH": str(self.library)}}}}), encoding="utf-8")

    def _library_hashes(self):
        data = self.library.with_name(self.library.stem + ".Data")
        found = {self.library.name: hashlib.sha1(self.library.read_bytes()).hexdigest()}
        for f in sorted(data.rglob("*")):
            if f.is_file():
                found[f.relative_to(data).as_posix()] = hashlib.sha1(f.read_bytes()).hexdigest()
        return found

    def extra_args(self, root):
        return ["--mcp-config", str(self.mcp_config), "--strict-mcp-config"]

    WEB_TOOLS = r'"name":\s*"(?:WebFetch|WebSearch)"|mcp__exa__|Consensus__'

    def external_calls(self, root, hosts, tools=WEB_TOOLS):
        """Tool calls in the session transcripts that name one of the hosts (a regex) or one of the tools (a regex)."""
        import glob
        pattern = re.compile(hosts + ("|" + tools if tools else ""), re.I)
        found = []
        for f in glob.glob(str(CLAUDE_HOME / "projects" / project_key(root) / "**" / "*.jsonl"), recursive=True):
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"tool_use"' in line and pattern.search(line):
                        found.append(line[:160])
        return found


# ---------------------------------------------------------------------------------------------------------
class Proofread(Fixture):
    name = "proofread"
    timeout = 1800
    # (text in the converted paragraph, text with the planted fault); each lies inside one run
    PLANTS = [
        ("relatively stable", "relativly stable"),
        ("supply of sediment.", "supply of sedement."),
        ("interplay of processes which", "interplay of proceses which"),
        ("drowned valley harbours", "drowned valley harbors"),
        ("past and future, is affected", "past and future, are affected"),
        ("estuaries have had similar", "estuaries has had similar"),
    ]
    MUST_NOT_REMAIN = ["relativly", "sedement", "proceses", "harbors", "are affected", "estuaries has"]
    MUST_REMAIN = ["relatively stable", "supply of sediment", "interplay of processes", "valley harbours"]
    checks_listed = (
        "the proofread copy is saved beside the original as '<name> - proofread.docx'",
        "the original is unchanged",
        "every change is tracked: rejecting all changes restores the planted text exactly",
        "each of the six planted faults is corrected in the accepted text",
        "every revision is authored by Claude",
        "no change is made outside the first paragraph",
        "comments: at most 5, each at most 50 words",
        "the reply says that citation accuracy is not checked (citation-check)",
        "Word opens the proofread copy without error and reports revisions",
    )

    def build(self, tmp, args=None):
        source = Path(getattr(args, "estuary_doc", None) or REPO / "working_docs" / "Estuary Notes.doc")
        if not source.is_file():
            raise Skip(f"source document not found: {source} (give --estuary-doc)")
        if sys.platform != "win32" or not word_available():
            raise Skip("Microsoft Word is not available (needed to convert the .doc and for the skill)")
        root = (Path(tmp) / "Notes").resolve()
        root.mkdir()
        converted = root / "converted.docx"
        code, out = word_run(
            "$w = New-Object -ComObject Word.Application; $w.Visible = $false; $w.DisplayAlerts = 0\n"
            f"try {{ $d = $w.Documents.Open('{source}', $false, $true); $d.SaveAs2('{converted}', 16); $d.Close($false) }}\n"
            "finally { $w.Quit() }\n")
        if code != 0 or not converted.is_file():
            raise Skip(f"conversion with Word failed: {out[:200]}")
        target = root / "Estuary Notes.docx"
        with zipfile.ZipFile(converted) as zin, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "word/document.xml":
                    xml = data.decode("utf-8")
                    for old, new in self.PLANTS:
                        if xml.count(old) != 1:
                            raise Skip(f"planted text not found exactly once in the converted document: {old!r}")
                        xml = xml.replace(old, new)
                    data = xml.encode("utf-8")
                zout.writestr(item, data)
        converted.unlink()
        self.root = root
        self.target = target
        self.planted = doc_text(target)
        self.before = tree_hashes(root)
        return root

    def prompt(self, root):
        return ("Use the proofread skill on 'Estuary Notes.docx' in this folder. Scope: the first paragraph only, the prose "
                "paragraph that begins 'Macrotidal estuaries'; leave the rest of the document alone. Do not ask me "
                "questions. When the skill has finished, give me the path of the proofread copy and the summary.")

    def check(self, root, reply, before):
        out = []

        def add(name, ok, detail=""):
            out.append((name, bool(ok), detail))

        copies = [p for p in root.rglob("*proofread*.docx")]
        copy = next((p for p in copies if p.parent == root and p.name == "Estuary Notes - proofread.docx"), None)
        add(self.checks_listed[0], copy is not None, f"found: {[p.name for p in copies]}")
        add(self.checks_listed[1], tree_hashes(root).get("Estuary Notes.docx") == before.get("Estuary Notes.docx"))
        if copy is None:
            for c in self.checks_listed[2:6]:
                add(c, False, "no copy")
        else:
            rejected, accepted = doc_text(copy, "reject"), doc_text(copy, "accept")
            add(self.checks_listed[2], rejected == self.planted, "paragraphs differing: "
                f"{[i for i, (a, b) in enumerate(zip(rejected, self.planted)) if a != b][:5]}")
            first = accepted[0] if accepted else ""
            bad = [w for w in self.MUST_NOT_REMAIN if w in first]
            missing = [w for w in self.MUST_REMAIN if w not in first]
            add(self.checks_listed[3], not bad and not missing, f"still present: {bad}; missing: {missing}")
            with zipfile.ZipFile(copy) as z:
                xml = z.read("word/document.xml").decode("utf-8")
                comments = z.read("word/comments.xml").decode("utf-8") if "word/comments.xml" in z.namelist() else ""
            authors = set(re.findall(r"<w:(?:ins|del)\b[^>]*w:author=\"([^\"]*)\"", xml))
            add(self.checks_listed[4], authors == {"Claude"}, f"authors: {sorted(authors)}")
            add(self.checks_listed[5], accepted[1:] == self.planted[1:] and rejected[1:] == self.planted[1:])
            bodies = [re.sub(r"\s+", " ", paragraph_text(c, "accept")).strip()
                      for c in re.findall(r"<w:comment\b.*?</w:comment>", comments, re.S)]
            add(self.checks_listed[6], len(bodies) <= 5 and all(len(b.split()) <= 50 for b in bodies),
                f"{len(bodies)} comments; words: {[len(b.split()) for b in bodies]}")
        rl = reply.lower()
        add(self.checks_listed[7], "citation-check" in rl or "citation check" in rl)
        if copy is None:
            add(self.checks_listed[8], False, "no copy")
        else:
            code, text = word_run(
                "$w = New-Object -ComObject Word.Application; $w.Visible = $false; $w.DisplayAlerts = 0\n"
                f"try {{ $d = $w.Documents.Open('{copy}', $false, $true); 'revisions=' + $d.Revisions.Count; "
                "'comments=' + $d.Comments.Count; $d.Close($false) }\nfinally { $w.Quit() }\n")
            m = re.search(r"revisions=(\d+)", text)
            add(self.checks_listed[8], code == 0 and m is not None and int(m.group(1)) >= 1, text[:160])
        return out


# ---------------------------------------------------------------------------------------------------------
class CitationCheck(TestLibrary, Fixture):
    name = "citation-check"
    timeout = 1800
    # (library id, rec-number written in the field, year written in the field or None for the library's year)
    CITES = [(1, 1, None), (2, 52, None), (3, 3, "2024")]
    INVENTED = ("Harrington and Osei", "2021", "Adaptive Planning Horizons for Estuarine Flood Defences", 99)
    checks_listed = (
        "a report citation-check-report.md is saved in an output folder of the task",
        "the invented reference is reported as unresolved",
        "the year in the field (2024) against the library (2025) is reported for WorldPop",
        "the stale rec-number 52 against the library record is reported for IPCC",
        "the correct reference (World Economic Forum) is not reported as a problem",
        "no external call was made",
        "the report says external verification was not done",
        "the manuscript, the library and the project files are unchanged",
    )

    def build(self, tmp, args=None):
        lib, sdb = self.locate_library(args)
        import sqlite3
        con = sqlite3.connect("file:" + sdb.as_posix() + "?mode=ro", uri=True)
        records = {}
        for i, _, _ in self.CITES:
            row = con.execute("select author, year, title, number, reference_type from refs where id = ?", (i,)).fetchone()
            if not row or not row[2]:
                raise Skip(f"library record {i} not found or has no title")
            # the snapshot in the field repeats the library record exactly, so only the planted faults differ
            records[i] = (row[0], row[1], row[2], row[3] or "", row[4])
        con.close()
        self.records = records
        root = (Path(tmp) / "Paper").resolve()
        root.mkdir()
        self.manuscript = root / "manuscript.docx"
        self._write_docx(self.manuscript)
        self.write_mcp_config(tmp)
        self.root = root
        self.before = tree_hashes(root)
        self.lib_before = self._library_hashes()
        return root

    @staticmethod
    def _field(author, year, title, recnum, display, number="", reftype=12):
        esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        cite = (f"<EndNote><Cite><Author>{esc(author)}</Author><Year>{year}</Year><RecNum>{recnum}</RecNum>"
                f"<DisplayText>{esc(display)}</DisplayText><record><rec-number>{recnum}</rec-number>"
                f"<foreign-keys><key app=\"EN\" db-id=\"fixture\">{recnum}</key></foreign-keys>"
                f"<ref-type name=\"Web Page\">{reftype}</ref-type><contributors><authors><author>{esc(author)}</author>"
                f"</authors></contributors><titles><title>{esc(title)}</title></titles>"
                + (f"<number>{esc(number)}</number>" if number else "") +
                f"<dates><year>{year}</year></dates></record></Cite></EndNote>")
        instr = " ADDIN EN.CITE " + esc(cite)
        half = len(instr) // 2
        return ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
                f'<w:r><w:instrText xml:space="preserve">{instr[:half]}</w:instrText></w:r>'
                f'<w:r><w:instrText xml:space="preserve">{instr[half:]}</w:instrText></w:r>'
                '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
                f'<w:r><w:t>{esc(display)}</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>')

    def _write_docx(self, path):
        sentences = []
        for (i, recnum, year), lead in zip(self.CITES, ["Public attention to global risks has grown ",
                                                        "Climate assessments are synthesised in a single report ",
                                                        "Open demographic data are widely used "]):
            author, lib_year, title, number, reftype = self.records[i]
            shown = year or lib_year
            name = author.strip().rstrip(",")
            sentences.append(f'<w:r><w:t xml:space="preserve">{lead}</w:t></w:r>'
                             + self._field(author, shown, title, recnum, f"({name}, {shown})", number, reftype)
                             + '<w:r><w:t xml:space="preserve">. </w:t></w:r>')
        author, year, title, recnum = self.INVENTED
        sentences.append('<w:r><w:t xml:space="preserve">Flood defences need adaptive planning </w:t></w:r>'
                         + self._field(author, year, title, recnum, f"({author}, {year})")
                         + '<w:r><w:t xml:space="preserve">.</w:t></w:r>')
        body = "<w:p>" + "".join(sentences) + "</w:p>"
        document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                    + body + "</w:body></w:document>")
        types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/'
                 'package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-'
                 'package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override '
                 'PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.'
                 'wordprocessingml.document.main+xml"/></Types>')
        rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.'
                'org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", types)
            z.writestr("_rels/.rels", rels)
            z.writestr("word/document.xml", document)

    def prompt(self, root):
        return ("Use the citation-check skill on 'manuscript.docx' in this folder. Scope: the whole document. Run stage 1 "
                "only. Do not ask me questions: where the skill asks for confirmation before external verification, the "
                "answer is no, so make no external call of any kind (no CrossRef, Semantic Scholar, OpenAlex, arXiv or "
                "web request) and report the external checks as not done. When the skill has finished, tell me the path "
                "of the report and whether the run is pending review.")

    def check(self, root, reply, before):
        import glob
        text = self.result_text(root, "citation-check-report.md")
        t = text or ""
        lines = t.splitlines()
        out = []

        def add(name, ok, detail=""):
            out.append((name, bool(ok), detail))

        def lines_with(*needles, any_of=()):
            return [ln for ln in lines if all(n.lower() in ln.lower() for n in needles)
                    and (not any_of or any(a.lower() in ln.lower() for a in any_of))]

        add(self.checks_listed[0], text is not None)
        add(self.checks_listed[1], lines_with("Adaptive Planning", any_of=("unresolved", "not found", "no match", "no reasonable"))
            or lines_with("Harrington", any_of=("unresolved", "not found", "no match", "no reasonable")))
        add(self.checks_listed[2], lines_with("WorldPop", "2024", "2025"))
        add(self.checks_listed[3], lines_with("IPCC", "52") or lines_with("AR6", "52"))
        bad = lines_with("World Economic Forum", any_of=("mismatch", "unresolved", "ambiguous", "drift"))
        add(self.checks_listed[4], not bad, f"lines: {bad[:2]}")
        external = []
        pattern = re.compile(r"crossref\.org|openalex\.org|semanticscholar|arxiv\.org|\"name\":\s*\"(WebFetch|WebSearch)\"", re.I)
        for f in glob.glob(str(CLAUDE_HOME / "projects" / project_key(root) / "**" / "*.jsonl"), recursive=True):
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"tool_use"' in line and pattern.search(line):
                        external.append(line[:120])
        add(self.checks_listed[5], not external, f"{len(external)} tool calls to external services")
        add(self.checks_listed[6], re.search(r"not (verified|checked|done|run)|declined|no external", t, re.I) is not None)
        add(self.checks_listed[7], tree_hashes(root) == before and self._library_hashes() == self.lib_before)
        return out


# ---------------------------------------------------------------------------------------------------------
class LiteratureSearch(TestLibrary, Fixture):
    """The local half of the skill: the test EndNote library only, with no external source."""
    name = "literature-search"
    timeout = 1200
    WANTED = ["Theatre in Education", "Serious game"]
    UNRELATED = ["Open Spatial Demographic Data", "AR6 Synthesis"]
    checks_listed = (
        "a report literature-search-report.md is saved in an output folder of the task",
        "the derived search terms are reported",
        "the two library records that match the question are in the candidate list",
        "records that cannot match the question are not in the candidate list",
        "local-PDF availability is reported",
        "the report says that no external source was queried",
        "no external call was made",
        "the library and the project files are unchanged",
        "the reply reports the run as pending",
    )

    def build(self, tmp, args=None):
        lib, sdb = self.locate_library(args)
        import sqlite3
        con = sqlite3.connect("file:" + sdb.as_posix() + "?mode=ro", uri=True)
        titles = {r[0] for r in con.execute("select title from refs")}
        con.close()
        missing = [w for w in self.WANTED + self.UNRELATED if not any(w in t for t in titles)]
        if missing:
            raise Skip(f"the test library lacks the records this fixture expects: {missing}")
        root = (Path(tmp) / "Review").resolve()
        root.mkdir()
        self.write_mcp_config(tmp)
        self.root = root
        self.before = tree_hashes(root)
        self.lib_before = self._library_hashes()
        return root

    def prompt(self, root):
        return ("Use the literature-search skill. Question: which theatre and serious-game approaches are used to engage "
                "the public? Subject: public-engagement. Sources: the EndNote library only; do not query any external "
                "source and do not make any web request. No date range. Do not ask me questions. When the skill has "
                "finished, tell me the path of the report and whether the run is pending review.")

    def check(self, root, reply, before):
        text = self.result_text(root, "literature-search-report.md")
        t = text or ""
        low = t.lower()
        out = []

        def add(name, ok, detail=""):
            out.append((name, bool(ok), detail))

        add(self.checks_listed[0], text is not None)
        add(self.checks_listed[1], re.search(r"derived|search terms", t, re.I) is not None and "theatre" in low)
        add(self.checks_listed[2], all(w in t for w in self.WANTED), f"missing: {[w for w in self.WANTED if w not in t]}")
        add(self.checks_listed[3], not any(w in t for w in self.UNRELATED),
            f"present: {[w for w in self.UNRELATED if w in t]}")
        add(self.checks_listed[4], re.search(r"no (local |linked )?pdf|not linked|none linked|no linked|pdf", low) is not None)
        add(self.checks_listed[5], re.search(r"(openalex|arxiv|semantic scholar|exa|consensus)[^\n]*"
                                              r"(not queried|not searched|not used|excluded|skipped|out of scope|not run|"
                                              r"no external)|no external source|external sources? (were|was) not", low) is not None)
        external = self.external_calls(root, r"openalex\.org|crossref\.org|arxiv\.org|semanticscholar")
        add(self.checks_listed[6], not external, f"{len(external)} calls")
        add(self.checks_listed[7], tree_hashes(root) == before and self._library_hashes() == self.lib_before)
        add(self.checks_listed[8], "pending" in reply.lower())
        return out


# ---------------------------------------------------------------------------------------------------------
class LiteratureSearchExternal(TestLibrary, Fixture):
    """OpenAlex only, with an import list: structure and de-duplication, not content (needs --external)."""
    name = "literature-search-external"
    timeout = 1800
    checks_listed = (
        "a report literature-search-report.md is saved in an output folder of the task",
        "the report gives OpenAlex as a source with a hit count",
        "the candidate list has at least 5 candidates (table rows or numbered sections), each with a year and a peer-reviewed, grey or explicitly unclear label",
        "no DOI appears twice in the candidate list",
        "the import list literature-search-import.ris holds well-formed records",
        "the number of records in the import list equals the number of candidates",
        "no mailto parameter or personal identifier was sent",
        "no source other than OpenAlex was queried",
        "the library and the project files are unchanged",
    )

    def build(self, tmp, args=None):
        if not getattr(args, "external", False):
            raise Skip("sends a query to OpenAlex; give --external to run it")
        lib, sdb = self.locate_library(args)
        root = (Path(tmp) / "Search").resolve()
        root.mkdir()
        self.write_mcp_config(tmp)
        self.root = root
        self.before = tree_hashes(root)
        self.lib_before = self._library_hashes()
        return root

    def prompt(self, root):
        return ("Use the literature-search skill. Query: tidal inlet morphodynamics. Subject: tidal-inlets. Sources: the "
                "EndNote library and OpenAlex only. Result cap: 10 for OpenAlex. No date range. Include the import-ready "
                "reference list. You may send the query text to OpenAlex, and to no other service; that is my answer to "
                "the external confirmation, so do not ask again. Do not add a mailto parameter. When the skill has "
                "finished, tell me the path of the report and whether the run is pending review.")

    @staticmethod
    def rows(text):
        """The candidates: table rows that hold a four-digit year or, if there are none, the numbered sections
        ('### 1. Title') that make up the candidate list."""
        table = [ln for ln in text.splitlines() if ln.lstrip().startswith("|") and re.search(r"\b(19|20)\d\d\b", ln)]
        if table:
            return table
        return re.split(r"^#{3,4}\s+\d+\.\s+", text, flags=re.M)[1:]

    def check(self, root, reply, before):
        text = self.result_text(root, "literature-search-report.md")
        ris = self.result_text(root, "literature-search-import.ris")
        t = text or ""
        rows = self.rows(t)
        out = []

        def add(name, ok, detail=""):
            out.append((name, bool(ok), detail))

        add(self.checks_listed[0], text is not None)
        add(self.checks_listed[1], re.search(r"openalex[^\n]*\d+", t, re.I) is not None)
        labelled = [r for r in rows if re.search(r"peer|grey|gray|unclear|not verified|preprint|conference", r, re.I) and re.search(r"\b(19|20)\d\d\b", r)]
        add(self.checks_listed[2], len(rows) >= 5 and len(labelled) == len(rows), f"{len(rows)} rows, {len(labelled)} labelled")
        dois = []
        for r in rows:
            dois += [d.rstrip(".,;|)").lower() for d in re.findall(r"10\.\d{4,9}/[^\s|]+", r)]
        add(self.checks_listed[3], len(dois) == len(set(dois)), f"{len(dois) - len(set(dois))} repeated")
        records = [b for b in re.split(r"\n\s*\n", (ris or "").strip()) if b.strip()]
        wellformed = bool(records) and all(re.search(r"^TY\s+-\s+\S+", b, re.M) and re.search(r"^TI\s+-\s+\S+", b, re.M)
                                           and re.search(r"^ER\s+-", b, re.M) for b in records)
        authors_ok = all(re.search(r",", ln) for b in records for ln in b.splitlines() if ln.startswith("AU  -"))
        add(self.checks_listed[4], wellformed and authors_ok, f"{len(records)} records")
        add(self.checks_listed[5], len(records) == len(rows), f"{len(records)} records, {len(rows)} rows")
        sent = self.external_calls(root, r"mailto=", tools="")
        mail = [s for s in sent if "mailto=" in s.lower()]
        add(self.checks_listed[6], not mail, f"{len(mail)} calls")
        others = self.external_calls(root, r"crossref\.org|arxiv\.org|semanticscholar|unpaywall", tools=r"mcp__exa__|Consensus__")
        add(self.checks_listed[7], not others, f"{len(others)} calls")
        add(self.checks_listed[8], tree_hashes(root) == before and self._library_hashes() == self.lib_before)
        return out


FIXTURES = {f.name: f for f in (ProjectDisclosure(), AnalysisAdversary(), Proofread(), CitationCheck(),
                                      LiteratureSearch(), LiteratureSearchExternal())}


def purge(fixture, root, claude):
    for key in fixture.log_folders(root):
        shutil.rmtree(CLAUDE_HOME / "projects" / key, ignore_errors=True)


def run_one(fixture, args, out_dir):
    tmp = Path(tempfile.mkdtemp(prefix="fx-"))
    try:
        root = fixture.build(tmp, args)
    except Skip as why:
        shutil.rmtree(tmp, ignore_errors=True)
        return None, 0, str(why)
    stamp = datetime.now().strftime("%d%m%y-%H%M")
    dest = out_dir / f"{fixture.name}-{stamp}"
    dest.mkdir(parents=True, exist_ok=True)
    print(f"[{fixture.name}] project {root}", flush=True)
    started = time.time()
    try:
        command = [args.claude, "-p", "--max-turns", str(fixture.max_turns), "--permission-mode", args.permission_mode,
                   *fixture.extra_args(root)]
        r = subprocess.run(command, input=fixture.prompt(root), cwd=root, capture_output=True, text=True,
                           timeout=args.timeout or fixture.timeout)
        reply = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr.strip() else "")
    except subprocess.TimeoutExpired:
        reply = "[timed out]"
    seconds = round(time.time() - started)
    (dest / "reply.txt").write_text(reply, encoding="utf-8")
    results = fixture.check(root, reply, fixture.before)
    if (root / "outputs").is_dir():
        shutil.copytree(root / "outputs", dest / "outputs", dirs_exist_ok=True)
    (dest / "checks.json").write_text(json.dumps(
        [{"check": n, "passed": p, "detail": d} for n, p, d in results], indent=2), encoding="utf-8")
    if not args.keep:
        purge(fixture, root, args.claude)
        shutil.rmtree(tmp, ignore_errors=True)
    return results, seconds, dest


def main(argv):
    ap = argparse.ArgumentParser(prog="run_fixtures.py", description="Run skills on fixtures with headless Claude Code.")
    ap.add_argument("--version", action="version", version=f"run_fixtures.py {VERSION}")
    ap.add_argument("skills", nargs="*")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--timeout", type=int, default=None)
    ap.add_argument("--estuary-doc", default=None)
    ap.add_argument("--test-library", default=None)
    ap.add_argument("--external", action="store_true")
    ap.add_argument("--claude", default=shutil.which("claude") or "claude")
    ap.add_argument("--permission-mode", default="auto")
    ap.add_argument("--out", default=str(REPO / "working_docs" / "skill-runs"))
    a = ap.parse_args(argv)
    names = a.skills or list(FIXTURES)
    unknown = [n for n in names if n not in FIXTURES]
    if unknown:
        print(f"Unknown fixture: {', '.join(unknown)}. Known: {', '.join(FIXTURES)}", file=sys.stderr)
        return 2
    if a.list:
        for n in names:
            print(n)
            for c in FIXTURES[n].checks_listed:
                print(f"  - {c}")
        return 0
    failed = False
    for n in names:
        results, seconds, dest = run_one(FIXTURES[n], a, Path(a.out))
        if results is None:
            print(f"[{n}] SKIPPED: {dest}")
            continue
        print(f"[{n}] {seconds} s; results in {dest}")
        for name, ok, detail in results:
            print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))
            failed = failed or not ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
