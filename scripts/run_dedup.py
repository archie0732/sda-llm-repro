"""Phase 2 (PLAN.md section 6): how much does cross-view de-duplication matter?

For each selected scene:
  1. re-load the ARKitScenes frames chosen during preparation (same 8 views)
  2. get per-view detections, from ground truth ('gt', isolates the de-dup step)
     or from YOLO ('yolo', like the paper; needs `pip install ultralytics`)
  3. back-project each box with depth and cluster with D1 (none) / D2 (geometric)
  4. report pairwise precision / recall / count error -> results/dedup.jsonl

python scripts/run_dedup.py --source gt --tau 0.5
python scripts/run_dedup.py --source yolo --tau 0.5
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sdarepro.annotate import load_depth_m  # noqa: E402
from sdarepro.arkit import load_scene  # noqa: E402
from sdarepro.dedup import (Detection, backproject, dedup_geometric, dedup_none,  # noqa: E402
                            evaluate_clusters, match_to_gt)

# COCO names from YOLO -> ARKitScenes labels (only classes that exist in both)
COCO2ARKIT = {"chair": "chair", "couch": "sofa", "dining table": "table", "bed": "bed", "toilet": "toilet",
              "tv": "tv_monitor", "refrigerator": "refrigerator", "oven": "oven", "sink": "sink"}

ap = argparse.ArgumentParser()
ap.add_argument("--root", default="data/arkitscenes")
ap.add_argument("--prepared", default="data/prepared")
ap.add_argument("--source", choices=["gt", "yolo"], default="gt")
ap.add_argument("--tau", type=float, default=0.5)
ap.add_argument("--yolo_weights", default="yolov8m.pt")
ap.add_argument("--out", default="results/dedup.jsonl")
a = ap.parse_args()

yolo = None
if a.source == "yolo":
    from ultralytics import YOLO
    yolo = YOLO(a.yolo_weights)

os.makedirs(os.path.dirname(a.out), exist_ok=True)
for meta_path in sorted(glob.glob(os.path.join(a.prepared, "*", "scene.json"))):
    meta = json.load(open(meta_path))
    vid = meta["scene_id"]
    dirs = [d for d in glob.glob(os.path.join(a.root, "**", vid), recursive=True) if os.path.isdir(d)]
    if not dirs:
        continue
    scene = load_scene(dirs[0], frame_stride=1)
    by_id = {f.frame_id: f for f in scene.frames}
    frames = [by_id[fid] for fid in meta["frame_ids"] if fid in by_id]
    labels = {o["obj_id"]: o["label"] for o in meta["objects"]}
    gt_boxes = [{int(k): tuple(v) for k, v in vb.items()} for vb in meta["view_boxes"]]
    dets = []
    for vi, f in enumerate(frames):
        depth = load_depth_m(f)
        if a.source == "gt":
            cand = [(labels[k], b, 1.0) for k, b in gt_boxes[vi].items()]
        else:
            res = yolo(f.image_path, verbose=False)[0]
            cand = []
            for xyxy, c, s in zip(res.boxes.xyxy.tolist(), res.boxes.cls.tolist(), res.boxes.conf.tolist()):
                name = COCO2ARKIT.get(res.names[int(c)])
                if name and s >= 0.35:
                    cand.append((name, tuple(xyxy), s))
        for lab, b, s in cand:
            d = Detection(view=vi, label=lab, box=b, score=s)
            d.world = backproject(d, f, depth)
            dets.append(d)
    match_to_gt(dets, gt_boxes, labels)
    for method, cl in (("none", dedup_none(dets)), ("geometric", dedup_geometric(dets, a.tau))):
        rec = {"scene_id": vid, "source": a.source, "method": method, "tau": a.tau, "n_dets": len(dets),
               **evaluate_clusters(dets, cl)}
        with open(a.out, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
        print(rec)
