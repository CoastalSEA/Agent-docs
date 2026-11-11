"""Run control for task output folders (global Outputs rules in the global CLAUDE.md).

Two modes, chosen from the project root:
- tracked: the project is a git repository and outputs/ is not git-ignored. A run overwrites
  outputs/<task>/: its files other than .md are removed first, in its subfolders too (a subfolder
  left empty is removed), and reports (.md), which are edited in place, are kept. A new run is pending (uncommitted) until the user reviews it. A
  rerun replaces a pending run, with a warning (trial from 240926). Only the user decides to
  accept, reject or discard a run; the commands below then do the git steps.
- run folder: the project is not a git repository, or outputs/ is git-ignored. Each run gets a
  new folder outputs/<task>-<DDMMYY>-run<N>/ and no git steps apply.

run_info.txt records the task, the run tag or folder name, the date, the script, the commit at
the start of the run and whether the working tree was clean (git only). N is one more than the
highest run number for that task and date among the git tags and the folders in outputs/.

Commands (python run_control.py <command> ... [--root <project root>]):
  start <task>                  prepare the folder and print its absolute path
  path <task>                   print the folder a `start` would use; changes nothing
  check <task> [--allow F]      file guard on the task folder (in run folder mode, the latest
                                run folder of the task), and what `accept` would commit
  accept <task> ["question"]    guard, commit outputs/<task>/ and changed files under code/, add
         [--allow F]            the annotated tag from run_info.txt and the outputs/INDEX.md row;
                                the previous current row of the task becomes superseded
                                (only if the project keeps an INDEX.md; otherwise the tag is
                                the record, as in the minimal and handoff template levels)
  reject <task> ["question"]    as accept, tag suffix -rejected, status "not adopted"
  discard <task>                restore outputs/<task>/ to the last accepted run (deletes the
                                pending files, including new .md files; ask the user first)
  status                        pending task folders, guard failures, tags with no INDEX row
If no question is given, accept and reject reuse the question of the last tag of the task.
Other changed files (outside outputs/<task>/ and code/) are listed and left uncommitted.

File guard (check, accept, reject, status), over the task folder and its subfolders:
  excluded types: .pdf .docx .pptx .zip .7z .rar .gz .pyc and Office lock files (~$*)
  images (.png .jpg .jpeg .tif .tiff .gif .bmp) up to 1 MB each; other files up to 5 MB each;
  the whole folder up to 25 MB. --allow <file> (repeatable, path relative to the task folder)
  passes a named file; allowed files are listed in the tag message. Downloaded sources belong
  in the git-ignored sources/ folder, not in outputs/.

Data check (check, accept, reject): `start` records the state of data/ (file names, sizes and times, not
DATA-NOTES.md or README files) in run_info.txt. If data/ differs later, `check` fails and `accept` and
`reject` refuse, because input data must not change during a run. The files changed after the start are
named; deleted files are counted only. --data-changed-ok on accept or reject passes it after the user
has reviewed the change. Runs started by an earlier version have no record and are not checked.

Use the command line from any language. The root defaults to the current directory; a copy imported
from <project>/code/ defaults to <project>. Task names are reduced to letters, digits, '-' and '_'.

Version: see VERSION; `--version` prints it, and it is written to run_info.txt and the tag message.
The master is scripts/run_control.py in the Agent-docs repository; deploy.py installs it as ~/.claude/scripts/run_control.py.

Inputs:  task name; project root (git repository optional); outputs/INDEX.md if the project keeps one
Outputs: the run's output folder and <folder>/run_info.txt (start); commits, annotated tags and
         outputs/INDEX.md rows (accept, reject); a restored folder (discard); reports on stdout
Exit:    0 on success; 1 with a message on stderr on a guard failure or any refused step

Created using: Claude Opus-v5.5-date: 230926
Modified using: Claude Opus-v5.5-date: 240926 (run folder mode, command line, task name check)
Modified using: Claude Opus-v5.5-date: 240926 (keep .md reports when a tracked folder is cleared)
Modified using: Claude Opus-v5.5-date: 240926 (accept, reject, discard, check, status; file
                guard; a rerun replaces a pending run)
Modified using: Claude Sonnet-v5.5-date: 290926 (check resolves the latest run folder in run
                folder mode)
Modified using: claude-sonnet-5-5-v5.5-date: 081126 (version 1.1: --root accepted anywhere in the command line,
                including accept/reject without a question)
Modified using: claude-sonnet-5-5-v5.5-date: 091126 (version 1.2: data check)
Modified using: claude-fable-5-2-v5.2-date: 111126 (version 1.3: a rerun clears subfolders; a failed commit
                leaves no INDEX.md row; a task name is not read as a prefix of another)
"""

