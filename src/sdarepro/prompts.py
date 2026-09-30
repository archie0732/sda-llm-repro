"""Prompt text for every condition. Keep all wording here so runs are comparable."""
from __future__ import annotations

import math

import numpy as np

from .dialogue import GeoContext, nice

# Verbatim from the authors' release (Code/VLM.ipynb, `start_instruction`); the first two
# sentences are also printed in the paper (Fig. 6 of arXiv v1, Fig. 5 of the IROS version).
PAPER_INSTRUCTION = (
    "Based on user input, identify the specific object in the image by progressively narrowing "
    "down the possibilities. If multiple objects match the description in each interaction, "
    "inform me of the number of potential matches and their IDs. Use each round of user input to refine "
    "your guesses until the unique object is confirmed by the user. Apply all previous hints to focus on "
    "the correct object and always provide the object ID with your guesses."
)

OUTPUT_RULES = (
    "Reply with JSON only, no prose outside it: "
    '{"candidate_ids": [<ID tag exactly as drawn>, ...], "count": <int>, "reason": "<one short sentence>"}. '
    "List every ID that still matches everything the user has said so far. "
    "Only use IDs that appear in the object tags. The same tag in different views is the same physical object."
)

SYSTEM_IMAGES = (
    "You are the perception module of an indoor service robot. The robot turned on the spot and took "
    "one photo per heading. Every detected object has a box and an ID tag. " + PAPER_INSTRUCTION + " " + OUTPUT_RULES
)

SYSTEM_TEXT_ONLY = (
    "You are the perception module of an indoor service robot. You cannot see images; you get a table of "
    "detected objects with their positions relative to the robot (x = metres forward, y = metres to the left). "
    "Identify the specific object the user means by progressively narrowing down the possibilities. "
    + OUTPUT_RULES
)

SYSTEM_ACTIVE = (
    "You are the perception and dialogue module of an indoor service robot. The robot turned on the spot and "
    "took one photo per heading; every object has a tag like #7 (same number = same object across views). "
    "The user wants you to go to one object. If more than one object still matches, you may ask the user ONE short "
    "question that best separates the remaining candidates; ask only about things the user can see or know "
    "(never ask about tag numbers). Reply with JSON only: either "
    '{"action": "ask", "question": "...", "candidate_ids": [...]} or '
    '{"action": "go", "candidate_ids": [<exactly one id>]}.'
)

SIM_USER = (
    "You are a person talking to a robot. You know which object you want; the facts below are all you know about it. "
    "Answer the robot's question truthfully in one short sentence using only these facts. Never mention numbers "
    "that look like tags or IDs. If the facts do not answer the question, say you are not sure and add one fact "
    "that has not been mentioned yet.\n\nFacts:\n"
)


def _tag(o) -> str:
    return getattr(o, "tag", None) or f"#{o.obj_id}"


def object_table(ctx: GeoContext) -> str:
    """Condition C3/C4 text: robot-centred coordinates, forward = view 0 heading."""
    h = math.radians(ctx.heading_deg)
    fwd = (math.cos(h), math.sin(h))
    left = (-math.sin(h), math.cos(h))
    rows = ["id | class | x_forward_m | y_left_m | distance_m | height_m"]
    for o in sorted(ctx.objects, key=lambda o: o.obj_id):
        d = ctx.xy(o) - ctx.station_xy
        if not np.all(np.isfinite(d)):
            rows.append(f"{_tag(o)} | {nice(o.label)} | unknown | unknown | unknown | unknown")
            continue
        x = d[0] * fwd[0] + d[1] * fwd[1]
        y = d[0] * left[0] + d[1] * left[1]
        h = f"{ctx.height(o):.2f}" if ctx.height(o) > 0 else "unknown"
        rows.append(f"{_tag(o)} | {nice(o.label)} | {x:.2f} | {y:.2f} | {ctx.dist_robot(o):.2f} | {h}")
    return "\n".join(rows)


def view_caption(i: int, heading_rel_deg: float) -> str:
    return f"View {i} (robot heading {heading_rel_deg:.0f} degrees counter-clockwise from view 0)"


# VisDial Type B (released without boxes or ids): the model reports counts, a human checks the final pick.
SYSTEM_COUNT = (
    "You are the perception module of an indoor service robot. The robot turned on the spot and took one photo per "
    "heading (views are in order). The user describes an object step by step. After each user turn, count how many "
    "distinct physical objects in the whole scene still match everything said so far (an object seen in two views "
    "counts once). Reply with JSON only: "
    '{"count": <int>, "where": "<view number(s) and a short description that locates the match(es); if exactly one, '
    'describe it so a person can point to it>"}.'
)
