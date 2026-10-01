import json
import math
import os
import random

import cv2
import numpy as np
import pytest
from PIL import Image

from sdarepro import arkit
from sdarepro.annotate import assign_ids, compute_view_boxes
from sdarepro.dedup import Detection, backproject, dedup_geometric, dedup_none, evaluate_clusters, match_to_gt
from sdarepro.dialogue import GeoContext, build_constraints, gen_type_a, gen_type_b, target_facts
from sdarepro.geometry import (camera_yaw_deg, estimate_up_axis, project_box, traj_line_to_pose,
                               world_to_camera)
from sdarepro.metrics import jaccard, score_type_a, score_type_b
from sdarepro.prepare import load_prepared, prepare_scene
from sdarepro.prompts import object_table
from sdarepro.runner import context_blocks, run_active, run_dialogue
from sdarepro.synth import camera_pose, synthetic_room
from sdarepro.views import select_views
from sdarepro.vlm import ScriptedClient, ids_from, parse_json


# ---------------------------------------------------------------- geometry
def test_traj_matches_official_formula():
    pose = camera_pose(np.array([0.3, -0.2, 1.3]), 37.0)
    w2c = np.linalg.inv(pose)
    aa = cv2.Rodrigues(w2c[:3, :3])[0].ravel()
    line = f"12.5 {aa[0]} {aa[1]} {aa[2]} {w2c[0, 3]} {w2c[1, 3]} {w2c[2, 3]}"
    ts, got = traj_line_to_pose(line)
    assert ts == 12.5
    assert np.allclose(got, pose, atol=1e-6)


def test_projection_and_heading():
    scene = synthetic_room()
    f0 = scene.frames[0]            # yaw 0 looks along +x, where the table is
    table = scene.objects[0]
    box = project_box(table, f0)
    assert box is not None
    cx = (box[0] + box[2]) / 2
    assert abs(cx - 320) < 40
    assert estimate_up_axis([f.pose for f in scene.frames]) == 2
    assert abs(camera_yaw_deg(scene.frames[18].pose, 2) - 90) < 1e-6   # 18 * 5 deg
    fridge = scene.objects[7]       # at -y, behind the camera for yaw 0? no: at 270 deg
    assert project_box(fridge, f0) is None


def _rolled(pose, roll):
    """Roll the camera about its optical axis: 'left' = sky on the image's left (portrait recording)."""
    cols = {"up": (0, 1, 2, 1, 1), "left": (1, 0, 2, 1, -1), "right": (1, 0, 2, -1, 1), "down": (0, 1, 2, -1, -1)}
    ix, iy, iz, sx, sy = cols[roll]
    R = pose[:3, :3]
    out = pose.copy()
    out[:3, 0], out[:3, 1], out[:3, 2] = sx * R[:, ix], sy * R[:, iy], R[:, iz]
    return out


@pytest.mark.parametrize("roll,rot", [("up", 0), ("left", 90), ("right", 270), ("down", 180)])
def test_up_axis_and_rotation_for_any_phone_roll(roll, rot):
    # bug found in M1: portrait videos (sky_direction Left) gave up_axis 1 instead of 2
    from sdarepro.geometry import image_rotation_cw, up_vector
    poses = [_rolled(camera_pose(np.array([0.1 * i, 0.0, 1.3]), yaw), roll) for i, yaw in enumerate(range(0, 360, 20))]
    assert all(np.isclose(np.linalg.det(p[:3, :3]), 1) for p in poses)
    assert estimate_up_axis(poses) == 2
    up = up_vector(poses, 2, below=np.array([[1.0, 0.0, 0.4], [2.0, 1.0, 0.5]]))
    assert np.allclose(up, [0, 0, 1])
    assert image_rotation_cw(poses, up) == rot


@pytest.mark.parametrize("k", [0, 90, 180, 270])
def test_rotate_box_matches_image_rotation(k):
    from sdarepro.annotate import rotate_image_cw
    from sdarepro.geometry import rotate_box_cw
    img = Image.new("L", (64, 48))
    img.paste(255, (10, 5, 30, 12))                     # pixels x 10..29, y 5..11 -> box (10, 5, 30, 12)
    got = rotate_box_cw((10, 5, 30, 12), k, 64, 48)
    x0, y0, x1, y1 = rotate_image_cw(img, k).getbbox()
    assert (x0, y0, x1, y1) == tuple(int(v) for v in got)


def test_box_corners_use_rows_as_axes():
    # bug found in M1: corners used columns of normalizedAxes; official compute_box_3d uses rows
    from sdarepro.scene import Object3D
    y = math.radians(40)
    R = np.array([[math.cos(y), math.sin(y), 0], [-math.sin(y), math.cos(y), 0], [0, 0, 1]])
    o = Object3D(uid="a", label="sofa", center=np.array([1.0, 2.0, 0.4]), size=np.array([2.0, 0.5, 0.8]), rotation=R)
    l, h, w = o.size / 2    # official formula, ARKitScenes threedod/benchmark_scripts/utils/box_utils.py
    local = np.array([[l, l, -l, -l, l, l, -l, -l], [h, -h, -h, h, h, -h, -h, h], [w, w, w, w, -w, -w, -w, -w]])
    official = (R.T @ local).T + o.center
    assert np.allclose(sorted(map(tuple, np.round(o.corners(), 9))), sorted(map(tuple, np.round(official, 9))))
    long_edge = o.corners()[4] - o.corners()[0]         # corners differ only in the first local axis
    assert np.allclose(long_edge / 2.0, R[0])


