"""results/raw/*.jsonl -> results/summary.md (+ results/summary.csv).

Reports per condition x dialogue type: n, found rate, mean score with a 95%
bootstrap CI, turns used, tokens. Also paired differences vs C1 (multi_image)
on the same dialogues, with an exact sign test on 'found'.
"""
import glob
import json
import math
import os
import random

import pandas as pd

RAW, OUT = "results/raw", "results"
recs = []
for p in glob.glob(os.path.join(RAW, "*.jsonl")):
    for line in open(p):
        if line.strip():
            r = json.loads(line)
            r["tokens_in"] = sum(x.get("in", 0) for x in r.get("replies", []))
            r["score"] = r.get("T_A", r.get("T_B", float(r.get("found", False))))
            recs.append(r)
if not recs:
    raise SystemExit("no results yet")
df = pd.DataFrame(recs)
df["dtype"] = df.get("dtype", "B").fillna("B")


def boot_ci(x, n=2000, seed=0):
    x = list(x)
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(x) for _ in x) / len(x) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n)]


def sign_test(wins, losses):
    n, k = wins + losses, min(wins, losses)
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


rows = []
for (cond, dtype), g in df.groupby(["cond", "dtype"]):
    lo, hi = boot_ci(g["score"])
    rows.append({"cond": cond, "dtype": dtype, "n": len(g), "found": g["found"].mean(),
                 "score": g["score"].mean(), "ci_lo": lo, "ci_hi": hi,
                 "turns": g.get("alpha", g.get("robot_turns")).mean(), "tokens_in": g["tokens_in"].mean()})
tab = pd.DataFrame(rows).sort_values(["dtype", "score"], ascending=[True, False])
tab.to_csv(os.path.join(OUT, "summary.csv"), index=False)

lines = ["# Results", "", "score = T_A for Type A, T_B for Type B, found rate for active mode.", "",
         tab.to_markdown(index=False, floatfmt=".3f"), "", "## Paired vs multi_image", ""]
base = df[df["cond"] == "multi_image"].set_index("dialogue_id")
for cond, g in df[df["cond"] != "multi_image"].groupby("cond"):
    g = g.set_index("dialogue_id")
    common = g.index.intersection(base.index)
    if len(common) == 0:
        continue
    d = (g.loc[common, "score"] - base.loc[common, "score"])
    w = int(((g.loc[common, "found"]) & (~base.loc[common, "found"])).sum())
    l = int(((~g.loc[common, "found"]) & (base.loc[common, "found"])).sum())
    lo, hi = boot_ci(d)
    lines.append(f"- {cond}: mean diff {d.mean():+.3f} (95% CI {lo:+.3f} to {hi:+.3f}), "
                 f"found wins/losses {w}/{l}, sign test p = {sign_test(w, l):.3f}, n = {len(common)}")
open(os.path.join(OUT, "summary.md"), "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
