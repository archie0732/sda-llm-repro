"""Scores from the SDA-LLM paper (arXiv 2410.12802v1, Section V).

Interpretation choices (the paper is terse; see PLAN.md "Metric interpretation"):
- A dialogue stops at the first turn where the model returns exactly one id
  (the robot would drive there), or when the scripted turns run out.
- alpha = number of turns consumed.
- found = the final prediction is exactly {target}.
- Type A:  SR = (k - (alpha - 1)) / k if found else 0
           AS = (1/alpha) * sum_i [target in pred_i] / |pred_i|   (0 if not found)
           T_A = 0.8 SR + 0.2 AS
- Type B:  AR = 1 if found else 0
           NS = (1/alpha) * sum_i Jaccard(gt_i, pred_i)
           T_B = 0.6 AR + 0.4 NS
"""
from __future__ import annotations


def jaccard(a, b) -> float:
    a, b = set(a), set(b)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def score_type_a(target: int, preds: list[list[int]], k: int) -> dict:
    alpha = len(preds)
    found = alpha > 0 and set(preds[-1]) == {target}
    if not found:
        return {"found": False, "alpha": alpha, "SR": 0.0, "AS": 0.0, "T_A": 0.0}
    sr = (k - (alpha - 1)) / k
    acc = sum((1.0 / len(p)) if (target in p and p) else 0.0 for p in preds) / alpha
    return {"found": True, "alpha": alpha, "SR": sr, "AS": acc, "T_A": 0.8 * sr + 0.2 * acc}


def score_type_b(target: int, preds: list[list[int]], gt_sets: list[list[int]]) -> dict:
    alpha = len(preds)
    found = alpha > 0 and set(preds[-1]) == {target}
    ns = sum(jaccard(g, p) for g, p in zip(gt_sets[:alpha], preds)) / alpha if alpha else 0.0
    ar = 1.0 if found else 0.0
    return {"found": found, "alpha": alpha, "AR": ar, "NS": ns, "T_B": 0.6 * ar + 0.4 * ns}


def score_dialogue(dlg: dict, preds: list[list[int]]) -> dict:
    gts = [t["gt_set"] for t in dlg["turns"]]
    if dlg["dtype"] == "A":
        return score_type_a(dlg["target"], preds, k=len(dlg["turns"]))
    return score_type_b(dlg["target"], preds, gts)
