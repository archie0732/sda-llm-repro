"""Loader for the paper's own public data (github.com/CKL9001/SDA-LLM, folder Dataset/).

What the release contains (checked 2026-09-30, commit of 2026-01-10):
- Type A, Office: 8 RGB views (1080x1080), LabelMe boxes per view with names that are
  already de-duplicated across views (e.g. 'whiteboard2' in views 2 and 3), object map
  coordinates (CSV, map metres), robot pose per view (ROS log text), 15 dialogues with the
  target name. Meeting room I has images/boxes but NO dialogue file.
- Type B (8 folders x 5 dialogues): 8 raw photos and, per turn, only the NUMBER of
  matching objects. No boxes, no ids, no target identity.

The repository has no licence file: use it for private research only, do not re-upload
the images. `scripts/fetch_visdial.sh` clones it into third_party/.
"""
from __future__ import annotations

import csv
import glob
import json
import math
import os
import re
from typing import Optional

import numpy as np
from PIL import Image

from .annotate import ViewBoxes, draw_view, make_grid
from .dialogue import GeoContext
from .prepare import PreparedScene
from .scene import Frame, Object3D
from .vlm import norm_name


def _class_of(name: str) -> str:
    return re.sub(r"[\d_\s]+$", "", name.lower())


def _yaw_from_ros_log(path: str) -> tuple[np.ndarray, float]:
    txt = json.load(open(path))
    pos = re.search(r"Position: x=([-\d.]+), y=([-\d.]+)", txt)
    ori = re.search(r"Orientation: x=([-\d.]+), y=([-\d.]+), z=([-\d.]+), w=([-\d.]+)", txt)
    x, y = float(pos.group(1)), float(pos.group(2))
    qz, qw = float(ori.group(3)), float(ori.group(4))
    return np.array([x, y]), math.degrees(2 * math.atan2(qz, qw)) % 360.0


def _tag_text(name: str) -> str:
    """'chair10' -> 'chair 10' (the style the paper's code draws)."""
    m = re.match(r"([a-zA-Z]+)[_\s]*(\d*)$", name)
    return f"{m.group(1)} {m.group(2)}".strip() if m else name


