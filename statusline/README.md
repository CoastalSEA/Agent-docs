# statusline

Statusline scripts for Claude Code's terminal status bar. Source of truth for
`~/.claude/statusline-command.sh`, which is deployed to user level. Back up the live
file to `~/.claude/backups/` before copying, then confirm the two copies are identical
with `diff`.

## statusline-command.sh

Prints one line: model, context usage bar, session (5 hour) usage %, week (7 day)
usage %, and a spend slot. The spend slot shows the spend limit % when Claude Code
supplies it, otherwise the estimated session cost in USD. Absent values show as `--`.
Claude Code supplies no extra usage credit balance, so none is shown. See
`records/DECISIONS.md` (rows dated 210926) for the reasons.
