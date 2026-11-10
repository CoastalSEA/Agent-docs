r"""Deploy the Agent-docs master files to the Claude configuration folder.

Created using: $\text {Created using: }\ claude-sonnet-5-5-\text{v}1.0-\text {date: }081126$
Modified using: claude-sonnet-5-5-v5.5-date: 091126 (init and help)

Compares the master files in this repository with the live copies in the Claude configuration
folder, and copies the ones that differ. Creates the two local user files on a new machine.
Needs only Python 3 (standard library). Writes nothing unless the command is `apply` or `init`.

Usage (run from any folder; the repository is the folder that holds this script):
  python deploy.py help       show the deployment instructions (the Deployment section of README.md)
  python deploy.py init [--yes]         create <target>/rules/machine.md from values detected on this
                                        machine, and <target>/rules/profile.md as a short stub.
                                        Never overwrites a file that exists. Shows what it will write
                                        and asks for confirmation on a terminal; without a terminal
                                        `--yes` is required.
  python deploy.py [status]   show what differs; changes nothing; exit 1 if anything differs
  python deploy.py status --diff        also print a unified diff for each differing text file
  python deploy.py apply [--yes]        sync repository copies, back up each live file that will
                                        change, copy, then compare again. Asks for confirmation on
                                        a terminal; without a terminal `--yes` is required.
  python deploy.py hooks [--yes] [--retention-notice]
                                        add the hooks (scripts/hook_*.py) to
                                        <target>/settings.json with the Python of machine.md; backs up the file
                                        and keeps every other setting; run `apply` first.
                                        --retention-notice also adds a start-of-session notice of
                                        transcripts that expire soon (scripts/log_retention.py).
  python deploy.py doctor     check the two local user files in <target>/rules: present, marker
                              line found, form filled in, and each absolute path in machine.md
                              exists. Changes nothing; exit 1 on any problem.
Options:
  --target PATH   the configuration folder (default: ~/.claude). Use a scratch folder to test.

Inputs:
  claude-md/global-CLAUDE.md              -> <target>/CLAUDE.md
  skills/<name>/ (folders with SKILL.md)  -> <target>/skills/<name>/ (every file except docs/)
  scripts/*.py                            -> <target>/scripts/ (the project scripts)
  claude-md/project-CLAUDE.md             -> claude-md/project-template/CLAUDE.md (repository copy,
                                             written by `apply`; the first file is the source)
Outputs:
  `apply` writes the files above and copies each live file it replaces to
  <target>/backups/deploy-<DDMMYY-HHMM>/<path under target>. Nothing is ever deleted.
  `init` writes <target>/rules/machine.md and profile.md only when they do not exist. Nothing
  else ever writes them. The blank forms are in claude-md/user-files/.
Line endings: files that differ only in line endings count as the same and are not copied.
Not covered yet: agents, other hooks, statusline, MCP servers.
"""
import argparse
import difflib
import os
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent

# (source file, repository copy): the first file is the master.
REPO_COPIES = [
    (REPO / "claude-md" / "project-CLAUDE.md", REPO / "claude-md" / "project-template" / "CLAUDE.md"),
]

MARKERS = {"machine.md": "machine-file-v1", "profile.md": "profile-file-v1"}


def items(target):
    """Return (label, source, live) for every file to deploy."""
    out = [("global rules", REPO / "claude-md" / "global-CLAUDE.md", target / "CLAUDE.md")]
    for d in sorted((REPO / "skills").iterdir()):
        if d.is_dir() and (d / "SKILL.md").exists():
            for f in sorted(p for p in d.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                             and "docs" not in p.relative_to(d).parts[:-1]):
                out.append(("skill " + d.name, f, target / "skills" / d.name / f.relative_to(d)))
    for f in sorted((REPO / "scripts").glob("*.py")):
        out.append(("script " + f.stem, f, target / "scripts" / f.name))
    return out


def norm(b):
    return b.replace(b"\r\n", b"\n")


def state(src, dst):
    """same | eol (differs only in line endings) | differs | missing"""
    if not dst.exists():
        return "missing"
    a, b = src.read_bytes(), dst.read_bytes()
    if a == b:
        return "same"
    return "eol" if norm(a) == norm(b) else "differs"


