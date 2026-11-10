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
                                           [--external] [--no-preflight]
  skill      project-disclosure, project-disclosure-detailed, analysis-adversary, analysis-adversary-model,
             analysis-adversary-independent, document-adversary, document-adversary-independent, proofread, proofread-structure, citation-check,
             citation-check-context, citation-check-external, literature-search, literature-search-external
             (default: all that can run)
  --list     print the fixtures and their checks, and run nothing
  --keep     keep the temporary project and its logs
  --timeout  seconds allowed for each session (default: 900, or 1800 for proofread and citation-check)
  --no-preflight  skip the one-turn test session that checks the requested permission mode is the one that starts
  --external  also run the two external fixtures: literature-search-external sends a query to OpenAlex, and
             citation-check-external sends the titles, authors, years and DOIs of four records to CrossRef, OpenAlex
             and arXiv (both are skipped otherwise)
  --claude   the claude command (default: the one on PATH)
  --permission-mode  the mode for the sessions (default auto, as in interactive use; a headless session
             started in the default mode cannot get approval for run control or Python commands)
  --out      folder for the results (default: working_docs/skill-runs under the repository)
Inputs:  the live Claude configuration; `claude` on PATH.
Outputs: <out>/<skill>-<DDMMYY-HHMM>/ with reply.txt, the saved deliverable, checks.json, tool-calls.txt (a one-line summary of
         each tool call, kept because the session transcripts are removed after the run) and, for the proofread fixtures,
         docx-skill-check.txt (whether the docx skill scripts are present and unchanged); a table on standard output.
