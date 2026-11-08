# Blank prompt template

Copy this to write a prompt for one task, whether you give it to a fresh subagent or run it yourself. Replace each bracket and delete this note. One prompt per task: if it needs three tasks, write three prompts.

Use a prompt, not a skill, when the step is open reasoning over varying evidence. Use a skill when the steps are fixed (`prompts/new-skill-workflow.md`). To brief a subagent, see `agents/subagent-task-template.md`. To decide how much to delegate, use `prompts/delegation-map.md`.

## Task

[One sentence, imperative.]

## Context

[Two or three sentences: the project, what exists, where the files are. Point at documents instead of summarising them.]

## Inputs

[Exact paths. If an input does not exist yet, say who produces it.]

## Neutral framing

[State the question, never the hoped-for answer. Write it so a stranger could not guess which result you prefer.]

## Method

[Only if the reasoning needs guidance: what to weigh, what to report when evidence is thin or missing. Remove if not needed.]

## Acceptance criteria

[Each item can be checked from the files, without asking the agent: numbers, paths, pass or fail.]

- [ ] ...

## Output

[Where the result goes and what it is called. Use the task name `<prompt>-<subject>` and the run control command in `machine.md` (`path`, then `start`). Fix the file name. A forked subagent returns a `.md` report as text under `FILE: <path>`.]

## Rules that apply

- Use only what the inputs support. Where they are silent, write MISSING. Report nulls as plainly as effects.
- Every number comes from the inputs or from a script run. State the standard deviation with a mean, and the p-value and sample size with an R squared.
- Report assumptions and ask where there is a choice.

## Out of scope

[What the agent must not touch or decide: the bibliography, the input data, any judgement you keep.]

## Definition of done

Ran end to end in a fresh session, outputs on disc, and a short report of what changed and what surprised you.
