r"""Report which project template level a project is at, and add the missing template files.

Created using: $\text {Created using: }\ claude-sonnet-5-5-\text{v}5.5-\text {date: }101126$
Modified using: claude-opus-5-5-v5.5-date: 231126 (version 1.3: the outputs layout, through outputs_layout.py)

The project templates have three levels. Minimal holds `CLAUDE.md` only. Handoff adds `records/HANDOFF.md`. Full
adds the data notes, the output index, the decision log, the products register and a `.gitignore`. The upgrade
check in the minimal and handoff `CLAUDE.md` files calls `status` so that the counts are not made by hand.

Usage: project.py status [--quiet] [--root <project root>]
       project.py init --level minimal|handoff|full [--topics | --flat | --layout-later] [--library] [--apply]
                       [--templates <claude-md folder>] [--root <project root>]
       project.py --version
  --root may stand anywhere in the command line; the default is the current folder.
  status    prints the level in use, the counts (files in data/, runs, memory notes), the recommended level and the
            files each level is missing, and the outputs layout (flat, topics with the open topics, or undecided;
            read through outputs_layout.py beside this script). While the layout is undecided the last line says so.
            In a flat project with 15 or more task folders it adds advice that acts within the project. --quiet
            prints only the last line. Nothing is written.
  init      is a dry run unless --apply is given. It adds the files of the level that are missing, never overwrites
            a file, and appends missing lines to `.gitignore`. An existing `CLAUDE.md` that differs from the template
            is left as it is and named, so that it is merged by hand. --library also appends the block in
            `project-library-block.md` (a project EndNote library under `sources/references/`) to `CLAUDE.md`
            when it has no "## Project library" heading; fill in its brackets.
            In a project with no task folder, run tag, INDEX.md row or outputs/TOPICS.md, the dry run prints the
            outputs layout choice, and --apply needs one of --topics, --flat or --layout-later: it writes
            outputs/TOPICS.md with the matching layout line (--topics also writes the default topic). Elsewhere the
            options are not needed and nothing about the layout is written.
  --templates   the `claude-md` folder of the Agent-docs repository. The default is the folder beside this script's
            parent, which exists when the script is run from the repository.
Inputs:  the project folder, its git tags (if it is a git repository) and the Claude memory folder for the project.
Outputs: a report on standard output; `init --apply` writes the missing template files.
Exit:    0 on success; 1 if init --apply needs a layout option; 2 if the folder or the templates are unusable.
Version: see VERSION; `--version` prints it.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # outputs_layout.py is installed beside this script
import outputs_layout as ol  # noqa: E402

VERSION = "1.3"
LEVELS = ("minimal", "handoff", "full")
LEVEL_FILES = {
    "minimal": ["CLAUDE.md"],
    "handoff": ["CLAUDE.md", "records/HANDOFF.md"],
    "full": ["CLAUDE.md", "data/DATA-NOTES.md", "outputs/INDEX.md", "records/DECISIONS.md",
             "records/HANDOFF.md", "products/PRODUCTS.md", ".gitignore"],
}
TEMPLATE_DIRS = {"minimal": "project-template-minimal", "handoff": "project-template-handoff", "full": "project-template"}
RUN = re.compile(r"-\d{6}-run\d+(-rejected)?$")
DATA_LIMIT, RUN_LIMIT = 3, 5
FLAT_ADVICE_LIMIT = 15  # task folders in a flat outputs/ before the advice in status
LAYOUT_OPTIONS = {"topics": "topics", "flat": "flat", "layout_later": "undecided"}
LAYOUT_CHOICE = """Outputs layout: not chosen yet. Choose one when you add --apply:
  --topics        outputs/<topic>/<task>/. Fits a project with a plan that has phases or work packages, or one
                  expected to produce many runs. The topics are added when the plan is agreed.
  --flat          outputs/<task>/. Fits a series of prompts with no plan.
  --layout-later  leaves the question open until the first run is due; run control `start` refuses until
                  `run_control.py layout topics` or `layout flat` settles it.
