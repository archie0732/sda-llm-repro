"""Run one condition with Claude over all prepared scenes (resumable).

python scripts/run_experiment.py --cond multi_image --model $SDA_MODEL
python scripts/run_experiment.py --cond active --model $SDA_MODEL --user_model $SDA_USER_MODEL
"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sdarepro.prepare import load_prepared  # noqa: E402
from sdarepro.runner import CONDITIONS, append_jsonl, done_ids, run_active, run_dialogue  # noqa: E402
from sdarepro.vlm import ClaudeClient  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--cond", required=True, choices=list(CONDITIONS) + ["active"])
ap.add_argument("--model", default=os.environ.get("SDA_MODEL"))
ap.add_argument("--user_model", default=os.environ.get("SDA_USER_MODEL"))
ap.add_argument("--prepared", default="data/prepared")
ap.add_argument("--out", default="results/raw")
ap.add_argument("--limit", type=int, default=0, help="max dialogues (0 = all)")
ap.add_argument("--dtype", choices=["A", "B", "both"], default="both")
a = ap.parse_args()

out = os.path.join(a.out, f"{a.cond}__{(a.model or 'model').replace('/', '_')}.jsonl")
done = done_ids(out)
robot = ClaudeClient(model=a.model)
user = ClaudeClient(model=a.user_model or a.model) if a.cond == "active" else None
n = 0
for d in sorted(glob.glob(os.path.join(a.prepared, "*", "scene.json"))):
    ps = load_prepared(os.path.dirname(d))
    for dlg in ps.dialogues:
        if a.dtype != "both" and dlg["dtype"] != a.dtype:
            continue
        if a.cond == "active" and dlg["dtype"] != "B":
            continue
        if (dlg["dialogue_id"], a.cond) in done:
            continue
        rec = run_active(robot, user, ps, dlg) if a.cond == "active" else run_dialogue(robot, a.cond, ps, dlg)
        append_jsonl(out, rec)
        n += 1
        print(rec["dialogue_id"], a.cond, "found" if rec["found"] else "miss")
        if a.limit and n >= a.limit:
            sys.exit(0)