import argparse
import hashlib
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

VERSION = "1.3"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".pdf", ".docx", ".pptx", ".zip", ".7z", ".rar", ".gz", ".pyc"}
IMAGES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".gif", ".bmp"}
MB = 1024 * 1024
IMAGE_LIMIT, FILE_LIMIT, FOLDER_LIMIT = 1 * MB, 5 * MB, 25 * MB


def git(root, *args, check=True):
    res = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if check and res.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res


def clean_task(task):
    name = re.sub(r"[^A-Za-z0-9_-]+", "-", task.strip()).strip("-")
    if not name:
        raise SystemExit(f"Task name {task!r} has no usable characters.")
    return name


def is_repo(root):
    try:
        res = git(root, "rev-parse", "--is-inside-work-tree", check=False)
    except FileNotFoundError:
        return False
    return res.returncode == 0 and res.stdout.strip() == "true"


def is_ignored(root, folder):
    # Test a file inside the folder: git 2.41 reports a missing folder given with a trailing
    # slash as ignored (matched to a blank line) after a negated pattern in .gitignore.
    return git(root, "check-ignore", "-q", f"{folder}/run_info.txt", check=False).returncode == 0


def tracked_mode(root):
    return is_repo(root) and not is_ignored(root, "outputs")


def changes(root, rel):
    """Porcelain status lines under rel (a path relative to the root)."""
    return git(root, "status", "--porcelain", "-uall", "--", rel).stdout.splitlines()


def next_name(root, task, stamp, repo):
    pat = re.compile(rf"^{re.escape(task)}-{stamp}-run(\d+)(-rejected)?$")
    outputs = root / "outputs"
    names = [p.name for p in outputs.iterdir() if p.is_dir()] if outputs.is_dir() else []
    if repo:
        names += git(root, "tag", "-l").stdout.split()
    nums = [int(m.group(1)) for m in (pat.match(n) for n in names) if m]
    return f"{task}-{stamp}-run{max(nums, default=0) + 1}"


def plan_run(task, root=None):
    """Return (mode, folder, run name) for the next run of task, without changing anything."""
    root = Path(root).resolve() if root else PROJECT_ROOT
    task = clean_task(task)
    stamp = date.today().strftime("%d%m%y")
    repo = is_repo(root)
    name = next_name(root, task, stamp, repo)
    if not repo or is_ignored(root, "outputs"):
        return "run folder", root / "outputs" / name, name
    if is_ignored(root, f"outputs/{task}"):
        raise SystemExit(f"outputs/{task}/ is git-ignored although outputs/ is not. Rename the task or "
                         f"change .gitignore before running.")
    return "tracked", root / "outputs" / task, name


