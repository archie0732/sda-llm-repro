"""Generate VisDia-style dialogues from ground-truth geometry.

Every turn carries its ground-truth candidate set, which the paper's Narrowing
Score (NS) needs. Superlatives ("closest to the sofa") are evaluated over the
candidates that are still left, which is how people talk in a narrowing dialogue.
"""
from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field
from typing import Callable, Optional

import numpy as np

from .geometry import to_floor
from .scene import Object3D

NICE_NAMES = {"tv_monitor": "TV", "refrigerator": "fridge"}
# PLAN.md 3.3: dialogue targets (and scene ranking) use these classes; any class can still be a landmark
TARGET_CLASSES = ("chair", "stool", "table", "sofa")


def nice(label: str) -> str:
    return NICE_NAMES.get(label, label.replace("_", " "))


@dataclass
class Turn:
    text: str
    gt_set: list[int]
    kind: str


@dataclass
class Dialogue:
    dialogue_id: str
    scene_id: str
    dtype: str            # "A" or "B"
    target: int
    turns: list[Turn] = field(default_factory=list)

    def to_json(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class GeoContext:
    objects: list[Object3D]          # candidate universe (visible objects), obj_id assigned
    up_axis: int
    station_xy: np.ndarray
    heading_deg: float
    near_thr: float = 1.2
    near_margin: float = 0.3
    superlative_gap: float = 0.3
    height_gap: float = 0.15

    def xy(self, o: Object3D) -> np.ndarray:
        return to_floor(o.center, self.up_axis)

    def dist(self, a: Object3D, b: Object3D) -> float:
        return float(np.linalg.norm(self.xy(a) - self.xy(b)))

    def dist_robot(self, a: Object3D) -> float:
        return float(np.linalg.norm(self.xy(a) - self.station_xy))

    def height(self, o: Object3D) -> float:
        """Top of the box above its bottom = world extent along the up axis."""
        return float(np.sum(np.abs(o.rotation[:, self.up_axis]) * o.size))  # rows are box axes

    def rel_angle(self, o: Object3D) -> float:
        """Angle of the object seen from the station, 0 = robot forward, positive = left."""
        d = self.xy(o) - self.station_xy
        return (math.degrees(math.atan2(d[1], d[0])) - self.heading_deg + 180.0) % 360.0 - 180.0

    def landmarks(self, exclude_label: str) -> list[Object3D]:
        counts: dict[str, int] = {}
        for o in self.objects:
            counts[o.label] = counts.get(o.label, 0) + 1
        return [o for o in self.objects if o.label != exclude_label and counts[o.label] == 1]


# ---------------------------------------------------------------- constraints
@dataclass
class Constraint:
    kind: str
    text_first: str    # phrasing when used as (part of) the first sentence
    text_follow: str   # phrasing when used as a follow-up turn
    apply: Callable[[list[Object3D]], Optional[list[Object3D]]]  # None = not usable (ambiguous)


def _superlative(ctx: GeoContext, S: list[Object3D], score, pick_max: bool) -> Optional[list[Object3D]]:
    if len(S) < 2:
        return None
    vals = sorted(((score(o), o) for o in S), key=lambda t: t[0], reverse=pick_max)
    if abs(vals[0][0] - vals[1][0]) < ctx.superlative_gap:
        return None
    return [vals[0][1]]


def build_constraints(ctx: GeoContext, target: Object3D, allow_egocentric: bool = False) -> list[Constraint]:
    cls = nice(target.label)
    cons: list[Constraint] = []
    for L in ctx.landmarks(target.label):
        ln = nice(L.label)

        def near(S, L=L):
            d = [ctx.dist(o, L) for o in S]
            if any(ctx.near_thr < x <= ctx.near_thr + ctx.near_margin for x in d):
                return None
            return [o for o, x in zip(S, d) if x <= ctx.near_thr]

        cons.append(Constraint("near", f"the {cls} near the {ln}", f"I mean the one near the {ln}.", near))
        cons.append(Constraint(
            "closest_to", f"the {cls} closest to the {ln}", f"It's the one closest to the {ln}.",
            lambda S, L=L: _superlative(ctx, S, lambda o: ctx.dist(o, L), pick_max=False)))
        cons.append(Constraint(
            "farthest_from", f"the {cls} farthest from the {ln}", f"It's the one farthest from the {ln}.",
            lambda S, L=L: _superlative(ctx, S, lambda o: ctx.dist(o, L), pick_max=True)))
    cons.append(Constraint(
        "closest_to_robot", f"the {cls} closest to you", "The one closest to you.",
        lambda S: _superlative(ctx, S, ctx.dist_robot, pick_max=False)))
    cons.append(Constraint(
        "farthest_from_robot", f"the {cls} farthest from you", "The one farthest from you.",
        lambda S: _superlative(ctx, S, ctx.dist_robot, pick_max=True)))

    def tallest(S):
        if len(S) < 2:
            return None
        hs = sorted(((ctx.height(o), o) for o in S), key=lambda t: -t[0])
        return [hs[0][1]] if hs[0][0] - hs[1][0] >= ctx.height_gap else None

    cons.append(Constraint("tallest", f"the tallest {cls}", "It's the tallest one.", tallest))

    if allow_egocentric:  # reference-frame ablation, off by default (see PLAN.md E7)
        for name, lo, hi in (("in front of you", -45, 45), ("on your left", 45, 135),
                             ("on your right", -135, -45)):
            def side(S, lo=lo, hi=hi):
                return [o for o in S if lo <= ctx.rel_angle(o) < hi]
            cons.append(Constraint("ego_side", f"the {cls} {name}", f"The one {name}.", side))
    return cons


def _true_and_reducing(c: Constraint, S: list[Object3D], target: Object3D) -> Optional[list[Object3D]]:
    out = c.apply(S)
    if out is None or target not in out or len(out) >= len(S) or len(out) == 0:
        return None
    return out


# ---------------------------------------------------------------- generators
def gen_type_b(ctx: GeoContext, target: Object3D, dialogue_id: str, scene_id: str,
               rng: random.Random, max_turns: int = 5, allow_egocentric: bool = False) -> Optional[Dialogue]:
    """Ambiguous start ('go to the chair'), each turn narrows the set until one is left."""
    S = [o for o in ctx.objects if o.label == target.label]
    if len(S) < 2:
        return None
    dlg = Dialogue(dialogue_id, scene_id, "B", target.obj_id)
    dlg.turns.append(Turn(f"Please go to the {nice(target.label)}.", sorted(o.obj_id for o in S), "class"))
    cons = build_constraints(ctx, target, allow_egocentric)
    used: set[str] = set()
    while len(S) > 1 and len(dlg.turns) < max_turns:
        options = []
        for c in cons:
            if c.text_follow in used:
                continue
            out = _true_and_reducing(c, S, target)
            if out is not None:
                options.append((c, out))
        if not options:
            return None
        # gradual narrowing: prefer steps that keep >1 candidate while turns remain
        partial = [t for t in options if len(t[1]) > 1]
        final = [t for t in options if len(t[1]) == 1]
        turns_left = max_turns - len(dlg.turns)
        pool = partial if (partial and turns_left > 1 and rng.random() < 0.7) else (final or partial)
        c, S = rng.choice(pool)
        used.add(c.text_follow)
        dlg.turns.append(Turn(c.text_follow, sorted(o.obj_id for o in S), c.kind))
    return dlg if len(S) == 1 else None


def gen_type_a(ctx: GeoContext, target: Object3D, dialogue_id: str, scene_id: str,
               rng: random.Random, n_turns: int = 4, allow_egocentric: bool = False) -> Optional[Dialogue]:
    """First sentence already identifies one object; later turns add (redundant) evidence."""
    S0 = [o for o in ctx.objects if o.label == target.label]
    if len(S0) < 2:
        return None
    cons = build_constraints(ctx, target, allow_egocentric)
    singles = [c for c in cons if (out := _true_and_reducing(c, S0, target)) is not None and len(out) == 1]
    if not singles:
        return None
    first = rng.choice(singles)
    dlg = Dialogue(dialogue_id, scene_id, "A", target.obj_id)
    dlg.turns.append(Turn(f"Help me find {first.text_first}.", [target.obj_id], first.kind))
    extra = []
    for c in cons:
        if c is first:
            continue
        out = c.apply(S0)
        if out is not None and target in out:  # true about the target, evaluated over all of its class
            extra.append(c)
    rng.shuffle(extra)
    for c in extra[: n_turns - 1]:
        dlg.turns.append(Turn(f"Also, it is {c.text_first}.", [target.obj_id], c.kind))
    return dlg if len(dlg.turns) >= 2 else None


def target_facts(ctx: GeoContext, target: Object3D) -> list[str]:
    """True statements about the target for the simulated user (E6). Never mentions ids."""
    S0 = [o for o in ctx.objects if o.label == target.label]
    facts = [f"The target is a {nice(target.label)}. There are {len(S0)} {nice(target.label)}s visible."]
    for c in build_constraints(ctx, target, allow_egocentric=True):
        out = c.apply(S0)
        if out is not None and target in out:
            facts.append(f"It is {c.text_first}.")
    for L in ctx.landmarks(target.label):
        facts.append(f"Distance to the {nice(L.label)}: {ctx.dist(target, L):.1f} m.")
    facts.append(f"Distance to the robot: {ctx.dist_robot(target):.1f} m. Height: {ctx.height(target):.2f} m.")
    return facts
