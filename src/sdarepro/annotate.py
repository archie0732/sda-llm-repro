"""Build the paper's 'annotated images': boxes + ID tags drawn on each view.

With oracle (ground-truth) boxes, one physical object has the same ID in every
view, which is exactly the result a perfect cross-view de-duplication would give.
"""
from __future__ import annotations

import math
import zlib
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .geometry import project_box, rotate_box_cw, to_floor, visible_with_depth
from .scene import Frame, Object3D, Scene

PALETTE = [(230, 25, 75), (60, 180, 75), (0, 130, 200), (245, 130, 48), (145, 30, 180),
           (70, 240, 240), (240, 50, 230), (210, 245, 60), (250, 190, 190), (0, 128, 128),
           (170, 110, 40), (128, 0, 0), (0, 0, 128), (128, 128, 0)]


@dataclass
class ViewBoxes:
    frame: Frame
    boxes: dict[int, tuple[float, float, float, float]] = field(default_factory=dict)  # obj_id -> box


def load_depth_m(frame: Frame) -> Optional[np.ndarray]:
    if not frame.depth_path:
        return None
    d = np.asarray(Image.open(frame.depth_path)).astype(np.float32) / 1000.0
    return d


def compute_view_boxes(objects: list[Object3D], frames: list[Frame], use_depth: bool = True,
                       min_area: float = 150.0) -> list[ViewBoxes]:
    out = []
    for f in frames:
        depth = load_depth_m(f) if use_depth else None
        vb = ViewBoxes(frame=f)
        for o in objects:
            box = project_box(o, f, min_area=min_area)
            if box is None:
                continue
            if use_depth and not visible_with_depth(o, f, depth):
                continue
            vb.boxes[o.obj_id] = box
        out.append(vb)
    return out


def assign_ids(scene: Scene, station_xy: np.ndarray, heading_deg: float) -> None:
    """Give objects short ids 1..N, ordered clockwise from the robot's forward heading.

    The order is deterministic but carries no hint about the target.
    """
    def key(o: Object3D):
        d = to_floor(o.center, scene.up_axis) - station_xy
        ang = (math.degrees(math.atan2(d[1], d[0])) - heading_deg) % 360.0
        return (round(ang, 3), o.uid)

    for i, o in enumerate(sorted(scene.objects, key=key), start=1):
        o.obj_id = i


def visible_object_ids(view_boxes: list[ViewBoxes]) -> set[int]:
    ids: set[int] = set()
    for vb in view_boxes:
        ids.update(vb.boxes)
    return ids


def _font(size: int):
    for name in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_view(image: Image.Image, vb: ViewBoxes, labels: dict[int, str], scale: float = 1.0,
              color_by_class: bool = False, tags: Optional[dict[int, str]] = None) -> Image.Image:
    """Draw OpenCV-style boxes and '#id' tags. `scale` maps box coords to `image` size.

    Default: one colour for every box, so colour carries no class hint (a confound).
    """
    img = image.convert("RGB").copy()
    d = ImageDraw.Draw(img)
    font = _font(max(12, int(16 * img.width / 640)))
    placed: list[list[float]] = []
    for oid, (x0, y0, x1, y1) in sorted(vb.boxes.items()):
        c = PALETTE[zlib.crc32(labels.get(oid, "").encode()) % len(PALETTE)] if color_by_class else PALETTE[0]
        x0, y0, x1, y1 = [v * scale for v in (x0, y0, x1, y1)]
        d.rectangle([x0, y0, x1, y1], outline=c, width=max(2, img.width // 320))
        tag = (tags or {}).get(oid, f"#{oid}")
        tb = d.textbbox((0, 0), tag, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        tx, ty = x0 + 2, max(0, y0 - th - 6)
        # avoid covering an earlier tag: slide down until free (small neighbouring boxes, M1 issue)
        def hit(r):
            return any(not (r[2] < q[0] or r[0] > q[2] or r[3] < q[1] or r[1] > q[3]) for q in placed)
        rect = [tx - 2, ty - 1, tx + tw + 4, ty + th + 5]
        while hit(rect) and rect[3] < img.height:
            ty += th + 7
            rect = [tx - 2, ty - 1, tx + tw + 4, ty + th + 5]
        placed.append(rect)
        d.rectangle(rect, fill=c)
        d.text((tx, ty), tag, fill=(255, 255, 255), font=font)
    return img


_TRANSPOSE_CW = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}


def rotate_image_cw(image: Image.Image, k_deg: int) -> Image.Image:
    return image.transpose(_TRANSPOSE_CW[k_deg]) if k_deg else image


def render_views(view_boxes: list[ViewBoxes], labels: dict[int, str], rot_cw: int = 0) -> list[Image.Image]:
    """Draw boxes on each view. `rot_cw` turns image and boxes upright (portrait recordings);
    `view_boxes` themselves stay in the original camera image coordinates."""
    imgs = []
    for vb in view_boxes:
        f = vb.frame
        if f.image_path:
            base = Image.open(f.image_path)
        else:  # synthetic tests
            base = Image.new("RGB", (f.width, f.height), (200, 200, 200))
        scale = base.width / f.width
        if rot_cw:
            boxes = {k: rotate_box_cw(b, rot_cw, f.width, f.height) for k, b in vb.boxes.items()}
            vb = ViewBoxes(frame=f, boxes=boxes)
            base = rotate_image_cw(base, rot_cw)
        imgs.append(draw_view(base, vb, labels, scale))
    return imgs


def make_grid(images: list[Image.Image], cols: int = 4, tile_w: int = 320) -> Image.Image:
    """Concatenate views into one image (condition C2 in PLAN.md)."""
    tiles = [im.resize((tile_w, int(im.height * tile_w / im.width))) for im in images]
    th = max(t.height for t in tiles)
    rows = math.ceil(len(tiles) / cols)
    grid = Image.new("RGB", (cols * tile_w, rows * th), (0, 0, 0))
    d = ImageDraw.Draw(grid)
    font = _font(14)
    for i, t in enumerate(tiles):
        x, y = (i % cols) * tile_w, (i // cols) * th
        grid.paste(t, (x, y))
        d.text((x + 4, y + th - 18), f"view {i}", fill=(255, 255, 0), font=font)
    return grid
