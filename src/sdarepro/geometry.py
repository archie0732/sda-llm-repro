"""Camera geometry helpers: poses, projection, floor-plane coordinates."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .scene import Frame, Object3D


def axis_angle_to_matrix(v: np.ndarray) -> np.ndarray:
    """Rodrigues formula. `v` is an axis-angle vector in radians."""
    v = np.asarray(v, dtype=float)
    theta = float(np.linalg.norm(v))
    if theta < 1e-12:
        return np.eye(3)
    k = v / theta
    Kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(theta) * Kx + (1 - math.cos(theta)) * (Kx @ Kx)


def traj_line_to_pose(line: str) -> tuple[float, np.ndarray]:
    """Parse one ARKitScenes `.traj` line.

    Columns: timestamp, axis-angle (3, world->camera rotation), translation (3, world->camera).
    Returns (timestamp, camera-to-world 4x4), same as the official
    `TrajStringToMatrix` in ARKitScenes/threedod/benchmark_scripts/utils/tenFpsDataLoader.py.
    """
    tok = line.split()
    if len(tok) != 7:
        raise ValueError(f"bad traj line: {line!r}")
    ts = float(tok[0])
    w2c = np.eye(4)
    w2c[:3, :3] = axis_angle_to_matrix(np.array([float(t) for t in tok[1:4]]))
    w2c[:3, 3] = [float(t) for t in tok[4:7]]
    return ts, np.linalg.inv(w2c)


def pincam_to_K(values) -> tuple[int, int, np.ndarray]:
    """`.pincam` = width height fx fy cx cy."""
    w, h, fx, fy, cx, cy = [float(x) for x in values]
    K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1.0]])
    return int(round(w)), int(round(h)), K


def world_to_camera(points: np.ndarray, pose: np.ndarray) -> np.ndarray:
    """points (N,3) world -> (N,3) camera coordinates."""
    w2c = np.linalg.inv(pose)
    homo = np.c_[points, np.ones(len(points))]
    return (homo @ w2c.T)[:, :3]


def project(points_cam: np.ndarray, K: np.ndarray) -> np.ndarray:
    """(N,3) camera coords with z>0 -> (N,2) pixel coords."""
    z = points_cam[:, 2:3]
    uv = (points_cam[:, :2] / z) * np.array([K[0, 0], K[1, 1]]) + np.array([K[0, 2], K[1, 2]])
    return uv


def project_box(obj: Object3D, frame: Frame, min_area: float = 150.0,
                min_center_frac_in_view: bool = True) -> Optional[tuple[float, float, float, float]]:
    """Project an object's 3D box into `frame`.

    Returns a clipped (x0, y0, x1, y1) pixel box, or None when the object is
    behind the camera, off-screen or too small. Occlusion is NOT handled here;
    with depth, use `object_pixels` + `box_from_pixels` instead.
    """
    pts = np.vstack([obj.corners(), obj.center[None]])
    cam = world_to_camera(pts, frame.pose)
    if cam[-1, 2] <= 0.1:  # centre behind or too close to the camera
        return None
    front = cam[cam[:, 2] > 0.1]
    uv = project(front, frame.K)
    x0, y0 = uv.min(axis=0)
    x1, y1 = uv.max(axis=0)
    cx, cy = project(cam[-1:], frame.K)[0]
    if min_center_frac_in_view and not (0 <= cx < frame.width and 0 <= cy < frame.height):
        return None
    x0, x1 = np.clip([x0, x1], 0, frame.width - 1)
    y0, y1 = np.clip([y0, y1], 0, frame.height - 1)
    if (x1 - x0) * (y1 - y0) < min_area:
        return None
    return float(x0), float(y0), float(x1), float(y1)


def depth_to_world(depth_m: np.ndarray, frame: Frame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Back-project every valid depth pixel. Returns (u, v, world points (N,3)) in depth-image pixels."""
    v, u = np.nonzero(depth_m > 0)
    z = depth_m[v, u].astype(float)
    Kd = frame.depth_K
    cam = np.c_[(u - Kd[0, 2]) * z / Kd[0, 0], (v - Kd[1, 2]) * z / Kd[1, 1], z, np.ones_like(z)]
    return u, v, (cam @ frame.pose.T)[:, :3]