def show_diff(src, dst):
    try:
        a = norm(src.read_bytes()).decode("utf-8").splitlines()
        b = norm(dst.read_bytes()).decode("utf-8").splitlines() if dst.exists() else []
    except UnicodeDecodeError:
        print("      (binary file, no diff)")
        return
    for line in difflib.unified_diff(b, a, "live", "repository", lineterm="", n=1):
        print("      " + line)


def collect(target):
    rows, bad = [], 0
    for master, copy in REPO_COPIES:
        s = state(master, copy)
        rows.append(("repository copy", master, copy, s))
        bad += s in ("differs", "missing")
    for label, src, dst in items(target):
        s = state(src, dst)
        rows.append((label, src, dst, s))
        bad += s in ("differs", "missing")
    return rows, bad


def status(target, want_diff):
    rows, bad = collect(target)
    print(f"Repository: {REPO}\nTarget:     {target}\n")
    for label, src, dst, s in rows:
        rel = dst.relative_to(target) if target in dst.parents else dst.relative_to(REPO)
        flag = {"same": "same   ", "eol": "same*  ", "differs": "DIFFERS", "missing": "MISSING"}[s]
        print(f"  {flag}  {label:<24} {rel}")
        if want_diff and s == "differs":
            show_diff(src, dst)
    if any(r[3] == "eol" for r in rows):
        print("\n  same* = differs only in line endings; not copied")
    live_only = []
    sk = target / "skills"
    if sk.is_dir():
        known = {d.name for d in (REPO / "skills").iterdir() if d.is_dir() and (d / "SKILL.md").exists()}
        live_only = sorted(p.name for p in sk.iterdir() if p.is_dir() and p.name not in known)
    if live_only:
        print("  live only (not in the repository, left alone): " + ", ".join(live_only))
    print(f"\n{bad} file(s) to copy." if bad else "\nIn sync.")
    return bad, rows


def apply(target, yes):
    bad, rows = status(target, False)
    todo = [r for r in rows if r[3] in ("differs", "missing")]
    if not todo:
        return 0
    if not yes:
        if not ask("\nCopy these files? [y/N] "):
            print("\nNothing copied. Re-run with --yes to confirm without a terminal.")
            return 1
    stamp = datetime.now().strftime("%d%m%y-%H%M")
    bdir = target / "backups" / f"deploy-{stamp}"
    for label, src, dst, s in todo:
        if target in dst.parents and dst.exists():
            keep = bdir / dst.relative_to(target)
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, keep)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    print(f"\nCopied {len(todo)} file(s). Backups of replaced live files: {bdir}")
    print("\nChecking again:")
    bad2, _ = status(target, False)
    return 1 if bad2 else 0


def ask(prompt):
    """True only if a person answers y at a terminal."""
    if not sys.stdin.isatty():
        return False
    try:
        return input(prompt).strip().lower() == "y"
    except EOFError:
        return False


# ---- init: detect this machine and write the two local user files ---------------------------------

