# Working rules for Claude in this repo

1. PLAN.md is the source of truth for experiment definitions, thresholds and metrics. If you change any of them, update PLAN.md in the same commit and say why.
2. Work milestone by milestone (PLAN.md section 10), starting with M0 then M0.5 (Track V). Do not start the next one until the acceptance check of the current one passes, and write the outcome in `results/LOG.md` (date, what was run, numbers, problems).
3. Run `pytest -q` before every commit. Add a test for every bug you fix.
4. API cost guard: every new condition or model is first run with `--limit 5`. Report the actual token usage before running the full set. Never loop over paid calls without the resumable `done_ids` check.
5. Never hard-code a model id. Use `SDA_MODEL` / `SDA_USER_MODEL` and record the exact ids in `results/LOG.md`.
6. Never commit `data/`, `third_party/`, API keys or dataset images. The authors' release (third_party/SDA-LLM) has no licence file: never copy its images into the repo or any public page. Small result JSONL files and summaries are fine.
7. Milestone M1 needs a human look: save the annotated images of one scene to `results/m1_check/` and ask the user to confirm the boxes sit on the objects before continuing.
8. Report honestly. If a result contradicts the hypotheses in PLAN.md section 1, keep it and say so. Do not tune prompts per condition to make one condition win; all prompt text lives in `src/sdarepro/prompts.py` and is shared.
9. The user writes Chinese documents without semicolons and without "label: text" style headings. Follow that in any Chinese text you add.
10. The experiment API key lives in `SDA_API_KEY`, never in `ANTHROPIC_API_KEY`: that variable would switch Claude Code itself to API-key auth and turn off Remote Control. Never print the key.
