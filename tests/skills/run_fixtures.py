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
  skill      project-disclosure, analysis-adversary (default: both)
  --list     print the fixtures and their checks, and run nothing
  --keep     keep the temporary project and its logs
  --timeout  seconds allowed for each session (default 900)
  --claude   the claude command (default: the one on PATH)
  --permission-mode  the mode for the sessions (default auto, as in interactive use; a headless session
             started in the default mode cannot get approval for run control or Python commands)
  --out      folder for the results (default: working_docs/skill-runs under the repository)
Inputs:  the live Claude configuration; `claude` on PATH.
Outputs: <out>/<skill>-<DDMMYY-HHMM>/ with reply.txt, the saved deliverable and checks.json; a table on standard output.
Exit:    0 if every check of every fixture passed; 1 otherwise.
Version: see VERSION; `--version` prints it.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

VERSION = "1.0"
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

    def build(self, tmp):
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

    def build(self, tmp):
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

    def build(self, tmp):
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


FIXTURES = {f.name: f for f in (ProjectDisclosure(), AnalysisAdversary())}


def purge(fixture, root, claude):
    for key in fixture.log_folders(root):
        shutil.rmtree(CLAUDE_HOME / "projects" / key, ignore_errors=True)


def run_one(fixture, args, out_dir):
    tmp = Path(tempfile.mkdtemp(prefix="fx-"))
    root = fixture.build(tmp)
    stamp = datetime.now().strftime("%d%m%y-%H%M")
    dest = out_dir / f"{fixture.name}-{stamp}"
    dest.mkdir(parents=True, exist_ok=True)
    print(f"[{fixture.name}] project {root}", flush=True)
    started = time.time()
    try:
        r = subprocess.run([args.claude, "-p", "--max-turns", "30", "--permission-mode", args.permission_mode], input=fixture.prompt(root), cwd=root,
                           capture_output=True, text=True, timeout=args.timeout)
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
    ap.add_argument("--timeout", type=int, default=900)
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
        print(f"[{n}] {seconds} s; results in {dest}")
        for name, ok, detail in results:
            print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))
            failed = failed or not ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
