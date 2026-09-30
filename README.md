# sda-llm-repro

A small-scale re-examination of **SDA-LLM** (*Spatial DisAmbiguation via Multi-turn Vision-Language Dialogues for Robot Navigation*, IROS 2025, arXiv 2410.12802) on the public **ARKitScenes** dataset, using Claude as the vision-language model.

The paper resolves "go to the chair" when there are many chairs: a robot takes 8 photos (one per 45°), tags every object with an ID, and a VLM narrows the candidates over a multi-turn dialogue. This repo re-runs that second stage and adds the controls the paper does not report:

| Question | Experiment |
| --- | --- |
| Do the images help, or is an object list with coordinates enough? | text-only baseline (E3, E3b) |
| Is "only GPT-4o can take multiple images" still true? Does a stitched grid hurt? | multi-image vs grid (E1, E2, E5) |
| Can the robot ask its own clarifying questions and finish in fewer turns? | active questioning with a simulated user (E6) |
| What happens when cross-view de-duplication is imperfect? | Phase 2 (D0–D3) |

Track V first re-runs the authors' own public data ([CKL9001/SDA-LLM](https://github.com/CKL9001/SDA-LLM), fetched into `third_party/`, never re-uploaded here). Track R then uses ARKitScenes for larger, automatically generated dialogues with ground-truth candidate sets.

The full plan (in Traditional Chinese) is in [PLAN.md](PLAN.md). Instructions for coding agents are in [CLAUDE.md](CLAUDE.md).

## Quick start

```bash
pip install -e ".[dev]"
bash scripts/fetch_visdial.sh  # authors' release (private research use)
pytest -q                      # 20 tests (synthetic room + authors' release)
python scripts/dry_run.py      # end-to-end without data or API key

export SDA_API_KEY=...         # never commit it; not ANTHROPIC_API_KEY (breaks Claude Code Remote Control)
python -m sdarepro.vlm --list  # pick a model id
export SDA_MODEL=<model id>

bash scripts/download_arkit.sh annotations
python scripts/select_scenes.py --n 40
bash scripts/download_arkit.sh frames data/selected_scenes.csv
python scripts/prepare_all.py
python scripts/run_experiment.py --cond multi_image --limit 5   # always pilot first
python scripts/summarize.py
```

## Status

Core logic is implemented and unit-tested. The loader for the authors' release is tested on the real files. The ARKitScenes path has **not** yet been run on real files; milestone M1 in PLAN.md is that check. No model calls have been made yet.

## Credits

SDA-LLM is by K.-L. Chen, T.-T. Wei, L.-T. Yeh, E. Kao, Y.-C. Tseng and J.-J. Chen (NYCU). ARKitScenes is by Apple (non-commercial research license). This repository is an independent student re-examination and is not affiliated with either.
