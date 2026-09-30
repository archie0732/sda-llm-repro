"""Camera geometry helpers: poses, projection, floor-plane coordinates."""
from __future__ import annotations

import math
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
    use `visible_with_depth` for that.
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


def visible_with_depth(obj: Object3D, frame: Frame, depth_m: Optional[np.ndarray],
                       tol: float = 0.35) -> bool:
    """Crude occlusion test at the projected box centre.

    `depth_m` is the depth map in metres (any resolution; `frame.depth_K` must
    match it). If depth is missing we assume visible.
    """
    if depth_m is None or frame.depth_K is None:
        return True
    cam = world_to_camera(obj.center[None], frame.pose)[0]
    if cam[2] <= 0.1:
        return False
    u, v = project(cam[None], frame.depth_K)[0]
    h, w = depth_m.shape
    if not (0 <= u < w and 0 <= v < h):
        return False
    r = 2
    patch = depth_m[max(0, int(v) - r):int(v) + r + 1, max(0, int(u) - r):int(u) + r + 1]
    patch = patch[patch > 0]
    if patch.size == 0:
        return True
    # visible if the measured surface is not much closer than the box centre
    half_depth = float(np.max(obj.size)) / 2.0
    return float(np.median(patch)) >= cam[2] - half_depth - tol


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
