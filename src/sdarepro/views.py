"""Pick ~8 frames that imitate the robot's 'rotate in place, one shot every 45 degrees'.

ARKitScenes is recorded with a hand-held phone, so there is no true in-place
rotation. We search for a floor position (the "station") around which the
camera passed with many different headings, then take the best frame per
45-degree heading bin. This is a documented deviation from the paper.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometry import angle_diff_deg, camera_position, camera_yaw_deg, to_floor
from .scene import Frame, Scene


@dataclass
class ViewSelection:
    station_xy: np.ndarray        # floor coords of the virtual robot
    station_heading_deg: float    # heading of view 0, defines "robot forward"
    frames: list[Frame]           # ordered by heading bin
    bin_headings: list[float]     # nominal heading (deg) of each selected frame
    coverage: int                 # number of filled bins


def select_views(scene: Scene, n_bins: int = 8, radius: float = 1.0,
                 max_bin_error: float = 22.5, n_station_candidates: int = 200,
                 seed: int = 0) -> ViewSelection:
    frames = scene.frames
    if not frames:
        raise ValueError("scene has no frames")
    pos = np.array([to_floor(camera_position(f.pose), scene.up_axis) for f in frames])
    yaw = np.array([camera_yaw_deg(f.pose, scene.up_axis) for f in frames])

    rng = np.random.default_rng(seed)
    idx = np.arange(len(frames))
    cand = idx if len(idx) <= n_station_candidates else rng.choice(idx, n_station_candidates, replace=False)

    best = None
    width = 360.0 / n_bins
    for ci in cand:
        st = pos[ci]
        near = np.where(np.linalg.norm(pos - st, axis=1) <= radius)[0]
        if len(near) == 0:
            continue
        chosen, chosen_bins = [], []
        for b in range(n_bins):
            nominal = (yaw[ci] + b * width) % 360.0
            errs = np.array([angle_diff_deg(yaw[j], nominal) for j in near])
            ok = near[errs <= max_bin_error]
            if len(ok) == 0:
                continue
            # prefer frames close to the station and close to the nominal heading
            score = np.linalg.norm(pos[ok] - st, axis=1) / radius + \
                np.array([angle_diff_deg(yaw[j], nominal) for j in ok]) / max_bin_error
            chosen.append(int(ok[np.argmin(score)]))
            chosen_bins.append(nominal)
        spread = float(np.mean(np.linalg.norm(pos[chosen] - st, axis=1))) if chosen else 1e9
        key = (len(chosen), -spread)
        if best is None or key > best[0]:
            best = (key, st, yaw[ci], chosen, chosen_bins)

    _, st, heading0, chosen, bins = best
    # the station is the mean position of the chosen frames (closer to "one spot")
    st = pos[chosen].mean(axis=0)
    return ViewSelection(station_xy=st, station_heading_deg=float(heading0),
                         frames=[frames[i] for i in chosen], bin_headings=[float(b) for b in bins],
                         coverage=len(chosen))
