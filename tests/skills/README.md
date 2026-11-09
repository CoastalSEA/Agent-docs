# Skill fixtures

`run_fixtures.py` runs a skill on a small synthetic project with a known correct answer, using a fresh headless Claude Code session (`claude -p`), and checks what the session produced. It makes model calls, so it is run by hand and never from CI or the unit tests.

```
python tests/skills/run_fixtures.py [skill ...] [--list] [--keep] [--timeout SECONDS] [--permission-mode MODE]
                                    [--estuary-doc PATH] [--test-library PATH] [--external]
```

| Fixture | Planted facts | Checks |
|---|---|---|
| `project-disclosure` | Three sessions with known dates, two models, an auto-to-default permission change, a secret in a prompt, a refused write, a subagent log, a decoy session in a sibling folder | The disclosure is the only file written; every fixture session is found and the decoy is left out; models and modes are reported as logged; the subagent mode is `MISSING`; the secret is redacted; the refused write is marked attempted; the subfolder is in the scope; no claim about human oversight; the run is reported pending; the project files are unchanged |
| `analysis-adversary` | A decay fit whose script uses `log10`, so the reported rate is 0.130 when the data give 0.30 | A report is saved; it gives about 0.30; it says 0.130 does not reproduce; it names the logarithm base; the script under review was not run; the project files are unchanged |
| `proofread` | The user's own `.doc` (a prose paragraph and a poem) converted with Word, with six faults planted in the paragraph: three misspellings, one American spelling, two subject-verb errors | The copy `<name> - proofread.docx` is saved beside the original; the original is unchanged; rejecting all tracked changes restores the planted text exactly; each fault is corrected; every revision is by Claude; nothing changes outside the first paragraph; at most 5 comments of at most 50 words; the reply says citations are not checked; Word opens the copy |
| `citation-check` | A generated `.docx` with four EndNote cite-while-write fields against a test library: one correct, one stale rec-number, one wrong year, one invented reference | The report is saved; the invented reference is unresolved; the year difference and the stale rec-number are reported; the correct reference is not a problem; no external call was made; external verification is reported as not done; manuscript, library and project are unchanged |
| `literature-search` | The test library only, no external source; a question that two library records answer | The report is saved; the derived terms are reported; the two matching records are in the candidate list and records that cannot match are not; local-PDF availability is reported; the report says no external source was queried; no external call was made; the library and project are unchanged; the run is reported pending |
| `literature-search-external` | OpenAlex only, with an import list (run only with `--external`, because it sends the query to OpenAlex) | The report gives OpenAlex with a hit count; at least 5 candidates (table rows or numbered sections), each with a year and a peer-reviewed, grey or explicitly unclear label (the skill must not assume a status, so an honest 'unclear' passes); no DOI twice; the `.ris` file is well formed and has one record per row; no `mailto` and no other service; the library and project are unchanged |

- `proofread` needs Microsoft Word and the source document (`--estuary-doc`, default `working_docs/Estuary Notes.doc`); `citation-check` and the two `literature-search` fixtures need a test EndNote library (`--test-library`, or the environment variable `FIXTURE_ENDNOTE_LIBRARY`). Neither source is in the repository. A fixture whose source is missing is skipped, and a skip is not a failure. The test library is served to the session through `--mcp-config` with `--strict-mcp-config`, so the session reads it and not the library registered for normal work.
- The sessions run in `auto` mode, as in interactive use. A headless session in the default mode cannot get approval for run control or Python commands, and the skills then stop at their first step.
- Each run uses the live configuration: the installed skills, the run control script and `machine.md`. It tests what is deployed.
- The `project-disclosure` fixture writes synthetic session logs into `~/.claude/projects/` and removes them afterwards.
- Results go to `working_docs/skill-runs/<skill>-<DDMMYY-HHMM>/` (git-ignored): `reply.txt`, the saved deliverable and `checks.json`.
- The checks look for planted facts and for things that must not happen. They do not compare wording, so a changed skill is judged by whether it still finds what it should.
- `tests/test_skill_fixtures.py` tests the fixtures and checks without a model: the planted fault is in the data, each check passes on a good result and fails on a result with the planted problem.
