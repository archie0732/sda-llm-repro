"""Phase 2: cross-view de-duplication (the step the paper does not describe).

A detection is one box in one view. De-duplication decides which detections
are the same physical object, i.e. which share an ID across the 8 views.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Optional

import numpy as np

from .scene import Frame


@dataclass
class Detection:
    view: int
    label: str
    box: tuple[float, float, float, float]   # pixels in the view image
    score: float = 1.0
    gt_obj: Optional[int] = None             # filled by `match_to_gt` for evaluation
    world: Optional[np.ndarray] = None       # filled by `backproject`


def iou(a, b) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def backproject(det: Detection, frame: Frame, depth_m: np.ndarray, inner: float = 0.4) -> Optional[np.ndarray]:
    """World point of the box centre using the median depth of the inner part of the box."""
    if depth_m is None or frame.depth_K is None:
        return None
    sx = depth_m.shape[1] / frame.width
    sy = depth_m.shape[0] / frame.height
    x0, y0, x1, y1 = det.box
    cx, cy, w, h = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) * inner, (y1 - y0) * inner
    u0, u1 = int((cx - w / 2) * sx), int((cx + w / 2) * sx) + 1
    v0, v1 = int((cy - h / 2) * sy), int((cy + h / 2) * sy) + 1
    patch = depth_m[max(0, v0):v1, max(0, u0):u1]
    patch = patch[patch > 0]
    if patch.size == 0:
        return None
    z = float(np.median(patch))
    Kd = frame.depth_K
    u, v = cx * sx, cy * sy
    cam = np.array([(u - Kd[0, 2]) * z / Kd[0, 0], (v - Kd[1, 2]) * z / Kd[1, 1], z, 1.0])
    return (frame.pose @ cam)[:3]


def dedup_none(dets: list[Detection]) -> list[int]:
    """Baseline D1: every detection is its own object (what happens without de-duplication)."""
    return list(range(len(dets)))


def dedup_geometric(dets: list[Detection], tau: float = 0.5) -> list[int]:
    """D2: union-find over same-label detections whose 3D points are closer than `tau` metres."""
    parent = list(range(len(dets)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j in combinations(range(len(dets)), 2):
        a, b = dets[i], dets[j]
        if a.label != b.label or a.world is None or b.world is None or a.view == b.view:
            continue
        if np.linalg.norm(a.world - b.world) < tau:
            parent[find(i)] = find(j)
    roots = [find(i) for i in range(len(dets))]
    remap = {r: k for k, r in enumerate(dict.fromkeys(roots))}
    return [remap[r] for r in roots]


def evaluate_clusters(dets: list[Detection], cluster: list[int]) -> dict:
    """Pairwise precision / recall of 'same object' links against ground truth, plus count error."""
    idx = [i for i, d in enumerate(dets) if d.gt_obj is not None]
    tp = fp = fn = 0
    for i, j in combinations(idx, 2):
        same_pred = cluster[i] == cluster[j]
        same_gt = dets[i].gt_obj == dets[j].gt_obj
        tp += same_pred and same_gt
        fp += same_pred and not same_gt
        fn += (not same_pred) and same_gt
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    n_pred = len(set(cluster[i] for i in idx))
    n_gt = len(set(dets[i].gt_obj for i in idx))
    return {"precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0,
            "n_pred_objects": n_pred, "n_gt_objects": n_gt, "count_error": n_pred - n_gt}


def match_to_gt(dets: list[Detection], gt_boxes_per_view: list[dict[int, tuple]], labels: dict[int, str],
                thr: float = 0.5) -> None:
    for d in dets:
        best, best_iou = None, thr
        for oid, b in gt_boxes_per_view[d.view].items():
            if labels.get(oid) != d.label:
                continue
            v = iou(d.box, b)
            if v >= best_iou:
                best, best_iou = oid, v
        d.gt_obj = best
