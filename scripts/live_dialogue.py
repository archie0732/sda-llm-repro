"""Live Track V dialogue, the way the authors' Code/VLM.ipynb runs it (PLAN.md 5.0, live protocol).

For each Office question the first sentence of the answer file is sent automatically, then the person types
the next sentence in the terminal. The dialogue ends when
  - the person types `ee` (as in VLM.ipynb, cell 0 lines 47-48),
  - the model answers exactly one ID,
  - or after the round in which the round counter passes 10 (VLM.ipynb `if i > 10`, lines 75-78).
The views box only the target's class (C6 images, like the authors' label/chair/). The system prompt is the
authors' start_instruction verbatim plus the shared JSON output rules (prompts.SYSTEM_LIVE).

The person's sentences may only describe what can be seen: no ID numbers, no "view 3" or "the third photo".
Inputs with digits or view words are refused and asked again.

Every round is appended to results/raw_visdial/live__<model>__r<rep>.jsonl as soon as the reply arrives, with
the person's sentence, the model's candidates and timestamps. A rerun skips finished questions and continues an
interrupted one from its stored rounds (the conversation is rebuilt from the stored texts, no API call).

python scripts/live_dialogue.py --dry_run                     # scripted model and scripted typing, no API
python scripts/live_dialogue.py --only A1 A11                 # real run (needs SDA_API_KEY, SDA_MODEL)
"""
import argparse
import json
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sdarepro.metrics import score_type_a  # noqa: E402
from sdarepro.prompts import SYSTEM_LIVE, view_caption  # noqa: E402
from sdarepro.runner import append_jsonl  # noqa: E402
from sdarepro.visdial import load_type_a  # noqa: E402
from sdarepro.vlm import ScriptedClient, ids_from, norm_name  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--model", default=os.environ.get("SDA_MODEL"))
ap.add_argument("--rep", type=int, default=1)
ap.add_argument("--root", default="third_party/SDA-LLM/Dataset")
ap.add_argument("--out", default=None, help="default results/raw_visdial, or a temp folder with --dry_run")
ap.add_argument("--targets", default="results/visdial_target_fix.json", help="A11-A14 in our labels (PLAN.md 5.0)")
ap.add_argument("--only", nargs="*", help="question ids, e.g. A1 A11")
ap.add_argument("--max_round", type=int, default=10, help="stop after the round whose counter exceeds this (authors: 10)")
ap.add_argument("--dry_run", action="store_true", help="scripted model and typing, output in a temp folder")
a = ap.parse_args()

# the person describes only what is visible: no ID numbers, no "view 3" or "the third photo"
FORBIDDEN = re.compile(r"\d|\b(views?|images?|pictures?|photos?|frames?|tags?|ids?)\b|第.*張|張圖|號", re.I)


def allowed(text: str) -> bool:
    return not FORBIDDEN.search(text)


ps = load_type_a(os.path.join(a.root, "Type_A_Dataset", "Office"))
tag = {o.obj_id: o.tag for o in ps.ctx.objects}
label = {o.obj_id: o.label for o in ps.ctx.objects}
trans = {}
if a.targets and os.path.exists(a.targets):
    for q, v in json.load(open(a.targets, encoding="utf-8")).items():
        trans[q] = ps.name_map[norm_name(v["target"] if isinstance(v, dict) else v)]
dialogues = [d for d in ps.dialogues if not a.only or d["dialogue_id"].split("-")[-1] in a.only]

if a.dry_run:
    out_dir = a.out or tempfile.mkdtemp(prefix="live_dry_")
    model = "dry_run"
    script = {   # per question: model replies in order, typed sentences in order
        "A1": ([{"candidate_ids": ["chair 1", "chair 2"], "count": 2, "reason": "both near the lamp"},
                {"candidate_ids": ["chair 2"], "count": 1, "reason": "the right one"}],
               ["the chair on the right of the lamp"]),
        "A11": ([{"candidate_ids": ["whiteboard 1", "whiteboard 2"], "count": 2, "reason": "two boards"}],
                ["the board in view 2", "ee"]),
    }
    dialogues = [d for d in dialogues if d["dialogue_id"].split("-")[-1] in script]
else:
    out_dir, model = a.out or "results/raw_visdial", a.model
    if not model:
        sys.exit("set SDA_MODEL (CLAUDE.md rule 5)")
out = os.path.join(out_dir, f"live__{model.replace('/', '_')}__r{a.rep}.jsonl")
if not a.dry_run:
    from sdarepro.vlm import ClaudeClient
    live_client = ClaudeClient(model=model)

# resume: finished questions and stored rounds of an interrupted one
stored, ended = {}, set()
if os.path.exists(out):
    for r in map(json.loads, open(out, encoding="utf-8")):
        if r["type"] == "turn":
            stored.setdefault(r["dialogue_id"], []).append(r)
        elif r["type"] == "end":
            ended.add(r["dialogue_id"])


