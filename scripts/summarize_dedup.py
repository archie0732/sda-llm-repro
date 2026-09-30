"""results/dedup.jsonl -> results/dedup_summary.md (PLAN.md section 6).

Pools the link counts over scenes (micro average) per source x method x tau. D1 ('none') has no tau and
predicts no links, so its precision is N/A. Count error is reported as mean and mean absolute value.

python scripts/summarize_dedup.py
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sdarepro.dedup import link_scores  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--inp", default="results/dedup.jsonl")
ap.add_argument("--out", default="results/dedup_summary.md")
a = ap.parse_args()

recs = {}
for line in open(a.inp):
    if line.strip():
        r = json.loads(line)
        tau = None if r["method"] == "none" else r["tau"]
        recs[(r["source"], r["method"], tau, r["scene_id"])] = r  # the D1 row repeats once per tau run
groups = {}
for (src, method, tau, _), r in recs.items():
    groups.setdefault((src, method, tau), []).append(r)


def fmt(x):
    return "N/A" if x is None else f"{x:.2f}"


lines = ["# Cross-view de-duplication", "",
         "Precision, recall and F1 of 'same object' links, pooled over scenes. N/A = no predicted links.", "",
         "| source | method | tau (m) | scenes | links (gt) | precision | recall | F1 | count error (mean) | abs count error (mean) |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
for (src, method, tau), rs in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] != "none", kv[0][2] or 0)):
    tp, fp, fn = (sum(r[k] for r in rs) for k in ("tp", "fp", "fn"))
    s = link_scores(tp, fp, fn)
    ce = [r["count_error"] for r in rs]
    lines.append(f"| {src} | {method} | {'-' if tau is None else tau} | {len(rs)} | {tp + fn} | {fmt(s['precision'])} | "
                 f"{fmt(s['recall'])} | {fmt(s['f1'])} | {sum(ce) / len(ce):+.2f} | {sum(map(abs, ce)) / len(ce):.2f} |")
open(a.out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("\n".join(lines))
