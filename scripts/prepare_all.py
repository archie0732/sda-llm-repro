"""ARKitScenes raw folders -> data/prepared/<video_id>/ (views, annotated images, dialogues).

python scripts/prepare_all.py --csv data/selected_scenes.csv
"""
import argparse
import csv
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sdarepro.arkit import load_scene  # noqa: E402
from sdarepro.prepare import prepare_scene  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--root", default="data/arkitscenes")
ap.add_argument("--csv", default="data/selected_scenes.csv")
ap.add_argument("--out", default="data/prepared")
ap.add_argument("--dialogues_per_type", type=int, default=3)
ap.add_argument("--no_depth", action="store_true")
ap.add_argument("--egocentric", action="store_true", help="allow 'on your left' constraints (E7)")
a = ap.parse_args()

log = []
for r in csv.DictReader(open(a.csv)):
    vid = r["video_id"]
    dirs = [d for d in glob.glob(os.path.join(a.root, "**", vid), recursive=True) if os.path.isdir(d)]
    if not dirs:
        log.append({"video_id": vid, "status": "missing"}); continue
    try:
        scene = load_scene(dirs[0])
        ps = prepare_scene(scene, a.out, dialogues_per_type=a.dialogues_per_type, use_depth=not a.no_depth,
                           allow_egocentric=a.egocentric)
        status = "ok" if ps else "rejected"
        log.append({"video_id": vid, "status": status, "n_dialogues": len(ps.dialogues) if ps else 0})
    except Exception as e:  # keep going, record why
        log.append({"video_id": vid, "status": f"error: {e}"})
    print(log[-1])
json.dump(log, open(os.path.join(a.out, "prepare_log.json"), "w"), indent=1)