def test_view_selection_covers_all_bins():
    sel = select_views(synthetic_room())
    assert sel.coverage == 8
    heads = sorted(camera_yaw_deg(f.pose, 2) for f in sel.frames)
    gaps = np.diff(heads + [heads[0] + 360])
    assert np.all(np.abs(gaps - 45) < 12)


# ---------------------------------------------------------------- dialogues
def _ctx():
    scene = synthetic_room()
    sel = select_views(scene)
    assign_ids(scene, sel.station_xy, sel.station_heading_deg)
    return scene, sel, GeoContext(objects=scene.objects, up_axis=2, station_xy=sel.station_xy,
                                  heading_deg=sel.station_heading_deg)


def test_type_b_dialogues_narrow_to_target():
    scene, sel, ctx = _ctx()
    rng = random.Random(1)
    chairs = [o for o in ctx.objects if o.label == "chair"]
    made = 0
    for t in chairs:
        d = gen_type_b(ctx, t, "d", "s", rng)
        if d is None:
            continue
        made += 1
        sizes = [len(tu.gt_set) for tu in d.turns]
        assert sizes[0] == len(chairs)
        assert all(a > b for a, b in zip(sizes, sizes[1:])), sizes
        assert d.turns[-1].gt_set == [t.obj_id]
        assert all(t.obj_id in tu.gt_set for tu in d.turns)
    assert made >= 3


def test_type_a_dialogues_are_true_and_unique():
    scene, sel, ctx = _ctx()
    rng = random.Random(2)
    made = 0
    for t in [o for o in ctx.objects if o.label == "chair"]:
        d = gen_type_a(ctx, t, "d", "s", rng)
        if d is None:
            continue
        made += 1
        assert all(tu.gt_set == [t.obj_id] for tu in d.turns)
        assert d.turns[0].text.startswith("Help me find the chair")
    assert made >= 2


def test_superlative_requires_gap():
    scene, sel, ctx = _ctx()
    ctx.superlative_gap = 100.0  # impossible gap -> no superlative is usable
    t = next(o for o in ctx.objects if o.label == "chair")
    S = [o for o in ctx.objects if o.label == "chair"]
    for c in build_constraints(ctx, t):
        if c.kind in ("closest_to", "farthest_from", "closest_to_robot", "farthest_from_robot"):
            assert c.apply(S) is None


def test_facts_never_contain_ids():
    scene, sel, ctx = _ctx()
    t = next(o for o in ctx.objects if o.label == "chair")
    facts = " ".join(target_facts(ctx, t))
    assert "#" not in facts


def test_object_table_robot_frame():
    scene, sel, ctx = _ctx()
    ctx.heading_deg = 0.0
    ctx.station_xy = np.zeros(2)
    row = [r for r in object_table(ctx).splitlines() if "| table |" in r][0]
    x, y = float(row.split("|")[2]), float(row.split("|")[3])
    assert abs(x - 2.6) < 1e-6 and abs(y) < 1e-6


# ---------------------------------------------------------------- metrics
def test_metrics_values():
    assert jaccard([1, 2], [2, 3]) == pytest.approx(1 / 3)
    a = score_type_a(1, [[1, 2], [1]], k=4)
    assert a["SR"] == pytest.approx(0.75) and a["AS"] == pytest.approx(0.75) and a["T_A"] == pytest.approx(0.75)
    assert score_type_a(1, [[2]], k=4)["T_A"] == 0.0
    b = score_type_b(3, [[1, 2, 3], [3]], [[1, 2, 3, 4], [3]])
    assert b["AR"] == 1.0 and b["NS"] == pytest.approx((0.75 + 1) / 2)
    assert b["T_B"] == pytest.approx(0.6 + 0.4 * 0.875)


def test_claude_client_sends_no_temperature(monkeypatch):
    # M0.5: SDK 1.x has no `temperature` argument and current models reject non-default sampling
    from types import SimpleNamespace
    from sdarepro.vlm import ClaudeClient
    sent = {}

    def create(**kw):
        sent.update(kw)
        return SimpleNamespace(content=[SimpleNamespace(text='{"candidate_ids": [1]}')], stop_reason="end_turn",
                               usage=SimpleNamespace(input_tokens=5, output_tokens=3, cache_read_input_tokens=0,
                                                     cache_creation_input_tokens=0))

    monkeypatch.setenv("SDA_API_KEY", "test")
    monkeypatch.setenv("SDA_MODEL", "some-model")
    monkeypatch.delenv("SDA_THINKING", raising=False)
    c = ClaudeClient()
    c.client = SimpleNamespace(messages=SimpleNamespace(create=create))
    r = c.respond("sys", [{"role": "user", "content": [{"type": "text", "text": "hi"}]}])
    assert "temperature" not in sent and sent["thinking"] == {"type": "between_tools"}
    assert r.parsed == {"candidate_ids": [1]} and r.stop_reason == "end_turn"
    c.thinking = "omit"
    sent.clear()
    c.respond("sys", [{"role": "user", "content": [{"type": "text", "text": "hi"}]}])
    assert "thinking" not in sent


