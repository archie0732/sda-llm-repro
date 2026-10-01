"""results/raw_visdial/*.jsonl -> results/visdial_summary.md (PLAN.md section 5.0, Track V).

V1 (Type A, Office): per condition, the mean over repeats of found rate, the lenient 'final set contains the
target' rate, SR, AS, T_A, with the range over repeats, next to the paper's GPT-4o numbers for Office and a
human baseline (make_human_sheet.py, scored with metrics.score_type_a). A per-dialogue table shows the
final answers. `--fix` adds sensitivity columns (found, T_A) with corrected targets; the original targets stay the
main result. V2 (Type B): per-turn count accuracy. Also lists the dialogues whose final answer differs
between repeats, and the token cost.

Prices are per million tokens and are NOT looked up from the model id; pass them if the model changes.

python scripts/summarize_visdial.py
python scripts/summarize_visdial.py --fix results/visdial_target_fix.json
python scripts/summarize_visdial.py --price_in 2 --price_out 10 --price_cache_read 0.2 --price_cache_write 2.5
"""
import argparse
import glob
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sdarepro.metrics import score_type_a  # noqa: E402
from sdarepro.visdial import load_type_a  # noqa: E402
from sdarepro.vlm import norm_name  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--raw", default="results/raw_visdial")
ap.add_argument("--root", default="third_party/SDA-LLM/Dataset")
ap.add_argument("--out", default="results/visdial_summary.md")
ap.add_argument("--human", default="results/human_office/answers.json", help="make_human_sheet.py download")
ap.add_argument("--fix", default="", help="JSON {dialogue: corrected target tag}, sensitivity columns only")
ap.add_argument("--price_in", type=float, default=2.0)
ap.add_argument("--price_out", type=float, default=10.0)
ap.add_argument("--price_cache_read", type=float, default=0.2)
ap.add_argument("--price_cache_write", type=float, default=2.5)
a = ap.parse_args()

PAPER_OFFICE = {"SR": 0.866, "AS": 0.835, "T_A": 0.86}   # Table I, GPT-4o, Office
CONDS = ("multi_image", "grid", "text_only", "multi_image_text", "forced_choice")
ps = load_type_a(os.path.join(a.root, "Type_A_Dataset", "Office"))
tag = {o.obj_id: o.tag for o in ps.ctx.objects}
dlgs = {d["dialogue_id"]: d for d in ps.dialogues}
turns = {d["dialogue_id"]: [t["text"] for t in d["turns"]] for d in ps.dialogues}
qid = {did: did.split("-")[-1] for did in dlgs}
# sensitivity analysis only: corrected targets as {"A11": "whiteboard 2", ...}, used after the person confirmed them
fix = {}
if a.fix:
    fix = {q: ps.name_map[norm_name(t)] for q, t in json.load(open(a.fix, encoding="utf-8")).items()}

recs = []
for p in sorted(glob.glob(os.path.join(a.raw, "*.jsonl"))):
    recs += [json.loads(l) for l in open(p) if l.strip()]


def usage(r):
    rows = r.get("replies") or r.get("turns") or []
    return [sum(x.get(k, 0) or 0 for x in rows) for k in ("in", "out", "cache_read", "cache_write")]


def cost(u):
    return (u[0] * a.price_in + u[1] * a.price_out + u[2] * a.price_cache_read + u[3] * a.price_cache_write) / 1e6


def mean(x):
    return sum(x) / len(x) if x else float("nan")


def names(ids):
    return "{" + ", ".join(tag.get(i, str(i)) for i in ids) + "}"


def short(ids):
    """chair 3 -> 3, whiteboard 2 -> wb2, empty -> -"""
    return ",".join(tag.get(i, str(i)).replace("chair ", "").replace("whiteboard ", "wb") for i in ids) or "-"


