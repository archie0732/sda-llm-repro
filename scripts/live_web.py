"""Local web page for live Track V dialogues (PLAN.md 5.0). Needs `pip install -e ".[web]"`.

Binds to 127.0.0.1 only; there is no option to listen on other interfaces. Do not deploy it anywhere: it
serves the authors' images (no licence) and, without --dry_run, spends the key in SDA_API_KEY.

python scripts/live_web.py --dry_run          # dry-run model, no API call
python scripts/live_web.py                    # real model from SDA_MODEL (needs SDA_API_KEY)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sdarepro.visdial import load_type_a  # noqa: E402
from sdarepro.webapp import create_app  # noqa: E402

HOST = "127.0.0.1"   # fixed on purpose

ap = argparse.ArgumentParser()
ap.add_argument("--model", default=os.environ.get("SDA_MODEL"))
ap.add_argument("--rep", type=int, default=1)
ap.add_argument("--port", type=int, default=8765)
ap.add_argument("--root", default="third_party/SDA-LLM/Dataset")
ap.add_argument("--out", default=None, help="experiment records (default results/raw_visdial, a temp folder with --dry_run)")
ap.add_argument("--demo_out", default=None, help="demo records (default results/demo, git-ignored, a temp folder with --dry_run)")
ap.add_argument("--max_round", type=int, default=10)
ap.add_argument("--dry_run", action="store_true", help="dry-run model, no API call")
a = ap.parse_args()

if not a.dry_run and not a.model:
    sys.exit("set SDA_MODEL (CLAUDE.md rule 5) or use --dry_run")
if not a.dry_run and not os.environ.get("SDA_API_KEY"):
    sys.exit("SDA_API_KEY is not set (CLAUDE.md rule 10: do not use ANTHROPIC_API_KEY)")

import tempfile  # noqa: E402

import uvicorn  # noqa: E402

if a.dry_run:   # dry-run records never land next to the experiment data
    tmp = tempfile.mkdtemp(prefix="live_web_dry_")
    a.out, a.demo_out = a.out or tmp, a.demo_out or tmp
a.out, a.demo_out = a.out or "results/raw_visdial", a.demo_out or "results/demo"

ps = load_type_a(os.path.join(a.root, "Type_A_Dataset", "Office"))
app = create_app(ps, model=a.model or "dry_run", rep=a.rep, dry_run=a.dry_run, out_dir=a.out, demo_dir=a.demo_out,
                 max_round=a.max_round)
print(f"open http://{HOST}:{a.port}/  ({'dry run, no API calls' if a.dry_run else 'model ' + a.model}), records in {a.out}")
uvicorn.run(app, host=HOST, port=a.port, log_level="warning")