def run_text(cmd, timeout=15):
    """Output (stdout and stderr) of a command, or an empty string if it cannot run."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def first_line(text):
    return next((ln.strip() for ln in text.splitlines() if ln.strip()), "")


def newest(paths):
    """The path that sorts highest when its numbers are compared as numbers."""
    key = lambda p: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", str(p))]
    return max(paths, key=key) if paths else None


def bash_path(p):
    """A Windows path in the form Git Bash uses: drive C, folder d -> /c/d."""
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", str(p))
    return f"/{m.group(1).lower()}/{m.group(2).replace(chr(92), '/')}" if m else str(p)


def program_files():
    return Path(os.environ.get("ProgramFiles", r"C:\Program Files"))


def find_tool(names, windows_globs=(), unix_globs=()):
    """(path, on_path) for the first executable found, or (None, False)."""
    for n in names:
        found = shutil.which(n)
        if found:
            return Path(found).resolve(), True
    pools = [(program_files(), g) for g in windows_globs] if os.name == "nt" else \
            [(Path("/"), g) for g in unix_globs]
    hits = [p for base, g in pools for p in base.glob(g)]
    best = newest(hits)
    return (best, False) if best else (None, False)


def detect():
    """Facts about this machine, the notes on how each was found, and what could not be found."""
    f = {"notes": [], "undetected": []}
    system = platform.system()
    f["windows"] = system == "Windows"
    if system == "Windows":
        build = sys.getwindowsversion().build
        f["os"] = "Windows 11" if build >= 22000 else "Windows 10"
        f["notes"].append(f"Operating system: Windows build {build}; build 22000 or later is taken as Windows 11.")
    elif system == "Darwin":
        f["os"] = "macOS " + platform.mac_ver()[0]
    else:
        try:
            f["os"] = platform.freedesktop_os_release().get("PRETTY_NAME", "Linux")
        except (OSError, AttributeError):
            f["os"] = "Linux"
    f["home"] = str(Path.home())

    # shells
    git_bash = None
    if f["windows"]:
        git = shutil.which("git")
        for parent in (Path(git).parents if git else []):
            if (parent / "bin" / "bash.exe").exists():
                git_bash = parent / "bin" / "bash.exe"
                break
        shells = []
        if git_bash:
            shells.append("Git Bash (the Bash tool)")
        else:
            f["undetected"].append("Git Bash was not found next to git. Claude Code needs it on Windows.")
        if shutil.which("pwsh"):
            shells.append("PowerShell 7")
        ps = shutil.which("powershell")
        if ps:
            v = first_line(run_text([ps, "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"]))
            shells.append("PowerShell " + ".".join(v.split(".")[:2]) if re.match(r"^\d+(\.\d+)*$", v) else "PowerShell")
        f["shells"] = " and ".join(shells) if shells else "none found"
    else:
        found = [s for s in ("bash", "zsh") if shutil.which(s)]
        login = Path(os.environ.get("SHELL", "")).name
        f["shells"] = " and ".join(found) if found else "none found"
        if login:
            f["shells"] += f". Login shell: {login}"
            f["notes"].append("Bash tool shell: not detected; the login shell from $SHELL is listed instead.")
    f["bash_form"] = bool(git_bash) if f["windows"] else False

    # python
    py = Path(sys.executable)
    f["python"] = py
    plain = shutil.which("python")
    if plain is None:
        f["plain_python"] = "no (not on PATH)"
    elif "WindowsApps" in plain:
        f["plain_python"] = "no (a Windows Store stub)"
    elif Path(plain).resolve() == py.resolve():
        f["plain_python"] = "yes"
    else:
        f["plain_python"] = f"yes, but it is another interpreter ({plain})"
    marker = Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED"
    f["pip"] = "only inside a venv (this interpreter is externally managed)" if marker.exists() \
        else "in any environment (no externally-managed marker was found)"
    f["notes"].append(f"Python: the interpreter that is running this script ({py}).")

    # other tools
    tools = []
    r, on_path = find_tool(["Rscript"], [r"R/R-*/bin/x64/Rscript.exe", r"R/R-*/bin/Rscript.exe"],
                           ["Library/Frameworks/R.framework/Resources/bin/Rscript", "usr/lib/R/bin/Rscript"])
    if r:
        v = re.search(r"version (\d+(\.\d+)+)", run_text([str(r), "--version"]))
        tools.append(("R", r, on_path, f"R {v.group(1)}" if v else "R"))
    else:
        f["undetected"].append("R (Rscript) was not found.")
    m, on_path = find_tool(["matlab"], [r"MATLAB/R*/bin/win64/MATLAB.exe"],
                           ["Applications/MATLAB_R*.app/bin/matlab", "usr/local/MATLAB/R*/bin/matlab"])
    if m:
        rel = re.search(r"R20\d\d[ab]", str(m))
        tools.append(("MATLAB", m, on_path, f"MATLAB {rel.group(0)}" if rel else "MATLAB"))
    else:
        f["undetected"].append("MATLAB was not found.")
    t, on_path = find_tool(["tesseract"], [r"Tesseract-OCR/tesseract.exe"],
                           ["opt/homebrew/bin/tesseract", "usr/local/bin/tesseract"])
    if t:
        v = re.search(r"tesseract (\S+)", run_text([str(t), "--version"]))
        langs = [ln.strip() for ln in run_text([str(t), "--list-langs"]).splitlines()[1:] if ln.strip()]
        label = f"Tesseract {v.group(1)}" if v else "Tesseract"
        if langs:
            label += ", languages " + " and ".join(langs[:8])
        tools.append(("OCR", t, on_path, label))
    else:
        f["undetected"].append("Tesseract (OCR) was not found.")
    f["tools"] = tools
    f["undetected"] += ["EndNote library and server registration (add by hand if you use them).",
                        "Python environments and any rule about what may be installed in them.",
                        "Your private companion repository, if you keep one."]
    return f


def render_machine(f, scripts, repo, config, today=None):
    """The text of machine.md for the facts in f."""
    today = today or date.today().strftime("%d%m%y")
    win, bash = f["windows"], f["bash_form"]
    py = str(f["python"])

    def forms(path, ps_prefix=""):
        """The Bash and PowerShell forms of a path, or the one form on other systems."""
        if not win:
            return f'`"{path}"`'
        out = []
        if bash:
            out.append(f'Bash `"{bash_path(path)}"`')
        out.append(f"PowerShell `{ps_prefix}{path}`")
        return "; ".join(out)

    def command(script):
        tail = '<command> <task> --root "<project root>"'
        if not win:
            return f'`"{py}" "{scripts / script}" {tail}`'
        out = []
        if bash:
            out.append(f'Bash `"{bash_path(py)}" "{bash_path(scripts / script)}" {tail}`')
        out.append(f'PowerShell `& "{py}" "{scripts / script}" {tail}`')
        return "; ".join(out)

    lines = ["# Machine file", "", "Marker: machine-file-v1", "",
             f"Created by `deploy.py init` on {today} from detected values. Edit freely. The file is local to this machine.",
             "", "## System", "",
             f"- Operating system: {f['os']}.",
             f"- Shells: {f['shells']}.",
             f"- Home folder: `{f['home']}`" + (f" (`{bash_path(f['home'])}` in Git Bash)." if bash else "."),
             "- Path style in commands: " + ("`C:\\...` in PowerShell" + (", `/c/...` in Git Bash." if bash else ".")
                                              if win else "`/...`."),
             "", "## Commands", "",
             f"- Python: {forms(py)}. Plain `python` works: {f['plain_python']}. `pip` works: {f['pip']}.",
             f"- Run control: {command('run_control.py')}. The commands are `start`, `path`, `check`, `accept`, "
             "`reject`, `discard` and `status`. For `accept` and `reject` the question follows the task: "
             '`accept <task> "<question>"`.',
             "- Other project scripts, in the same folder with the same `--root` option: `archive_control.py` "
             "(`archive`, `restore`, `list`), `check_records.py` (the records check), `wrapup_status.py` "
             "(whether the handoff is current; exit code 1 if it is stale; `--quiet` prints only the status line), "
             "`rotate_records.py` (moves the "
             "oldest decision lines to the archive; `--apply` writes) and `project.py` (`status` reports the template level "
             "and whether an upgrade is suggested; `init --level minimal|handoff|full` is a dry run until `--apply`, and `--templates` "
             "names the `claude-md` folder of this repository). Use the Python and path forms of the "
             "run control line, with the script name replaced. `check_docx_skill.py` takes no `--root`: `--find` prints the folder of the docx skill scripts that the proofread skill calls, and a plain run checks them."]
    for name, path, on_path, label in f["tools"]:
        where = "on `PATH`" if on_path else "not on `PATH`"
        if name == "MATLAB":
            ex = "-batch \"run('script.m')\""
            call = (f'Bash `"{bash_path(path)}" {ex}`; ' if bash else "") + \
                   (f'PowerShell `& "{path}" {ex}`' if win else f'`"{path}" {ex}`')
            lines.append(f"- MATLAB: {label} at {forms(path)}, {where}. Run scripts with `-batch`, for example {call}.")
        else:
            lines.append(f"- {name}: {label}, {where}. {forms(path)}.")
    lines += ["", "## Locations", "",
              f"- This repository: `{repo}`.",
              f"- Claude configuration folder: `{config}`.", ""]
    return "\n".join(lines)


def render_profile(today=None):
    """The text of profile.md: a stub, because the rules are the user's own."""
    today = today or date.today().strftime("%d%m%y")
    return "\n".join([
        "# Profile file", "", "Marker: profile-file-v1", "",
        f"Created by `deploy.py init` on {today}. Add your own rules for writing and for code. The file is local to one user.",
        "", "## Writing rules", "", "- None set. Ask the user before assuming a style.", "",
        "## Code standards", "", "- Header format: not set. Ask the user before choosing one.", ""])