def start_run(task, root=None):
    root = Path(root).resolve() if root else PROJECT_ROOT
    mode, out, name = plan_run(task, root)
    out.mkdir(parents=True, exist_ok=True)
    if mode == "tracked":
        rel = out.relative_to(root).as_posix()
        if changes(root, rel):
            print(f"Warning: {rel}/ held a run pending review; it is replaced by this run "
                  f"(.md files are kept).", file=sys.stderr)
        # Reports (.md) are edited in place in the task folder, so they survive a rerun. Everything else
        # goes, at any depth (deepest first), and a subfolder left empty is removed.
        below = 0
        for p in sorted(out.rglob("*"), reverse=True):
            if p.is_dir() and not p.is_symlink():
                try:
                    p.rmdir()
                except OSError:
                    pass  # still holds a report
            elif p.suffix.lower() != ".md":
                p.unlink()
                below += p.parent != out
        if below:
            print(f"Removed {below} file(s) of the earlier run from the subfolders of {rel}/ "
                  f"(.md files are kept).", file=sys.stderr)
    info = [f"task: {clean_task(task)}",
            f"mode: {mode}",
            f"{'proposed tag' if mode == 'tracked' else 'run folder'}: {name}",
            f"date: {date.today().strftime('%d%m%y')}",
            f"script: {Path(sys.argv[0]).name}",
            f"run control version: {VERSION}"]
    if is_repo(root):
        rel = out.relative_to(root).as_posix()
        commit = git(root, "rev-parse", "--short", "HEAD", check=False).stdout.strip() or "none"
        status = [ln for ln in git(root, "status", "--porcelain", "-uall").stdout.splitlines()
                  if not ln[3:].startswith(rel + "/")]
        # Other tasks' pending outputs are separate runs, reviewed on their own: never commit them with this one.
        dirty = [ln for ln in status if not ln[3:].startswith("outputs/")]
        pending = sorted({ln[3:].split("/")[1] for ln in status
                          if ln[3:].startswith("outputs/") and ln[3:].count("/") >= 2})
        info += [f"commit at start: {commit}", f"working tree clean at start: {not dirty}"]
        if dirty and mode == "tracked":
            info.append("uncommitted files at start (accept commits those under code/ with the outputs):")
            info += [f"  {ln}" for ln in dirty]
        if pending and mode == "tracked":
            info.append("other output folders pending review at start (not part of this run): "
                        + ", ".join(pending))
    else:
        info.append("git: not a git repository")
    state = data_state_line(root)
    if state:
        info.append(state)
    (out / "run_info.txt").write_text("\n".join(info) + "\n", encoding="utf-8")
    return out


DATA_EXEMPT = ("DATA-NOTES.md", "README")


def data_files(root):
    """{relative path: (size, mtime_ns)} for the files under data/, or None if there is no data/ folder."""
    data = root / "data"
    if not data.is_dir():
        return None
    found = {}
    for f in sorted(data.rglob("*")):
        if f.is_file() and not f.name.startswith(DATA_EXEMPT):
            s = f.stat()
            found[f.relative_to(root).as_posix()] = (s.st_size, s.st_mtime_ns)
    return found


def data_digest(files):
    return hashlib.sha1(repr(sorted(files.items())).encode("utf-8")).hexdigest()[:16]


def data_state_line(root):
    files = data_files(root)
    if files is None:
        return None
    return f"data state at start: {len(files)}|{data_digest(files)}|{time.time_ns()}"


def data_change(root, info):
    """None if data/ is as recorded at start (or nothing was recorded); otherwise a message."""
    rec = info.get("data state at start")
    if not rec:
        return None
    n, digest, started = rec.split("|")
    now = data_files(root) or {}
    if data_digest(now) == digest:
        return None
    newer = [name for name, (_, m) in now.items() if m > int(started)]
    msg = f"data/ changed since the run started ({n} files then, {len(now)} now)"
    return msg + (": " + ", ".join(newer[:10]) if newer else " (files removed or older files replaced)")


