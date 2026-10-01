"""Re-parse stored Track V replies with the current `vlm.parse_json` and re-score, without API calls.

Needed after the parse_json fix (a reply with a JSON answer followed by a corrected JSON was read as
empty). A dialogue stops at the first single-ID answer, so a re-parse that turns a turn into (or out
of) a single answer would have changed what the model saw next. Such records are NOT re-scored, only
listed, so they can be re-run. Files are rewritten in place, a copy is kept as <file>.bak.

python scripts/reparse_visdial.py
"""
import glob
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sdarepro.metrics import score_dialogue  # noqa: E402
from sdarepro.visdial import load_type_a  # noqa: E402
from sdarepro.runner import CLASS_ONLY  # noqa: E402
from sdarepro.vlm import ids_from, parse_json  # noqa: E402

ps = load_type_a("third_party/SDA-LLM/Dataset/Type_A_Dataset/Office")
dlgs = {d["dialogue_id"]: d for d in ps.dialogues}
changed, flow = [], []
for path in sorted(glob.glob("results/raw_visdial/*.jsonl")):
    recs, dirty = [json.loads(l) for l in open(path) if l.strip()], False
    for r in recs:
        if r.get("dtype") == "A" and r["cond"] != "count":
            # C6 views show one class only, so a bare number is that class's tag (same rule as runner)
            bare = (next(o.label for o in ps.ctx.objects if o.obj_id == r["target"])
                    if r["cond"] in CLASS_ONLY else None)
            new = [ids_from(parse_json(x["text"]), ps.name_map, bare) for x in r["replies"]]
            if new == r["preds"]:
                continue
            if [len(p) == 1 for p in new] != [len(p) == 1 for p in r["preds"]]:
                flow.append((os.path.basename(path), r["dialogue_id"], r["preds"], new))
                continue
            changed.append((os.path.basename(path), r["dialogue_id"], r["preds"], new))
            r.update(preds=new, **score_dialogue(dlgs[r["dialogue_id"]], new))
            dirty = True
        elif r.get("cond") == "count":
            for t in r["turns"]:
                if "text" not in t:
                    continue
                try:
                    n = int((parse_json(t["text"]) or {}).get("count"))
                except (TypeError, ValueError):
                    n = None
                if n != t["pred"]:
                    changed.append((os.path.basename(path), r["dialogue_id"], t["pred"], n))
                    t["pred"], dirty = n, True
            if dirty:
                exact = [t["pred"] == t["gt"] for t in r["turns"]]
                r.update(count_exact_rate=sum(exact) / len(exact), final_exact=exact[-1], found=exact[-1])
    if dirty:
        shutil.copy(path, path + ".bak")
        with open(path, "w") as fh:
            fh.writelines(json.dumps(r) + "\n" for r in recs)
print("re-scored:", *changed, sep="\n  ")
print("flow would change (not re-scored, re-run these):", *flow, sep="\n  ")
