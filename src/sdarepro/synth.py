"""A small synthetic room used by the unit tests and by `scripts/dry_run.py`.

z is up. The 'robot' stands at the origin; the camera spins in place at 1.3 m.
"""
from __future__ import annotations

import math

import numpy as np

from .scene import Frame, Object3D, Scene

K640 = np.array([[500.0, 0, 320], [0, 500.0, 240], [0, 0, 1]])


def camera_pose(pos, yaw_deg: float) -> np.ndarray:
    y = math.radians(yaw_deg)
    fwd = np.array([math.cos(y), math.sin(y), 0.0])
    down = np.array([0.0, 0.0, -1.0])
    right = np.cross(down, fwd)
    P = np.eye(4)
    P[:3, 0], P[:3, 1], P[:3, 2], P[:3, 3] = right, down, fwd, pos
    return P


def box(uid, label, x, y, w, d, h) -> Object3D:
    return Object3D(uid=uid, label=label, center=np.array([x, y, h / 2]), size=np.array([w, d, h]),
                    rotation=np.eye(3))


def synthetic_room(step_deg: float = 5.0, jitter: float = 0.05, seed: int = 0) -> Scene:
    rng = np.random.default_rng(seed)
    objs = [
        box("t", "table", 2.6, 0.0, 1.2, 0.8, 0.75),
        box("c1", "chair", 1.8, 0.45, 0.45, 0.45, 0.9),
        box("c2", "chair", 1.8, -0.55, 0.45, 0.45, 0.9),
        box("c3", "chair", 3.4, 0.2, 0.45, 0.45, 0.9),
        box("c4", "chair", -1.2, 2.6, 0.5, 0.5, 1.25),
        box("c5", "chair", 0.2, -2.9, 0.45, 0.45, 0.9),
        box("s", "sofa", -2.4, 1.8, 2.0, 0.9, 0.8),
        box("f", "refrigerator", 0.0, -3.6, 0.8, 0.7, 1.8),
        box("tv", "tv_monitor", -3.2, -1.0, 0.1, 1.2, 0.7),
    ]
    frames = []
    for i, yaw in enumerate(np.arange(0, 360, step_deg)):
        pos = np.array([rng.normal(0, jitter), rng.normal(0, jitter), 1.3])
        frames.append(Frame(frame_id=f"f{i:03d}", timestamp=float(i), pose=camera_pose(pos, float(yaw)),
                            K=K640.copy(), width=640, height=480))
    return Scene(scene_id="synth0", objects=objs, frames=frames, up_axis=2)