def load_type_a(scene_dir: str, max_side: int = 1080) -> PreparedScene:
    scene_id = "visdial_" + os.path.basename(os.path.normpath(scene_dir))
    # boxes per view
    views, seen, dup_views = [], {}, set()
    for p in sorted(glob.glob(os.path.join(scene_dir, "Object_Bounding_Box", "color_image_*.json")),
                    key=lambda q: int(re.findall(r"(\d+)\.json$", q)[0])):
        raw_bytes = open(p, "rb").read()
        v_id = int(re.findall(r"(\d+)\.json$", p)[0])
        if raw_bytes in seen:      # a copy of an earlier view's file (Office: color_image_3 == color_image_2)
            dup_views.add(v_id)
        seen.setdefault(raw_bytes, v_id)
        d = json.load(open(p))
        boxes = {}
        for sh in d["shapes"]:
            (x0, y0), (x1, y1) = sh["points"][:2]
            boxes[norm_name(sh["label"])] = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        views.append((int(re.findall(r"(\d+)\.json$", p)[0]), boxes, d.get("imageWidth"), d.get("imageHeight")))
    names = sorted({n for _, b, _, _ in views for n in b}, key=lambda n: (_class_of(n), int(re.sub(r"\D", "", n) or 0)))
    # map coordinates (some objects are missing from the CSV -> unknown position)
    coords = {}
    for r in csv.reader(open(os.path.join(scene_dir, "Object_coordinate_points.csv"), encoding="utf-8-sig")):
        if r and r[0] and r[0] != "Objects":
            coords[norm_name(r[0])] = (float(r[1]), float(r[2]))
    objects, name_map = [], {}
    for i, n in enumerate(names, start=1):
        xy = coords.get(n, (float("nan"), float("nan")))
        o = Object3D(uid=n, label=_class_of(n), center=np.array([xy[0], xy[1], 0.0]), size=np.zeros(3),
                     rotation=np.eye(3), obj_id=i, tag=_tag_text(n))
        objects.append(o)
        name_map[n] = i
    # robot poses (one per view)
    poses = [_yaw_from_ros_log(p) for p in sorted(glob.glob(os.path.join(scene_dir, "Robot_coordinate_points", "*.json")),
                                                     key=lambda q: int(os.path.basename(q)[:-5]))]
    station = np.mean([p for p, _ in poses], axis=0)
    heading0 = poses[0][1]
    heads = [((yaw - heading0) % 360.0) for _, yaw in poses]
    ctx = GeoContext(objects=objects, up_axis=2, station_xy=station, heading_deg=heading0)
    # images with the paper-style tags
    raw, annot = [], []
    tags = {o.obj_id: o.tag for o in objects}
    labels = {o.obj_id: o.label for o in objects}
    classes = sorted(set(labels.values()))
    class_only = {c: [] for c in classes}

    def fit(im):
        if max(im.size) <= max_side:
            return im
        s = max_side / max(im.size)
        return im.resize((int(im.width * s), int(im.height * s)))

    for v, boxes, w, h in views:
        img = Image.open(os.path.join(scene_dir, "RGB_image", f"color_image_{v}.jpg")).convert("RGB")
        f = Frame(frame_id=str(v), timestamp=float(v), pose=np.eye(4), K=np.eye(3), width=w or img.width,
                  height=h or img.height)
        vb = ViewBoxes(frame=f, boxes={name_map[n]: b for n, b in boxes.items()})
        annot.append(fit(draw_view(img, vb, labels, scale=img.width / f.width, tags=tags)))
        # C6 target_class_only: the authors' VLM.ipynb reads images that box only the target class
        # (label/chair/). A view whose box file duplicates an earlier view's gets no boxes at all.
        for c in classes:
            keep = {} if v in dup_views else {o: b for o, b in vb.boxes.items() if labels[o] == c}
            class_only[c].append(fit(draw_view(img, ViewBoxes(frame=f, boxes=keep), labels,
                                               scale=img.width / f.width, tags=tags)))
        raw.append(fit(img))
    # dialogues
    dialogues = []
    dfile = glob.glob(os.path.join(scene_dir, "*Multi-turn_dialogue.csv"))
    if dfile:
        rows = list(csv.reader(open(dfile[0], encoding="utf-8-sig")))
        for k, r in enumerate(rows[1:]):
            if not r or not r[0].startswith("Question"):
                continue
            target = name_map.get(norm_name(r[1]))
            turns = [t.strip() for t in r[2:] if t.strip()]
            if target is None or not turns:
                continue
            dialogues.append({"dialogue_id": f"{scene_id}-A{k}", "scene_id": scene_id, "dtype": "A", "target": target,
                              "turns": [{"text": t, "gt_set": [target], "kind": "human"} for t in turns]})
    return PreparedScene(scene_id, ctx, heads, raw, annot, make_grid(annot), dialogues, name_map=name_map,
                         class_only_annot=class_only)


def load_type_b(folder: str, max_side: int = 1280) -> dict:
    """Raw photos + dialogues with per-turn object counts (no ids are released for Type B)."""
    imgs = sorted([p for p in glob.glob(os.path.join(folder, "*")) if re.search(r"\.(jpe?g|png)$", p, re.I)],
                  key=lambda q: int(re.sub(r"\D", "", os.path.basename(q)) or 0))
    images = []
    for p in imgs:
        im = Image.open(p).convert("RGB")
        s = min(1.0, max_side / max(im.size))
        images.append(im.resize((int(im.width * s), int(im.height * s))))
    dfile = glob.glob(os.path.join(folder, "*Multi-turn_dialogue.csv"))[0]
    rows = list(csv.reader(open(dfile, encoding="utf-8-sig")))
    dialogues = []
    for k, r in enumerate(rows[1:]):
        if not r or not r[0].startswith("Question"):
            continue
        turns = []
        for j in range(1, len(r) - 1, 2):
            t, c = r[j].strip(), r[j + 1].strip()
            if t and c:
                turns.append({"text": t, "count": int(float(c))})
        if turns:
            dialogues.append({"dialogue_id": f"visdial_{os.path.basename(folder)}-B{k}", "turns": turns})
    return {"scene_id": "visdial_" + os.path.basename(folder), "images": images, "dialogues": dialogues}