def test_parse_json_tolerates_fences():
    p = parse_json('```json\n{"candidate_ids": ["#3", 5], "count": 2}\n```')
    assert ids_from(p) == [3, 5]
    assert parse_json("no json here") is None


def test_parse_json_takes_the_last_object():
    # Track V: an answer followed by 'Correction to format: {...}' was parsed as empty
    t = ('{"candidate_ids": ["chair 5", "chair 6"], "reason": "x"}\n\nCorrection to format: '
         '{"candidate_ids": ["chair 5", "chair 6"], "count": 2, "reason": "y {braces} inside"}')
    assert parse_json(t) == {"candidate_ids": ["chair 5", "chair 6"], "count": 2, "reason": "y {braces} inside"}
    assert parse_json('Let me reconsider: {"count": 1} and {not json') == {"count": 1}


# ---------------------------------------------------------------- pipeline
@pytest.fixture()
def prepared(tmp_path):
    ps = prepare_scene(synthetic_room(), str(tmp_path), use_depth=False, dialogues_per_type=3)
    assert ps is not None
    return tmp_path, ps


def test_prepare_and_reload(prepared):
    root, ps = prepared
    again = load_prepared(os.path.join(root, ps.scene_id))
    assert len(again.images_annot) == 8
    assert again.dialogues == ps.dialogues
    assert {o.obj_id for o in again.ctx.objects} == {o.obj_id for o in ps.ctx.objects}


def test_context_blocks_per_condition(prepared):
    _, ps = prepared
    n_img = lambda blocks: sum(b["type"] == "image" for b in blocks)
    assert n_img(context_blocks("multi_image", ps)[1]) == 8
    assert n_img(context_blocks("grid", ps)[1]) == 1
    sys_t, blocks_t = context_blocks("text_only", ps)
    assert n_img(blocks_t) == 0 and "Detected objects" in blocks_t[-1]["text"]
    assert n_img(context_blocks("multi_image_text", ps)[1]) == 8


def test_oracle_client_scores_perfectly(prepared):
    _, ps = prepared
    for dlg in ps.dialogues:
        replies = [{"candidate_ids": t["gt_set"], "count": len(t["gt_set"])} for t in dlg["turns"]]
        rec = run_dialogue(ScriptedClient(replies), "multi_image", ps, dlg)
        key = "T_A" if dlg["dtype"] == "A" else "T_B"
        if dlg["dtype"] == "A":
            assert rec["alpha"] == 1 and rec[key] == pytest.approx(1.0)
        else:
            assert rec["found"] and rec["NS"] == pytest.approx(1.0) and rec[key] == pytest.approx(1.0)


def test_images_sent_only_once(prepared):
    _, ps = prepared
    dlg = next(d for d in ps.dialogues if d["dtype"] == "B")
    replies = [{"candidate_ids": t["gt_set"]} for t in dlg["turns"]]
    client = ScriptedClient(replies)
    run_dialogue(client, "multi_image", ps, dlg)
    last_msgs = client.calls[-1][1]
    imgs = sum(b["type"] == "image" for m in last_msgs for b in m["content"])
    assert imgs == 8


def test_forced_choice_system_message_only_on_last_turn(prepared):
    from sdarepro.prompts import FORCED_CHOICE
    _, ps = prepared
    dlg = next(d for d in ps.dialogues if len(d["turns"]) >= 2)
    two = dlg["turns"][0]["gt_set"][:2] if len(dlg["turns"][0]["gt_set"]) >= 2 else [1, 2]
    client = ScriptedClient([{"candidate_ids": two}] * len(dlg["turns"]))   # never single: every turn is sent
    run_dialogue(client, "forced_choice", ps, dlg)
    assert len(client.calls) == len(dlg["turns"])
    lasts = [msgs[-1] for _, msgs in client.calls]
    assert all(m["role"] == "user" for m in lasts[:-1])
    assert lasts[-1]["role"] == "system" and lasts[-1]["content"][0]["text"] == FORCED_CHOICE
    assert sum(b["type"] == "image" for b in client.calls[0][1][0]["content"]) == 8   # same views as multi_image


def test_active_mode_loop(prepared):
    _, ps = prepared
    dlg = next(d for d in ps.dialogues if d["dtype"] == "B")
    robot = ScriptedClient([{"action": "ask", "question": "Near what?", "candidate_ids": dlg["turns"][0]["gt_set"]},
                            {"action": "go", "candidate_ids": [dlg["target"]]}])
    user = ScriptedClient([{"answer": "near the sofa"}])
    rec = run_active(robot, user, ps, dlg)
    assert rec["found"] and rec["robot_turns"] == 2
    assert "Facts:" in user.calls[0][0]


