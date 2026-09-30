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


def test_parse_json_tolerates_fences():
    p = parse_json('```json\n{"candidate_ids": ["#3", 5], "count": 2}\n```')
    assert ids_from(p) == [3, 5]
    assert parse_json("no json here") is None


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
    assert geo["recall"] > 0.8 and geo["precision"] > 0.9


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
def test_visdial_type_b_counts():
    from sdarepro.runner import run_count_dialogue
    from sdarepro.visdial import load_type_b
    b = load_type_b(os.path.join(VISDIAL, "Type_B_Dataset", "Meeting_room_II"))
    assert len(b["images"]) == 8 and len(b["dialogues"]) == 5
    d = b["dialogues"][0]
    rec = run_count_dialogue(ScriptedClient([{"count": t["count"]} for t in d["turns"]]), b, d)
    assert rec["count_exact_rate"] == 1.0
