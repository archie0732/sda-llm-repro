"""Pick scenes that can produce ambiguous references.

Keeps a video when some class has >= MIN_SAME instances (e.g. 3 chairs) and the
scene has >= MIN_LANDMARKS other classes that occur exactly once (landmarks such
as 'the sofa'). Writes data/selected_scenes.csv for download_arkit.sh frames.

python scripts/select_scenes.py --n 40
"""
import argparse
import collections
import csv
import glob
import json
import os

ap = argparse.ArgumentParser()
ap.add_argument("--root", default="data/arkitscenes")
ap.add_argument("--out", default="data/selected_scenes.csv")
ap.add_argument("--n", type=int, default=40)
ap.add_argument("--min_same", type=int, default=3)
ap.add_argument("--min_landmarks", type=int, default=2)
a = ap.parse_args()

rows = []
for p in glob.glob(os.path.join(a.root, "**", "*_3dod_annotation.json"), recursive=True):
    vid = os.path.basename(p).split("_")[0]
    labels = [d["label"] for d in json.load(open(p)).get("data", [])]
    c = collections.Counter(labels)
    same = max(c.values()) if c else 0
    landmarks = sum(1 for v in c.values() if v == 1)
    if same >= a.min_same and landmarks >= a.min_landmarks:
        top = c.most_common(1)[0][0]
        rows.append((same, landmarks, vid, top, len(labels)))
rows.sort(reverse=True)
os.makedirs(os.path.dirname(a.out), exist_ok=True)
with open(a.out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["video_id", "fold", "max_same", "landmarks", "top_class", "n_objects"])
    for same, lm, vid, top, n in rows[: a.n]:
        w.writerow([vid, "Validation", same, lm, top, n])
print(f"{len(rows)} usable scenes, wrote {min(len(rows), a.n)} to {a.out}")