def in_box_mask(obj: Object3D, points: np.ndarray, margin: float = 0.05) -> np.ndarray:
    """Which world points lie inside the object's oriented box grown by `margin` metres on every side."""
    local = (points - obj.center) @ obj.rotation.T   # rows of `rotation` are the box axes
    return np.all(np.abs(local) <= obj.size / 2.0 + margin, axis=1)


@dataclass
class ObjectPixels:
    """Depth pixels of one object in one frame (PLAN.md 4.2 step 4)."""
    u: np.ndarray        # depth-image columns
    v: np.ndarray        # depth-image rows
    z: np.ndarray        # measured depth, metres


def estimate_floor_height(heights: np.ndarray, bin_m: float = 0.02, min_frac: float = 0.02) -> float:
    """Floor height from the heights (along world up) of depth points of the scene's views.

    The floor is the lowest large flat surface: the lowest 2 cm height bin that holds at least
    `min_frac` of all points, refined to the median height of the points within 3 cm of it.
    A few noisy points below the floor are skipped by the size condition."""
    h = np.asarray(heights, float)
    edges = np.arange(h.min(), h.max() + 2 * bin_m, bin_m)
    counts, _ = np.histogram(h, edges)
    big = np.nonzero(counts >= min_frac * h.size)[0]
    if big.size == 0:
        return float(np.percentile(h, 1))
    c = (edges[big[0]] + edges[big[0] + 1]) / 2
    return float(np.median(h[np.abs(h - c) <= 0.03]))


def frame_object_pixels(objects: list[Object3D], frame: Frame, depth_m: np.ndarray, up: np.ndarray,
                        floor_h: float, margin: float = 0.05, floor_clear: float = 0.05
                        ) -> dict[int, ObjectPixels]:
    """Depth pixels of each object in one frame (PLAN.md 4.2 step 4).

    A pixel belongs to an object when its 3D point lies in the object's box grown by `margin`, it is
    at least `floor_clear` above the floor, and it lies in no other object's grown box (a pixel shared
    by two boxes, e.g. a chair tucked under a table, counts for neither)."""
    u, v, world = depth_to_world(depth_m, frame)
    keep = world @ up >= floor_h + floor_clear
    masks = {o.obj_id: in_box_mask(o, world, margin) & keep for o in objects}
    n_boxes = np.sum(list(masks.values()), axis=0) if masks else np.zeros(u.size)
    out = {}
    for oid, m in masks.items():
        m = m & (n_boxes == 1)
        out[oid] = ObjectPixels(u[m], v[m], depth_m[v[m], u[m]].astype(float))
    return out


def depth_px_to_image(u: np.ndarray, v: np.ndarray, frame: Frame) -> tuple[np.ndarray, np.ndarray]:
    """Depth-image pixel coordinates -> `frame` image coordinates (same camera, other resolution)."""
    Kd, K = frame.depth_K, frame.K
    return ((u - Kd[0, 2]) / Kd[0, 0] * K[0, 0] + K[0, 2],
            (v - Kd[1, 2]) / Kd[1, 1] * K[1, 1] + K[1, 2])


def box_from_pixels(px: ObjectPixels, frame: Frame, trim: float = 0.02, min_pixels: int = 30,
                    min_area: float = 150.0) -> Optional[tuple[float, float, float, float]]:
    """2D box over the object's visible depth pixels, dropping `trim` of outliers at each end.

    Returns None (= not visible in this view) when fewer than `min_pixels` depth pixels fall in the
    object's box or the resulting box is smaller than `min_area` image pixels."""
    if px.u.size < min_pixels:
        return None
    lo, hi = 100 * trim, 100 * (1 - trim)
    u0, u1 = np.percentile(px.u, [lo, hi])
    v0, v1 = np.percentile(px.v, [lo, hi])
    # a depth pixel covers [u - 0.5, u + 0.5]
    (x0, x1), (y0, y1) = depth_px_to_image(np.array([u0 - 0.5, u1 + 0.5]), np.array([v0 - 0.5, v1 + 0.5]), frame)
    x0, x1 = np.clip([x0, x1], 0, frame.width - 1)
    y0, y1 = np.clip([y0, y1], 0, frame.height - 1)
    if (x1 - x0) * (y1 - y0) < min_area:
        return None
    return float(x0), float(y0), float(x1), float(y1)


