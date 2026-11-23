r"""The layout of a project's outputs/ folder: flat, or topic folders (shared by the run control scripts).

A project chooses its layout in `outputs/TOPICS.md`:
- no TOPICS.md: flat, as every project made before this module. Task folders are outputs/<task>/.
- `Layout: flat`: flat; the file records that the choice was made, and its table may list topics, each with
  the prefix that new task names of that topic start with. `project.py status` and `check_records.py` then
  report task folders that have no listed prefix and are not named in backticks in the file. Run control
  does not enforce the prefixes (skills choose their own task names). `layout flat` may be written in a
  project that already has runs, because it changes nothing.
- `Layout: undecided`: no run may start until the layout is chosen.
- `Layout: topics`: every folder in outputs/ is a topic named in the table, and its subfolders are task
  folders, outputs/<topic>/<task>/. A line `Default topic: <topic>` names the topic of a new task given
  without one.
Every TOPICS.md table has five columns: topic, prefix (`none` allowed in a topic project), scope, plan reference
and state (open or closed). A topic project's layout is fixed once any task folder, run tag or INDEX.md row exists. Task names are unique in the
project, so a tag (<task>-<DDMMYY>-run<N>) never names the topic.

Imported by run_control.py, archive_control.py, check_records.py, wrapup_status.py and project.py from their
own folder (deploy.py installs it beside them). With no TOPICS.md every function returns what those scripts
computed before this module existed.

Functions (root is the project root, a Path):
  read_registry(root)              the parsed TOPICS.md, or None when there is none
  layout(root)                     'flat', 'topics' or 'undecided'; LayoutError if TOPICS.md is malformed
  task_folder(root, task)          the present folder of a task (tracked task folder), or None
  task_topic(root, task)           the topic of an existing task (folder, INDEX row or tag message), or None
  new_task_folder(root, task, topic=None)   the folder for a new task, with the refusals (LayoutError)
  start_folder(root, arg, topic=None)       the folder `start` and `path` use, for a new or an existing task
  all_task_folders(root)           the task (or run) folders, one level deep (flat) or two (topics)
  index_name(root, task)           the second INDEX.md cell, without backticks: 'task' or 'topic/task'
  task_label(root, rel)            the task label of a path under outputs/ ('task' or 'topic/task'), or None
  has_runs(root)                   whether any task folder, run tag or INDEX.md row exists
  registry_text(layout, rows, default)      the text of a new TOPICS.md
  write_registry(root, reg)        write the layout, default and topic rows, keeping every other line of the file
  prefix_report(root)              (prefixes, task folders with no listed prefix and not named) in a flat project
Usage: outputs_layout.py --version | outputs_layout.py show [--root <project root>]
Inputs:  outputs/TOPICS.md, the folders under outputs/, outputs/INDEX.md and the git tags of the project.
Outputs: return values; `show` prints the layout and the task folders. No file is written by this module
         except through registry_text, whose text the calling script writes.
Exit:    0; 1 with a message when TOPICS.md is malformed (show).
Version: see VERSION; `--version` prints it.

Created using: claude-opus-5-5-v5.5-date: 231126
Modified using: claude-opus-5-5-v5.5-date: 231126 (version 1.1: prefix column; topics and prefixes in a flat project;
                the registry is edited in place)
"""
import re
import subprocess
import sys
from pathlib import Path

VERSION = "1.1"
REGISTRY = "TOPICS.md"
LAYOUTS = ("flat", "topics", "undecided")
DEFAULT_TOPIC = "general"
DEFAULT_SCOPE = "runs before the plan or outside its phases"
RUN_TAG = re.compile(r"^(.+)-\d{6}-run\d+(-rejected)?$")
RUN_FOLDER = re.compile(r"^(.+)-\d{6}-run\d+$")
FORM = "a line 'Layout: flat', 'Layout: topics' or 'Layout: undecided'"
HEADER = ["| Topic | Prefix | Scope | Plan reference | State |", "|---|---|---|---|---|"]
PREFIX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class LayoutError(Exception):
    """A refused step or a malformed TOPICS.md; the message says what to do."""


