"""ARKitScenes loader (3DOD layout or raw layout).

Expected files somewhere under `scene_dir` (found recursively, so both
`<id>/<id>_frames/...` (3dod) and `<id>/...` (raw) layouts work):
    <id>_3dod_annotation.json          oriented 3D boxes
    lowres_wide.traj                   camera trajectory
    vga_wide/<id>_<ts>.png             640x480 RGB   (raw asset, preferred for the VLM)
    vga_wide_intrinsics/<id>_<ts>.pincam
    lowres_wide/<id>_<ts>.png          256x192 RGB   (fallback)
    lowres_wide_intrinsics/<id>_<ts>.pincam
    lowres_depth/<id>_<ts>.png         256x192 depth, uint16 mm, aligned with lowres_wide

NOTE: this loader was written against the official parsing code
(threedod/benchmark_scripts/utils/tenFpsDataLoader.py) but could not be run on
real files in the environment where it was written. Milestone M1 in PLAN.md is
to verify it on one scene (projected boxes must sit on the objects).
"""
from __future__ import annotations

import bisect
import glob
import json
import os
from typing import Optional

import numpy as np

from .geometry import estimate_up_axis, image_rotation_cw, pincam_to_K, traj_line_to_pose, up_vector
from .scene import Frame, Object3D, Scene


def _find_one(root: str, pattern: str) -> Optional[str]:
    hits = sorted(glob.glob(os.path.join(root, "**", pattern), recursive=True))
    return hits[0] if hits else None


def _find_dir(root: str, name: str) -> Optional[str]:
    hits = [p for p in glob.glob(os.path.join(root, "**", name), recursive=True) if os.path.isdir(p)]
    return sorted(hits)[0] if hits else None


def _ts_from_name(path: str) -> float:
    return float(os.path.splitext(os.path.basename(path))[0].split("_")[-1])


def load_annotation(path: str) -> list[Object3D]:
    gt = json.load(open(path))
    objs = []
    for d in gt.get("data", []):
        seg = d["segments"]["obbAligned"]
        objs.append(Object3D(uid=str(d.get("uid", len(objs))), label=d["label"],
                             center=np.array(seg["centroid"], float).reshape(3),
                             size=np.array(seg["axesLengths"], float).reshape(3),
                             rotation=np.array(seg["normalizedAxes"], float).reshape(3, 3)))
    return objs


def load_traj(path: str) -> tuple[list[float], list[np.ndarray]]:
    ts, poses = [], []
    for line in open(path):
        if line.strip():
            t, p = traj_line_to_pose(line)
            ts.append(t)
            poses.append(p)
    order = np.argsort(ts)
    return [ts[i] for i in order], [poses[i] for i in order]


def _nearest(sorted_ts: list[float], t: float) -> tuple[int, float]:
    i = bisect.bisect_left(sorted_ts, t)
    best = min((j for j in (i - 1, i) if 0 <= j < len(sorted_ts)), key=lambda j: abs(sorted_ts[j] - t))
    return best, abs(sorted_ts[best] - t)


def load_scene(scene_dir: str, image_source: str = "vga_wide", max_pose_dt: float = 0.05,
               frame_stride: int = 5) -> Scene:
    video_id = os.path.basename(os.path.normpath(scene_dir))
    ann = _find_one(scene_dir, "*_3dod_annotation.json")
    traj = _find_one(scene_dir, "lowres_wide.traj")
    if ann is None or traj is None:
        raise FileNotFoundError(f"annotation or traj missing under {scene_dir}")
    objects = load_annotation(ann)
    tts, tposes = load_traj(traj)

    img_dir = _find_dir(scene_dir, image_source) or _find_dir(scene_dir, "lowres_wide")
    intr_dir = img_dir + "_intrinsics" if img_dir else None
    depth_dir = _find_dir(scene_dir, "lowres_depth")
    depth_intr_dir = _find_dir(scene_dir, "lowres_wide_intrinsics")
    depth_files = sorted(glob.glob(os.path.join(depth_dir, "*.png"))) if depth_dir else []
    depth_ts = [_ts_from_name(p) for p in depth_files]

    frames: list[Frame] = []
    imgs = sorted(glob.glob(os.path.join(img_dir, "*.png")))[::frame_stride]
    for p in imgs:
        t = _ts_from_name(p)
        j, dt = _nearest(tts, t)
        if dt > max_pose_dt:
            continue
        stem = os.path.splitext(os.path.basename(p))[0]
        pincam = os.path.join(intr_dir, stem + ".pincam")
        if not os.path.exists(pincam):
            continue
        w, h, K = pincam_to_K(np.loadtxt(pincam))
        f = Frame(frame_id=stem, timestamp=t, pose=tposes[j], K=K, width=w, height=h, image_path=p)
        if depth_files:
            k, ddt = _nearest(depth_ts, t)
            dstem = os.path.splitext(os.path.basename(depth_files[k]))[0]
            dpin = os.path.join(depth_intr_dir or "", dstem + ".pincam")
            if ddt <= max_pose_dt and os.path.exists(dpin):
                f.depth_path = depth_files[k]
                f.depth_K = pincam_to_K(np.loadtxt(dpin))[2]
        frames.append(f)

    poses = [f.pose for f in frames]
    up = estimate_up_axis(poses) if frames else 2
    rot = 0
    if frames and objects:
        rot = image_rotation_cw(poses, up_vector(poses, up, np.array([o.center for o in objects])))
    return Scene(scene_id=video_id, objects=objects, frames=frames, up_axis=up, image_rot_cw=rot,
                 meta={"annotation": ann, "image_source": os.path.basename(img_dir or "")})
