"""Run one condition over prepared scenes and write JSONL records.

Conditions (PLAN.md section 5):
    C1 multi_image       8 annotated views as separate images (paper setting)
    C2 grid              the 8 views pasted into one image
    C3 text_only         object table only, no image (the missing baseline)
    C4 multi_image_text  C1 + object table
    C5 forced_choice     C1, but after the last user sentence a system message demands exactly one ID
    C6 target_class_only C1, but the views box only the target's class (VisDial, like the authors' label/chair/)
    C6f target_class_only_forced   C6 + the C5 system message
    E6 active            robot may ask questions, simulated user answers
"""
from __future__ import annotations

import json
import os
from typing import Optional

from .dialogue import target_facts
from .metrics import score_dialogue
from .prepare import PreparedScene
from .prompts import (FORCED_CHOICE, SIM_USER, SYSTEM_ACTIVE, SYSTEM_IMAGES, SYSTEM_TEXT_ONLY, object_table,
                      view_caption)
from .vlm import Reply, VLMClient, ids_from

CONDITIONS = ("multi_image", "grid", "text_only", "multi_image_text", "forced_choice",
              "target_class_only", "target_class_only_forced")
FORCED = ("forced_choice", "target_class_only_forced")
CLASS_ONLY = ("target_class_only", "target_class_only_forced")


def context_blocks(cond: str, ps: PreparedScene, dlg: Optional[dict] = None) -> tuple[str, list[dict]]:
    blocks: list[dict] = []
    if cond in ("multi_image", "multi_image_text", "forced_choice") + CLASS_ONLY:
        images = ps.images_annot
        if cond in CLASS_ONLY:
            label = next(o.label for o in ps.ctx.objects if o.obj_id == dlg["target"])
            images = ps.class_only_annot[label]
        for i, (img, h) in enumerate(zip(images, ps.view_headings_rel)):
            blocks.append({"type": "text", "text": view_caption(i, h)})
            blocks.append({"type": "image", "image": img})
    elif cond == "grid":
        blocks.append({"type": "text", "text": "All views pasted into one image, view 0 top-left, row by row."})
        blocks.append({"type": "image", "image": ps.grid_annot})
    if cond in ("text_only", "multi_image_text"):
        blocks.append({"type": "text", "text": "Detected objects:\n" + object_table(ps.ctx)})
    system = SYSTEM_TEXT_ONLY if cond == "text_only" else SYSTEM_IMAGES
    return system, blocks


def run_dialogue(client: VLMClient, cond: str, ps: PreparedScene, dlg: dict,
                 stop_on_singleton: bool = True) -> dict:
    system, ctx_blocks = context_blocks(cond, ps, dlg)
    bare = next(o.label for o in ps.ctx.objects if o.obj_id == dlg["target"]) if cond in CLASS_ONLY else None
    messages: list[dict] = []
    preds, replies = [], []
    for i, turn in enumerate(dlg["turns"]):
        content = (ctx_blocks if i == 0 else []) + [{"type": "text", "text": f"User: {turn['text']}"}]
        messages.append({"role": "user", "content": content})
        send = messages
        if cond in FORCED and i == len(dlg["turns"]) - 1:
            # a mid-conversation system message keeps the cached images valid (the top-level system would not)
            send = messages + [{"role": "system", "content": [{"type": "text", "text": FORCED_CHOICE}]}]
        r: Reply = client.respond(system, send)
        ids = ids_from(r.parsed, ps.name_map, bare)
        preds.append(ids)
        replies.append({"text": r.text, "in": r.input_tokens, "out": r.output_tokens,
                        "cache_read": r.cache_read_tokens, "cache_write": r.cache_write_tokens,
                        "latency": r.latency_s, "stop": r.stop_reason})
        messages.append({"role": "assistant", "content": [{"type": "text", "text": r.text}]})
        if stop_on_singleton and len(ids) == 1:
            break
    score = score_dialogue(dlg, preds)
    return {"dialogue_id": dlg["dialogue_id"], "scene_id": ps.scene_id, "dtype": dlg["dtype"], "cond": cond,
            "model": getattr(client, "model", client.name), "target": dlg["target"],
            "gt_sets": [t["gt_set"] for t in dlg["turns"]], "preds": preds, "replies": replies, **score}


