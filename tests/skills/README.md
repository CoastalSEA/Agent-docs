# Skill fixtures

`run_fixtures.py` runs a skill on a small synthetic project with a known correct answer, using a fresh headless Claude Code session (`claude -p`), and checks what the session produced. It makes model calls, so it is run by hand and never from CI or the unit tests.

```
python tests/skills/run_fixtures.py [skill ...] [--list] [--keep] [--timeout SECONDS] [--permission-mode MODE]
```

| Fixture | Planted facts | Checks |
|---|---|---|
| `project-disclosure` | Three sessions with known dates, two models, an auto-to-default permission change, a secret in a prompt, a refused write, a subagent log, a decoy session in a sibling folder | The disclosure is the only file written; every fixture session is found and the decoy is left out; models and modes are reported as logged; the subagent mode is `MISSING`; the secret is redacted; the refused write is marked attempted; the subfolder is in the scope; no claim about human oversight; the run is reported pending; the project files are unchanged |
| `analysis-adversary` | A decay fit whose script uses `log10`, so the reported rate is 0.130 when the data give 0.30 | A report is saved; it gives about 0.30; it says 0.130 does not reproduce; it names the logarithm base; the script under review was not run; the project files are unchanged |

- The sessions run in `auto` mode, as in interactive use. A headless session in the default mode cannot get approval for run control or Python commands, and the skills then stop at their first step.
- Each run uses the live configuration: the installed skills, the run control script and `machine.md`. It tests what is deployed.
- The `project-disclosure` fixture writes synthetic session logs into `~/.claude/projects/` and removes them afterwards.
- Results go to `working_docs/skill-runs/<skill>-<DDMMYY-HHMM>/` (git-ignored): `reply.txt`, the saved deliverable and `checks.json`.
- The checks look for planted facts and for things that must not happen. They do not compare wording, so a changed skill is judged by whether it still finds what it should.
- `tests/test_skill_fixtures.py` tests the fixtures and checks without a model: the planted fault is in the data, each check passes on a good result and fails on a result with the planted problem.
