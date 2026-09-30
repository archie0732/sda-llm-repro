"""End-to-end check without any dataset or API key.

python scripts/dry_run.py              # synthetic room, oracle + random scripted models
python scripts/dry_run.py --claude     # same room, real Claude calls (needs ANTHROPIC_API_KEY, SDA_MODEL)
"""
import argparse
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sdarepro.prepare import prepare_scene  # noqa: E402
from sdarepro.runner import CONDITIONS, run_dialogue  # noqa: E402
from sdarepro.synth import synthetic_room  # noqa: E402
from sdarepro.vlm import ScriptedClient  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--claude", action="store_true")
ap.add_argument("--out", default="data/prepared_synth")
a = ap.parse_args()

ps = prepare_scene(synthetic_room(), a.out, use_depth=False)
print(f"prepared {ps.scene_id}: {len(ps.ctx.objects)} objects, {len(ps.dialogues)} dialogues -> {a.out}")
rng = random.Random(0)
for dlg in ps.dialogues:
    oracle = ScriptedClient([{"candidate_ids": t["gt_set"]} for t in dlg["turns"]])
    ids = [o.obj_id for o in ps.ctx.objects]
    rand = ScriptedClient([{"candidate_ids": [rng.choice(ids)]} for _ in dlg["turns"]])
    r1 = run_dialogue(oracle, "multi_image", ps, dlg)
    r2 = run_dialogue(rand, "multi_image", ps, dlg)
    key = "T_A" if dlg["dtype"] == "A" else "T_B"
    print(f"{dlg['dialogue_id']}: oracle {key}={r1[key]:.2f}  random {key}={r2[key]:.2f}")

if a.claude:
    from sdarepro.vlm import ClaudeClient
    client = ClaudeClient()
    for cond in CONDITIONS:
        rec = run_dialogue(client, cond, ps, ps.dialogues[0])
        print(cond, rec["preds"], "found" if rec["found"] else "miss", rec["replies"][0]["text"][:200])