# ---------------------------------------------------------------- dedup
def test_geometric_dedup_on_synthetic_depth():
    scene = synthetic_room()
    sel = select_views(scene)
    assign_ids(scene, sel.station_xy, sel.station_heading_deg)
    labels = {o.obj_id: o.label for o in scene.objects}
    vbs = compute_view_boxes(scene.objects, sel.frames, use_depth=False)
    dets = []
    for vi, vb in enumerate(vbs):
        f = vb.frame
        f.depth_K = f.K.copy()
        depth = np.zeros((f.height, f.width), np.float32)
        for oid, b in vb.boxes.items():   # paint each object's centre depth into its box
            z = world_to_camera(scene.by_id(oid).center[None], f.pose)[0, 2]
            x0, y0, x1, y1 = [int(v) for v in b]
            region = depth[y0:y1 + 1, x0:x1 + 1]
            region[(region == 0) | (region > z)] = z
        for oid, b in vb.boxes.items():
            d = Detection(view=vi, label=labels[oid], box=b)
            d.world = backproject(d, f, depth)
            dets.append(d)
    match_to_gt(dets, [vb.boxes for vb in vbs], labels)
    geo = evaluate_clusters(dets, dedup_geometric(dets, tau=0.6))
    none = evaluate_clusters(dets, dedup_none(dets))
    assert none["recall"] == 0.0 and none["count_error"] > 0
    assert none["precision"] is None and none["f1"] == 0.0   # no predicted links: precision is N/A, not 1.0
    assert geo["recall"] > 0.8 and geo["precision"] > 0.9


# ---------------------------------------------------------------- per-pixel visibility (M2 check)
def _render_depth(objects, frame, w=160, h=120):
    """Ray-cast axis-aligned boxes and the floor (z=0) into a depth map; sets `frame.depth_K`."""
    s = w / frame.width
    Kd = frame.K.copy()
    Kd[:2] *= s
    frame.depth_K = Kd
    v, u = np.mgrid[0:h, 0:w]
    d_cam = np.stack([(u - Kd[0, 2]) / Kd[0, 0], (v - Kd[1, 2]) / Kd[1, 1], np.ones_like(u, float)], -1)
    d = d_cam @ frame.pose[:3, :3].T            # world ray per pixel, parametrised so that t = camera depth
    o = frame.pose[:3, 3]
    depth = np.full((h, w), np.inf)
    with np.errstate(divide="ignore", invalid="ignore"):
        t_floor = np.where(d[..., 2] < 0, -o[2] / d[..., 2], np.inf)
        depth = np.minimum(depth, t_floor)
        for ob in objects:
            lo, hi = ob.center - ob.size / 2, ob.center + ob.size / 2
            t1, t2 = (lo - o) / d, (hi - o) / d
            tn = np.nanmax(np.minimum(t1, t2), axis=-1)
            tf = np.nanmin(np.maximum(t1, t2), axis=-1)
            depth = np.where((tn <= tf) & (tn > 0), np.minimum(depth, tn), depth)
    depth[~np.isfinite(depth)] = 0
    return depth


def _tablecloth_scene(tmp_path, extra=(), hidden=()):
    """Chair #2 hides behind a table whose cloth reaches the floor (48458417 views 4, 5); chair #3 is
    half hidden by a low box. One camera at 1.3 m looking along +x. `hidden` objects are annotated
    but not drawn into the depth map."""
    from sdarepro.synth import K640, box
    objs = [box("t", "table", 2.0, 0.0, 1.0, 1.6, 0.75), box("c", "chair", 2.9, 0.0, 0.45, 0.45, 0.6),
            box("c2", "chair", 2.9, 1.2, 0.45, 0.45, 0.9), box("b", "box", 2.0, 1.2, 0.5, 0.6, 0.5), *extra, *hidden]
    for i, ob in enumerate(objs, start=1):
        ob.obj_id = i
    from sdarepro.scene import Frame
    f = Frame("f0", 0.0, camera_pose(np.array([0.0, 0.0, 1.3]), 0.0), K640.copy(), 640, 480)
    depth = _render_depth([o for o in objs if not any(o is h for h in hidden)], f)
    f.depth_path = str(tmp_path / "d.png")
    Image.fromarray(np.round(depth * 1000).astype(np.uint16)).save(f.depth_path)
    return objs, f, depth


def test_depth_visibility_drops_hidden_objects(tmp_path):
    # M2: chairs behind a tablecloth still got boxes (projected 3D box + centre-only depth test)
    objs, f, _ = _tablecloth_scene(tmp_path)
    assert project_box(objs[1], f) is not None          # the projection alone says "visible"
    vb = compute_view_boxes(objs, [f], up_axis=2)[0]
    assert 2 not in vb.boxes
    assert {1, 3} <= set(vb.boxes)


