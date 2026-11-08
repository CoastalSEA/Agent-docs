# Subagent task template

Use this to define a reusable subagent, or to task a one-off subagent. Subagent format and options: https://code.claude.com/docs/en/sub-agents

A subagent has its own context window and sees only its system prompt and the task it is given, not this conversation. Everything it needs must be in the definition or the task.

## Part 1: define the subagent (reusable role)

Save as `.claude/agents/<name>.md` (one project) or `~/.claude/agents/<name>.md` (all projects). The body is the system prompt.

```markdown
---
name: <lower-case-name>
description: <What it does and when to use it, in one or two sentences. Add "Use proactively" to encourage automatic delegation.>
tools: <Read, Glob, Grep>
model: <sonnet | opus | haiku | inherit>
---

# Role
<One sentence: what this agent is for, and what it must not do.>

# Steps
1. <Concrete step, naming the input it reads.>
2. <...>

# Deliverable
<What it returns or saves, and where. Fix the file name.>

# Checks
- <What it verifies before it reports, and what it reports as MISSING instead of guessing.>
```

- `name` and `description` are required. Other fields are optional, and unrecognised fields are ignored without an error, so test the agent with a short invocation.
- Grant the fewest `tools` the role needs. If `tools` is omitted the agent inherits all of them. Read-only roles should not have `Write`, `Edit` or `Bash`.
- A subagent can start subagents of its own unless `Agent` is left out of `tools`. Leave it out unless the role needs it.

## Part 2: task the subagent

Write the task with the sections in `prompts/blank-prompt-template.md` (Task, Context, Inputs, Neutral framing, Acceptance criteria, Out of scope, Definition of done). Then:

- Pass the scope in the task text. The agent does not know what you were discussing.
- Include the instructions from the Subagents section of the global `CLAUDE.md` in the prompt.
- Invoke it by name in the request, with `@agent-<name>`, or let Claude choose from the `description`.

## Part 3: after the run

- Check every claim against the files the agent saved. Do not rely on its summary.
- Save any file it returned as text under `FILE: <path>`.
- If it was refused a write, do not work round it. Report it.
