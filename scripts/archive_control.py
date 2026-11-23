"""Archive and restore task output folders (project addition to run control).

An archived folder is removed from the working tree. Nothing is lost: the folder is held by the git history
and by an annotated tag `archive-<task>-<DDMMYY>` that points at the commit that still holds it. The run tags
(`<task>-<DDMMYY>-run<N>`) are kept, so the INDEX.md rows and the reports that cite run tags stay valid.

Commands (archive_control.py <command> ... [--root <project root>], --root anywhere; --version prints the version):
  archive <task> [<task> ...] [--message TEXT] [--no-commit]
        for each task: refuse unless outputs/<task>/ is committed and unchanged, has no git-ignored files and
        has a row with status current in outputs/INDEX.md. Then add the archive tag, set the status of the
        current row to archived (the cell Superseded by holds the archive tag), `git rm` the folder and
        commit the folder removal and INDEX.md only (other changes are left alone). --message adds text
        (for example the attribution lines) to the end of the commit message.
  restore <task>
        check the latest archive tag of the task out into outputs/<task>/ (staged, not committed) and set
        the status of the row back to current. Commit it when it is wanted again.
  list  print the archived tasks and their archive tags.
A legacy row (a folder with no run tag, first cell the folder name) is handled in the same way.
In a topic project (outputs/TOPICS.md, read through outputs_layout.py beside this script) the task folder is
outputs/<topic>/<task>/ and its INDEX.md row names topic/task. The archive tag message records the relative
folder, and restore reads it from there, not from the registry.

Used with: outputs/INDEX.md, check_records.py (a path under an archived folder counts as existing).
The master is scripts/archive_control.py in the Agent-docs repository; deploy.py installs it as ~/.claude/scripts/archive_control.py.
Version: see VERSION; it is written to the archive tag message.

Created using: Claude Sonnet-v5.5-date: 131026
Modified using: claude-sonnet-5-5-v5.5-date: 081126 (moved to scripts/; --root anywhere; version)
Modified using: claude-opus-5-5-v5.5-date: 231126 (version 1.1: topic layout through outputs_layout.py)
"""
import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # outputs_layout.py is installed beside this script
import outputs_layout as ol  # noqa: E402

VERSION = "1.1"


def git(root, *args, check=True):
    res = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if check and res.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {res.stderr.strip() or res.stdout.strip()}")
    return res


def rows(lines):
    for i, line in enumerate(lines):
        if line.startswith("| `"):
            yield i, [c.strip() for c in line.strip().strip("|").split("|")]


def task_rows(lines, task, name=None):
    """INDEX.md rows of a task; name is the second cell (outputs_layout.index_name), the task when flat."""
    t, legacy = f"`{name or task}`", f"`{task}`"
    return [(i, c) for i, c in rows(lines) if len(c) == 5 and (c[1] == t or (c[1] == "" and c[0] == legacy))]


def task_folder(root, task):
    """(folder, relative folder, INDEX.md name) of a task's present folder."""
    try:
        folder = ol.task_folder(root, task)
    except ol.LayoutError as e:
        raise SystemExit(str(e))
    folder = folder or root / "outputs" / task
    rel = folder.relative_to(root).as_posix()
    return folder, rel, rel[len("outputs/"):]


def write(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_archive(root, tasks, message, commit):
    idx = root / "outputs" / "INDEX.md"
    lines = idx.read_text(encoding="utf-8").splitlines()
    stamp = dt.date.today().strftime("%d%m%y")
    plan = []
    for task in tasks:
        folder, rel, name = task_folder(root, task)
        if not folder.is_dir():
            raise SystemExit(f"{folder} not found")
        if git(root, "status", "--porcelain", "--", rel).stdout.strip():
            raise SystemExit(f"{rel}/ has uncommitted changes: accept, reject or discard the run first")
        if git(root, "status", "--porcelain", "--ignored", "--", rel).stdout.strip():
            raise SystemExit(f"{rel}/ holds git-ignored files: move them out first")
        cur = [(i, c) for i, c in task_rows(lines, task, name) if c[3] == "current"]
        if not cur:
            raise SystemExit(f"{task}: no INDEX.md row with status current")
        tag = f"archive-{task}-{stamp}"
        if git(root, "tag", "-l", tag).stdout.strip():
            raise SystemExit(f"tag {tag} exists")
        plan.append((task, tag, cur, rel))
    for task, tag, cur, rel in plan:
        git(root, "tag", "-a", tag, "-m", f"Archive of {rel}/. Restore with archive_control.py restore {task}.\n\nArchive control version: {VERSION}")
        for i, c in cur:
            c[3], c[4] = "archived", f"`{tag}`"
            lines[i] = "| " + " | ".join(c) + " |"
        git(root, "rm", "-r", "-q", rel)
        if (root / rel).exists():
            shutil.rmtree(root / rel)
    write(idx, lines)
    paths = ["outputs/INDEX.md"] + [rel for _, _, _, rel in plan]
    if commit:
        msg = f"Archive {len(plan)} task folders: " + ", ".join(t for t, _, _, _ in plan)
        if message:
            msg += "\n\n" + message
        git(root, "add", "--", "outputs/INDEX.md")
        git(root, "commit", "-q", "-m", msg, "--", *paths)
    print(f"Archived {len(plan)} folders: " + ", ".join(f"{t} ({tag})" for t, tag, _, _ in plan))


def cmd_restore(root, task):
    idx = root / "outputs" / "INDEX.md"
    lines = idx.read_text(encoding="utf-8").splitlines()
    tags = git(root, "tag", "-l", f"archive-{task}-*", "--sort=-creatordate").stdout.split()
    if not tags:
        raise SystemExit(f"no archive tag for {task}")
    # The folder comes from the tag message that archive wrote, so a later change to TOPICS.md cannot move it.
    text = git(root, "tag", "-l", "--format=%(contents)", tags[0]).stdout
    m = re.search(r"^Archive of (outputs/\S+?)/?\. Restore", text, re.M)
    rel = m.group(1) if m else f"outputs/{task}"
    if (root / rel).exists():
        raise SystemExit(f"{rel}/ already exists")
    git(root, "checkout", tags[0], "--", rel)
    for i, c in task_rows(lines, task, rel[len("outputs/"):]):
        if c[3] == "archived":
            c[3], c[4] = "current", ""
            lines[i] = "| " + " | ".join(c) + " |"
    write(idx, lines)
    print(f"Restored {rel}/ from {tags[0]} (staged, not committed); INDEX.md status set to current.")


def cmd_list(root):
    lines = (root / "outputs" / "INDEX.md").read_text(encoding="utf-8").splitlines()
    n = 0
    for i, c in rows(lines):
        if len(c) == 5 and c[3] == "archived":
            n += 1
            print(f"{c[1] or c[0]}  {c[4]}")
    print(f"{n} archived")


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
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--version", action="version", version=f"archive_control.py {VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("archive")
    a.add_argument("tasks", nargs="+")
    a.add_argument("--message", default="")
    a.add_argument("--no-commit", action="store_true")
    r = sub.add_parser("restore")
    r.add_argument("task")
    sub.add_parser("list")
    args = ap.parse_args(argv)
    root = Path(root_arg or ".").resolve()
    if args.cmd == "archive":
        cmd_archive(root, args.tasks, args.message, not args.no_commit)
    elif args.cmd == "restore":
        cmd_restore(root, args.task)
    else:
        cmd_list(root)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