def test_depth_box_is_tight_on_the_visible_part(tmp_path):
    # M2: the projected 3D box of a partly hidden object covers far more than what is seen
    from sdarepro.dedup import iou
    objs, f, _ = _tablecloth_scene(tmp_path)
    vb = compute_view_boxes(objs, [f], up_axis=2)[0]
    assert iou(vb.boxes[1], project_box(objs[0], f)) > 0.85  # unoccluded table: about the projection
    proj, got = project_box(objs[2], f), vb.boxes[3]          # chair behind the low box
    assert abs(got[1] - proj[1]) < 8                          # top edge unchanged
    assert got[3] < proj[3] - 40                              # bottom cut where the box hides it


def test_box_from_pixels_trims_outliers_and_needs_enough_pixels():
    from sdarepro.geometry import ObjectPixels, box_from_pixels
    from sdarepro.scene import Frame
    from sdarepro.synth import K640
    f = Frame("f", 0.0, np.eye(4), K640.copy(), 640, 480, depth_K=K640.copy())
    v, u = np.mgrid[100:150, 200:260]
    u = np.r_[u.ravel(), [5, 630]]                   # two stray pixels far away
    v = np.r_[v.ravel(), [5, 470]]
    x0, y0, x1, y1 = box_from_pixels(ObjectPixels(u, v, np.ones(u.size)), f)
    assert 195 < x0 < 205 and 255 < x1 < 265 and 95 < y0 < 105 and 145 < y1 < 155
    few = ObjectPixels(np.arange(10), np.arange(10), np.ones(10))
    assert box_from_pixels(few, f) is None


def test_mask_backprojection_lands_on_the_object(tmp_path):
    # D2b: median depth of the object's own pixels; D2 (box centre) on the projected box hits the occluder
    from sdarepro.geometry import backproject_pixels, frame_object_pixels, in_box_mask
    objs, f, depth = _tablecloth_scene(tmp_path)
    chair = objs[2]
    p = backproject_pixels(frame_object_pixels(objs, f, depth, np.array([0, 0, 1.0]), 0.0)[3], f)
    assert in_box_mask(chair, p[None], margin=0.05)[0]
    d2 = backproject(Detection(view=0, label="chair", box=project_box(chair, f)), f, depth)
    assert np.linalg.norm(p - chair.center) < np.linalg.norm(d2 - chair.center)


def test_floor_height_is_estimated_and_floor_pixels_dropped(tmp_path):
    # M2 re-check: 24-47% of an object's pixels were floor inside its grown box
    from sdarepro.annotate import compute_view_boxes
    from sdarepro.geometry import depth_to_world, estimate_floor_height, in_box_mask
    from sdarepro.synth import box
    objs, f, depth = _tablecloth_scene(tmp_path, extra=(box("k", "cabinet", 4.0, -2.0, 0.5, 0.5, 0.8),))
    h = depth_to_world(depth, f)[2][:, 2]
    noisy = np.r_[h, np.full(20, -0.4)]                      # a few stray points under the floor
    assert abs(estimate_floor_height(noisy)) < 0.02
    vb = compute_view_boxes(objs, [f], up_axis=2)[0]
    assert abs(vb.floor_h) < 0.02 and np.allclose(vb.up, [0, 0, 1])
    u, v, world = depth_to_world(depth, f)
    for oid, px in vb.pixels.items():
        pts = {(a, b) for a, b in zip(px.u, px.v)}
        low = [(a, b) for a, b, w in zip(u, v, world) if w[2] < 0.05]
        assert not pts & set(low), oid
    floor_in_box = in_box_mask(objs[4], world) & (world[:, 2] < 0.05)
    assert floor_in_box.sum() >= 10                          # the rule had floor to remove around the cabinet
    assert 5 in vb.boxes


def test_pixels_shared_by_two_boxes_count_for_neither(tmp_path):
    # M2 re-check: in 48458417 view 5 every pixel of chair #17 was tablecloth inside the chair's box
    from sdarepro.annotate import compute_view_boxes
    from sdarepro.geometry import depth_to_world, in_box_mask
    from sdarepro.synth import box
    # annotated but not rendered: the chair itself is under the cloth, its box pokes above the tabletop
    tucked = box("c3", "chair", 1.8, -0.5, 0.45, 0.45, 0.9)
    half = box("c4", "chair", 2.4, 0.6, 0.45, 0.45, 0.95)     # rendered, sticks out of the table's corner
    objs, f, depth = _tablecloth_scene(tmp_path, extra=(half,), hidden=(tucked,))
    u, v, world = depth_to_world(depth, f)
    in_tucked = in_box_mask(tucked, world) & (world[:, 2] >= 0.05)
    assert in_tucked.sum() >= 30                             # without the rule it would get a box (tablecloth)
    vb = compute_view_boxes(objs, [f], up_axis=2)[0]
    assert tucked.obj_id not in vb.boxes
    assert {1, half.obj_id} <= set(vb.boxes)
    idx = {(a, b): i for i, (a, b) in enumerate(zip(u, v))}
    for oid, px in vb.pixels.items():
        w = world[[idx[(a, b)] for a, b in zip(px.u, px.v)]]
        for o in objs:
            if o.obj_id != oid:
                assert not in_box_mask(o, w).any(), (oid, o.obj_id)