def run_active(robot: VLMClient, user: VLMClient, ps: PreparedScene, dlg: dict, max_turns: int = 5) -> dict:
    """E6: same target as a scripted dialogue, but the robot asks and a simulated user answers."""
    target = next(o for o in ps.ctx.objects if o.obj_id == dlg["target"])
    facts = "\n".join(target_facts(ps.ctx, target))
    _, ctx_blocks = context_blocks("multi_image", ps)
    messages = [{"role": "user", "content": ctx_blocks + [{"type": "text", "text": f"User: {dlg['turns'][0]['text']}"}]}]
    log, final = [], []
    for turn in range(max_turns):
        r = robot.respond(SYSTEM_ACTIVE, messages)
        p = r.parsed or {}
        ids = ids_from(p, ps.name_map)
        log.append({"robot": r.text, "ids": ids})
        messages.append({"role": "assistant", "content": [{"type": "text", "text": r.text}]})
        if p.get("action") == "go" or turn == max_turns - 1:
            final = ids
            break
        q = p.get("question", "Which one do you mean?")
        a = user.respond(SIM_USER + facts, [{"role": "user", "content": [{"type": "text", "text": f"Robot asks: {q}"}]}])
        log[-1]["user"] = a.text
        messages.append({"role": "user", "content": [{"type": "text", "text": f"User: {a.text}"}]})
    return {"dialogue_id": dlg["dialogue_id"], "scene_id": ps.scene_id, "cond": "active",
            "target": dlg["target"], "found": final == [dlg["target"]], "robot_turns": len(log),
            "scripted_turns": len(dlg["turns"]), "log": log}


def append_jsonl(path: str, rec: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(rec) + "\n")


def done_ids(path: str) -> set[tuple[str, str]]:
    """(dialogue_id, cond) pairs already in a results file, for resumable runs."""
    if not os.path.exists(path):
        return set()
    return {(r["dialogue_id"], r["cond"]) for r in map(json.loads, open(path)) if r}


def run_count_dialogue(client: VLMClient, bundle: dict, dlg: dict) -> dict:
    """VisDial Type B protocol: compare the model's per-turn count with the released object count."""
    from .prompts import SYSTEM_COUNT

    blocks: list[dict] = []
    for i, img in enumerate(bundle["images"]):
        blocks += [{"type": "text", "text": f"View {i}"}, {"type": "image", "image": img}]
    messages, per_turn = [], []
    for i, t in enumerate(dlg["turns"]):
        messages.append({"role": "user", "content": (blocks if i == 0 else []) + [{"type": "text", "text": f"User: {t['text']}"}]})
        r = client.respond(SYSTEM_COUNT, messages)
        try:
            n = int((r.parsed or {}).get("count"))
        except (TypeError, ValueError):
            n = None
        per_turn.append({"gt": t["count"], "pred": n, "where": (r.parsed or {}).get("where", ""), "in": r.input_tokens,
                         "out": r.output_tokens, "cache_read": r.cache_read_tokens,
                         "cache_write": r.cache_write_tokens, "stop": r.stop_reason, "text": r.text})
        messages.append({"role": "assistant", "content": [{"type": "text", "text": r.text}]})
    exact = [p["pred"] == p["gt"] for p in per_turn]
    return {"dialogue_id": dlg["dialogue_id"], "scene_id": bundle["scene_id"], "cond": "count", "dtype": "B",
            "model": getattr(client, "model", client.name), "turns": per_turn,
            "count_exact_rate": sum(exact) / len(exact), "final_exact": exact[-1],
            "found": exact[-1],  # proxy only; the final pick itself needs a human check of 'where'
            "needs_human_check": dlg["turns"][-1]["count"] == 1}