Exit:    0 if every check of every fixture that ran passed (a skipped fixture is not a failure); 1 otherwise.
Version: see VERSION; `--version` prints it.
"""
import argparse
import glob
import hashlib
import html
import importlib.util
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

VERSION = "1.4"
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
    uses_docx_skill = False

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
        "short form: a timeline of at most 15 lines, no prompt appendix, and --detailed is offered",
    )
    form = "short"
    TAIL = ("Do not ask me questions. When the skill has returned, tell me where the file was written and whether the "
            "run is pending review.")

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
        return ("Use the project-disclosure skill to draft the AI-use disclosure for this project. " + self.TAIL)

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
        add(self.checks_listed[11], *self.form_check(t))
        return out

    def form_check(self, t):
        low = t.lower()
        appendix = re.search(r"^#+\s*.*appendix", t, re.I | re.M) is not None
        m = re.search(r"^#+\s*.*timeline.*$", t, re.I | re.M)
        if not m:
            return False, "no timeline heading"
        tail = t[m.end():]
        nxt = re.search(r"^#+\s", tail, re.M)
        body = tail[:nxt.start()] if nxt else tail
        items = [ln for ln in body.splitlines() if re.match(r"\s*(?:[-*]|\d+[.)]|\|)", ln) and not re.match(r"\s*\|[-\s|:]+\|?\s*$", ln)]
        return (len(items) <= 15 and not appendix and "--detailed" in t,
                f"timeline lines: {len(items)}; appendix heading: {appendix}; offers --detailed: {'--detailed' in t}")


class ProjectDisclosureDetailed(ProjectDisclosure):
    name = "project-disclosure-detailed"
    form = "detailed"
    checks_listed = ProjectDisclosure.checks_listed[:11] + (
        "detailed form: a per-session checklist and a prompt appendix holding the prompt text",
    )

    def prompt(self, root):
        return ("Use the project-disclosure skill with the argument --detailed to draft the detailed AI-use "
                "disclosure for this project. " + self.TAIL)

    def form_check(self, t):
        appendix = re.search(r"^#+\s*.*appendix", t, re.I | re.M) is not None
        prompts = "Plot the decay curve" in t and "log transform" in t and "Summarise the repository layout" in t
        return appendix and prompts, f"appendix heading: {appendix}; prompt text present: {prompts}"


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


def first_use_times(root, needles):
    """{needle: earliest timestamp of a tool call whose input contains the needle, or None}.

    Reads every session and subagent log of the fixture project, so it sees what a forked skill did."""
    found = {n: None for n in needles}
    for f in glob.glob(str(CLAUDE_HOME / "projects" / project_key(root) / "**" / "*.jsonl"), recursive=True):
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                content = (e.get("message") or {}).get("content")
                if e.get("type") != "assistant" or not isinstance(content, list):
                    continue
                for item in content:
                    if (isinstance(item, dict) and item.get("type") == "tool_use"
                            and item.get("name") in ("Read", "Bash", "Grep", "Glob", "PowerShell")):
                        text = json.dumps(item.get("input", {})).replace("\\\\", "/")
                        if item.get("name") in ("Bash", "PowerShell") and "<<" in str((item.get("input") or {}).get("command", "")):
                            continue  # a here-document writes text; a file name inside it is not a read
                        for n in needles:
                            if n in text and (found[n] is None or e.get("timestamp", "") < found[n]):
                                found[n] = e.get("timestamp", "")
    return found


def tool_inputs(root, names):
    """The input dict of every tool call by the given tool names in the session and subagent logs of the project."""
    found = []
    for f in glob.glob(str(CLAUDE_HOME / "projects" / project_key(root) / "**" / "*.jsonl"), recursive=True):
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                content = (e.get("message") or {}).get("content")
                if e.get("type") != "assistant" or not isinstance(content, list):
                    continue
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_use" and item.get("name") in names:
                        found.append(item.get("input") or {})
    return found


def background_tasks(root):
    """Calls that started a background task (run_in_background true) in the session and subagent logs."""
    return [i for i in tool_inputs(root, ("Bash", "PowerShell", "Agent", "Task")) if i.get("run_in_background") is True]


def ran_python(root):
    """Shell commands that ran Python or a .py script."""
    pattern = re.compile(r"python|\.py\b", re.I)
    return [str(i.get("command", ""))[:100] for i in tool_inputs(root, ("Bash", "PowerShell")) if pattern.search(str(i.get("command", "")))]


def reading_challenges(t, needle):
    """(heading line, text) of each numbered challenge whose heading line mentions `needle`."""
    starts = [m.start() for m in re.finditer(r"^\W*C\d+\b", t, re.M)]
    blocks = [t[a:b].lstrip() for a, b in zip(starts, starts[1:] + [len(t)])]
    return [(b.splitlines()[0], b) for b in blocks if needle in b.splitlines()[0]]


def four_parts(t):
    """(ok, detail): every numbered challenge has an evidence, consequence and what-would-settle-it part."""
    ids = set(re.findall(r"^\W*C(\d+)\b", t, re.M))
    n = len(ids)
    counts = {p: len(re.findall(p, t, re.I)) for p in (r"\bevidence\b", r"\bconsequence\b", r"what would settle it")}
    return n >= 3 and all(c >= n for c in counts.values()), f"challenges {n}; part counts {list(counts.values())}"


def run_scripts(root, task_prefix):
    """The files saved under code/ in the run folder of the task."""
    out = root / "outputs"
    folders = sorted(out.glob(task_prefix + "*")) if out.is_dir() else []
    return [p for f in folders for p in (f / "code").rglob("*") if p.is_file()] if folders else []


class DocumentAdversary(Fixture):
    name = "document-adversary"
    checks_listed = (
        "a report document-adversary-report.md is saved in an output folder of the task",
        "the uncovered requirement R3 (uncertainty) is named as a challenge",
        "the half-life error is found and the recomputed value 2.3 days is given",
        "the 10 samples over 20 days inconsistency is found",
        "the zero baseline fixed without a test is named as an assumption",
        "the 1 per cent recovery claim is referred to analysis-adversary, not passed",
        "numbered challenges (C1, C2, C3) each have a severity and a what-would-settle-it line",
        "the report has a verdict and a not-checked section",
        "the correct hourly conversion 0.0125 is not reported as an error",
        "the project files are unchanged",
        "the reply gives the saved path and reports the run as pending",
        "the earlier review was opened only after the specification and the objective were read",
        "the report says the earlier review was read after the challenges were drafted",
        "the open earlier finding E2 (zero baseline) is tagged as a repeat and the resolved E1 is not raised",
        "the earlier null result E3 (half-life 3.5 days) is tagged as contradicted",
        "every challenge has evidence, consequence and what-would-settle-it parts",
        "the report has an alternatives section and a section of numbers the document did not state",
        "any script the report cites is saved under code/ in the run folder",
        "a scratch script was run for the recomputation (not only arithmetic in the head)",
        "no background task was started",
        "a challenge about the Reliable grade, if raised, states both readings and is rated no higher than moderate",
    )
    n_core = 11

    OBJECTIVE = (
        "# Objective: decay-rate estimator\n\n"
        "The estimator must meet these requirements.\n\n"
        "- R1. Estimate the decay rate k from daily samples.\n"
        "- R2. Report the half-life.\n"
        "- R3. Report the uncertainty of k and of the half-life.\n"
        "- R4. State the conditions under which the method is valid.\n")
    SPEC = (
        "# Specification: decay-rate estimator (version 1.0)\n\n"
        "## 1. Purpose\n\n"
        "The estimator gives the decay rate k of a first-order decay, y = A exp(-k t), from daily samples.\n\n"
        "## 2. Data\n\n"
        "One sample is taken each day. Ten samples are taken in each run, so a run covers 20 days.\n\n"
        "## 3. Method\n\n"
        "The background level is assumed to be zero and is not estimated. The estimator fits ln y on t by least squares. "
        "The slope is -k.\n\n"
        "## 4. Derived quantities\n\n"
        "At k = 0.30 per day the half-life is 3.5 days. The same rate is 0.0125 per hour.\n\n"
        "## 5. Performance\n\n"
        "The method recovers k to within 1 per cent.\n\n"
        "## 6. Reporting\n\n"
        "The estimate of k and the half-life are reported with the run date.\n\n"
        "## 7. Grading\n\n"
        "A result is graded Reliable when it is confirmed in more than one source or at more than one scale. "
        "The decay rate k is graded Reliable (one decay series, sampled daily).\n")
    EARLIER = (
        "# Review of version 0.9 of the decay-rate estimator specification\n\n"
        "## Findings\n\n"
        "- E1. The sampling interval is not stated. Status: resolved in version 1.0 (section 2).\n"
        "- E2. The background level is fixed at zero with no test. Status: open.\n\n"
        "## Null results\n\n"
        "- E3. The half-life of 3.5 days at k = 0.30 per day was checked and holds.\n")

    def build(self, tmp, args=None):
        root = (Path(tmp) / "Spec").resolve()
        (root / "docs").mkdir(parents=True)
        (root / "docs" / "objective.md").write_text(self.OBJECTIVE, encoding="utf-8")
        (root / "docs" / "spec.md").write_text(self.SPEC, encoding="utf-8")
        (root / "docs" / "review-v0.9.md").write_text(self.EARLIER, encoding="utf-8")
        self.root = root
        self.before = tree_hashes(root)
        return root

    EARLIER_LINE = "Earlier review: docs/review-v0.9.md."

    def prompt(self, root):
        return (f"Use the document-adversary skill to try to break the specification docs/spec.md (version 1.0). "
                f"Objective: docs/objective.md. {self.EARLIER_LINE} Subject: decay-spec. Project root: {root}. "
                f"When the skill has returned, save its report and any scripts as the skill instructs, tell me the "
                f"path and say whether the run is pending review.")

    def extra(self, root, t, text, reply):
        out = []
        times = first_use_times(root, ["docs/spec.md", "docs/objective.md", "review-v0.9.md"])
        spec, obj, rev = times["docs/spec.md"], times["docs/objective.md"], times["review-v0.9.md"]
        ordered = rev is not None and spec is not None and obj is not None and rev > spec and rev > obj
        out.append((self.checks_listed[11], ordered, f"first use: spec {spec}, objective {obj}, review {rev}"))
        out.append((self.checks_listed[12], re.search(r"(earlier|previous|prior)[^.\n]{0,80}(read|opened)[^.\n]{0,80}after|"
                                                      r"after[^.\n]{0,100}(drafted|written|wrote)[^.\n]{0,80}(earlier|previous|prior|review)",
                                                      t, re.I) is not None, ""))
        repeat = re.search(r"(repeat|extend)\w*[^\n]{0,40}\bE2\b|\bE2\b[^\n]{0,80}(repeat|extend)", t, re.I) is not None
        raised = re.search(r"interval[^.\n]{0,60}(not stated|missing|undefined|unstated)", t, re.I) is not None
        out.append((self.checks_listed[13], repeat and not raised, f"repeat tag {repeat}; E1 raised {raised}"))
        out.append((self.checks_listed[14], re.search(r"contradict\w*[^\n]{0,40}\bE3\b|\bE3\b[^\n]{0,80}contradict", t, re.I) is not None, ""))
        ok, detail = four_parts(t)
        out.append((self.checks_listed[15], ok, detail))
        out.append((self.checks_listed[16], re.search(r"^#+ .*alternativ", t, re.I | re.M) is not None
                    and re.search(r"^#+ .*(did not state|not stated|unstated)", t, re.I | re.M) is not None, ""))
        cited = re.search(r"\.py\b|scratch script", t, re.I) is not None
        saved = run_scripts(root, "document-adversary")
        out.append((self.checks_listed[17], not cited or bool(saved), f"script cited {cited}; saved {[p.name for p in saved]}"))
        out.extend(self.behaviour_checks(root, t, self.checks_listed[18:21]))
        return out

    @staticmethod
    def behaviour_checks(root, t, names):
        ran, background = ran_python(root), background_tasks(root)
        raised = reading_challenges(t, "Reliable")
        ok = all("major" not in head.lower() and re.search(r"reading|interpret|could mean|alternative", block, re.I)
                 for head, block in raised)
        return [(names[0], bool(ran), f"commands: {ran[:2]}"),
                (names[1], not background, f"{len(background)} background calls"),
                (names[2], ok, f"challenges about the grade: {[h[:70] for h, _ in raised]}")]

    def check(self, root, reply, before):
        text = self.result_text(root, "document-adversary-report.md")
        t = text or ""
        out = []

        def add(name, ok, detail=""):
            out.append((name, bool(ok), detail))

        add(self.checks_listed[0], text is not None)
        add(self.checks_listed[1], re.search(r"\bR3\b", t) and re.search(r"uncertaint", t, re.I))
        add(self.checks_listed[2], re.search(r"\b2\.3\d*\b", t) and "3.5" in t)
        add(self.checks_listed[3], re.search(r"\b(10|ten)\b[^.\n]{0,100}\b(20|twenty)\b|\b(20|twenty)\b[^.\n]{0,100}\b(10|ten)\b", t, re.I))
        add(self.checks_listed[4], re.search(r"baseline|background", t, re.I) and re.search(r"fixed|assum|not estimated|untested|not tested", t, re.I))
        add(self.checks_listed[5], "analysis-adversary" in t)
        ids = set(re.findall(r"\bC([1-9]\d*)\b", t))
        severities = re.findall(r"\b(major|moderate|minor)\b", t, re.I)
        settle = re.findall(r"what would settle it", t, re.I)
        add(self.checks_listed[6], {"1", "2", "3"} <= ids and len(severities) >= 3 and len(settle) >= 3,
            f"ids {sorted(ids)}; severities {len(severities)}; settle lines {len(settle)}")
        add(self.checks_listed[7], re.search(r"^#+\s*.*verdict", t, re.I | re.M) and re.search(r"not checked|could not check|what was not", t, re.I))
        raised = [ln.strip()[:100] for ln in t.splitlines()
                  if "0.0125" in ln and re.search(r"error|wrong|incorrect|inconsisten|mistake", ln, re.I)
                  and not re.search(r"\bholds\b|checks out|is correct|is right", ln, re.I)]
        add(self.checks_listed[8], not raised, f"lines: {raised[:2]}")
        add(self.checks_listed[9], tree_hashes(root) == before)
        add(self.checks_listed[10], text is not None and "document-adversary-report.md" in reply and "pending" in reply.lower()
            and "accepted the run" not in reply.lower())
        out.extend(self.extra(root, t, text, reply))
        return out


class DocumentAdversaryIndependent(DocumentAdversary):
    name = "document-adversary-independent"
    checks_listed = DocumentAdversary.checks_listed[:11] + (
        "the earlier review file was never opened",
        "the report says that no earlier review was read",
        "no challenge is tagged as a repeat of or contradiction of an earlier finding",
        "every challenge has evidence, consequence and what-would-settle-it parts",
        "a scratch script was run for the recomputation (not only arithmetic in the head)",
        "no background task was started",
        "a challenge about the Reliable grade, if raised, states both readings and is rated no higher than moderate",
    )
    EARLIER_LINE = "earlier reviews: independent."

    def extra(self, root, t, text, reply):
        rev = first_use_times(root, ["review-v0.9.md"])["review-v0.9.md"]
        out = [(self.checks_listed[11], rev is None, f"first use of the review file: {rev}"),
               (self.checks_listed[12], re.search(r"(no|not|none|never)[^.\n]{0,80}(earlier|previous|prior)?[^.\n]{0,40}(review|report)s?[^.\n]{0,40}"
                                                  r"(read|opened)|independent", t, re.I) is not None, ""),
               (self.checks_listed[13], re.search(r"(repeats?|contradicts?)\W{0,4}E\d|E\d\b[^\n]{0,80}(repeat|contradict)", t, re.I) is None, "")]
        ok, detail = four_parts(t)
        out.append((self.checks_listed[14], ok, detail))
        out.extend(self.behaviour_checks(root, t, self.checks_listed[15:18]))
        return out


class AnalysisAdversaryModel(Fixture):
    name = "analysis-adversary-model"
    N = 150
    checks_listed = (
        "a report analysis-adversary-report.md is saved in an output folder of the task",
        "an independent calibrated rate near the true 0.10 is given when the exponent is freed",
        "the fixed exponent 0.5 is named and a fitted exponent near 1 is given",
        "the report says the calibration used all the data and nothing was held out for validation",
        "skill is compared with a baseline (persistence, climatology or similar)",
        "the report has a process-model checks section",
        "the model code under review was not run",
        "the project files are unchanged",
        "the reply gives the saved path and reports the run as pending",
        "the report starts with a table of the two claims and a block for each",
        "the earlier review was opened only after the data and the model code were read",
        "the report says the earlier review was read after the findings were drafted",
        "the open earlier finding F2 (no validation split) is tagged as a repeat; F1 (rate insensitive to the exponent) as contradicted",
        "the comparison with the standard deviation of y gives both numbers",
        "the scripts are saved under code/ in the run folder and take their output location from an argument or a relative path",
        "no background task was started",
    )
    EARLIER_LINE = "Earlier review: docs/earlier-review.md."

    MODEL = (
        '"""Relaxation model y(t+1) = y(t) + lam (c h(t)**(-p) - y(t)); calibrate lam and c on all rows of data/obs.csv."""\n'
        "import csv\n"
        "import math\n\n"
        "EXPONENT = 0.5  # p, fixed\n\n"
        "rows = list(csv.DictReader(open('data/obs.csv', newline='')))\n"
        "h = [float(r['h']) for r in rows]\n"
        "y = [float(r['y']) for r in rows]\n\n\n"
        "def simulate(lam, c):\n"
        "    out = [y[0]]\n"
        "    for t in range(len(h) - 1):\n"
        "        out.append(out[-1] + lam * (c * h[t] ** (-EXPONENT) - out[-1]))\n"
        "    return out\n\n\n"
        "best = None\n"
        "for k in range(1, 60):\n"
        "    lam = 0.01 * k\n"
        "    base = simulate(lam, 0.0)\n"
        "    unit = [a - b for a, b in zip(simulate(lam, 1.0), base)]\n"
        "    c = sum(u * (o - b) for u, o, b in zip(unit, y, base)) / sum(u * u for u in unit)\n"
        "    rmse = math.sqrt(sum((b + c * u - o) ** 2 for u, o, b in zip(unit, y, base)) / len(y))\n"
        "    if best is None or rmse < best[2]:\n"
        "        best = (lam, c, rmse)\n"
        "print('lam = %.3f per day, c = %.3f, rmse = %.3f' % best)\n")
    EARLIER = (
        "# Earlier review of the relaxation model\n\n"
        "## Findings\n\n"
        "- F1. The calibrated rate of 0.160 per day is not sensitive to the exponent. Status: stated by the author.\n"
        "- F2. The calibration used all the data and no validation split was made. Status: open.\n")

    @staticmethod
    def _simulate(lam, c, p, h, y0):
        y = [y0]
        for t in range(len(h) - 1):
            y.append(y[-1] + lam * (c * h[t] ** (-p) - y[-1]))
        return y

    def build(self, tmp, args=None):
        import math
        import random
        rng = random.Random(1)
        x, h = 0.0, []
        for t in range(self.N):
            x = 0.85 * x + 0.35 * math.sqrt(1 - 0.85 ** 2) * rng.gauss(0, 1)
            h.append(math.exp(0.6 * math.cos(2 * math.pi * t / 60.0) + x))
        clean = self._simulate(0.10, 2.0, 1.0, h, 2.0)
        noise = random.Random(101)
        y = [v * (1 + 0.02 * noise.gauss(0, 1)) for v in clean]
        root = (Path(tmp) / "Relax").resolve()
        (root / "data").mkdir(parents=True)
        (root / "code").mkdir()
        (root / "docs").mkdir()
        (root / "data" / "obs.csv").write_text(
            "day,h,y\n" + "".join(f"{i},{a:.5f},{b:.5f}\n" for i, (a, b) in enumerate(zip(h, y))), encoding="utf-8")
        (root / "code" / "model.py").write_text(self.MODEL, encoding="utf-8")
        (root / "docs" / "earlier-review.md").write_text(self.EARLIER, encoding="utf-8")
        (root / "draft.md").write_text(
            "# Relaxation model\n\nThe model y(t+1) = y(t) + lam (c h(t)^(-0.5) - y(t)) was calibrated on data/obs.csv "
            "(all 150 days, code/model.py). The calibrated relaxation rate is lam = 0.160 per day, and the model fits "
            "the observations with an error far smaller than the standard deviation of y.\n", encoding="utf-8")
        self.root = root
        self.before = tree_hashes(root)
        return root

    def prompt(self, root):
        return (f"Use the analysis-adversary skill to try to break these two claims about the process model in "
                f"code/model.py, reported in draft.md: (1) the calibrated relaxation rate is lam = 0.160 per day; "
                f"(2) the model fits the observations with an error far smaller than the standard deviation of y. "
                f"Subject: relaxation-rate. Raw input: data/obs.csv. Code: code/model.py. The model code may not be "
                f"run. {self.EARLIER_LINE} Project root: {root}. When the skill has returned, save its report and any "
                f"scripts as the skill instructs, tell me the path and say whether the run is pending review.")

    def extra(self, root, t, text, reply):
        out = []
        times = first_use_times(root, ["data/obs.csv", "code/model.py", "earlier-review.md"])
        obs, mod, rev = times["data/obs.csv"], times["code/model.py"], times["earlier-review.md"]
        ordered = rev is not None and obs is not None and mod is not None and rev > obs and rev > mod
        out.append((self.checks_listed[10], ordered, f"first use: data {obs}, model {mod}, review {rev}"))
        out.append((self.checks_listed[11], re.search(r"(earlier|previous|prior)[^.\n]{0,80}(read|opened)[^.\n]{0,80}after|"
                                                      r"after[^.\n]{0,100}(drafted|written|wrote)[^.\n]{0,80}(earlier|previous|prior|review)",
                                                      t, re.I) is not None, ""))
        repeat = re.search(r"repeat\w*[^\n]{0,40}\bF2\b|\bF2\b[^\n]{0,80}repeat", t, re.I) is not None
        contra = re.search(r"contradict\w*[^\n]{0,40}\bF1\b|\bF1\b[^\n]{0,80}contradict", t, re.I) is not None
        out.append((self.checks_listed[12], repeat and contra, f"F2 repeat {repeat}; F1 contradicted {contra}"))
        both = [ln.strip()[:120] for ln in t.splitlines()
                if re.search(r"standard deviation|\bSD\b|\bs\.d\.|constant|mean", ln, re.I)
                and re.search(r"\b0\.9[3-6]\d*\b", ln) and re.search(r"\b0\.4[5-9]\d*\b", ln)]
        out.append((self.checks_listed[13], bool(both), f"lines with both numbers: {both[:1]}"))
        return out

    def extra_scripts(self, root):
        saved = [p for p in run_scripts(root, "analysis-adversary") if p.suffix == ".py"]
        absolute = [p.name for p in saved
                    if re.search(r"[A-Za-z]:[\\/]|['\"]/(tmp|home|Users|c)/", p.read_text(encoding="utf-8", errors="replace"))]
        return (bool(saved) and not absolute, f"scripts {[p.name for p in saved]}; with an absolute path {absolute}")

    def check(self, root, reply, before):
        text = self.result_text(root, "analysis-adversary-report.md")
        t = text or ""
        out = []

        def add(name, ok, detail=""):
            out.append((name, bool(ok), detail))

        add(self.checks_listed[0], text is not None)
        add(self.checks_listed[1], re.search(r"\b0\.(09\d*|10\d*|11\d*)\b", t))
        name = r"(exponent|\bp\b)"
        add(self.checks_listed[2], re.search(name, t, re.I) and re.search(r"\b0\.5\b", t)
            and (re.search(name + r"[^\n]{0,160}\b(0\.9\d*|1\.0\d*|1\.1\d*|1)\b", t, re.I)
                 or re.search(r"\bp\s*=\s*\**1(\.0)?\b", t)))
        add(self.checks_listed[3], re.search(r"validat|hold[- ]?out|held out|out[- ]of[- ]sample", t, re.I)
            and re.search(r"all (the |150 )?(data|rows|days)|same data|no (independent |separate )?validation|not held out|no hold", t, re.I))
        add(self.checks_listed[4], re.search(r"persistence|baseline|climatolog|trivial|naive|null model|mean model", t, re.I))
        add(self.checks_listed[5], re.search(r"^[#*\s\d.)]*process[- ]model checks", t, re.I | re.M))
        ran = []
        for f in glob.glob(str(CLAUDE_HOME / "projects" / project_key(root) / "**" / "*.jsonl"), recursive=True):
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    for m in re.finditer(r'"command":\s*"((?:[^"\\]|\\.)*)"', line):
                        if re.search(r"(python\S*|\bpy)\s+(-\S+\s+)*\S*model\.py", m.group(1).replace("\\\\", "/")):
                            ran.append(m.group(1)[:100])
        add(self.checks_listed[6], not ran, f"commands that ran it: {ran[:2]}")
        add(self.checks_listed[7], tree_hashes(root) == before)
        add(self.checks_listed[8], text is not None and "analysis-adversary-report.md" in reply and "pending" in reply.lower()
            and "accepted the run" not in reply.lower())
        head = t[:4000]
        add(self.checks_listed[9], re.search(r"^\|.*(reproduc|not checked|confirmed|holds)", head, re.I | re.M)
            and re.search(r"claim\W{0,3}1", t, re.I) and re.search(r"claim\W{0,3}2", t, re.I))
        out.extend(self.extra(root, t, text, reply))
        if len(self.checks_listed) > 14:
            ok, detail = self.extra_scripts(root)
            out.append((self.checks_listed[14], ok, detail))
            background = background_tasks(root)
            out.append((self.checks_listed[15], not background, f"{len(background)} background calls"))
        return out


class AnalysisAdversaryIndependent(AnalysisAdversaryModel):
    name = "analysis-adversary-independent"
    checks_listed = AnalysisAdversaryModel.checks_listed[:9] + (
        "the earlier review file was never opened",
        "the report says that no earlier review was read",
        "no finding is tagged as a repeat of or contradiction of an earlier finding",
        "no background task was started",
    )
    EARLIER_LINE = "earlier reviews: independent."

    def extra(self, root, t, text, reply):
        return []

    def check(self, root, reply, before):
        base = AnalysisAdversaryModel.check(self, root, reply, before)[:9]
        t = self.result_text(root, "analysis-adversary-report.md") or ""
        rev = first_use_times(root, ["earlier-review.md"])["earlier-review.md"]
        base.append((self.checks_listed[9], rev is None, f"first use of the review file: {rev}"))
        base.append((self.checks_listed[10], re.search(r"(no|not|none|never)[^.\n]{0,80}(review|report)s?[^.\n]{0,40}(read|opened)|"
                                                       r"independent", t, re.I) is not None, ""))
        base.append((self.checks_listed[11], re.search(r"(repeats?|contradicts?)\W{0,4}F\d|F\d\b[^\n]{0,80}(repeat|contradict)", t, re.I) is None, ""))
        background = background_tasks(root)
        base.append((self.checks_listed[12], not background, f"{len(background)} background calls"))
        return base


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
    """Shared by the fixtures that read a generated EndNote library through a second, read-only server."""

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
    uses_docx_skill = True
    timeout = 1800
    # (text in the clean paragraph, text with the planted fault)
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
        "the reply says that the validator ran or that it did not",
    )

    # A generated prose paragraph (the proofread scope), a second paragraph that is out of scope and holds a fault the
    # skill must leave alone, and a short verse. Each fault in PLANTS is made in a run of the first paragraph.
    PROSE = ("Macrotidal estuaries are relatively stable landforms over decades, although their form depends on the "
             "supply of sediment. The channels and flats of each system reflect an interplay of processes which act over "
             "very different time scales. Sheltered drowned valley harbours fill slowly with mud, and the present form, "
             "like the past and future, is affected by changes in sea level. Many estuaries have had similar histories of "
             "infilling and scour.")
    OUT_OF_SCOPE = ("Surveys of the two seperate channels were repeated each spring, and the results are summarised in "
                    "the notes that follow.")
    VERSE = ["The tide comes in,", "the tide goes out,", "and the mud remains."]

    def build(self, tmp, args=None):
        require_word()
        root = (Path(tmp) / "Notes").resolve()
        root.mkdir()
        faulty = self.PROSE
        for old, new in self.PLANTS:
            if faulty.count(old) != 1:
                raise AssertionError(f"the generated paragraph must hold {old!r} exactly once")
            faulty = faulty.replace(old, new)
        target = root / "Estuary Notes.docx"
        write_minimal_docx(target, [w_para(faulty), w_para(self.OUT_OF_SCOPE), *[w_para(v) for v in self.VERSE]])
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
        add(self.checks_listed[9], "validat" in rl)
        return out


# ---------------------------------------------------------------------------------------------------------
def require_word():
    if sys.platform != "win32" or not word_available():
        raise Skip("Microsoft Word is not available (the proofread skill and this fixture need it)")


def xml_text(text):
    return html.escape(text, quote=False)


def w_run(text):
    return f'<w:r><w:t xml:space="preserve">{xml_text(text)}</w:t></w:r>'


def w_para(*runs):
    return "<w:p>" + "".join(r if r.startswith("<") else w_run(r) for r in runs) + "</w:p>"


def w_field(instruction, result):
    return ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            f'<w:r><w:instrText xml:space="preserve"> {instruction} </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            f'{w_run(result)}<w:r><w:fldChar w:fldCharType="end"/></w:r>')


def write_minimal_docx(path, paragraphs):
    """A minimal .docx (content types, relationships, document.xml) whose body holds the given paragraph XML."""
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                + "".join(paragraphs) + "</w:body></w:document>")
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


def comment_bodies(path):
    """The text of each comment in a .docx."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/comments.xml").decode("utf-8") if "word/comments.xml" in z.namelist() else ""
    return [re.sub(r"\s+", " ", paragraph_text(c, "accept")).strip() for c in re.findall(r"<w:comment\b.*?</w:comment>", xml, re.S)]


