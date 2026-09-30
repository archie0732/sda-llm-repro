"""Phase 2 (PLAN.md section 6): how much does cross-view de-duplication matter?

For each selected scene:
  1. re-load the ARKitScenes frames chosen during preparation (same 8 views)
  2. get per-view detections, from ground truth ('gt', isolates the de-dup step)
     or from YOLO ('yolo', like the paper; needs `pip install ultralytics`)
  3. back-project each box with depth and cluster with D1 (none) / D2 (geometric, box-centre depth)
     / D2b (geometric_mask, median depth of the object's own depth pixels; gt source only)
  4. report pairwise precision / recall / count error -> results/dedup.jsonl

python scripts/run_dedup.py --source gt --tau 0.3 0.4 0.5 0.6 0.8
python scripts/run_dedup.py --source yolo --tau 0.5
"""
import argparse
import csv
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sdarepro.annotate import load_depth_m  # noqa: E402
from sdarepro.arkit import load_scene  # noqa: E402
from sdarepro.dedup import (Detection, backproject, dedup_geometric, dedup_none,  # noqa: E402
                            evaluate_clusters, match_to_gt)
from sdarepro.geometry import backproject_pixels, frame_object_pixels  # noqa: E402

# COCO names from YOLO -> ARKitScenes labels (only classes that exist in both)
COCO2ARKIT = {"chair": "chair", "couch": "sofa", "dining table": "table", "bed": "bed", "toilet": "toilet",
              "tv": "tv_monitor", "refrigerator": "refrigerator", "oven": "oven", "sink": "sink"}

ap = argparse.ArgumentParser()
ap.add_argument("--root", default="data/arkitscenes")
ap.add_argument("--prepared", default="data/prepared")
ap.add_argument("--source", choices=["gt", "yolo"], default="gt")
ap.add_argument("--tau", type=float, nargs="+", default=[0.5])
ap.add_argument("--yolo_weights", default="yolov8m.pt")
ap.add_argument("--out", default="results/dedup.jsonl")
ap.add_argument("--csv", default="data/selected_scenes.csv", help="only prepared scenes in this list")
a = ap.parse_args()
wanted = {r["video_id"] for r in csv.DictReader(open(a.csv))}

yolo = None
if a.source == "yolo":
    from ultralytics import YOLO
    yolo = YOLO(a.yolo_weights)

os.makedirs(os.path.dirname(a.out), exist_ok=True)
for meta_path in sorted(glob.glob(os.path.join(a.prepared, "*", "scene.json"))):
    meta = json.load(open(meta_path))
    vid = meta["scene_id"]
    if vid not in wanted:
        continue
    dirs =[d for d in glob.glob(os.path.join(a.root, "**", vid), recursive=True) if os.path.isdir(d)]
    if not dirs:
        continue
    scene = load_scene(dirs[0], frame_stride=1)
    by_id = {f.frame_id: f for f in scene.frames}
    frames = [by_id[fid] for fid in meta["frame_ids"] if fid in by_id]
    labels = {o["obj_id"]: o["label"] for o in meta["objects"]}
    # the overlap rule (PLAN.md 4.2 step 4) needs every annotated object, not only the visible ones
    ids = {o["uid"]: o["obj_id"] for o in meta["objects"]}
    for n, o in enumerate(scene.objects):
        o.obj_id = ids.get(o.uid, -1 - n)
    up = np.array(meta["up_vector"]) if meta.get("up_vector") else None
    gt_boxes = [{int(k): tuple(v) for k, v in vb.items()} for vb in meta["view_boxes"]]
    dets = []
    for vi, f in enumerate(frames):
        depth = load_depth_m(f)
        pix = (frame_object_pixels(scene.objects, f, depth, up, meta["floor_height"])
               if depth is not None and f.depth_K is not None and up is not None else None)
        if a.source == "gt":
            cand = [(labels[k], b, 1.0, k) for k, b in gt_boxes[vi].items()]
        else:
            res = yolo(f.image_path, verbose=False)[0]
            cand = []
            for xyxy, c, s in zip(res.boxes.xyxy.tolist(), res.boxes.cls.tolist(), res.boxes.conf.tolist()):
                name = COCO2ARKIT.get(res.names[int(c)])
                if name and s >= 0.35:
                    cand.append((name, tuple(xyxy), s, None))
        for lab, b, s, k in cand:
            d = Detection(view=vi, label=lab, box=b, score=s)
            d.world = backproject(d, f, depth)
            if k is not None and pix is not None:  # D2b: the object's own depth pixels (a perfect mask)
                d.world_mask = backproject_pixels(pix[k], f)
            dets.append(d)
    match_to_gt(dets, gt_boxes, labels)
    for tau in a.tau:
        runs = [("none", dedup_none(dets)), ("geometric", dedup_geometric(dets, tau))]
        if a.source == "gt":
            runs.append(("geometric_mask", dedup_geometric(dets, tau, point="world_mask")))
        for method, cl in runs:
            rec = {"scene_id": vid, "source": a.source, "method": method, "tau": tau, "n_dets": len(dets),
                   **evaluate_clusters(dets, cl)}
            with open(a.out, "a") as fh:
                fh.write(json.dumps(rec) + "\n")
            print(rec)