def init(target, yes):
    rules = target / "rules"
    f = detect()
    machine = render_machine(f, target / "scripts", REPO, target)
    plan = []
    print(f"Target: {target}\n")
    for path, text in ((rules / "machine.md", machine), (rules / "profile.md", render_profile())):
        if path.exists():
            print(f"  EXISTS   {path}  (left alone)")
        else:
            print(f"  CREATE   {path}")
            plan.append((path, text))
    if not plan:
        print("\nNothing to create.")
        return 0
    print("\nValues detected on this machine (review them before you rely on them):")
    for n in f["notes"]:
        print(f"  - {n}")
    print("\nNot detected, so not written:")
    for u in f["undetected"]:
        print(f"  - {u}")
    if any(p.name == "machine.md" for p, _ in plan):
        print("\nmachine.md will contain:\n")
        print("\n".join("    " + ln for ln in machine.splitlines()))
    if not yes and not ask("\nCreate these files? [y/N] "):
        print("\nNothing created. Re-run with --yes to confirm without a terminal.")
        return 1
    for path, text in plan:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"Created {path}")
    print("\nNext: edit the files if needed, run `deploy.py apply` to install the shared files, then "
          "`deploy.py doctor`. Run `deploy.py help` for the full steps.")
    return 0


# (script, event, matcher, arguments) for each hook that `hooks` installs.
HOOKS = [
    ("hook_push_check.py", "PreToolUse", "Bash", ""),
    ("hook_guard.py", "PreToolUse", "Bash|Write|Edit|MultiEdit|NotebookEdit", ""),
    ("hook_confirm.py", "PreToolUse", "Bash", ""),
]
# installed only with `hooks --retention-notice`
OPTIONAL_HOOKS = [
    ("log_retention.py", "SessionStart", "startup", " --hook"),
]