def revision_authors(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    return set(re.findall(r"<w:(?:ins|del)\b[^>]*w:author=\"([^\"]*)\"", xml))


def clauses(text):
    """Sentences and list items, so that a finding about one item is not read as a finding about its neighbour."""
    return [c for c in re.split(r"(?<!et al)[.;]\s|\n+", text) if c.strip()]


# ---------------------------------------------------------------------------------------------------------
class ProofreadStructure(Fixture):
    """The other half of the proofread skill: captions, cross-references and citations against the References list."""
    name = "proofread-structure"
    timeout = 1800
    uses_docx_skill = True
    PROBLEM = re.compile(
        r"cross-?ref|not (?:referred|referenced|mentioned|cited|matched|found)|never (?:referred|referenced|mentioned|cited)"
        r"|isn't (?:referred|cited|mentioned)|nothing (?:refers|cites|in the text)|unreferenced|uncited|unmatched|unresolved"
        r"|no (?:caption|matching|entry|reference|in-text|mention|citation)|missing|orphan", re.I)
    checks_listed = (
        "the proofread copy is saved beside the original as '<name> - proofread.docx'",
        "the original is unchanged",
        "the earlier proofread copy is renamed '<name> - proofread (previous run).docx' with its content intact",
        "every change is tracked: rejecting all changes restores the original text exactly",
        "every revision is authored by Claude",
        "Figure 2 (a caption that nothing refers to) is flagged",
        "Figure 3 (a cross-reference with no caption) is flagged",
        "Brown 2015 (a citation with no References entry) is flagged",
        "Zeta 2010 (a References entry that nothing cites) is flagged",
        "the correctly matched citations (Smith, Jones and Lee, Kirby et al.) are not flagged as problems",
        "comments: at most 5, each at most 50 words",
        "the reply says that the validator ran or that it did not",
        "the reply says that citation accuracy is not checked (citation-check)",
        "Word opens the proofread copy without error and reports its revisions",
    )

    def body(self):
        cite = CitationCheck._field("Jones, A and Lee, B", "2021", "Tidal asymmetry in estuaries", 7, "(Jones and Lee, 2021)")
        return [
            w_para("Introduction"),
            w_para("Tidal range varies along the estuary (Smith, 2019; Jones and Lee, 2021) and is shown in Figure 1. "
                   "The mean flow follows the same pattern, as set out in ", w_field("REF _Ref100000001 \\h", "Table 1"),
                   ". Earlier work by Brown (2015) used a similar approach, and the survey of Kirby et al. (2000) found the "
                   "same trend. The discharge series is plotted in Figure 3."),
            w_para("The result agrees with earlier findings ", cite, "."),
            w_para("Figure ", w_field("SEQ Figure \\* ARABIC", "1"), " – Tidal range along the estuary"),
            w_para("Figure ", w_field("SEQ Figure \\* ARABIC", "2"), " – Mean flow at the mouth"),
            w_para('<w:bookmarkStart w:id="1" w:name="_Ref100000001"/>', "Table ", w_field("SEQ Table \\* ARABIC", "1"),
                   '<w:bookmarkEnd w:id="1"/>', " – Survey dates"),
            w_para("References"),
            w_para('<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> ADDIN EN.REFLIST '
                   '</w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r>',
                   "Jones A and Lee B, 2021, Tidal asymmetry in estuaries, Journal of Coastal Research, 37, 1-10."),
            w_para("Kirby A, Lee B and Cho C, 2000, Tidal flat shape, Estuarine Science, 12, 100-120."),
            w_para("Smith J, 2019, Tides and flow, Marine Reports, 5, 20-30."),
            w_para("Zeta Q, 2010, An unused source, Unused Press.", '<w:r><w:fldChar w:fldCharType="end"/></w:r>'),
        ]

    def build(self, tmp, args=None):
        require_word()
        root = (Path(tmp) / "Structure").resolve()
        root.mkdir()
        self.manuscript = root / "Structure Notes.docx"
        write_minimal_docx(self.manuscript, self.body())
        marker = root / "Structure Notes - proofread.docx"
        write_minimal_docx(marker, [w_para("PREVIOUS RUN MARKER")])
        self.marker_bytes = marker.read_bytes()
        self.original_text = doc_text(self.manuscript)
        self.root = root
        self.before = tree_hashes(root)
        return root

    def prompt(self, root):
        return ("Use the proofread skill on 'Structure Notes.docx' in this folder. Scope: the whole document. Do not ask me "
                "questions. When the skill has finished, give me the path of the proofread copy and the summary.")

    def flagged(self, texts, needle):
        rx = re.compile(needle, re.I)
        return any(rx.search(c) and self.PROBLEM.search(c) for text in texts for c in clauses(text))

    def check(self, root, reply, before):
        out = []

        def add(name, ok, detail=""):
            out.append((name, bool(ok), detail))

        c = self.checks_listed
        copy = root / "Structure Notes - proofread.docx"
        previous = root / "Structure Notes - proofread (previous run).docx"
        made = copy.is_file() and copy.read_bytes() != self.marker_bytes
        add(c[0], made, f"files: {sorted(p.name for p in root.iterdir())}")
        add(c[1], tree_hashes(root).get("Structure Notes.docx") == before.get("Structure Notes.docx"))
        add(c[2], previous.is_file() and previous.read_bytes() == self.marker_bytes)
        if not made:
            for name in c[3:11]:
                add(name, False, "no new copy")
        else:
            rejected = doc_text(copy, "reject")
            add(c[3], rejected == self.original_text, "paragraphs differing: "
                f"{[i for i, (a, b) in enumerate(zip(rejected, self.original_text)) if a != b][:5]}")
            authors = revision_authors(copy)
            add(c[4], authors <= {"Claude"}, f"authors: {sorted(authors)}")
            bodies = comment_bodies(copy)
            texts = [reply] + bodies
            add(c[5], self.flagged(texts, r"Figure\s*2"))
            add(c[6], self.flagged(texts, r"Figure\s*3"))
            add(c[7], self.flagged(texts, r"Brown"))
            add(c[8], self.flagged(texts, r"Zeta"))
            wrong = [t for t in texts for cl in clauses(t) if re.search(r"Smith|Jones|Kirby", cl)
                     and any(w in cl.lower() for w in ("no entry", "no matching", "unmatched", "not matched", "orphan",
                                                       "not found", "unresolved", "missing"))]
            add(c[9], not wrong, f"{len(wrong)} mentions")
            add(c[10], len(bodies) <= 5 and all(len(b.split()) <= 50 for b in bodies),
                f"{len(bodies)} comments; words: {[len(b.split()) for b in bodies]}")
        add(c[11], "validat" in reply.lower())
        rl = reply.lower()
        add(c[12], "citation-check" in rl or "citation check" in rl)
        if not made:
            add(c[13], False, "no new copy")
        else:
            code, text = word_run(
                "$w = New-Object -ComObject Word.Application; $w.Visible = $false; $w.DisplayAlerts = 0\n"
                f"try {{ $d = $w.Documents.Open('{copy}', $false, $true); 'revisions=' + $d.Revisions.Count; "
                "$d.Close($false) }\nfinally { $w.Quit() }\n")
            m = re.search(r"revisions=(\d+)", text)
            add(c[13], code == 0 and m is not None, text[:160])
        return out


REF_TYPES = {17: "Journal Article", 12: "Web Page", 16: "Report"}


def require_server_packages(*names):
    """Skip a fixture whose generated library is served by the EndNote server when the server's packages are missing."""
    missing = [n for n in names if importlib.util.find_spec(n) is None]
    if missing:
        raise Skip(f"the EndNote server's packages are not importable here: {', '.join(missing)}")


def make_pdf(path, lines, font_size=9):
    """A minimal one-page PDF whose text is the given lines (ASCII only), readable by pypdf."""
    def esc(s):
        return s.replace(chr(92), chr(92) * 2).replace("(", chr(92) + "(").replace(")", chr(92) + ")")
    content = f"BT /F1 {font_size} Tf {font_size + 4} TL 60 740 Td\n" + "".join(f"({esc(ln)}) Tj T*\n" for ln in lines) + "ET"
    objects = ["<< /Type /Catalog /Pages 2 0 R >>",
               "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
               f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode("ascii")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii")
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode("ascii")
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    Path(path).write_bytes(out)


class SyntheticLibrary(TestLibrary):
    """A generated EndNote library (the two tables the read-only server uses) so that a fixture never touches a real one."""
    COLUMNS = ("author", "year", "title", "secondary_title", "volume", "number", "pages", "publisher", "abstract", "keywords",
               "url", "notes", "isbn", "electronic_resource_number")

    def make_library(self, tmp, records, pdfs=None):
        """records: [dict with the COLUMNS keys that are needed]; ids run from 1. pdfs: {record id: (file name, lines)}."""
        import sqlite3
        base = Path(tmp) / "Library"
        base.mkdir()
        lib = base / "Synthetic.enl"
        data = base / "Synthetic.Data"
        data.mkdir()
        con = sqlite3.connect(lib)  # the .enl file is itself the SQLite database that the server opens
        cols = ", ".join(f"{c} TEXT NOT NULL DEFAULT ''" for c in self.COLUMNS)
        con.execute("CREATE TABLE refs (id INTEGER PRIMARY KEY AUTOINCREMENT, trash_state INTEGER NOT NULL DEFAULT 0, "
                    f"reference_type INTEGER NOT NULL DEFAULT 17, {cols})")
        con.execute("CREATE TABLE file_res (refs_id INTEGER NOT NULL, file_path TEXT NOT NULL DEFAULT '', "
                    "file_type INTEGER NOT NULL, file_pos INTEGER NOT NULL)")
        for rec in records:
            names = [c for c in self.COLUMNS if c in rec]
            con.execute(f"INSERT INTO refs ({', '.join(names)}) VALUES ({', '.join('?' for _ in names)})",
                        [rec[c] for c in names])
        for ref_id, (name, lines) in (pdfs or {}).items():
            (data / "PDF").mkdir(exist_ok=True)
            make_pdf(data / "PDF" / name, lines)
            con.execute("INSERT INTO file_res (refs_id, file_path, file_type, file_pos) VALUES (?, ?, 0, 0)", (ref_id, name))
        con.commit()
        con.close()
        self.library = lib.resolve()
        self.write_mcp_config(tmp)
        return self.library


# ---------------------------------------------------------------------------------------------------------
class CitationCheck(SyntheticLibrary, Fixture):
    name = "citation-check"
    timeout = 1800
    # the generated library: ids run from 1 in this order
    LIBRARY = [
        {"author": "Coastal Hazards Panel,", "year": "2023", "title": "Annual Coastal Hazards Outlook 2023", "number": "May 2025"},
        {"author": "Tidal Futures Commission", "year": "2023", "title": "Synthesis Report on Tidal Change 2023"},
        {"author": "OpenShore Atlas", "year": "2025", "title": "Open Spatial Shoreline Data and Research"},
    ]
    # (library id, rec-number written in the field, year written in the field or None for the library's year)
    CITES = [(1, 1, None), (2, 52, None), (3, 3, "2024")]
    INVENTED = ("Harrington and Osei", "2021", "Adaptive Planning Horizons for Estuarine Flood Defences", 99)
    checks_listed = (
        "a report citation-check-report.md is saved in an output folder of the task",
        "the invented reference is reported as unresolved",
        "the year in the field (2024) against the library (2025) is reported for OpenShore Atlas",
        "the stale rec-number 52 against the library record is reported for the Tidal Futures Commission",
        "the correct reference (Coastal Hazards Panel) is not reported as a problem",
        "no external call was made",
        "the report says external verification was not done",
        "the manuscript, the library and the project files are unchanged",
    )

    def build(self, tmp, args=None):
        require_server_packages("mcp")
        self.make_library(tmp, self.LIBRARY)
        # the snapshot in the field repeats the library record exactly, so only the planted faults differ
        self.records = {n + 1: (r["author"], r["year"], r["title"], r.get("number", ""), 17) for n, r in enumerate(self.LIBRARY)}
        root = (Path(tmp) / "Paper").resolve()
        root.mkdir()
        self.manuscript = root / "manuscript.docx"
        self._write_docx(self.manuscript)
        self.root = root
        self.before = tree_hashes(root)
        self.lib_before = self._library_hashes()
        return root

    @staticmethod
    def _field(author, year, title, recnum, display, number="", reftype=17):
        esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        cite = (f"<EndNote><Cite><Author>{esc(author)}</Author><Year>{year}</Year><RecNum>{recnum}</RecNum>"
                f"<DisplayText>{esc(display)}</DisplayText><record><rec-number>{recnum}</rec-number>"
                f"<foreign-keys><key app=\"EN\" db-id=\"fixture\">{recnum}</key></foreign-keys>"
                f"<ref-type name=\"{REF_TYPES.get(reftype, 'Generic')}\">{reftype}</ref-type><contributors><authors><author>{esc(author)}</author>"
                f"</authors></contributors><titles><title>{esc(title)}</title></titles>"
                + (f"<number>{esc(number)}</number>" if number else "") +
                f"<dates><year>{year}</year></dates></record></Cite></EndNote>")
        # split the raw text first and escape each half, so that no XML entity is cut in two
        raw = " ADDIN EN.CITE " + cite
        half = len(raw) // 2
        return ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
                f'<w:r><w:instrText xml:space="preserve">{esc(raw[:half])}</w:instrText></w:r>'
                f'<w:r><w:instrText xml:space="preserve">{esc(raw[half:])}</w:instrText></w:r>'
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

        negated = re.compile(r"\b(?:no|without|zero|not)\s+(?:\w+\s+){0,2}?(?:drift|mismatch\w*|ambigu\w*|unresolved)\b", re.I)

        def lines_with(*needles, any_of=()):
            # "no drift" and "no mismatch" say that the record is fine, so they are removed before the problem words are sought
            return [ln for ln in lines if all(n.lower() in ln.lower() for n in needles)
                    and (not any_of or any(a.lower() in negated.sub("", ln).lower() for a in any_of))]

        add(self.checks_listed[0], text is not None)
        add(self.checks_listed[1], lines_with("Adaptive Planning", any_of=("unresolved", "not found", "no match", "no reasonable"))
            or lines_with("Harrington", any_of=("unresolved", "not found", "no match", "no reasonable")))
        add(self.checks_listed[2], lines_with("OpenShore", "2024", "2025"))
        add(self.checks_listed[3], lines_with("Tidal Futures", "52") or lines_with("Synthesis Report", "52"))
        bad = lines_with("Coastal Hazards", any_of=("mismatch", "unresolved", "ambiguous", "drift"))
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


def flatten_strings(value):
    """Every string inside a nested value, joined by spaces."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(flatten_strings(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(flatten_strings(v) for v in value)
    return str(value)


def tool_calls(root):
    """[(tool name, all the strings of its input)] for every tool call in the session transcripts of root."""
    import glob
    found = []
    for f in glob.glob(str(CLAUDE_HOME / "projects" / project_key(root) / "**" / "*.jsonl"), recursive=True):
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"tool_use"' not in line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                content = (entry.get("message") or {}).get("content")
                for item in content if isinstance(content, list) else []:
                    if isinstance(item, dict) and item.get("type") == "tool_use":
                        found.append((item.get("name", ""), flatten_strings(item.get("input"))))
    return found


def short_author(record):
    """'Marlow and Okoro', 'Quill', or 'LeCun et al.' from an author string with authors separated by a carriage return."""
    if record.get("display"):
        return record["display"]
    surnames = [a.split(",")[0].strip() for a in record["author"].split(chr(13))]
    return surnames[0] if len(surnames) == 1 else " and ".join(surnames) if len(surnames) == 2 else surnames[0] + " et al."


def own_calls(calls):
    """The tool calls that do work. The Skill and Agent calls carry the user's prompt text as their arguments, so words in
    them (for example the names of the services the prompt forbids) are not evidence of anything."""
    return [(n, s) for n, s in calls if n not in ("Skill", "Agent", "Task")]


def cite_paragraph(lead, record, recnum, tail="."):
    """A paragraph: lead text, one CWYW field for the record (a dict with author, year, title), then the tail."""
    display = f"({short_author(record)}, {record['year']})"
    author = record["author"].replace(chr(13), " and ")
    return w_para(lead, CitationCheck._field(author, record["year"], record["title"], recnum, display), tail)


def verdict_line(lines, needle, verdict, exclude=None):
    """Is there a line (a table row or a list item) that names the needle and carries the verdict?"""
    return any(re.search(needle, ln, re.I) and re.search(verdict, ln, re.I) and not (exclude and re.search(exclude, ln, re.I))
               for ln in lines)


NOT_SUPPORTED = r"(?<!not )(?<!un)supported"


# ---------------------------------------------------------------------------------------------------------
class CitationCheckContext(SyntheticLibrary, Fixture):
    """Stage 2 (--context) against a generated library whose first record has a linked PDF of known text."""
    name = "citation-check-context"
    timeout = 1800
    max_turns = 80
    SOURCE = ["Sediment transport in the Lower Brook estuary",
              "Marlow T and Okoro E, 2018, Journal of Estuary Studies",
              "Abstract. We measured suspended sediment concentration at three stations in the Lower Brook estuary",
              "over one spring-neap cycle. Mean concentration was 120 mg per litre at the mouth and 340 mg per litre at the head.",
              "Results. Concentration increased towards the head of the estuary at all three stations.",
              "Peak concentration occurred during spring tides.",
              "We found no relationship between concentration and river discharge during the survey.",
              "Discussion. The data suggest that tidal pumping contributes to the up-estuary increase, although the survey",
              "was too short to separate it from other processes. We did not measure bed sediment composition."]
    RECORDS = [
        {"author": "Marlow, T\rOkoro, E", "year": "2018", "title": "Sediment transport in the Lower Brook estuary",
         "secondary_title": "Journal of Estuary Studies"},
        {"author": "Quill, R", "year": "2015", "title": "Wave climate of the outer estuary", "secondary_title": "Coastal Notes"},
    ]
    CLAIMS = [  # (sentence, record index, planted verdict)
        ("Peak suspended sediment concentration occurred during spring tides", 0, "Supported"),
        ("Tidal pumping is the main cause of the up-estuary increase in sediment concentration", 0, "Overstated"),
        ("Concentration increased towards the mouth of the estuary at all three stations", 0, "Contradicted"),
        ("The bed sediment of the estuary is mainly fine sand", 0, "Not located"),
        ("River discharge controlled the concentration, and the peak occurred during spring tides", 0, "Contradicted and Supported"),
        ("Wave climate is dominant in the outer estuary", 1, "Unable to verify"),
    ]
    checks_listed = (
        "a report citation-check-report.md is saved in an output folder of the task",
        "'Peak ... during spring tides' is Supported",
        "'Tidal pumping is the main cause' is Overstated",
        "'Concentration increased towards the mouth' is Contradicted",
        "'The bed sediment ... fine sand' is Not located",
        "the compound sentence on river discharge and spring tides gets a verdict for each component",
        "the citation with no linked file (Quill 2015) is Unable to verify",
        "read_linked_file_text was called with max_chars of 100,000 or more",
        "no external call was made",
        "the manuscript, the library, its PDF and the project files are unchanged",
    )

    def build(self, tmp, args=None):
        require_server_packages("pypdf", "mcp")  # the server reads the linked PDF with pypdf
        self.make_library(tmp, self.RECORDS, pdfs={1: ("Marlow2018.pdf", self.SOURCE)})
        root = (Path(tmp) / "Paper").resolve()
        root.mkdir()
        self.manuscript = root / "manuscript.docx"
        write_minimal_docx(self.manuscript, [w_para("Results")] + [
            cite_paragraph(sentence + " ", self.RECORDS[i], i + 1) for sentence, i, _ in self.CLAIMS])
        self.root = root
        self.before = tree_hashes(root)
        self.lib_before = self._library_hashes()
        return root

    def prompt(self, root):
        return ("Use the citation-check skill on 'manuscript.docx' in this folder, with context (--context). Scope: the whole "
                "document. Where the skill asks for confirmation before external verification, the answer is no: make no "
                "external call of any kind (no CrossRef, OpenAlex, arXiv, Semantic Scholar, Unpaywall or web request) and report "
                "the external checks as not done. Do not ask me questions. When the skill has finished, tell me the path of the "
                "report and whether the run is pending review.")

    def check(self, root, reply, before):
        text = self.result_text(root, "citation-check-report.md")
        lines = (text or "").splitlines()
        c = self.checks_listed
        out = []

        def add(name, ok, detail=""):
            out.append((name, bool(ok), detail))

        add(c[0], text is not None)
        add(c[1], verdict_line(lines, r"spring tides", NOT_SUPPORTED, exclude=r"discharge") or
            bool(re.search(r"supported\W*[:=|]?\W*[1-9]|[1-9]\W*supported", text or "", re.I)))
        add(c[2], verdict_line(lines, r"tidal pumping", r"overstated"))
        add(c[3], verdict_line(lines, r"towards the mouth|toward the mouth|the mouth of", r"contradict"))
        add(c[4], verdict_line(lines, r"bed sediment|fine sand", r"not located"))
        discharge = [ln for ln in lines if re.search(r"discharge", ln, re.I)]
        second_half = [ln for ln in lines if re.search(r"and the peak occurred during spring tides", ln, re.I)]
        add(c[5], verdict_line(discharge, r"discharge", r"contradict")
            and (verdict_line(discharge, r"discharge", NOT_SUPPORTED) or verdict_line(second_half, r"spring tides", NOT_SUPPORTED)),
            "needs a Contradicted verdict for the discharge component and a Supported one for the spring-tides component, "
            "on one row or on separate rows that quote each half of the sentence")
        add(c[6], verdict_line(lines, r"quill|wave climate", r"unable to verify"))
        calls = tool_calls(root)
        sizes = [int(m) for name, s in calls if "read_linked_file_text" in name for m in re.findall(r"\b(\d{4,9})\b", s)]
        add(c[7], any(n >= 100000 for n in sizes), f"values seen: {sizes}")
        external = [(name, s[:100]) for name, s in own_calls(calls)
                    if name in ("WebFetch", "WebSearch") or name.startswith(("mcp__exa__", "mcp__claude_ai_Consensus"))
                    or (name in ("Bash", "PowerShell") and re.search(r"https?://|crossref|openalex|arxiv|semanticscholar|unpaywall", s, re.I))]
        add(c[8], not external, f"{len(external)} calls: {external[:2]}")
        add(c[9], tree_hashes(root) == before and self._library_hashes() == self.lib_before)
        return out


# ---------------------------------------------------------------------------------------------------------
class CitationCheckExternal(SyntheticLibrary, Fixture):
    """Stage 1 with external verification confirmed for CrossRef, OpenAlex and arXiv only (run with --external)."""
    name = "citation-check-external"
    timeout = 2400
    max_turns = 80
    RECORDS = [
        {"author": "Watson, J. D.\rCrick, F. H. C.", "year": "1953",
         "title": "Molecular Structure of Nucleic Acids: A Structure for Deoxyribose Nucleic Acid",
         "secondary_title": "Nature", "volume": "171", "electronic_resource_number": "10.1038/171737a0"},
        {"author": "Shannon, C. E.", "year": "1949", "title": "A Mathematical Theory of Communication",
         "secondary_title": "Bell System Technical Journal", "electronic_resource_number": "10.1002/j.1538-7305.1948.tb01338.x"},
        {"author": "LeCun, Y.\rBengio, Y.\rHinton, G.", "year": "2015", "title": "Deep learning", "secondary_title": "Nature",
         "volume": "521", "display": "LeCun et al."},
        {"author": "Harrington, A.\rOsei, K.", "year": "2021", "title": "Adaptive Planning Horizons for Estuarine Flood Defences",
         "secondary_title": "Journal of Coastal Research", "volume": "37", "electronic_resource_number": "10.9999/jcr.2021.0099"},
    ]
    LEADS = ["The structure of DNA was first described ", "The theory of information is set out ",
             "Neural networks are reviewed ", "Flood defences need adaptive planning "]
    checks_listed = (
        "a report citation-check-report.md is saved in an output folder of the task",
        "CrossRef was queried by DOI for Watson and Crick (10.1038/171737a0)",
        "the year in the library for Shannon (1949) against CrossRef (1948) is reported",
        "Watson and Crick (correct record and DOI) is not reported as a problem",
        "LeCun et al. (no DOI) was found by a title search and is reported verified",
        "Harrington and Osei (invented, with a non-existent DOI prefix) is not reported as verified",
        "only CrossRef, OpenAlex and arXiv were used: no Semantic Scholar, Exa, Consensus or mailto",
        "every OpenAlex title search uses filter=title.search, never the bare search parameter",
        "arXiv was queried with the title double-quoted",
        "the manuscript, the library and the project files are unchanged",
    )

    def build(self, tmp, args=None):
        if not getattr(args, "external", False):
            raise Skip("sends bibliographic metadata to CrossRef, OpenAlex and arXiv; give --external to run it")
        require_server_packages("mcp")
        self.make_library(tmp, self.RECORDS)
        root = (Path(tmp) / "Paper").resolve()
        root.mkdir()
        self.manuscript = root / "manuscript.docx"
        write_minimal_docx(self.manuscript, [w_para("Background")] + [
            cite_paragraph(lead, self.RECORDS[i], i + 1) for i, lead in enumerate(self.LEADS)])
        self.root = root
        self.before = tree_hashes(root)
        self.lib_before = self._library_hashes()
        return root

    def prompt(self, root):
        return ("Use the citation-check skill on 'manuscript.docx' in this folder. Scope: the whole document. Stage 1 only. "
                "Where the skill asks for confirmation before external verification, the answer is yes, for CrossRef, OpenAlex "
                "and arXiv only: you may send the titles, authors, years and DOIs of the four cited records to those three "
                "services and to no other service (not Semantic Scholar, Exa, Consensus or Unpaywall), and you must not add a "
                "mailto parameter or any other personal identifier. Do not ask me again. When the skill has finished, tell me the "
                "path of the report and whether the run is pending review.")

    def check(self, root, reply, before):
        text = self.result_text(root, "citation-check-report.md")
        lines = (text or "").splitlines()
        calls = own_calls(tool_calls(root))
        joined = " ".join(s for _, s in calls)
        c = self.checks_listed
        out = []

        def add(name, ok, detail=""):
            out.append((name, bool(ok), detail))

        add(c[0], text is not None)
        # a session may script its queries, so the DOI and the CrossRef address can sit in one script as data and a template
        add(c[1], re.search(r"api\.crossref\.org/works", joined, re.I) is not None
            and re.search(r"10\.1038(?:/|%2F)171737a0", joined, re.I) is not None, "needs a CrossRef works call and the DOI")
        add(c[2], any(re.search("shannon", ln, re.I) and "1948" in ln and "1949" in ln for ln in lines))
        problem = r"mismatch|not verified|unresolved|not found|differ|wrong|discrepan"
        add(c[3], not verdict_line(lines, r"watson|crick|nucleic", problem), "a line about this record names a problem")
        title_search = re.search(r"title\.search|query\.title|query\.bibliographic|[?&]query=|ti:", joined, re.I) is not None
        positive = r"(?<!not )(?<!un)verified|(?<!no )(?<!not a )match(?:ed|es)? on|same work|confirmed"
        add(c[4], title_search and verdict_line(lines, r"lecun|deep learning", positive, exclude=r"not verified|unverified|ambiguous|unresolved"),
            f"title search seen: {title_search}")
        add(c[5], verdict_line(lines, r"harrington|adaptive planning", r"not verified|not found|no match|not indexed|could not|unverified|no result")
            and not verdict_line(lines, r"harrington|adaptive planning", r"(?<!not )(?<!un)verified", exclude=r"not verified|unverified|not been verified"))
        banned = re.search(r"semanticscholar\.org|unpaywall\.org|mailto=|mcp__exa__|Consensus__", " ".join(n + " " + s for n, s in calls), re.I)
        add(c[6], banned is None, f"found: {banned.group(0) if banned else ''}")
        openalex_used = re.search(r"openalex\.org", joined, re.I) is not None
        bare = re.search(r"[?&]search=", joined) is not None
        add(c[7], openalex_used and not bare, f"OpenAlex used: {openalex_used}; bare search parameter present: {bare}")
        arxiv_used = re.search(r"arxiv\.org", joined, re.I) is not None
        queries = re.findall(r"search_query=[^\s<>]*", joined)
        # a title quote is %22, or a quote that is followed by the title; in script text a quote followed by a space, +, ) , ;
        # is only the end of a string literal
        quote = r"search_query=(?:ti|all)(?::|%3A)(?:%22|" + chr(92) * 2 + r"?\"(?![\s+),;\]]|$))"
        unquoted = [q for q in queries if not re.match(quote, q, re.I)]
        add(c[8], arxiv_used and bool(queries) and not unquoted, f"arXiv used: {arxiv_used}; {len(queries)} queries, unquoted: {unquoted[:2]}")
        add(c[9], tree_hashes(root) == before and self._library_hashes() == self.lib_before)
        return out


# ---------------------------------------------------------------------------------------------------------
class LiteratureSearch(SyntheticLibrary, Fixture):
    """The local half of the skill: a generated EndNote library only, with no external source."""
    name = "literature-search"
    timeout = 1200
    WANTED = ["Theatre in Education", "Serious game"]
    UNRELATED = ["Open Spatial Shoreline Data", "Synthesis Report on Tidal Change"]
    LIBRARY = [
        {"author": "Lyon, A", "year": "2019", "title": "Theatre in Education for public engagement with flood risk",
         "secondary_title": "Journal of Applied Theatre", "abstract": "Drama workshops used to engage the public with flood risk."},
        {"author": "Moreau, C", "year": "2021", "title": "Serious game design for public engagement in coastal planning",
         "secondary_title": "Simulation and Gaming", "abstract": "A game used to engage communities in coastal planning."},
        {"author": "OpenShore Atlas", "year": "2025", "title": "Open Spatial Shoreline Data and Research"},
        {"author": "Tidal Futures Commission", "year": "2023", "title": "Synthesis Report on Tidal Change 2023"},
        {"author": "Ward, P", "year": "2016", "title": "Sediment budgets of sandy barrier islands"},
    ]
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
        require_server_packages("mcp")
        self.make_library(tmp, self.LIBRARY)
        root = (Path(tmp) / "Review").resolve()
        root.mkdir()
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
class LiteratureSearchExternal(SyntheticLibrary, Fixture):
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
    # records that the query (tidal inlet morphodynamics) cannot match, so that every candidate comes from OpenAlex
    LIBRARY = [
        {"author": "Ward, P", "year": "2016", "title": "Public perception of flood warnings"},
        {"author": "Lyon, A", "year": "2019", "title": "Survey methods for seagrass meadows"},
    ]

    def build(self, tmp, args=None):
        if not getattr(args, "external", False):
            raise Skip("sends a query to OpenAlex; give --external to run it")
        require_server_packages("mcp")
        self.make_library(tmp, self.LIBRARY)
        root = (Path(tmp) / "Search").resolve()
        root.mkdir()
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


FIXTURES = {f.name: f for f in (ProjectDisclosure(), ProjectDisclosureDetailed(), AnalysisAdversary(), AnalysisAdversaryModel(), AnalysisAdversaryIndependent(), DocumentAdversary(), DocumentAdversaryIndependent(), Proofread(), ProofreadStructure(), CitationCheck(), CitationCheckContext(), CitationCheckExternal(),
                                      LiteratureSearch(), LiteratureSearchExternal())}


def docx_skill_rows():
    """Rows from scripts/check_docx_skill.py for the live Claude folder: whether the scripts proofread uses are
    present and unchanged since they were last accepted."""
    spec = importlib.util.spec_from_file_location("check_docx_skill", REPO / "scripts" / "check_docx_skill.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.lines(mod.inspect(CLAUDE_HOME))


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
    if fixture.uses_docx_skill:
        rows = docx_skill_rows()
        (dest / "docx-skill-check.txt").write_text("\n".join(f"{k:5} {x}" for k, x in rows) + "\n", encoding="utf-8")
        for kind, text in rows:
            if kind != "OK":
                print(f"  docx skill {kind}: {text}")
    print(f"[{fixture.name}] project {root}", flush=True)
    started = time.time()
    try:
        command = [args.claude, "-p", "--max-turns", str(fixture.max_turns), "--permission-mode", args.permission_mode,
                   *fixture.extra_args(root)]
        r = subprocess.run(command, input=fixture.prompt(root), cwd=root, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=args.timeout or fixture.timeout)
        reply = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr.strip() else "")
    except subprocess.TimeoutExpired:
        reply = "[timed out]"
    seconds = round(time.time() - started)
    (dest / "reply.txt").write_text(reply, encoding="utf-8")
    results = fixture.check(root, reply, fixture.before)
    calls = tool_calls(root)
    urls = sorted({u for _, s in calls for u in re.findall(r"https?://[^\s\"'<>)\]]+", s)})
    (dest / "tool-calls.txt").write_text("\n".join(f"{n}: {s[:240]}" for n, s in calls)
                                         + "\n\nURLs seen in the calls:\n" + "\n".join(urls[:80]) + "\n", encoding="utf-8")
    if (root / "outputs").is_dir():
        shutil.copytree(root / "outputs", dest / "outputs", dirs_exist_ok=True)
    (dest / "checks.json").write_text(json.dumps(
        [{"check": n, "passed": p, "detail": d} for n, p, d in results], indent=2), encoding="utf-8")
    if not args.keep:
        purge(fixture, root, args.claude)
        shutil.rmtree(tmp, ignore_errors=True)
    return results, seconds, dest


def effective_mode(claude, mode, timeout=180):
    """The permission mode a headless session really starts in, read from the start message of a one-turn session.

    Returns (mode or None, message). Claude Code starts in Manual mode when the requested mode (auto) is not available to
    the session, so the requested mode is not enough."""
    with tempfile.TemporaryDirectory() as folder:
        try:
            r = subprocess.run([claude, "-p", "--max-turns", "1", "--permission-mode", mode, "--output-format", "stream-json",
                                "--verbose"], input="Reply with the single word ok.", cwd=folder, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as e:
            return None, f"could not run a test session with {claude}: {e}"
    for line in (r.stdout or "").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "system" and e.get("subtype") == "init":
            return e.get("permissionMode"), ""
    return None, "the test session sent no start message" + (f": {r.stderr.strip()[:200]}" if (r.stderr or "").strip() else "")


def preflight(claude, mode):
    """(exit code, message): 2 if sessions will not start in the requested mode or cannot start, else 0 (the message may
    be a warning that the mode could not be read)."""
    got, why = effective_mode(claude, mode)
    if got is None:
        if why.startswith("could not run"):
            return 2, why
        return 0, f"Warning: could not confirm the permission mode ({why}). Continuing."
    if got != mode:
        return 2, (f"Sessions requested in '{mode}' mode start in '{got}' mode. The requested mode is probably not available to "
                   f"this session (auto mode needs a supported model and provider, and an administrator or Anthropic can switch it "
                   f"off). A headless session in '{got}' mode cannot get approval for run control or Python commands, so the skills "
                   f"stop at their first step and every fixture would fail. Use a session where '{mode}' mode is available, or pass "
                   f"--permission-mode with a mode you have set up (for example with allow rules in your settings), or "
                   f"--no-preflight to run anyway.")
    return 0, ""


def main(argv):
    ap = argparse.ArgumentParser(prog="run_fixtures.py", description="Run skills on fixtures with headless Claude Code.")
    ap.add_argument("--version", action="version", version=f"run_fixtures.py {VERSION}")
    ap.add_argument("skills", nargs="*")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--timeout", type=int, default=None)
    ap.add_argument("--external", action="store_true")
    ap.add_argument("--claude", default=shutil.which("claude") or "claude")
    ap.add_argument("--permission-mode", default="auto")
    ap.add_argument("--no-preflight", action="store_true")
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
    if not a.no_preflight:
        code, message = preflight(a.claude, a.permission_mode)
        if message:
            print(message, file=sys.stderr)
        if code:
            return code
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