def backproject_pixels(px: ObjectPixels, frame: Frame) -> Optional[np.ndarray]:
    """World point at the median pixel of the object's mask, using the median depth of the mask
    (D2b in PLAN.md section 6: the paper's SAM-contour depth with a perfect mask)."""
    if px.u.size == 0:
        return None
    z = float(np.median(px.z))
    u, v = float(np.median(px.u)), float(np.median(px.v))
    Kd = frame.depth_K
    cam = np.array([(u - Kd[0, 2]) * z / Kd[0, 0], (v - Kd[1, 2]) * z / Kd[1, 1], z, 1.0])
    return (frame.pose @ cam)[:3]


def estimate_up_axis(poses: list[np.ndarray]) -> int:
    """Index of the world axis that points up (or down).

    The phone may be held in landscape or portrait (ARKitScenes `sky_direction`
    Up/Down/Left/Right), so world up is along camera -y *or* +-x. Whichever
    camera image axis it is, its world direction stays nearly constant over the
    video, while horizontal axes average out as the camera turns. So take the
    world axis with the largest |mean| over camera x and y axes.
    """
    P = np.array(poses)
    score = np.maximum(np.abs(P[:, :3, 0].mean(axis=0)), np.abs(P[:, :3, 1].mean(axis=0)))
    return int(np.argmax(score))


def up_vector(poses: list[np.ndarray], up_axis: int, below: np.ndarray) -> np.ndarray:
    """Unit world up vector: the sign is chosen so that points in `below` (e.g. object centres)
    lie mostly under the cameras, as furniture does in a hand-held indoor scan."""
    cam_h = np.mean([p[up_axis, 3] for p in poses])
    sign = 1.0 if np.median(np.asarray(below)[:, up_axis]) <= cam_h else -1.0
    u = np.zeros(3)
    u[up_axis] = sign
    return u


def image_rotation_cw(poses: list[np.ndarray], up: np.ndarray) -> int:
    """Clockwise rotation (0/90/180/270 deg) that makes the images upright.

    World up expressed in camera coordinates tells where the sky is in the image
    (OpenCV: x right, y down). Sky on the left -> rotate 90 deg clockwise.
    """
    uc = np.mean([p[:3, :3].T @ up for p in poses], axis=0)
    ux, uy = uc[0], uc[1]
    if abs(uy) >= abs(ux):
        return 0 if uy < 0 else 180
    return 90 if ux < 0 else 270


def rotate_box_cw(box: tuple[float, float, float, float], k_deg: int, width: int, height: int
                  ) -> tuple[float, float, float, float]:
    """Pixel box of a `width` x `height` image after rotating the image `k_deg` clockwise."""
    x0, y0, x1, y1 = box
    if k_deg == 0:
        return box
    if k_deg == 90:
        return height - y1, x0, height - y0, x1
    if k_deg == 180:
        return width - x1, height - y1, width - x0, height - y0
    if k_deg == 270:
        return y0, width - x1, y1, width - x0
    raise ValueError(k_deg)


def floor_axes(up_axis: int) -> tuple[int, int]:
    """Two world axes spanning the floor plane (right-handed order)."""
    return {0: (1, 2), 1: (2, 0), 2: (0, 1)}[up_axis]


def to_floor(p: np.ndarray, up_axis: int) -> np.ndarray:
    a, b = floor_axes(up_axis)
    p = np.asarray(p)
    return p[..., [a, b]]


def camera_yaw_deg(pose: np.ndarray, up_axis: int) -> float:
    """Heading of the camera's viewing direction projected on the floor, degrees in [0, 360)."""
    fwd = pose[:3, 2]
    f = to_floor(fwd, up_axis)
    return math.degrees(math.atan2(f[1], f[0])) % 360.0


def camera_position(pose: np.ndarray) -> np.ndarray:
    return pose[:3, 3].copy()


def angle_diff_deg(a: float, b: float) -> float:
    """Smallest absolute difference between two headings."""
    d = (a - b) % 360.0
    return min(d, 360.0 - d)
