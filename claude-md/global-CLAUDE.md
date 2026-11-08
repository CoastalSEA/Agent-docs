# CLAUDE.md

Guidance for Claude Code when working with code, across all projects.

This file holds rules that apply on any machine. Two local files in `~/.claude/rules/` load with it:

- `machine.md`: the system, shells, interpreters, tools, commands and locations on this machine.
- `profile.md`: the user's writing rules and code header format.

Each of the two files has a line that starts with `Marker:` near its top. If you cannot find the content of either file in your instructions, say so at the start of the session and ask before assuming any path, command or style.

## Environment

- Use only the interpreters, tools and commands named in `machine.md`, in the form given for the shell in use. Do not guess a path. A tool that `machine.md` does not list is not available: say so and ask.
- Environments that `machine.md` marks as limited to one purpose are not used for anything else.

## Code standards

- Include a help header block with a summary of inputs and outputs and the code generation model name, version and date, in the format set in `profile.md`.
- After changing a script, re-run it and confirm the outputs regenerated.

## Analysis rules

- Every number included in output reports comes from input data, or the output from computations carried out using a model, function or script. Never include values that cannot be traced.
- Nulls get reported as plainly as effects. Distinguish statistical from substantive significance.
- When reporting mean values, include the standard deviation in parenthesis (i.e. $<mean> (<std.dev.>)$).
- When reporting coefficients of determination, $R^2$, include the p-value and the number of samples. If a model has more than one independent variable, include the adjusted $R^2$ estimate.

## Outputs
- Write all outputs from a task to `outputs/<task name>/`, one folder per task question. A rerun overwrites the folder, except `.md` reports, which are edited in place. Start a new folder only when the question changes.
- Start each run with the run control command in `machine.md` (`start <task>`, with `--root <project root>`). A project that still holds its own `code/run_control.py` may use that copy; skills always use the machine command. A new run is pending until the user reviews it (`git diff`, run control `check <task>`).
- Only the user accepts, rejects (keeps but does not adopt) or discards a run. Then run the run control command `accept`, `reject` or `discard` for that task; they commit, tag and update `outputs/INDEX.md` if the project keeps one, or restore the folder. Reports cite the run tag.
- Downloaded sources (papers, reports, fetched data) are inputs. Save them in the git-ignored `sources/` folder in the project root, never in `outputs/`.
- Ask before pushing commits that hold outputs to a remote.
- If the project is not a git repository, or `outputs/` itself is git-ignored, each run gets a new folder `outputs/<task name>-<DDMMYY>-run<N>/` and the git steps do not apply.

## Methodological guardrails

- Never make assumptions silently. Always report them and where there is a choice prompt for a selection to be made.
- Do not make pejorative or subjective statements. Only use phrases such as 'bad data', or make 'real world inferences', when there is a clear line of evidence to support such statements.
- Before repeating a check or test, search the project's records and memory, if it has any, for an earlier result. Cite what is found. Rerun only if the result is stale (the inputs or the method changed since) or the user asks.
- When the user says "wrap up", carry out the wrap-up rule in the project `CLAUDE.md`. If the project has none, write a short summary of what was decided, what is open and the next step, and ask where to save it.
- Before a commit that closes a piece of work, suggest a wrap up first (unless one has just been done), so the final decision lines and the handoff go into one commit. Mid-task commits the user asks for do not need this.

## Subagents

Subagent Write calls are refused for `.md` files whose names begin with report, summary, findings or analysis. This is a server-side rule with no setting to turn it off. It is enforced only in the Write tool, so other tools can still create such files: do not use them to get round it. Other files are not blocked.

- When you task a subagent, include these instructions in its prompt:
    - Save every data file, table, figure, and script yourself; list each with its path.
    - Do not create `.md` files whose names begin with report, summary, findings, or analysis (Write, Bash, or script). Return such files as text under `FILE: <intended path>` in the final message; list every file this applies to.
    - If a Write of any other file is refused, do not work around it. Report refusals only if you attempted the write.
    - Keep reports short (findings, nulls, assumptions, surprises, table pointers); put detail in saved tables.

- Save each returned file as text; check the subagent's statements against saved outputs before relying on them.
- If a plan must be saved before work starts, ask the subagent to return it as text and stop. Save it, then resume with SendMessage.
- If you are a subagent, follow these instructions whether or not your prompt repeats them.

## Hard boundaries

- Never create, edit, or delete a bibliography entry. Flag problems; don't fix them.
- Never touch files supplied as input data. Cleaning happens downstream, in scripts.
- Ask before any step that sends data off this machine or changes a live system.

## What done means

A task is done when it ran end to end in a fresh session, its outputs exist on disc, and you've told me what changed and what surprised you. "It should work" is not done.