# ---------------------------------------------------------------- ARKit loader on fake files
def test_arkit_loader_on_fake_layout(tmp_path):
    vid = "41069021"
    root = tmp_path / vid
    (root / "vga_wide").mkdir(parents=True)
    (root / "vga_wide_intrinsics").mkdir()
    scene = synthetic_room(step_deg=45)
    lines = []
    for f in scene.frames:
        ts = f"{f.timestamp + 100:.3f}"
        w2c = np.linalg.inv(f.pose)
        aa = cv2.Rodrigues(w2c[:3, :3])[0].ravel()
        lines.append(f"{ts} {aa[0]} {aa[1]} {aa[2]} {w2c[0, 3]} {w2c[1, 3]} {w2c[2, 3]}")
        Image.new("RGB", (640, 480)).save(root / "vga_wide" / f"{vid}_{ts}.png")
        (root / "vga_wide_intrinsics" / f"{vid}_{ts}.pincam").write_text("640 480 500 500 320 240")
    (root / "lowres_wide.traj").write_text("\n".join(lines))
    ann = {"data": [{"uid": o.uid, "label": o.label, "segments": {"obbAligned": {
        "centroid": o.center.tolist(), "axesLengths": o.size.tolist(),
        "normalizedAxes": o.rotation.ravel().tolist()}}} for o in scene.objects], "skipped": False}
    (root / f"{vid}_3dod_annotation.json").write_text(json.dumps(ann))
    loaded = arkit.load_scene(str(root), frame_stride=1)
    assert len(loaded.frames) == len(scene.frames)
    assert loaded.up_axis == 2
    for a, b in zip(loaded.frames, scene.frames):
        assert np.allclose(a.pose, b.pose, atol=1e-6)
    assert [o.label for o in loaded.objects] == [o.label for o in scene.objects]


# ---------------------------------------------------------------- real ARKitScenes data (skipped when absent)
ARKIT_RAW = os.path.join(os.path.dirname(__file__), "..", "data", "arkitscenes", "raw")
M1_VIDEO = "42446103"   # M1 scene, checked by eye (results/m1_check/)


@pytest.mark.skipif(not os.path.isdir(os.path.join(ARKIT_RAW, "Validation", M1_VIDEO, "vga_wide")),
                    reason="ARKitScenes M1 video not downloaded")
def test_m1_scene_orientation_matches_metadata():
    import csv
    sky = {r["video_id"]: r["sky_direction"] for r in csv.DictReader(open(os.path.join(ARKIT_RAW, "metadata.csv")))}
    expect = {"Up": 0, "Left": 90, "Down": 180, "Right": 270}
    scene = arkit.load_scene(os.path.join(ARKIT_RAW, "Validation", M1_VIDEO), frame_stride=10)
    assert scene.up_axis == 2
    assert scene.image_rot_cw == expect[sky[M1_VIDEO]]
    sel = select_views(scene)
    assert sel.coverage >= 6


# ---------------------------------------------------------------- VisDial release (skipped if not cloned)
VISDIAL = os.environ.get("VISDIAL_ROOT", "third_party/SDA-LLM/Dataset")


def test_ids_from_accepts_name_tags():
    nm = {"chair3": 7, "whiteboard1": 2}
    assert ids_from({"candidate_ids": ["chair 3", "Whiteboard_1", "#9", 4]}, nm) == [2, 4, 7, 9]


def test_ids_from_bare_number_means_the_drawn_class_tag():
    """C6f pilot: with only chairs drawn the model answered [1] for 'chair 1', which was read as internal id 1."""
    nm = {"chair1": 2, "chair3": 4, "cabinet": 1}
    assert ids_from({"candidate_ids": [1]}, nm) == [1]                          # old rule kept elsewhere
    assert ids_from({"candidate_ids": [1, "3"]}, nm, bare_class="chair") == [2, 4]
    assert ids_from({"candidate_ids": ["chair 3", 9]}, nm, bare_class="chair") == [4, 9]   # no chair 9: as before


@pytest.mark.skipif(not os.path.isdir(VISDIAL), reason="VisDial release not cloned")
def test_visdial_type_a_office():
    from sdarepro.visdial import load_type_a
    ps = load_type_a(os.path.join(VISDIAL, "Type_A_Dataset", "Office"))
    assert len(ps.dialogues) == 15 and len(ps.images_annot) == 8
    names = {o.tag for o in ps.ctx.objects}
    assert {"chair 1", "chair 11", "whiteboard 2", "door"} <= names
    oracle = [{"candidate_ids": [next(o.tag for o in ps.ctx.objects if o.obj_id == ps.dialogues[0]["target"])]}]
    rec = run_dialogue(ScriptedClient(oracle), "multi_image", ps, ps.dialogues[0])
    assert rec["found"] and rec["T_A"] == pytest.approx(1.0)


