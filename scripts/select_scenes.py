"""Pick scenes that can produce ambiguous references (PLAN.md 3.3).

Keeps a video when one target class (chair, stool, table, sofa) has >= MIN_SAME
instances (e.g. 3 chairs) and the scene has >= MIN_LANDMARKS classes that occur
exactly once (landmarks such as 'the fridge'). Ranks by the largest target-class
count, then the total target instances, then landmarks. Keeps one video per visit
(the same room recorded twice gives results that are not independent). A video in
--prefer takes its visit's place, e.g. one that is already downloaded.
Writes data/selected_scenes.csv for download_arkit.sh frames.

python scripts/select_scenes.py --n 40
"""
import argparse
import collections
import csv
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sdarepro.dialogue import TARGET_CLASSES  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--root", default="data/arkitscenes")
ap.add_argument("--metadata", default="data/arkitscenes/raw/metadata.csv")
ap.add_argument("--out", default="data/selected_scenes.csv")
ap.add_argument("--n", type=int, default=40)
ap.add_argument("--min_same", type=int, default=3)
ap.add_argument("--min_landmarks", type=int, default=2)
ap.add_argument("--target_classes", default=",".join(TARGET_CLASSES))
ap.add_argument("--prefer", default="42898849",
                help="comma-separated video ids that win their visit (already downloaded, PLAN.md 3.3)")
a = ap.parse_args()
prefer = set(filter(None, a.prefer.split(",")))
targets = a.target_classes.split(",")
visit_of = {r["video_id"]: r["visit_id"] for r in csv.DictReader(open(a.metadata))}

rows = []
for p in glob.glob(os.path.join(a.root, "**", "*_3dod_annotation.json"), recursive=True):
    vid = os.path.basename(p).split("_")[0]
    labels = [d["label"] for d in json.load(open(p)).get("data", [])]
    c = collections.Counter(labels)
    tc = {k: c[k] for k in targets if c[k]}
    if not tc:
        continue
    top = max(tc, key=lambda k: (tc[k], -targets.index(k)))
    landmarks = sum(1 for v in c.values() if v == 1)
    if tc[top] >= a.min_same and landmarks >= a.min_landmarks:
        rows.append({"video_id": vid, "visit_id": visit_of.get(vid, "NA"), "max_same": tc[top],
                     "n_target": sum(tc.values()), "landmarks": landmarks, "top_class": top,
                     "n_objects": len(labels), "target_counts": " ".join(f"{k}={v}" for k, v in tc.items())})
rows.sort(key=lambda r: (-r["max_same"], -r["n_target"], -r["landmarks"], r["video_id"]))

kept, seen = [], set()
for r in rows:
    v = r["visit_id"]
    if v != "NA" and v in seen:
        continue
    alt = [q for q in rows if q["visit_id"] == v and q["video_id"] in prefer] if v != "NA" else []
    seen.add(v)
    kept.append(alt[0] if alt else r)  # the visit keeps r's rank, the preferred video stands in for it
os.makedirs(os.path.dirname(a.out), exist_ok=True)
cols = ["video_id", "fold", "visit_id", "max_same", "top_class", "n_target", "target_counts", "landmarks", "n_objects"]
with open(a.out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for r in kept[: a.n]:
        w.writerow({**{k: r[k] for k in cols if k != "fold"}, "fold": "Validation"})
print(f"{len(rows)} videos pass, {len(kept)} after one per visit, wrote {min(len(kept), a.n)} to {a.out}")