def guard(folder, allow=()):
    """Return (problems, allowed) for the files in folder. Each problem is a message line."""
    allow = {Path(a).as_posix().lower() for a in allow}
    problems, allowed, total = [], [], 0
    for p in sorted(folder.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(folder).as_posix()
        size = p.stat().st_size
        total += size
        ext = p.suffix.lower()
        if p.name.startswith("~$"):
            why = "Office lock file"
        elif ext in EXCLUDED:
            why = f"excluded type {ext}"
        elif ext in IMAGES and size > IMAGE_LIMIT:
            why = f"image over {IMAGE_LIMIT // MB} MB"
        elif ext not in IMAGES and size > FILE_LIMIT:
            why = f"file over {FILE_LIMIT // MB} MB"
        else:
            continue
        line = f"{rel} ({size / MB:.2f} MB): {why}"
        if rel.lower() in allow and not p.name.startswith("~$"):
            allowed.append(line)
        else:
            problems.append(line)
    if total > FOLDER_LIMIT:
        problems.append(f"folder total {total / MB:.1f} MB is over {FOLDER_LIMIT // MB} MB")
    return problems, allowed


def read_info(folder):
    f = folder / "run_info.txt"
    if not f.exists():
        raise SystemExit(f"{f} not found: start the run with `run_control.py start` first.")
    return dict(ln.split(": ", 1) for ln in f.read_text(encoding="utf-8").splitlines() if ": " in ln)


def last_question(root, task):
    pat = re.compile(rf"^{re.escape(task)}-\d{{6}}-run\d+(-rejected)?$")
    tags = [t for t in git(root, "tag", "-l", "--sort=-creatordate").stdout.split() if pat.match(t)]
    if not tags:
        return None
    text = git(root, "tag", "-l", "--format=%(contents)", tags[0]).stdout.strip()
    return text.splitlines()[0].strip() if text else None


def index_rows(text):
    """Yield (line number, cells) for the table rows of INDEX.md that name a run."""
    for i, line in enumerate(text.splitlines()):
        if line.startswith("| `"):
            yield i, [c.strip() for c in line.strip().strip("|").split("|")]


def update_index(root, task, tag, question, status):
    """Add the run's row to outputs/INDEX.md. Return False if the project keeps no INDEX.md."""
    path = root / "outputs" / "INDEX.md"
    if not path.exists():
        # The minimal and handoff template levels keep no output index: the tag is the record.
        return False
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if status == "current":
        for i, cells in index_rows(text):
            if len(cells) == 5 and cells[1] == f"`{task}`" and cells[3] == "current":
                cells[3], cells[4] = "superseded", f"`{tag}`"
                lines[i] = "| " + " | ".join(cells) + " |"
    question = " ".join(question.split()).replace("|", "/")
    lines.append(f"| `{tag}` | `{task}` | {question} | {status} | |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def other_changes(root, task):
    keep = (f"outputs/{task}/", "code/", "outputs/INDEX.md")
    return [ln for ln in git(root, "status", "--porcelain", "-uall").stdout.splitlines()
            if not ln[3:].startswith(keep)]


def latest_run_folder(root, task):
    """Latest outputs/<task>-<DDMMYY>-run<N> folder (by date, then run number), or None."""
    pat = re.compile(rf"^{re.escape(task)}-(\d{{2}})(\d{{2}})(\d{{2}})-run(\d+)$")
    outputs = root / "outputs"
    found = []
    for p in (outputs.iterdir() if outputs.is_dir() else []):
        m = pat.match(p.name)
        if p.is_dir() and m:
            dd, mm, yy, n = m.groups()
            found.append(((yy, mm, dd, int(n)), p))
    return max(found, key=lambda f: f[0])[1] if found else None


def cmd_check(task, root, allow):
    task = clean_task(task)
    if tracked_mode(root):
        folder = root / "outputs" / task
    else:
        folder = latest_run_folder(root, task)
        if folder is None:
            raise SystemExit(f"No outputs/{task}-<DDMMYY>-run<N>/ folder found.")
    label = f"outputs/{folder.name}/"
    if not folder.is_dir():
        raise SystemExit(f"{label} not found.")
    problems, allowed = guard(folder, allow)
    print(f"Guard for {label}: {'FAIL' if problems else 'pass'}")
    for x in problems:
        print(f"  refused: {x}")
    for x in allowed:
        print(f"  allowed: {x}")
    changed = data_change(root, read_info(folder)) if (folder / "run_info.txt").exists() else None
    print(f"Data check: {'FAIL, ' + changed if changed else 'pass'}")
    if tracked_mode(root):
        print("accept would commit:")
        for ln in changes(root, f"outputs/{task}") + (changes(root, "code") if (root / "code").is_dir() else []):
            print(f"  {ln}")
        others = [ln for ln in other_changes(root, task) if not ln[3:].startswith("outputs/")]
        if others:
            print("left uncommitted:")
            for ln in others:
                print(f"  {ln}")
    return 1 if problems or changed else 0


def cmd_accept(task, root, question, allow, rejected=False, data_ok=False):
    task = clean_task(task)
    if not tracked_mode(root):
        print("Run folder mode: there is nothing to accept, reject or discard; the run folder is the record.")
        return 0
    folder = root / "outputs" / task
    rel = f"outputs/{task}"
    if not folder.is_dir() or not changes(root, rel):
        raise SystemExit(f"{rel}/ has no run pending review.")
    problems, allowed = guard(folder, allow)
    if problems:
        print(f"Guard failed for {rel}/; nothing was committed. Move or reduce these files, or pass "
              f"--allow <file> if the user accepts them:", file=sys.stderr)
        for x in problems:
            print(f"  {x}", file=sys.stderr)
        return 1
    changed = data_change(root, read_info(folder))
    if changed and not data_ok:
        print(f"{changed}. Input data must not change during a run; nothing was committed. Review the change, "
              f"then pass --data-changed-ok if the user accepts it.", file=sys.stderr)
        return 1
    tag = read_info(folder).get("proposed tag")
    if not tag:
        raise SystemExit(f"{rel}/run_info.txt names no proposed tag.")
    tag += "-rejected" if rejected else ""
    if git(root, "tag", "-l", tag).stdout.strip():
        raise SystemExit(f"Tag {tag} already exists. Start the run again to get a new run number.")
    question = question or last_question(root, task)
    if not question:
        raise SystemExit(f"No earlier run of {task} to take the question from: give the question.")
    index = root / "outputs" / "INDEX.md"
    index_before = index.read_bytes() if index.exists() else None
    indexed = update_index(root, task, tag, question, "not adopted" if rejected else "current")
    paths = [rel] + (["outputs/INDEX.md"] if indexed else []) + (["code"] if (root / "code").is_dir() else [])
    message = question + ("\n\nAllowed by the user although over the file guard:\n" + "\n".join(allowed)
                          if allowed else "")
    message += f"\n\nRun control version: {read_info(folder).get('run control version', 'not recorded')}"
    try:
        git(root, "add", "-A", "--", *paths)
        # Commit only these paths, so anything else the user has staged stays out of the run's commit.
        git(root, "commit", "-q", "-m", f"{'Reject' if rejected else 'Accept'} {tag}: {question}", "--", *paths)
    except SystemExit:
        # No commit was made: take the row back out, so that a retry does not add it twice.
        if indexed:
            index.write_bytes(index_before)
            git(root, "reset", "-q", "--", "outputs/INDEX.md", check=False)
        print("Nothing was committed or tagged; outputs/INDEX.md is as it was. Fix the cause and accept again.",
              file=sys.stderr)
        raise
    git(root, "tag", "-a", tag, "-m", message)
    print(f"Committed and tagged {tag} ({'not adopted' if rejected else 'current'})."
          + ("" if indexed else " This project keeps no outputs/INDEX.md, so the tag is the record."))
    others = other_changes(root, task)
    if others:
        print("Left uncommitted (not part of this run):")
        for ln in others:
            print(f"  {ln}")
    return 0


def cmd_discard(task, root):
    task = clean_task(task)
    if not tracked_mode(root):
        print("Run folder mode: there is nothing to accept, reject or discard; delete the run folder if unwanted.")
        return 0
    rel = f"outputs/{task}"
    if not changes(root, rel):
        print(f"{rel}/ has no run pending review; nothing to discard.")
        return 0
    if git(root, "ls-files", "--", rel).stdout.strip():
        git(root, "restore", "--staged", "--worktree", "--source=HEAD", "--", rel)
    git(root, "clean", "-fdq", "--", rel)
    print(f"{rel}/ restored to the last accepted run" if (root / rel).exists()
          else f"{rel}/ removed (the task had no accepted run)")
    return 0


def cmd_status(root):
    outputs = root / "outputs"
    if not outputs.is_dir():
        print("No outputs/ folder.")
        return 0
    failures = 0
    if not tracked_mode(root):
        print("Run folder mode (no git steps). Guard failures by run folder:")
        folders = [p for p in sorted(outputs.iterdir()) if p.is_dir()]
    else:
        pending = sorted({ln[3:].split("/")[1] for ln in changes(root, "outputs") if ln[3:].count("/") >= 2})
        print(f"Pending task folders: {', '.join(pending) if pending else 'none'}")
        folders = [outputs / p for p in pending]
        if (outputs / "INDEX.md").exists():
            rows = {c[0].strip("`") for _, c in index_rows((outputs / "INDEX.md").read_text(encoding="utf-8"))}
            runs = [t for t in git(root, "tag", "-l").stdout.split() if re.match(r"^.+-\d{6}-run\d+(-rejected)?$", t)]
            missing = sorted(set(runs) - rows)
            print(f"Run tags with no INDEX.md row: {', '.join(missing) if missing else 'none'}")
            failures += len(missing)
        else:
            print("This project keeps no outputs/INDEX.md: the run tags are the record.")
    for f in folders:
        problems, _ = guard(f)
        if problems:
            failures += 1
            print(f"  {f.name}: {len(problems)} guard problems")
            for x in problems:
                print(f"    {x}")
    return 1 if failures else 0


def split_root(argv):
    """Remove --root from argv wherever it stands; return (root or None, remaining arguments)."""
    rest, root, i = [], None, 0
    while i < len(argv):
        if argv[i] == "--root" and i + 1 < len(argv):
            root, i = argv[i + 1], i + 2
        elif argv[i].startswith("--root="):
            root, i = argv[i][7:], i + 1
        else:
            rest.append(argv[i])
            i += 1
    return root, rest


def main(argv):
    root_arg, argv = split_root(argv)
    ap = argparse.ArgumentParser(prog="run_control.py", description="Run control for task output folders.")
    ap.add_argument("--root", default=None, help="project root (default: current directory)")
    ap.add_argument("--version", action="version", version=f"run_control.py {VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("start", "path", "discard"):
        sub.add_parser(name).add_argument("task")
    p = sub.add_parser("check")
    p.add_argument("task")
    p.add_argument("--allow", action="append", default=[])
    for name in ("accept", "reject"):
        p = sub.add_parser(name)
        p.add_argument("task")
        p.add_argument("question", nargs="?")
        p.add_argument("--allow", action="append", default=[])
        p.add_argument("--data-changed-ok", action="store_true")
    sub.add_parser("status")
    args = ap.parse_args(argv)
    root = Path(root_arg).resolve() if root_arg else Path.cwd()
    if args.cmd == "start":
        print(start_run(args.task, root))
    elif args.cmd == "path":
        print(plan_run(args.task, root)[1])
    elif args.cmd == "check":
        return cmd_check(args.task, root, args.allow)
    elif args.cmd in ("accept", "reject"):
        return cmd_accept(args.task, root, args.question, args.allow, rejected=args.cmd == "reject",
                          data_ok=args.data_changed_ok)
    elif args.cmd == "discard":
        return cmd_discard(args.task, root)
    elif args.cmd == "status":
        return cmd_status(root)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
