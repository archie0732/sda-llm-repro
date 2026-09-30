"""Core data structures shared by every module.

Conventions (see PLAN.md section "Coordinate conventions"):
- World frame: metric, gravity aligned. `up_axis` (0, 1 or 2) says which world axis points up.
- Camera frame: OpenCV style (x right, y down, z forward).
- `Frame.pose` is a 4x4 camera-to-world matrix.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class Object3D:
    """One annotated object (an oriented 3D box)."""

    uid: str                 # id from the dataset annotation
    label: str               # class name, e.g. "chair"
    center: np.ndarray       # (3,) world coordinates, metres
    size: np.ndarray         # (3,) full box extents along the box axes, metres
    rotation: np.ndarray     # (3, 3) ARKitScenes `normalizedAxes`: ROWS are the box axes in world frame
                             # (same as the official box_utils.compute_box_3d; checked on real data in M1)
    obj_id: int = -1         # short numeric id shown to the model ("#3"); assigned later
    tag: Optional[str] = None  # drawn tag text if not "#<obj_id>" (e.g. VisDial style "chair 3")

    def corners(self) -> np.ndarray:
        """Return the 8 box corners in world coordinates, shape (8, 3)."""
        half = self.size / 2.0
        signs = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], dtype=float)
        local = signs * half
        return local @ self.rotation + self.center


@dataclass
class Frame:
    """One RGB(-D) frame with calibration."""

    frame_id: str
    timestamp: float
    pose: np.ndarray                 # (4, 4) camera-to-world
    K: np.ndarray                    # (3, 3) intrinsics for `image_path` resolution
    width: int
    height: int
    image_path: Optional[str] = None
    depth_path: Optional[str] = None  # uint16 millimetres, may have another resolution
    depth_K: Optional[np.ndarray] = None


@dataclass
class Scene:
    scene_id: str
    objects: list[Object3D]
    frames: list[Frame]
    up_axis: int = 2
    image_rot_cw: int = 0            # degrees clockwise that make the images upright (display only)
    meta: dict = field(default_factory=dict)

    def by_id(self, obj_id: int) -> Object3D:
        for o in self.objects:
            if o.obj_id == obj_id:
                return o
        raise KeyError(obj_id)