def hook_command(target, script, args=""):
    """The hook command: the Python of machine.md (else this Python) and the installed script, forward slashes."""
    path = (target / "scripts" / script).as_posix()
    return f'"{(machine_python(target) or Path(sys.executable)).as_posix()}" "{path}"{args}'


def machine_python(target):
    """The interpreter named on the Python line of <target>/rules/machine.md, if that file exists.

    It is the path as written there (for uv, the stable launcher), not the resolved sys.executable."""
    path = target / "rules" / "machine.md"
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("- Python:"):
            for p in abs_paths(line):
                cand = resolve(p)
                if cand.is_file():
                    return cand
    return None


def hooks(target, yes, optional=False):
    """Add the hooks in HOOKS (and OPTIONAL_HOOKS if asked) to <target>/settings.json, keeping every other
    setting. Idempotent."""
    import json
    path = target / "settings.json"
    cfg = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    changes = []
    for script, event, matcher, args in HOOKS + (OPTIONAL_HOOKS if optional else []):
        groups = cfg.setdefault("hooks", {}).setdefault(event, [])
        command = hook_command(target, script, args)
        entries = [h for g in groups for h in g.get("hooks", []) if script in h.get("command", "")]
        if entries and all(h["command"] == command for h in entries):
            continue
        if entries:
            for h in entries:
                h["command"] = command
        else:
            groups.append({"matcher": matcher, "hooks": [{"type": "command", "command": command}]})
        changes.append((script, f"{event}, matcher {matcher}", command))
        if not (target / "scripts" / script).exists():
            print(f"Note: {script} is not installed yet. Run `deploy.py apply` as well.")
    if not changes:
        print(f"Hooks already installed in {path}")
        return 0
    print(f"Will set these hooks in {path}:")
    for script, where, command in changes:
        print(f"  {script} ({where}): {command}")
    if not yes and not ask("Write them? [y/N] "):
        print("Nothing written. Re-run with --yes to confirm without a terminal.")
        return 1
    if path.exists():
        keep = target / "backups" / f"hooks-{datetime.now().strftime('%d%m%y-%H%M')}" / "settings.json"
        keep.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, keep)
        print(f"Backup: {keep}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2) + chr(10), encoding="utf-8")
    print("Written. Start a new session for the hooks to load.")
    return 0


def show_help():
    """Print the deployment instructions: the Deployment section of README.md."""
    readme = REPO / "README.md"
    print("deploy.py: install the Agent-docs files into the Claude configuration folder.\n")
    if readme.exists():
        text = readme.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        m = re.search(r"^## Deployment\n(.*?)(?=^## |\Z)", text, re.S | re.M)
        if m:
            print(m.group(1).strip("\n"))
            return 0
    print("README.md or its Deployment section was not found. The usage is at the top of deploy.py.")
    return 1


# ---- doctor ---------------------------------------------------------------------------------------

def abs_paths(text):
    """Absolute paths named in the code spans of a markdown file."""
    found = []
    for span in re.findall(r"`([^`\n]+)`", text):
        cands = re.findall(r'"([^"\n]+)"', span) or [span]
        for c in cands:
            c = c.strip()
            if "<" in c or c.startswith("-") or c.endswith("..."):
                continue
            if re.match(r"^[A-Za-z]:[\\/]", c) or c.startswith(("/", "~/", "$HOME")):
                found.append(c)
    return sorted(set(found))


def resolve(p):
    if p.startswith("~/"):
        return Path.home() / p[2:]
    if p.startswith("$HOME"):
        return Path.home() / p[6:]
    m = re.match(r"^/([a-z])/(.*)$", p)  # Git Bash form of a drive path
    if m and sys.platform == "win32":
        return Path(f"{m.group(1).upper()}:/{m.group(2)}")
    return Path(p)


def doctor(target):
    problems = 0
    rules = target / "rules"
    print(f"Target: {target}\n")
    for name, marker in MARKERS.items():
        f = rules / name
        if not f.exists():
            print(f"  MISSING  {f}\n           run `deploy.py init` to create it, or copy "
                  f"claude-md/user-files/{name[:-3]}.example.md there and fill it in")
            problems += 1
            continue
        t = f.read_text(encoding="utf-8", errors="replace")
        if f"Marker: {marker}" not in t:
            print(f"  PROBLEM  {f}: line 'Marker: {marker}' not found")
            problems += 1
        elif "Copy this form to" in t:
            print(f"  PROBLEM  {f}: looks like the blank form; fill it in")
            problems += 1
        else:
            print(f"  OK       {f}")
        if name == "machine.md":
            for p in abs_paths(t):
                if not resolve(p).exists():
                    print(f"  NOT FOUND  path in machine.md: {p}")
                    problems += 1
    live = target / "CLAUDE.md"
    if live.exists() and "machine.md" not in live.read_text(encoding="utf-8", errors="replace"):
        print("  NOTE     the live CLAUDE.md does not mention machine.md (the old single-file form?)")
    print("\ndocx skill (used by proofread; shown as a warning only, never a problem):")
    for kind, text in docx_skill_rows(target):
        print(f"  {'OK' if kind == 'OK' else 'WARN':<9}{text}")
    print("\nCannot check from here that a session loads the files. Start a session and ask it to quote the Marker lines.")
    print(f"\n{problems} problem(s)." if problems else "\nNo problems found.")
    return 1 if problems else 0


def docx_skill_rows(target):
    """(kind, text) rows from scripts/check_docx_skill.py for the target folder; empty if that script is missing."""
    path = REPO / "scripts" / "check_docx_skill.py"
    if not path.is_file():
        return []
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_docx_skill", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.lines(mod.inspect(target))


def main(argv):
    ap = argparse.ArgumentParser(prog="deploy.py", description="Deploy the Agent-docs master files.")
    ap.add_argument("command", nargs="?", default="status",
                    choices=["status", "apply", "init", "doctor", "help", "hooks"])
    ap.add_argument("--target", default=str(Path.home() / ".claude"))
    ap.add_argument("--diff", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--retention-notice", action="store_true")
    a = ap.parse_args(argv)
    target = Path(a.target).expanduser().resolve()
    if a.command == "help":
        return show_help()
    if a.command == "init":
        return init(target, a.yes)
    if a.command == "hooks":
        return hooks(target, a.yes, a.retention_notice)
    if a.command == "status":
        return 1 if status(target, a.diff)[0] else 0
    if a.command == "apply":
        # repository copies first, so the live copy and the repository copy come from the master
        for master, copy in REPO_COPIES:
            if state(master, copy) in ("differs", "missing"):
                if a.yes or ask(f"Write {copy.relative_to(REPO)} from {master.relative_to(REPO)}? [y/N] "):
                    shutil.copyfile(master, copy)
                    print(f"Wrote {copy.relative_to(REPO)}")
        return apply(target, a.yes)
    return doctor(target)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