def finish(dlg, rounds, reason, preds):
    q = dlg["dialogue_id"].split("-")[-1]
    tgt = trans.get(q, dlg["target"])
    k_csv = len(dlg["turns"])
    s = score_type_a(tgt, preds, k=k_csv)        # T_A with k = sentences in the answer file (PLAN.md 7)
    s["SR"] = max(0.0, s["SR"])
    s["T_A"] = 0.8 * s["SR"] + 0.2 * s["AS"] if s["found"] else 0.0
    rec = {"type": "end", "dialogue_id": dlg["dialogue_id"], "model": model, "rep": a.rep, "reason": reason,
           "rounds": rounds, "csv_turns": k_csv, "target": tgt, "author_target": dlg["target"],
           "final_ids": preds[-1] if preds else [], "found": s["found"], "T_A_kcsv": s["T_A"],
           "time": time.time()}
    append_jsonl(out, rec)
    print(f"  -> end ({reason}) after {rounds} round(s), final {[tag[i] for i in rec['final_ids']]}, "
          f"target {tag[tgt]}, {'found' if s['found'] else 'not found'}")


for dlg in dialogues:
    did = dlg["dialogue_id"]
    q = did.split("-")[-1]
    if did in ended:
        print(f"{q} already finished, skipped")
        continue
    if a.dry_run:
        client = ScriptedClient(script[q][0])
        typed = iter(script[q][1])
        ask = lambda prompt: (lambda s: (print(prompt + s), s)[1])(next(typed))   # noqa: E731
    else:
        client, ask = live_client, input
    cls = label[dlg["target"]]
    blocks = []
    for i, (img, h) in enumerate(zip(ps.class_only_annot[cls], ps.view_headings_rel)):
        blocks += [{"type": "text", "text": view_caption(i, h)}, {"type": "image", "image": img}]
    # rebuild an interrupted conversation from the stored texts
    messages, preds = [], []
    for r in stored.get(did, []):
        messages.append({"role": "user", "content": (blocks if not messages else []) + [{"type": "text", "text": f"User: {r['user']}"}]})
        messages.append({"role": "assistant", "content": [{"type": "text", "text": r["reply"]}]})
        preds.append(r["ids"])
    rnd = len(preds)
    print(f"\n=== {q} ({tag[dlg['target']]} in the answer file, {len(dlg['turns'])} sentence(s) there)"
          + (f", resuming after round {rnd}" if rnd else ""))
    if preds and len(preds[-1]) == 1:
        finish(dlg, rnd, "single", preds)
        continue
    while True:
        rnd += 1
        print(f"Round {rnd} Dialogue")
        if rnd == 1:
            text, auto = dlg["turns"][0]["text"], True
            print("Me (from the answer file):", text)
        else:
            auto = False
            while True:
                text = ask("請輸入描述（輸入 'ee' 來結束）：").strip()
                if text.lower() == "ee" or (text and allowed(text)):
                    break
                print("  只能描述看得到的特徵，不能用數字、編號或第幾張圖，請重新輸入。")
            if text.lower() == "ee":
                finish(dlg, rnd - 1, "ee", preds)
                break
        t_user = time.time()
        messages.append({"role": "user", "content": (blocks if rnd == 1 else []) + [{"type": "text", "text": f"User: {text}"}]})
        r = client.respond(SYSTEM_LIVE, messages)
        ids = ids_from(r.parsed, ps.name_map, cls)     # one class drawn: a bare number is that class's tag
        messages.append({"role": "assistant", "content": [{"type": "text", "text": r.text}]})
        preds.append(ids)
        append_jsonl(out, {"type": "turn", "dialogue_id": did, "model": model, "rep": a.rep, "round": rnd,
                           "user": text, "auto": auto, "reply": r.text, "ids": ids,
                           "candidates": [tag.get(i, str(i)) for i in ids], "t_user": t_user,
                           "t_reply": time.time(), "in": r.input_tokens, "out": r.output_tokens,
                           "cache_read": r.cache_read_tokens, "cache_write": r.cache_write_tokens})
        print(f"{model}: {[tag.get(i, str(i)) for i in ids]}  ({(r.parsed or {}).get('reason', '')})")
        if len(ids) == 1:
            finish(dlg, rnd, "single", preds)
            break
        if rnd > a.max_round:
            print("please ask again")
            finish(dlg, rnd, "max_round", preds)
            break

# summary: found rate and mean rounds do not depend on k
ends = [r for r in map(json.loads, open(out, encoding="utf-8")) if r["type"] == "end"] if os.path.exists(out) else []
if ends:
    print(f"\n{len(ends)} finished: found {sum(r['found'] for r in ends) / len(ends):.3f}, "
          f"mean rounds {sum(r['rounds'] for r in ends) / len(ends):.2f}, "
          f"T_A (k = answer-file length) {sum(r['T_A_kcsv'] for r in ends) / len(ends):.3f}")
print("records:", out)