@pytest.mark.skipif(not os.path.isdir(VISDIAL), reason="VisDial release not cloned")
def test_visdial_target_class_only_views():
    """C6: only the target's class is boxed, and view 3 (a byte copy of view 2's box file) gets no box."""
    from sdarepro.prompts import FORCED_CHOICE
    from sdarepro.visdial import load_type_a
    ps = load_type_a(os.path.join(VISDIAL, "Type_A_Dataset", "Office"))
    same = lambda a, b: a.tobytes() == b.tobytes()   # noqa: E731
    wb, ch = ps.class_only_annot["whiteboard"], ps.class_only_annot["chair"]
    assert not same(wb[2], ps.images_raw[2]) and same(ch[2], ps.images_raw[2])   # view 2 has only whiteboard2
    assert same(wb[3], ps.images_raw[3]) and same(ch[3], ps.images_raw[3])       # duplicated file: no boxes
    assert not same(ps.images_annot[3], ps.images_raw[3])                         # multi_image keeps it
    wb_dlg = next(d for d in ps.dialogues if d["dialogue_id"].endswith("-A11"))
    two = [{"candidate_ids": ["whiteboard 1", "whiteboard 2"]}] * len(wb_dlg["turns"])
    client = ScriptedClient(two)
    run_dialogue(client, "target_class_only_forced", ps, wb_dlg)
    sent = [b["image"] for b in client.calls[0][1][0]["content"] if b["type"] == "image"]
    assert len(sent) == 8 and all(same(a, b) for a, b in zip(sent, wb))
    assert client.calls[-1][1][-1]["content"][0]["text"] == FORCED_CHOICE


@pytest.mark.skipif(not os.path.isdir(VISDIAL), reason="VisDial release not cloned")
def test_visdial_type_b_counts():
    from sdarepro.runner import run_count_dialogue
    from sdarepro.visdial import load_type_b
    b = load_type_b(os.path.join(VISDIAL, "Type_B_Dataset", "Meeting_room_II"))
    assert len(b["images"]) == 8 and len(b["dialogues"]) == 5
    d = b["dialogues"][0]
    rec = run_count_dialogue(ScriptedClient([{"count": t["count"]} for t in d["turns"]]), b, d)
    assert rec["count_exact_rate"] == 1.0


def test_tags_of_boxes_at_top_edge_do_not_overlap(monkeypatch):
    """M1: #29 and #30 in 42446103 view 0 both touch the top edge; the second tag hid the first."""
    from PIL import ImageDraw
    from sdarepro.annotate import ViewBoxes, draw_view
    tags, orig = [], ImageDraw.ImageDraw.rectangle

    def rec(self, xy, fill=None, **kw):
        if fill is not None:
            tags.append([float(v) for v in xy])
        return orig(self, xy, fill=fill, **kw)

    monkeypatch.setattr(ImageDraw.ImageDraw, "rectangle", rec)
    vb = ViewBoxes(frame=None, boxes={29: (213, 0, 480, 42), 30: (206, 0, 480, 190), 31: (210, 5, 300, 60)})
    draw_view(Image.new("RGB", (480, 640)), vb, {29: "stove", 30: "oven", 31: "cabinet"})
    assert len(tags) == 3
    for i in range(3):
        for j in range(i + 1, 3):
            a, b = tags[i], tags[j]
            assert a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3], (a, b)


# ---------------------------------------------------------------- live dialogue (terminal and web share sdarepro.live)
def _strip_times(recs):
    from sdarepro.live import TIME_FIELDS
    return [{k: v for k, v in r.items() if k not in TIME_FIELDS} for r in recs]


def test_live_check_input():
    from sdarepro.live import check_input, is_ee
    for ok in ["the chair next to the umbrella", "the one on the right", "between two windows"]:
        assert check_input(ok) is None, ok
    for bad in ["chair 3", "the board in view 2", "the third photo", "in the image on the left", "第二張圖的椅子",
                "三號椅子", "  "]:
        assert check_input(bad), bad
    assert is_ee(" EE ") and not is_ee("see")


def test_live_session_end_conditions(prepared, tmp_path):
    from sdarepro.live import InputRejected, LiveSession, read_records
    _, ps = prepared
    dlg = next(d for d in ps.dialogues if d["dtype"] == "A")
    out = str(tmp_path / "live.jsonl")
    other = next(o.obj_id for o in ps.ctx.objects if o.obj_id != dlg["target"])
    # never a single answer: the round counter passes 10 after round 11 (VLM.ipynb `if i > 10`)
    s = LiveSession(ScriptedClient([{"candidate_ids": [dlg["target"], other]}] * 20), ps, out, "t", dlg=dlg,
                    images=ps.images_annot)
    s.send(s.first_sentence(), auto=True)
    with pytest.raises(InputRejected):
        s.send("the chair in view 2")
    while not s.ended:
        s.send("the one near the table")
    assert s.end["reason"] == "max_round" and s.rounds == 11 and s.end["found"] is False
    # a single answer ends at once and is scored
    dlg2 = next(d for d in ps.dialogues if d["dtype"] == "A" and d["dialogue_id"] != dlg["dialogue_id"])
    s2 = LiveSession(ScriptedClient([{"candidate_ids": [dlg2["target"]]}]), ps, out, "t", dlg=dlg2, images=ps.images_annot)
    s2.send(s2.first_sentence(), auto=True)
    assert s2.end["reason"] == "single" and s2.end["found"] and s2.end["rounds"] == 1
    # ee
    dlg3 = next(d for d in ps.dialogues if d["dialogue_id"] not in (dlg["dialogue_id"], dlg2["dialogue_id"]))
    s3 = LiveSession(ScriptedClient([{"candidate_ids": [other, dlg3["target"]]}]), ps, out, "t", dlg=dlg3,
                     images=ps.images_annot)
    s3.send(s3.first_sentence(), auto=True)
    assert s3.stop()["reason"] == "ee" and s3.end["rounds"] == 1
    with pytest.raises(RuntimeError):
        s3.send("anything")
    ends = [r for r in read_records(out) if r["type"] == "end"]
    assert [e["reason"] for e in ends] == ["max_round", "single", "ee"]


