# Blank prompt template

Copy this to write a prompt for one task. Replace each bracket, delete this note and delete any optional section that does not apply. One prompt per task: if it needs three tasks, write three prompts.

Use a prompt when the step is open reasoning over varying evidence. Use a skill when the steps are fixed (`prompts/new-skill-workflow.md`). To brief a subagent, also follow `agents/subagent-task-template.md`.

## Task

[One imperative sentence.]

## Context

[The project, what exists and where the files are, in two or three sentences. Point at documents instead of summarising them.]

## Inputs

[Exact paths. If an input does not exist yet, name who produces it.]

## Neutral framing

[The question, not the preferred answer. A stranger must not be able to guess which result you want. Omit only when the task has no question.]

## Method (optional)

[What to weigh, and what to report when evidence is thin or missing.]

## Out of scope

[What the agent must not touch or decide: the bibliography, the input data, any judgement you keep.]

## Output

[Where the result goes and what it is called. Use the task name `<prompt>-<subject>` and the run control command in `machine.md`. A forked subagent returns a `.md` report as text under `FILE: <path>`.]

## Acceptance criteria

[Each item can be checked from the files, without asking the agent.]

- [ ] ...
- [ ] The task ran end to end, and the report states what changed and what surprised you.
