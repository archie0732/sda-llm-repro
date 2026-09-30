"""Track V: the paper's own public data (PLAN.md section 5.0).

python scripts/run_visdial.py --track A --cond multi_image --limit 3     # pilot
python scripts/run_visdial.py --track A --cond text_only --rep 2          # second repeat
python scripts/run_visdial.py --track B --limit 3
python scripts/summarize_visdial.py                                       # tables + unstable items
"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sdarepro.runner import CONDITIONS, append_jsonl, done_ids, run_count_dialogue, run_dialogue  # noqa: E402
from sdarepro.vlm import ClaudeClient  # noqa: E402
from sdarepro.visdial import load_type_a, load_type_b  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--track", choices=["A", "B"], required=True)
ap.add_argument("--cond", choices=list(CONDITIONS), default="multi_image")
ap.add_argument("--model", default=os.environ.get("SDA_MODEL"))
ap.add_argument("--root", default="third_party/SDA-LLM/Dataset")
ap.add_argument("--out", default="results/raw_visdial")
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--rep", type=int, default=1, help="repeat number; each repeat has its own results file")
ap.add_argument("--save_images", action="store_true", help="write annotated Type A views to results/visdial_check/")
ap.add_argument("--images_only", action="store_true", help="with --save_images: save and exit, no API calls")
a = ap.parse_args()

cond = a.cond if a.track == "A" else "count"
out = os.path.join(a.out, f"track{a.track}_{cond}__{(a.model or 'model').replace('/', '_')}__r{a.rep}.jsonl")
done, n = done_ids(out), 0
if a.track == "A":
    ps = load_type_a(os.path.join(a.root, "Type_A_Dataset", "Office"))
    if a.save_images:
        os.makedirs("results/visdial_check", exist_ok=True)
        for i, im in enumerate(ps.images_annot):
            im.save(f"results/visdial_check/office_view_{i}.jpg")
    jobs = [(ps, d) for d in ps.dialogues]
else:
    folders = sorted(os.path.dirname(p) for p in glob.glob(os.path.join(a.root, "Type_B_Dataset", "**", "*Multi-turn_dialogue.csv"), recursive=True))
    jobs = [(b, d) for f in folders for b in [load_type_b(f)] for d in b["dialogues"]]
if a.images_only:
    sys.exit(0)
client = ClaudeClient(model=a.model)
for scene, dlg in jobs:
    if (dlg["dialogue_id"], cond) in done:
        continue
    rec = run_dialogue(client, cond, scene, dlg) if a.track == "A" else run_count_dialogue(client, scene, dlg)
    rec["rep"] = a.rep
    append_jsonl(out, rec)
    n += 1
    print(rec["dialogue_id"], cond, "found" if rec["found"] else "miss")
    if a.limit and n >= a.limit:
        break