def test_live_session_resumes_without_api_calls(prepared, tmp_path):
    from sdarepro.live import LiveSession, read_records
    _, ps = prepared
    dlg = next(d for d in ps.dialogues if d["dtype"] == "A")
    out = str(tmp_path / "live.jsonl")
    two = {"candidate_ids": [dlg["target"], next(o.obj_id for o in ps.ctx.objects if o.obj_id != dlg["target"])]}
    s = LiveSession(ScriptedClient([two, two]), ps, out, "t", dlg=dlg, images=ps.images_annot)
    s.send(s.first_sentence(), auto=True)
    s.send("the one near the sofa")                     # interrupted here, no end record
    again = ScriptedClient([{"candidate_ids": [dlg["target"]]}])
    r = LiveSession(again, ps, out, "t", dlg=dlg, images=ps.images_annot)
    assert again.calls == [] and r.rounds == 2 and not r.ended and r.first_sentence() is None
    r.send("the one by the window")
    sent = again.calls[0][1]
    assert len(sent) == 5 and sum(b["type"] == "image" for b in sent[0]["content"]) == 8   # images once, history kept
    assert [m["content"][-1]["text"] for m in sent if m["role"] == "user"][1] == "User: the one near the sofa"
    recs = read_records(out)
    assert [x["round"] for x in recs if x["type"] == "turn"] == [1, 2, 3] and recs[-1]["reason"] == "single"


@pytest.mark.skipif(not os.path.isdir(VISDIAL), reason="VisDial release not cloned")
def test_live_terminal_and_web_write_the_same_records(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from sdarepro.live import drive_terminal, experiment_session, read_records, translated_targets
    from sdarepro.visdial import load_type_a
    from sdarepro.webapp import create_app
    monkeypatch.setenv("SDA_API_KEY", "sk-test-never-shown")
    ps = load_type_a(os.path.join(VISDIAL, "Type_A_Dataset", "Office"))
    targets = translated_targets("results/visdial_target_fix.json", ps.name_map)
    typed = {"A1": ["the chair on the right of the lamp"], "A11": ["the board in view 2", "the board next to the red heart"]}
    term = tmp_path / "term"
    for d in ps.dialogues:
        q = d["dialogue_id"].split("-")[-1]
        if q in typed:
            it = iter(typed[q])
            drive_terminal(experiment_session(ps, d, str(term / "live__dry_run__r1.jsonl"), "dry_run", 1, targets,
                                              dry_run=True), lambda _p: next(it), say=lambda _s: None)
    web = tmp_path / "web"
    app = create_app(ps, model="dry_run", dry_run=True, out_dir=str(web), demo_dir=str(tmp_path / "demo"),
                     img_dir=str(tmp_path / "img"), allowed_hosts=("testserver",))
    c = TestClient(app)
    seen = []
    for q in ("A1", "A11"):
        assert c.post(f"/api/q/{q}/open?start=0").json()["session"]["rounds"] == 0      # showing is free
        seen.append(c.post(f"/api/q/{q}/open?start=1").text)
        for t in typed[q]:
            r = c.post(f"/api/q/{q}/send", json={"text": t})
            seen.append(r.text)
            if t == "the board in view 2":
                assert r.status_code == 422 and "不能" in r.json()["error"]
    assert _strip_times(read_records(str(web / "live__dry_run__r1.jsonl"))) == \
        _strip_times(read_records(str(term / "live__dry_run__r1.jsonl")))
    # demo records go elsewhere; the key is never sent; other hosts are refused
    n_exp = len(read_records(str(web / "live__dry_run__r1.jsonl")))
    c.post("/api/demo/new", json={"image_set": "all"})
    seen.append(c.post("/api/demo/send", json={"text": "chair 3 in view 2"}).text)   # demo: no rule check
    assert len(read_records(str(web / "live__dry_run__r1.jsonl"))) == n_exp == 6
    assert os.listdir(tmp_path / "demo")
    seen += [c.get("/api/meta").text, c.get("/api/progress").text, c.get("/").text]
    assert not any("sk-test-never-shown" in s for s in seen)
    assert TestClient(app, base_url="http://evil.example").get("/api/meta").status_code == 400
    assert c.get("/img/../../secret/0.jpg").status_code == 404 and c.get("/img/chair/9.jpg").status_code == 404