def scores(did, preds, target=None):
    """metrics.score_type_a plus the lenient 'final set contains the target' for one answer sequence."""
    t = dlgs[did]["target"] if target is None else target
    s = score_type_a(t, preds, k=len(dlgs[did]["turns"]))
    s["contains"] = bool(preds) and t in preds[-1]
    s["size"] = len(preds[-1]) if preds else 0
    return s


L = ["# Track V results", "",
     f"Model(s): {', '.join(sorted({r.get('model', '?') for r in recs}))}. Every number is the mean over repeats, "
     "the range over repeats is in brackets. Type A scoring stops at the first single-ID answer (PLAN.md section 7). "
     "'contains' is a lenient measure: the final answer set includes the target, whatever its size.", ""]

# ---------------------------------------------------------------- V1
A = [r for r in recs if r.get("dtype") == "A"]
by_cond = defaultdict(lambda: defaultdict(list))            # cond -> rep -> records
for r in A:
    by_cond[r["cond"]][r.get("rep", 1)].append(r)

human = None
if os.path.exists(a.human):
    H = json.load(open(a.human, encoding="utf-8"))["answers"]
    human = {did: [[ps.name_map[norm_name(t)] for t in p] for p in H[q]["picks"]]
             for did, q in qid.items() if q in H and H[q].get("done")}

fix_col = " | found, targets fixed | T_A, targets fixed" if fix else ""
L += ["## V1 Office, Type A (15 dialogues)", "",
      f"| condition | repeats | dialogues per repeat | found | contains | final set size | SR | AS | T_A | turns used | cost per repeat (USD){fix_col} |",
      "| --- " * (11 + 2 * bool(fix)) + "|",
      f"| paper, GPT-4o | 1 | 15 | - | - | - | {PAPER_OFFICE['SR']:.3f} | {PAPER_OFFICE['AS']:.3f} | {PAPER_OFFICE['T_A']:.3f} | - | -"
      + (" | - | -" if fix else "") + " |"]
if human:
    S = [scores(did, p) for did, p in human.items()]
    row = (f"| human (same protocol, one person) | 1 | {len(S)} | {mean([s['found'] for s in S]):.3f} | "
           f"{mean([s['contains'] for s in S]):.3f} | {mean([s['size'] for s in S]):.2f} | {mean([s['SR'] for s in S]):.3f} | {mean([s['AS'] for s in S]):.3f} | "
           f"{mean([s['T_A'] for s in S]):.3f} | {mean([s['alpha'] for s in S]):.3f} | -")
    if fix:
        F = [scores(did, p, fix.get(qid[did])) for did, p in human.items()]
        row += f" | {mean([s['found'] for s in F]):.3f} | {mean([s['T_A'] for s in F]):.3f}"
    L.append(row + " |")
for cond in CONDS:
    reps = by_cond.get(cond)
    if not reps:
        continue
    cells = []
    for key in ("found", "contains", "size", "SR", "AS", "T_A", "alpha"):
        per = [mean([float(scores(r["dialogue_id"], r["preds"])[key]) for r in rs]) for rs in reps.values()]
        cells.append(f"{mean(per):.3f} [{min(per):.2f}–{max(per):.2f}]")
    n = sorted({len(rs) for rs in reps.values()})
    c = mean([sum(cost(usage(r)) for r in rs) for rs in reps.values()])
    row = f"| {cond} | {len(reps)} | {'/'.join(map(str, n))} | " + " | ".join(cells) + f" | {c:.3f}"
    if fix:
        for key in ("found", "T_A"):
            per = [mean([float(scores(r["dialogue_id"], r["preds"], fix.get(qid[r["dialogue_id"]]))[key]) for r in rs])
                   for rs in reps.values()]
            row += f" | {mean(per):.3f} [{min(per):.2f}–{max(per):.2f}]"
    L.append(row + " |")

# per-dialogue table: final answers of the human and of each condition in each repeat
present = [c for c in CONDS if c in by_cond]
L += ["", "## Per dialogue: final answers", "",
      "Chair numbers are shown bare (3 = chair 3), wb2 = whiteboard 2. Each condition cell lists the final answer of "
      "repeats 1 / 2 / 3, and * marks a correct single answer.", "",
      "| # | first sentence | author target | human | " + " | ".join(present) + " |",
      "| --- " * (4 + len(present)) + "|"]
