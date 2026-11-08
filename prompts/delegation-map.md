# Delegation map

Fill this in before handing a task to a subagent or running it unattended. Then pick one outcome.

## The task

What decision does this task support?

## Triage

| Question | Low | Medium | High |
|---|---|---|---|
| Consequence if wrong |  |  |  |
| Difficulty of detecting an error |  |  |  |
| Difficulty of reversing the action |  |  |  |
| Data sensitivity |  |  |  |

Any task that edits input data or a bibliography entry, or sends data off this machine, is High and stays under direct control (Hard boundaries in the global `CLAUDE.md`).

## Decision

Choose one:

- **Speed up with a spot check.** Run it, then check a sample against the files.
- **Delegate inside a supervised workflow.** Write the prompt (`prompts/blank-prompt-template.md`, or `agents/subagent-task-template.md` for a subagent). The output stays a pending run until you accept, reject or discard it.
- **Keep under direct human control.** Claude drafts or advises; you decide and act.

## Human checkpoint

What must a person decide before the workflow continues?

## Evidence

What evidence would make you reject the output? Write it into the prompt as acceptance criteria.