The layout is fixed once the first run exists."""
SOURCES_LINE = "sources/"


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


def git(root, *args):
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    except OSError:
        return 1, ""
    return r.returncode, r.stdout


def is_repo(root):
    return git(root, "rev-parse", "--is-inside-work-tree")[0] == 0


def data_files(root):
    """Files under data/, not counting the data notes and README files."""
    folder = root / "data"
    if not folder.is_dir():
        return []
    return [p for p in sorted(folder.rglob("*"))
            if p.is_file() and p.name != "DATA-NOTES.md" and not p.name.lower().startswith("readme")]


def run_names(root):
    """The names of runs: task folders and git tags that look like <task>-<DDMMYY>-run<N>."""
    names = set()
    names |= {p.name for p in ol.all_task_folders(root) if RUN.search(p.name)}
    code, out = git(root, "tag", "-l")
    if code == 0:
        names |= {t for t in out.split() if RUN.search(t)}
    return sorted(names)


def memory_folder(root):
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(config) if config else Path.home() / ".claude"
    return base / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(root)) / "memory"


def memory_notes(root):
    folder = memory_folder(root)
    if not folder.is_dir():
        return []
    return [p for p in sorted(folder.glob("*.md")) if p.name != "MEMORY.md"]


def level_in_use(root):
    if not (root / "CLAUDE.md").is_file():
        return None
    if any((root / p).is_file() for p in ("records/DECISIONS.md", "data/DATA-NOTES.md", "outputs/INDEX.md")):
        return "full"
    if (root / "records" / "HANDOFF.md").is_file():
        return "handoff"
    return "minimal"


def missing_files(root, level):
    return [p for p in LEVEL_FILES[level] if p != ".gitignore" and not (root / p).is_file()]


def gitignore_lines(templates, level):
    """The lines a `.gitignore` of the level should hold, as (comment lines, line) groups."""
    if templates is not None:
        f = templates / TEMPLATE_DIRS[level] / ".gitignore"
        if f.is_file():
            return groups(f.read_text(encoding="utf-8").splitlines())
    return [([], SOURCES_LINE)]


def groups(lines):
    """Pair each pattern line with the comment lines that stand directly above it."""
    out, comments = [], []
    for line in lines:
        s = line.strip()
        if not s:
            comments = []
        elif s.startswith("#"):
            comments.append(line)
        else:
            out.append((comments, line))
            comments = []
    return out


def missing_gitignore(root, templates, level):
    """The (comment lines, line) groups whose pattern is not yet in the project `.gitignore`."""
    f = root / ".gitignore"
    have = {ln.strip() for ln in f.read_text(encoding="utf-8").splitlines()} if f.is_file() else set()
    return [(c, ln) for c, ln in gitignore_lines(templates, level) if ln.strip() not in have]


def recommend(level, data, runs, notes):
    """(target level or None, reasons)."""
    if level is None:
        return None, []
    reasons = []
    if level != "full":
        if len(data) >= DATA_LIMIT:
            reasons.append(f"data/ holds {len(data)} files (limit {DATA_LIMIT})")
        if len(runs) >= RUN_LIMIT:
            reasons.append(f"outputs hold {len(runs)} runs (limit {RUN_LIMIT})")
        if reasons:
            return "full", reasons
    if level == "minimal":
        if notes:
            reasons.append(f"the memory folder holds {len(notes)} notes")
        if runs:
            reasons.append(f"outputs hold {len(runs)} runs")
        if reasons:
            return "handoff", reasons
    return None, []


def find_templates(arg):
    folder = Path(arg) if arg else Path(__file__).resolve().parent.parent / "claude-md"
    return folder if (folder / TEMPLATE_DIRS["full"]).is_dir() else None


def layout_report(root):
    """(report line, last-line addition or None, advice or None) for the outputs layout."""
    reg = ol.read_registry(root)
    if reg is not None and reg["errors"]:
        return (f"Outputs layout: outputs/TOPICS.md is malformed ({'; '.join(reg['errors'])})",
                "OUTPUTS LAYOUT MALFORMED, see outputs/TOPICS.md", None)
    lay = reg["layout"] if reg else "flat"
    if lay == "undecided":
        return ("Outputs layout: undecided",
                "OUTPUTS LAYOUT UNDECIDED, ask the user to choose topics or flat before the first run "
                "(run_control.py layout topics, or layout flat)", None)
    if lay == "topics":
        return f"Outputs layout: topics; open topics: {', '.join(ol.open_topics(reg)) or 'none'}", None, None
    tasks = {ol.base_task(p.name) for p in ol.all_task_folders(root)}
    advice = None
    if len(tasks) >= FLAT_ADVICE_LIMIT:
        advice = (f"Advice: outputs/ holds {len(tasks)} task folders. To keep the listing readable, archive finished "
                  f"tasks with archive_control.py archive <task>, and begin new task names with a phase prefix such "
                  f"as wp2-.")
    return f"Outputs layout: flat{'' if reg else ' (no outputs/TOPICS.md)'}", None, advice


def status(root, templates, quiet):
    level = level_in_use(root)
    data, runs, notes = data_files(root), run_names(root), memory_notes(root)
    target, reasons = recommend(level, data, runs, notes)
    lines = [f"Project: {root}",
             f"Template level in use: {level or 'none (no CLAUDE.md)'}",
             f"Files in data/ (not DATA-NOTES.md or README files): {len(data)}",
             f"Runs (task folders and tags): {len(runs)}",
             f"Memory notes: {len(notes)}"]
    layout_line, layout_last, advice = layout_report(root)
    lines.append(layout_line)
    if target:
        lines.append(f"Recommended level: {target} ({'; '.join(reasons)})")
    lines.append("Missing by level:")
    for lv in LEVELS:
        miss = missing_files(root, lv)
        ignore = [ln for _, ln in missing_gitignore(root, templates, lv)] if lv == "full" or is_repo(root) else []
        parts = []
        if miss:
            parts.append(", ".join(miss))
        if ignore:
            parts.append(".gitignore lines: " + ", ".join(ignore))
        lines.append(f"  {lv}: {'; '.join(parts) if parts else 'none'}")
    if level is None:
        last = "Status: NO TEMPLATE, run init --level minimal (or handoff, full)"
    elif target:
        last = f"Status: UPGRADE SUGGESTED to {target}"
    else:
        last = f"Status: OK at {level}"
    if advice:
        lines.append(advice)
    if layout_last:
        last += f"; {layout_last}"
    lines.append(last)
    print(last if quiet else "\n".join(lines))
    return 0


def template_files(templates, level):
    folder = templates / TEMPLATE_DIRS[level]
    return [p for p in sorted(folder.rglob("*"))
            if p.is_file() and p.name != ".gitignore" and "__pycache__" not in p.parts and p.suffix != ".pyc"]


LIBRARY_BLOCK = "project-library-block.md"
LIBRARY_HEADING = "## Project library"


def init(root, level, templates, apply, library=False, layout=None):
    fresh = ol.read_registry(root) is None and not ol.has_runs(root)
    if fresh and apply and layout is None:
        print(LAYOUT_CHOICE, file=sys.stderr)
        print("Nothing written: --apply needs one of --topics, --flat or --layout-later in a project with no runs.",
              file=sys.stderr)
        return 1
    if templates is None:
        print("The templates were not found. Give --templates <the claude-md folder of the Agent-docs repository>.",
              file=sys.stderr)
        return 2
    folder = templates / TEMPLATE_DIRS[level]
    if not folder.is_dir():
        print(f"No template folder {folder}.", file=sys.stderr)
        return 2
    add, kept, differs = [], [], []
    for src in template_files(templates, level):
        rel = src.relative_to(folder)
        dst = root / rel
        if not dst.exists():
            add.append((src, dst, rel))
        elif rel.as_posix() == "CLAUDE.md" and dst.read_bytes().replace(b"\r\n", b"\n") != src.read_bytes().replace(b"\r\n", b"\n"):
            differs.append((src, rel))
        else:
            kept.append(rel)
    ignore = missing_gitignore(root, templates, level) if (is_repo(root) or (folder / ".gitignore").is_file()) else []
    verb = "Added" if apply else "Would add"
    for _, dst, rel in add:
        print(f"{verb}: {rel.as_posix()}")
    if ignore:
        print(f"{verb} to .gitignore: " + ", ".join(ln.strip() for _, ln in ignore))
    for rel in kept:
        print(f"Exists, left as it is: {rel.as_posix()}")
    for src, rel in differs:
        print(f"Exists and differs from the {level} template, left as it is; merge by hand: {rel.as_posix()} "
              f"(template: {src})")
    claude, lib_block = root / "CLAUDE.md", templates / LIBRARY_BLOCK
    if library and not lib_block.is_file():
        print(f"No library block {lib_block}.", file=sys.stderr)
        return 2
    want_block = library and not (claude.is_file() and LIBRARY_HEADING in claude.read_text(encoding="utf-8"))
    if library and not want_block:
        print("Exists, left as it is: the Project library block in CLAUDE.md")
    if want_block:
        print(f"{verb} to CLAUDE.md: the Project library block (fill in its brackets)")
    if fresh and layout is None:
        print(LAYOUT_CHOICE)
    elif fresh:
        print(f"{verb}: outputs/TOPICS.md (Layout: {layout}"
              + (f", default topic {ol.DEFAULT_TOPIC})" if layout == "topics" else ")"))
    elif layout is not None:
        print("Outputs layout: not written, because the project already has runs or an outputs/TOPICS.md.")
    write_layout = fresh and layout is not None
    if not add and not ignore and not want_block and not write_layout:
        print("Nothing to add.")
    if apply:
        for src, dst, _ in add:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        if ignore:
            f = root / ".gitignore"
            text = f.read_text(encoding="utf-8") if f.is_file() else ""
            block = []
            for comments, line in ignore:
                if block and comments:
                    block.append("")
                block += comments + [line]
            with open(f, "w", encoding="utf-8", newline="") as fh:
                fh.write(text + ("" if not text or text.endswith("\n") else "\n") + ("\n" if text else "")
                         + "\n".join(block) + "\n")
        if want_block:
            text = claude.read_text(encoding="utf-8")
            with open(claude, "w", encoding="utf-8", newline="") as fh:
                fh.write(text + ("" if text.endswith("\n") else "\n") + "\n" + lib_block.read_text(encoding="utf-8"))
        if write_layout:
            rows = [(ol.DEFAULT_TOPIC, ol.DEFAULT_SCOPE, "none", "open")] if layout == "topics" else []
            (root / "outputs").mkdir(exist_ok=True)
            with open(root / "outputs" / ol.REGISTRY, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(ol.registry_text(layout, rows, ol.DEFAULT_TOPIC))
    elif add or ignore or want_block or write_layout:
        print("Dry run: nothing written. Add --apply to write.")
    return 0


def main(argv):
    root_arg, rest = split_root(argv)
    ap = argparse.ArgumentParser(prog="project.py", description="Project template level and missing files.")
    ap.add_argument("--version", action="version", version=f"project.py {VERSION}")
    sub = ap.add_subparsers(dest="command", required=True)
    st = sub.add_parser("status", help="level in use, counts, recommendation")
    st.add_argument("--quiet", action="store_true", help="print only the last line")
    st.add_argument("--templates", help="the claude-md folder of the Agent-docs repository")
    ini = sub.add_parser("init", help="add the missing files of a level (dry run unless --apply)")
    ini.add_argument("--level", required=True, choices=LEVELS)
    ini.add_argument("--apply", action="store_true", help="write the files")
    ini.add_argument("--library", action="store_true", help="add the Project library block to CLAUDE.md")
    choice = ini.add_mutually_exclusive_group()
    choice.add_argument("--topics", action="store_true", help="outputs/<topic>/<task>/ (a project with a plan)")
    choice.add_argument("--flat", action="store_true", help="outputs/<task>/ (a series of prompts with no plan)")
    choice.add_argument("--layout-later", action="store_true", help="leave the outputs layout undecided for now")
    ini.add_argument("--templates", help="the claude-md folder of the Agent-docs repository")
    args = ap.parse_args(rest)
    root = Path(root_arg).resolve() if root_arg else Path.cwd().resolve()
    if not root.is_dir():
        print(f"Not a folder: {root}", file=sys.stderr)
        return 2
    templates = find_templates(args.templates)
    if args.command == "status":
        return status(root, templates, args.quiet)
    layout = next((v for k, v in LAYOUT_OPTIONS.items() if getattr(args, k)), None)
    return init(root, args.level, templates, args.apply, args.library, layout)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