for did in sorted(dlgs, key=lambda d: int(d.rsplit("A", 1)[1])):
    tgt = dlgs[did]["target"]

    def cell(preds):
        fin = preds[-1] if preds else []
        return short(fin) + ("*" if fin == [tgt] else "")

    hum = cell(human[did]) if human and did in human else ""
    per = []
    for c in present:
        by_rep = {r.get("rep", 1): r for rs in by_cond[c].values() for r in rs if r["dialogue_id"] == did}
        per.append(" / ".join(cell(by_rep[k]["preds"]) if k in by_rep else "" for k in sorted(by_cond[c])))
    first = turns[did][0].replace("Help me find the ", "")
    L.append(f"| {qid[did]} | {first} | {short([tgt])} | {hum} | " + " | ".join(per) + " |")

L += ["", "## Dialogues whose final answer differs between repeats", ""]
unstable = 0
for cond in CONDS:
    reps = by_cond.get(cond, {})
    if len(reps) < 2:
        continue
    final = defaultdict(dict)
    for rep, rs in reps.items():
        for r in rs:
            final[r["dialogue_id"]][rep] = (r["preds"][-1] if r["preds"] else [], r["found"])
    for did in sorted(final, key=lambda d: int(d.rsplit("A", 1)[1])):
        answers = final[did]
        if len({tuple(v[0]) for v in answers.values()}) > 1:
            unstable += 1
            got = "，".join(f"第 {k} 次 {names(v[0])}{' 對' if v[1] else ''}" for k, v in sorted(answers.items()))
            L.append(f"- {cond} {qid[did]}，目標 {tag[dlgs[did]['target']]}。{got}。對話為 {' / '.join(turns[did])}")
if not unstable:
    L.append("- 沒有（或還沒有兩次以上的重複）")

# ---------------------------------------------------------------- V2
B = [r for r in recs if r.get("cond") == "count"]
if B:
    L += ["", "## V2 Type B, object counts (40 dialogues)", "",
          "| repeats | dialogues | per-turn count exact | last turn exact | last turn count is 1 (needs a human check of `where`) | cost (USD) |",
          "| --- | --- | --- | --- | --- | --- |",
          f"| {len({r.get('rep', 1) for r in B})} | {len(B)} | {mean([r['count_exact_rate'] for r in B]):.3f} | "
          f"{mean([float(r['final_exact']) for r in B]):.3f} | {sum(r['needs_human_check'] for r in B)} | "
          f"{sum(cost(usage(r)) for r in B):.3f} |"]
    per_scene = defaultdict(list)
    for r in B:
        per_scene[r["scene_id"]].append(r)
    L += ["", "| scene | dialogues | per-turn exact | last turn exact |", "| --- | --- | --- | --- |"]
    for s, rs in sorted(per_scene.items()):
        L.append(f"| {s.replace('visdial_', '')} | {len(rs)} | {mean([r['count_exact_rate'] for r in rs]):.2f} | "
                 f"{mean([float(r['final_exact']) for r in rs]):.2f} |")

# ---------------------------------------------------------------- cost
tot = [sum(x) for x in zip(*(usage(r) for r in recs))] if recs else [0, 0, 0, 0]
L += ["", "## Tokens and cost", "",
      f"Uncached input {tot[0]}, output {tot[1]}, cache read {tot[2]}, cache write {tot[3]} tokens. "
      f"At {a.price_in}/{a.price_out}/{a.price_cache_read}/{a.price_cache_write} USD per million "
      f"(input/output/cache read/cache write) this is {cost(tot):.3f} USD."]
open(a.out, "w", encoding="utf-8").write("\n".join(L) + "\n")
sys.stdout.reconfigure(encoding="utf-8")
print("\n".join(L))
