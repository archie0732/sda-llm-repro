"""Live Track V dialogue in the terminal, the way the authors' Code/VLM.ipynb runs it (PLAN.md 5.0).

All rules, the JSONL format, resuming and scoring are in src/sdarepro/live.py, shared with the web page
(scripts/live_web.py). Records go to results/raw_visdial/live__<model>__r<rep>.jsonl.

python scripts/live_dialogue.py --dry_run                     # dry-run model and scripted typing, no API
python scripts/live_dialogue.py --only A1 A11                 # real run (needs SDA_API_KEY, SDA_MODEL)
"""
import argparse
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sdarepro.live import drive_terminal, experiment_session, question_id, read_records, summary, translated_targets  # noqa: E402
from sdarepro.visdial import load_type_a  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--model", default=os.environ.get("SDA_MODEL"))
ap.add_argument("--rep", type=int, default=1)
ap.add_argument("--root", default="third_party/SDA-LLM/Dataset")
ap.add_argument("--out", default=None, help="default results/raw_visdial, or a temp folder with --dry_run")
ap.add_argument("--targets", default="results/visdial_target_fix.json", help="A11-A14 in our labels (PLAN.md 5.0)")
ap.add_argument("--only", nargs="*", help="question ids, e.g. A1 A11")
ap.add_argument("--max_round", type=int, default=10, help="stop after the round whose counter exceeds this (authors: 10)")
ap.add_argument("--dry_run", action="store_true", help="dry-run model and scripted typing, output in a temp folder")
a = ap.parse_args()

ps = load_type_a(os.path.join(a.root, "Type_A_Dataset", "Office"))
targets = translated_targets(a.targets, ps.name_map)
dialogues = [d for d in ps.dialogues if not a.only or question_id(d) in a.only]

if a.dry_run:
    out_dir, model, client = a.out or tempfile.mkdtemp(prefix="live_dry_"), "dry_run", None
    typed = {"A1": ["the chair on the right of the lamp"], "A11": ["the board in view 2", "ee"]}
    dialogues = [d for d in dialogues if question_id(d) in typed]
else:
    if not a.model:
        sys.exit("set SDA_MODEL (CLAUDE.md rule 5)")
    from sdarepro.vlm import ClaudeClient
    out_dir, model, client = a.out or "results/raw_visdial", a.model, ClaudeClient(model=a.model)
out = os.path.join(out_dir, f"live__{model.replace('/', '_')}__r{a.rep}.jsonl")

for dlg in dialogues:
    q = question_id(dlg)
    s = experiment_session(ps, dlg, out, model, a.rep, targets, client=client, dry_run=a.dry_run, max_round=a.max_round)
    if s.ended:
        print(f"{q} already finished, skipped")
        continue
    print(f"\n=== {q} ({s.tag[dlg['target']]} in the answer file, {len(dlg['turns'])} sentence(s) there)")
    if a.dry_run:
        it = iter(typed[q])
        ask = lambda prompt: (lambda t: (print(prompt + t), t)[1])(next(it))   # noqa: E731
    else:
        ask = input
    drive_terminal(s, ask)

r = summary(read_records(out))
if r["finished"]:
    print(f"\n{r['finished']} finished: found {r['found']:.3f}, mean rounds {r['mean_rounds']:.2f}, "
          f"T_A (k = answer-file length) {r['T_A_kcsv']:.3f}")
print("records:", out)