def clean(name, kind="Task"):
    """Letters, digits, '-' and '_' only (the rule run_control.py has always applied to task names)."""
    out = re.sub(r"[^A-Za-z0-9_-]+", "-", name.strip()).strip("-")
    if not out:
        raise LayoutError(f"{kind} name {name!r} has no usable characters.")
    return out


def git(root, *args):
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    except OSError:
        return 1, ""
    return r.returncode, r.stdout


# ---------------------------------------------------------------- the registry

def read_registry(root):
    """{'layout', 'default', 'topics': {name: {'prefix', 'scope', 'plan', 'state'}}, 'order': [names], 'errors': [...]}
    or None if outputs/TOPICS.md does not exist. A missing or unknown layout line, a topic row without five cells,
    a missing, malformed or repeated prefix (a flat project needs one in every row) are listed in 'errors'."""
    path = Path(root) / "outputs" / REGISTRY
    if not path.is_file():
        return None
    reg = {"layout": None, "default": None, "topics": {}, "order": [], "errors": []}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^Layout:\s*(\S+)\s*$", line)
        if m:
            reg["layout"] = m.group(1).lower()
            continue
        m = re.match(r"^Default topic:\s*`?([^`\s]+)`?\s*$", line)
        if m:
            reg["default"] = m.group(1)
            continue
        if line.startswith("| `"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            name = cells[0].strip("`")
            if len(cells) != 5:
                reg["errors"].append(f"the row of topic {name!r} in outputs/TOPICS.md has {len(cells)} cells, not five "
                                     f"(topic, prefix, scope, plan reference, state)")
                continue
            reg["topics"][name] = {"prefix": cells[1].strip("`"), "scope": cells[2], "plan": cells[3],
                                   "state": cells[4].lower()}
            reg["order"].append(name)
    if reg["layout"] is None:
        reg["errors"].append(f"outputs/TOPICS.md has no layout line: expected {FORM}")
    elif reg["layout"] not in LAYOUTS:
        reg["errors"].append(f"outputs/TOPICS.md has an unknown layout {reg['layout']!r}: expected {FORM}")
    seen = {}
    for name in reg["order"]:
        pre = reg["topics"][name]["prefix"]
        if pre.lower() == "none" and reg["layout"] == "topics":
            continue
        if pre.lower() == "none" or not PREFIX.match(pre):
            reg["errors"].append(f"topic {name!r} in outputs/TOPICS.md has no usable prefix ({pre!r})"
                                 + (": a flat project needs one in every row" if reg["layout"] == "flat" else ""))
        elif pre in seen:
            reg["errors"].append(f"the prefix {pre!r} is given to two topics in outputs/TOPICS.md ({seen[pre]}, {name})")
        else:
            seen[pre] = name
    if reg["layout"] == "topics":
        if not reg["default"]:
            reg["errors"].append("outputs/TOPICS.md sets the topic layout but has no line 'Default topic: <topic>'")
        elif reg["default"] not in reg["topics"]:
            reg["errors"].append(f"the default topic {reg['default']!r} is not a row of the table in outputs/TOPICS.md")
    return reg


def checked_registry(root):
    reg = read_registry(root)
    if reg and reg["errors"]:
        raise LayoutError("; ".join(reg["errors"]))
    return reg


def layout(root):
    """'flat' (also when there is no TOPICS.md), 'topics' or 'undecided'. LayoutError if TOPICS.md is malformed."""
    reg = checked_registry(root)
    return reg["layout"] if reg else "flat"


def registry_text(layout_name, rows=None, default=None):
    """The text of a new outputs/TOPICS.md. rows: [(topic, prefix, scope, plan reference, state)]."""
    lines = ["# Output topics", "",
             "This file lives at `outputs/TOPICS.md` and is tracked in git. It records the layout of `outputs/`, "
             "which is fixed once the first run exists. Change it only with `run_control.py layout` and "
             "`run_control.py topics`.", "",
             f"Layout: {layout_name}"]
    if layout_name == "topics":
        lines += [f"Default topic: {default}", "",
                  "Each topic is a folder `outputs/<topic>/` that holds task folders. A closed topic takes no new "
                  "task. A topic that holds a task is never renamed or merged.", ""] + HEADER
        lines += [row_text(*r) for r in rows or []]
    elif layout_name == "flat":
        lines += ["", "Task folders are `outputs/<task>/`. New task names start with the prefix of their topic "
                      "(`run_control.py topics add <topic> \"<scope>\" --plan \"<reference>\" --prefix <prefix>`). A task "
                      "folder named in backticks in this file counts as placed. A topic that holds a task is never "
                      "renamed.", ""] + HEADER
        lines += [row_text(*r) for r in rows or []]
    elif layout_name == "undecided":
        lines += ["", "No run can start until the layout is chosen: `run_control.py layout topics` or "
                      "`run_control.py layout flat`."]
    return "\n".join(lines) + "\n"


def cell(text):
    return " ".join(str(text).split()).replace("|", "/") or "none"


def row_text(name, prefix, scope, plan, state):
    return f"| `{name}` | {'`' + prefix + '`' if prefix.lower() != 'none' else 'none'} | {cell(scope)} | {cell(plan)} | {state} |"


def write_registry(root, reg):
    """Write the topic rows (and the default topic line) into outputs/TOPICS.md, keeping every other line."""
    rows = [row_text(n, reg["topics"][n]["prefix"], reg["topics"][n]["scope"], reg["topics"][n]["plan"],
                     reg["topics"][n]["state"]) for n in reg["order"]]
    path = Path(root) / "outputs" / REGISTRY
    lines = path.read_text(encoding="utf-8").splitlines()
    at = [i for i, ln in enumerate(lines) if ln.startswith("| `") and len(ln.strip().strip("|").split("|")) == 5]
    if at:  # replace the old topic rows with the new ones, where the first one stood
        keep = [ln for i, ln in enumerate(lines) if i not in set(at)]
        lines = keep[:at[0]] + rows + keep[at[0]:]
    else:
        head = next((i for i, ln in enumerate(lines) if ln.replace(" ", "").lower().startswith("|topic|prefix|")), None)
        if head is None:
            lines += [""] + HEADER
            head = len(lines) - 2
        lines = lines[:head + 2] + rows + lines[head + 2:]
    if reg["default"]:
        lines = [f"Default topic: {reg['default']}" if ln.startswith("Default topic:") else ln for ln in lines]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


def prefix_report(root):
    """(prefixes, unplaced) in a flat project with listed prefixes, else None. unplaced: task names (run folders
    reduced to their task) that start with no listed prefix and are not named in backticks in TOPICS.md."""
    reg = read_registry(root)
    if not reg or reg["errors"] or reg["layout"] != "flat":
        return None
    prefixes = [reg["topics"][n]["prefix"] for n in reg["order"]]
    if not prefixes:
        return None
    named = set(re.findall(r"`([^`]+)`", (Path(root) / "outputs" / REGISTRY).read_text(encoding="utf-8")))
    tasks = sorted({base_task(p.name) for p in all_task_folders(root)})
    return prefixes, [t for t in tasks if not t.startswith(tuple(prefixes)) and t not in named]


# ---------------------------------------------------------------- tasks and folders

def topic_dirs(root):
    outputs = Path(root) / "outputs"
    return sorted(p for p in outputs.iterdir() if p.is_dir()) if outputs.is_dir() else []


def all_task_folders(root):
    """Task folders (or run folders in run folder mode): outputs/*/ when flat, outputs/*/*/ in a topic project."""
    if layout_or_flat(root) != "topics":
        return topic_dirs(root)
    return [q for p in topic_dirs(root) for q in sorted(p.iterdir()) if q.is_dir()]


def layout_or_flat(root):
    """The layout, with a malformed TOPICS.md read as flat (for reports that must not stop)."""
    try:
        return layout(root)
    except LayoutError:
        return "flat"


def task_label(root, rel, lay=None):
    """'task' (flat) or 'topic/task' (topics) for a path under outputs/ that lies inside a task folder, else None."""
    parts = rel.replace("\\", "/").split("/")
    if not parts or parts[0] != "outputs":
        return None
    if (lay or layout_or_flat(root)) == "topics":
        return f"{parts[1]}/{parts[2]}" if len(parts) >= 4 else None
    return parts[1] if len(parts) >= 3 else None


def base_task(name):
    m = RUN_FOLDER.match(name)
    return m.group(1) if m else name


def folders_of(root, task):
    """Folders on disc that belong to the task: its task folder and its run folders, in any topic."""
    return [p for p in all_task_folders(root) if p.name == task or base_task(p.name) == task]


def task_folder(root, task):
    """The present task folder of a task (outputs/<task> or outputs/<topic>/<task>), or None."""
    hits = [p for p in all_task_folders(root) if p.name == task]
    if len(hits) > 1:
        raise LayoutError(f"Task {task} has a folder in more than one topic: "
                          + ", ".join(rel(root, p) for p in hits) + ". Task names must be unique.")
    return hits[0] if hits else None


def rel(root, path):
    return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()


def index_cells(root):
    path = Path(root) / "outputs" / "INDEX.md"
    if not path.is_file():
        return []
    return [[c.strip() for c in ln.strip().strip("|").split("|")]
            for ln in path.read_text(encoding="utf-8").splitlines() if ln.startswith("| `")]


def run_tags(root, task=None):
    code, out = git(root, "tag", "-l")
    tags = [t for t in out.split() if RUN_TAG.match(t)] if code == 0 else []
    return [t for t in tags if RUN_TAG.match(t).group(1) == task] if task else tags


def tag_topic(root, tag):
    code, out = git(root, "tag", "-l", "--format=%(contents)", tag)
    m = re.search(r"^Topic: (\S+)\s*$", out, re.M) if code == 0 else None
    return m.group(1) if m else None


def task_topic(root, task):
    """The topic of an existing task in a topic project: from its folder, an INDEX.md row or a tag message."""
    found = {p.parent.name for p in folders_of(root, task)}
    for c in index_cells(root):
        if len(c) > 1 and c[1].strip("`").count("/") == 1 and c[1].strip("`").split("/")[1] == task:
            found.add(c[1].strip("`").split("/")[0])
    for t in run_tags(root, task):
        tp = tag_topic(root, t)
        if tp:
            found.add(tp)
    if len(found) > 1:
        raise LayoutError(f"Task {task} is recorded in more than one topic ({', '.join(sorted(found))}). "
                          f"Task names must be unique; check outputs/ and outputs/INDEX.md.")
    return found.pop() if found else None


def task_known(root, task):
    """Whether the name is used anywhere: a folder, an INDEX.md row (second cell or legacy first cell) or a run tag."""
    if folders_of(root, task) or run_tags(root, task):
        return True
    for c in index_cells(root):
        name = c[1].strip("`") if len(c) > 1 and c[1] else c[0].strip("`")
        first = RUN_TAG.match(c[0].strip("`"))
        if name.split("/")[-1] == task or (first and first.group(1) == task):
            return True
    return False


def has_runs(root):
    """Whether any task folder, run tag or INDEX.md row exists (the layout is then fixed)."""
    return bool(topic_dirs(root) or run_tags(root) or index_cells(root))


def index_name(root, task):
    """The second INDEX.md cell of a task, without backticks: 'task' (flat) or 'topic/task' (topics)."""
    if layout_or_flat(root) != "topics":
        return task
    topic = task_topic(root, task)
    return f"{topic}/{task}" if topic else task


def split_arg(arg, topic=None, lay="flat"):
    """(topic or None, task) from a `start` argument. The slash separates topic and task only in a topic project."""
    if lay != "topics":
        if topic:
            raise LayoutError("This project has a flat outputs layout: it has no topics, so --topic cannot be used.")
        return None, clean(arg)
    parts = arg.replace("\\", "/").split("/")
    if len(parts) > 2:
        raise LayoutError(f"{arg!r} has more than one '/': give <topic>/<task> or <task> --topic <topic>.")
    given = clean(parts[0], "Topic") if len(parts) == 2 else None
    task = clean(parts[-1])
    topic = clean(topic, "Topic") if topic else None
    if given and topic and given != topic:
        raise LayoutError(f"Two topics given for {task}: {given} and {topic}.")
    return given or topic, task


def undecided_message():
    return ("The outputs layout of this project is undecided (outputs/TOPICS.md), so no run can start. Ask the user "
            "to choose, then run `run_control.py layout topics` or `run_control.py layout flat`.")


def open_topics(reg):
    return [n for n in reg["order"] if reg["topics"][n]["state"] == "open"]


def new_task_folder(root, task, topic=None):
    """outputs/<topic>/<task> (topics) or outputs/<task> (flat) for a task that does not exist yet.
    Refused: an undecided layout, an unknown or closed topic, and a name already used in the project."""
    root = Path(root)
    reg = checked_registry(root)
    lay = reg["layout"] if reg else "flat"
    if lay == "undecided":
        raise LayoutError(undecided_message())
    if lay == "flat":
        return root / "outputs" / task
    if task_known(root, task):
        where = task_topic(root, task)
        raise LayoutError(f"The task name {task} is already used in this project"
                          + (f" (topic {where})" if where else " (a run tag or an INDEX.md row)")
                          + ". Task names are unique in the project: choose another name.")
    topic = topic or reg["default"]
    if topic not in reg["topics"]:
        raise LayoutError(f"Unknown topic {topic}. Open topics: {', '.join(open_topics(reg)) or 'none'}. To add it, "
                          f"on the user's instruction: run_control.py topics add {topic} \"<scope>\" --plan "
                          f"\"<plan reference>\"")
    if reg["topics"][topic]["state"] != "open":
        raise LayoutError(f"Topic {topic} is closed: it takes no new task. Open topics: "
                          f"{', '.join(open_topics(reg)) or 'none'}. To reopen it, on the user's instruction: "
                          f"run_control.py topics reopen {topic}")
    return root / "outputs" / topic / task


def start_folder(root, arg, topic=None):
    """(task, topic or None, task folder, notice or None) for `start` and `path`.

    An existing task goes to its present folder (its topic); a new task goes through new_task_folder."""
    root = Path(root)
    reg = checked_registry(root)
    lay = reg["layout"] if reg else "flat"
    if lay == "undecided":
        raise LayoutError(undecided_message())
    want, task = split_arg(arg, topic, lay)
    if lay == "flat":
        return task, None, root / "outputs" / task, None
    have = task_topic(root, task)
    if have is None:
        if task_known(root, task):
            raise LayoutError(f"The task name {task} is already used in this project (a run tag or an INDEX.md row "
                              f"with no topic). Task names are unique in the project: choose another name.")
        folder = new_task_folder(root, task, want)
        return task, folder.parent.name, folder, None
    if want and want != have:
        raise LayoutError(f"Task {task} already exists in topic {have}. Task names are unique in the project: rerun "
                          f"it as {task} (or {have}/{task}), or choose another name.")
    if have not in reg["topics"]:
        raise LayoutError(f"Task {task} is in topic {have}, which is not in outputs/TOPICS.md. Restore the row "
                          f"before running.")
    notice = None
    if reg["topics"][have]["state"] != "open":
        notice = f"Notice: topic {have} is closed; {task} is an existing task, so this rerun is allowed."
    return task, have, root / "outputs" / have / task, notice


def show(root):
    try:
        lay = layout(root)
    except LayoutError as e:
        print(e, file=sys.stderr)
        return 1
    reg = read_registry(root)
    print(f"Layout: {lay}" + ("" if reg else " (no outputs/TOPICS.md)"))
    if lay == "topics":
        for n in reg["order"]:
            print(f"  {n} ({reg['topics'][n]['state']}): {reg['topics'][n]['scope']}")
    for p in all_task_folders(root):
        print(f"  {rel(root, p)}")
    return 0


def main(argv):
    if "--version" in argv:
        print(f"outputs_layout.py {VERSION}")
        return 0
    root = Path(".")
    if "--root" in argv and argv.index("--root") + 1 < len(argv):
        root = Path(argv[argv.index("--root") + 1])
    if argv and argv[0] == "show":
        return show(root.resolve())
    print("Usage: outputs_layout.py --version | outputs_layout.py show [--root <project root>]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
