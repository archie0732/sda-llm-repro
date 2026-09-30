"""Turn a Scene into a 'prepared scene' folder used by every experiment.

data/prepared/<scene_id>/
    scene.json          objects (ids, labels, geometry), station, headings, visible ids
    view_<i>.jpg        raw view images
    view_<i>_annot.jpg  boxes + '#id' tags (oracle ids = perfect de-duplication)
    grid_annot.jpg      2x4 grid for condition C2
    dialogues.jsonl     generated Type A / Type B dialogues
"""
from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PIL import Image

from .annotate import (assign_ids, compute_view_boxes, make_grid, render_views, rotate_image_cw,
                       visible_object_ids)
from .dialogue import GeoContext, gen_type_a, gen_type_b
from .geometry import camera_yaw_deg
from .scene import Object3D, Scene
from .views import select_views


@dataclass
class PreparedScene:
    scene_id: str
    ctx: GeoContext
    view_headings_rel: list[float]
    images_raw: list[Image.Image]
    images_annot: list[Image.Image]
    grid_annot: Image.Image
    dialogues: list[dict]
    name_map: Optional[dict] = None   # drawn tag name -> obj_id, for name-style tags (VisDial)


def _obj_to_json(o: Object3D) -> dict:
    return {"obj_id": o.obj_id, "uid": o.uid, "label": o.label, "center": o.center.tolist(),
            "size": o.size.tolist(), "rotation": o.rotation.tolist()}


def _obj_from_json(d: dict) -> Object3D:
    return Object3D(uid=d["uid"], label=d["label"], center=np.array(d["center"]), size=np.array(d["size"]),
                    rotation=np.array(d["rotation"]), obj_id=d["obj_id"])


def prepare_scene(scene: Scene, out_root: str, n_bins: int = 8, min_coverage: int = 6,
                  dialogues_per_type: int = 3, seed: int = 0, use_depth: bool = True,
                  allow_egocentric: bool = False, labels_keep: Optional[set[str]] = None) -> Optional[PreparedScene]:
    """Returns None when the scene is unusable (poor heading coverage or no ambiguity)."""
    sel = select_views(scene, n_bins=n_bins)
    if sel.coverage < min_coverage:
        return None
    if labels_keep:
        scene.objects = [o for o in scene.objects if o.label in labels_keep]
    assign_ids(scene, sel.station_xy, sel.station_heading_deg)
    vbs = compute_view_boxes(scene.objects, sel.frames, use_depth=use_depth)
    vis = visible_object_ids(vbs)
    objects = [o for o in scene.objects if o.obj_id in vis]
    labels = {o.obj_id: o.label for o in objects}
    for vb in vbs:  # keep only boxes of the candidate universe
        vb.boxes = {k: v for k, v in vb.boxes.items() if k in vis}

    ctx = GeoContext(objects=objects, up_axis=scene.up_axis, station_xy=sel.station_xy,
                     heading_deg=sel.station_heading_deg)
    rng = random.Random(seed)
    dialogues = []
    ambiguous_targets = [o for o in objects if sum(p.label == o.label for p in objects) >= 2]
    rng.shuffle(ambiguous_targets)
    for dtype, gen in (("B", gen_type_b), ("A", gen_type_a)):
        n = 0
        for t in ambiguous_targets:
            if n >= dialogues_per_type:
                break
            d = gen(ctx, t, f"{scene.scene_id}-{dtype}{n}", scene.scene_id, rng, allow_egocentric=allow_egocentric)
            if d is not None:
                dialogues.append(d.to_json())
                n += 1
    if not dialogues:
        return None

    raw = []
    for f in sel.frames:
        im = (Image.open(f.image_path).convert("RGB") if f.image_path
              else Image.new("RGB", (f.width, f.height), (200, 200, 200)))
        raw.append(rotate_image_cw(im, scene.image_rot_cw))
    annot = render_views(vbs, labels, rot_cw=scene.image_rot_cw)
    grid = make_grid(annot)
    heads = [(camera_yaw_deg(f.pose, scene.up_axis) - sel.station_heading_deg) % 360.0 for f in sel.frames]

    d = os.path.join(out_root, scene.scene_id)
    os.makedirs(d, exist_ok=True)
    for i, (r, a) in enumerate(zip(raw, annot)):
        r.save(os.path.join(d, f"view_{i}.jpg"), quality=92)
        a.save(os.path.join(d, f"view_{i}_annot.jpg"), quality=92)
    grid.save(os.path.join(d, "grid_annot.jpg"), quality=92)
    meta = {"scene_id": scene.scene_id, "up_axis": scene.up_axis, "station_xy": sel.station_xy.tolist(),
            "heading_deg": sel.station_heading_deg, "view_headings_rel": heads,
            "frame_ids": [f.frame_id for f in sel.frames], "coverage": sel.coverage,
            # view_boxes below are in the ORIGINAL image coordinates; saved jpgs are rotated by this
            "image_rot_cw": scene.image_rot_cw,
            "objects": [_obj_to_json(o) for o in objects],
            "view_boxes": [{str(k): v for k, v in vb.boxes.items()} for vb in vbs]}
    json.dump(meta, open(os.path.join(d, "scene.json"), "w"), indent=1)
    with open(os.path.join(d, "dialogues.jsonl"), "w") as fh:
        for dl in dialogues:
            fh.write(json.dumps(dl) + "\n")
    return PreparedScene(scene.scene_id, ctx, heads, raw, annot, grid, dialogues)


def load_prepared(d: str) -> PreparedScene:
    meta = json.load(open(os.path.join(d, "scene.json")))
    objects = [_obj_from_json(o) for o in meta["objects"]]
    ctx = GeoContext(objects=objects, up_axis=meta["up_axis"], station_xy=np.array(meta["station_xy"]),
                     heading_deg=meta["heading_deg"])
    n = len(meta["view_headings_rel"])
    raw = [Image.open(os.path.join(d, f"view_{i}.jpg")).convert("RGB") for i in range(n)]
    annot = [Image.open(os.path.join(d, f"view_{i}_annot.jpg")).convert("RGB") for i in range(n)]
    grid = Image.open(os.path.join(d, "grid_annot.jpg")).convert("RGB")
    dls = [json.loads(l) for l in open(os.path.join(d, "dialogues.jsonl")) if l.strip()]
    return PreparedScene(meta["scene_id"], ctx, meta["view_headings_rel"], raw, annot, grid, dls)
