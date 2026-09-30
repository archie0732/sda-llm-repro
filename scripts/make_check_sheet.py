"""M2 acceptance: sample prepared dialogues into a local HTML sheet for a human check (PLAN.md section 10).

For each sampled dialogue the sheet shows the turns with their ground-truth sets, the numbers each
sentence was generated from (distances, heights), a top-down map with the target highlighted, and the
annotated views where the candidates can be seen. Output holds dataset images: it stays local
(results/m2_check/ is git-ignored), never publish it.

python scripts/make_check_sheet.py --n 10 --seed 0
"""
import argparse
import csv
import html
import json
import os
import random
import shutil
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sdarepro.dialogue import nice  # noqa: E402
from sdarepro.geometry import to_floor  # noqa: E402
from sdarepro.prepare import load_prepared  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--prepared", default="data/prepared")
ap.add_argument("--csv", default="data/selected_scenes.csv", help="only scenes in this list")
ap.add_argument("--out", default="results/m2_check")
ap.add_argument("--n", type=int, default=10)
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--recheck", nargs="*", default=[], help="views flagged in an earlier check, as <video_id>:<view>")
ap.add_argument("--old", nargs="*", default=["v1=results/m2_check_v1/img"],
                help="earlier versions of the annotated views, as <caption>=<folder>, oldest first")
a = ap.parse_args()

wanted = {r["video_id"] for r in csv.DictReader(open(a.csv))}
scenes, pool = {}, []
for vid in sorted(os.listdir(a.prepared)):
    d = os.path.join(a.prepared, vid)
    if vid in wanted and os.path.isfile(os.path.join(d, "scene.json")):
        scenes[vid] = (load_prepared(d), json.load(open(os.path.join(d, "scene.json"))), d)
        pool += [(vid, dl) for dl in scenes[vid][0].dialogues]
sample = random.Random(a.seed).sample(pool, min(a.n, len(pool)))
# start clean: images copied by an earlier run would otherwise survive a re-preparation (stale views)
shutil.rmtree(os.path.join(a.out, "img"), ignore_errors=True)
os.makedirs(os.path.join(a.out, "img"), exist_ok=True)

recheck = []
for item in a.recheck:
    vid, i = item.split(":")
    new = f"img/{vid}_view_{i}_annot.jpg"
    figs = []
    for k, spec in enumerate(a.old):
        cap, folder = spec.split("=", 1)
        old = f"img/old{k}_{vid}_view_{i}_annot.jpg"
        if os.path.exists(os.path.join(folder, f"{vid}_view_{i}_annot.jpg")):
            shutil.copy(os.path.join(folder, f"{vid}_view_{i}_annot.jpg"), os.path.join(a.out, old))
            figs.append(f'<figure><img src="{old}"><figcaption>{html.escape(cap)} {vid} view {i}</figcaption></figure>')
    shutil.copy(os.path.join(a.prepared, vid, f"view_{i}_annot.jpg"), os.path.join(a.out, new))
    figs.append(f'<figure><img src="{new}"><figcaption>新版 {vid} view {i}</figcaption></figure>')
    recheck.append(f"<div class=pics>{''.join(figs)}</div>")


def evidence(ctx, text, S, landmarks):
    """Numbers behind one sentence, over the candidates S that were left before it."""
    t = text.lower()
    if "you" in t:
        return "到機器人距離 " + "、".join(f"#{o.obj_id} {ctx.dist_robot(o):.2f} m" for o in S)
    if "tallest" in t:
        return "高度 " + "、".join(f"#{o.obj_id} {ctx.height(o):.2f} m" for o in S)
    for L in landmarks:
        if f"the {nice(L.label).lower()}" in t:
            return (f"到 {nice(L.label)}（#{L.obj_id}）的中心距離 "
                    + "、".join(f"#{o.obj_id} {ctx.dist(o, L):.2f} m" for o in S))
    return ""


def top_down(ctx, target, landmark_ids, cand_ids, path):
    fig, ax = plt.subplots(figsize=(5, 5))
    up = ctx.up_axis
    for o in ctx.objects:
        axes = [i for i in range(3) if np.argmax(np.abs(o.rotation[i])) != up][:2]  # rows are box axes
        c = to_floor(o.center, up)
        corners = []
        for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1), (1, 1)):
            p = o.center + sx * o.rotation[axes[0]] * o.size[axes[0]] / 2 + sy * o.rotation[axes[1]] * o.size[axes[1]] / 2
            corners.append(to_floor(p, up))
        corners = np.array(corners)
        col = "red" if o.obj_id == target else "tab:blue" if o.obj_id in landmark_ids else \
            "tab:orange" if o.obj_id in cand_ids else "0.6"
        ax.plot(corners[:, 0], corners[:, 1], color=col, lw=2 if col != "0.6" else 1)
        ax.text(c[0], c[1], f"#{o.obj_id}\n{nice(o.label)}", ha="center", va="center", fontsize=7, color=col)
    s = ctx.station_xy
    h = np.radians(ctx.heading_deg)
    ax.plot(*s, "k^", ms=9)
    ax.annotate("", xy=(s[0] + 0.8 * np.cos(h), s[1] + 0.8 * np.sin(h)), xytext=s, arrowprops=dict(arrowstyle="->"))
    ax.set_aspect("equal")
    ax.set_title("top-down (m)  red=target  orange=candidates  blue=landmarks  ^=robot, arrow=view 0", fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


rows, blocks = [], []
for k, (vid, dl) in enumerate(sample, start=1):
    ps, meta, d = scenes[vid]
    ctx = ps.ctx
    by_id = {o.obj_id: o for o in ctx.objects}
    tgt = by_id[dl["target"]]
    cand = set(dl["turns"][0]["gt_set"]) if dl["dtype"] == "B" else {o.obj_id for o in ctx.objects if o.label == tgt.label}
    landmarks = ctx.landmarks(tgt.label)
    lm_ids = {L.obj_id for L in landmarks
              if any(f"the {nice(L.label).lower()}" in t["text"].lower() for t in dl["turns"])}
    map_name = f"img/{k:02d}_map.png"
    top_down(ctx, tgt.obj_id, lm_ids, cand, os.path.join(a.out, map_name))
    views = [i for i, vb in enumerate(meta["view_boxes"]) if {int(x) for x in vb} & (cand | lm_ids)]
    imgs = []
    for i in views:
        name = f"img/{vid}_view_{i}_annot.jpg"
        if not os.path.exists(os.path.join(a.out, name)):
            shutil.copy(os.path.join(d, f"view_{i}_annot.jpg"), os.path.join(a.out, name))
        imgs.append(f'<figure><img src="{name}"><figcaption>view {i}</figcaption></figure>')
    S = [by_id[i] for i in sorted(cand)]
    turn_html = []
    for j, t in enumerate(dl["turns"]):
        ev = evidence(ctx, t["text"], S, landmarks) if j > 0 or dl["dtype"] == "A" else ""
        turn_html.append(f"<li><b>{html.escape(t['text'])}</b> <code>{t['kind']}</code> 正解集合 "
                         f"{', '.join('#' + str(x) for x in t['gt_set'])}"
                         + (f"<div class=ev>{ev}</div>" if ev else "") + "</li>")
        if dl["dtype"] == "B":
            S = [by_id[i] for i in t["gt_set"]]
    rows.append(f"<tr><td>{k}</td><td>{dl['dialogue_id']}</td><td>Type {dl['dtype']}</td>"
                f"<td>#{tgt.obj_id} {nice(tgt.label)}</td><td></td><td></td></tr>")
    blocks.append(f"""<section id="d{k}"><h2>{k}. {dl['dialogue_id']}（Type {dl['dtype']}，目標 #{tgt.obj_id} {nice(tgt.label)}）</h2>
<ol>{''.join(turn_html)}</ol>
<div class=pics><figure><img src="{map_name}"><figcaption>俯視圖</figcaption></figure>{''.join(imgs)}</div></section>""")

page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>M2 對話檢查</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#ddd}}
@media (prefers-color-scheme: dark){{:root{{--bg:#161616;--fg:#eee;--muted:#aaa;--line:#444}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,sans-serif;margin:0 auto;max-width:1200px;padding:16px}}
table{{border-collapse:collapse}} td,th{{border:1px solid var(--line);padding:4px 10px}}
section{{border-top:2px solid var(--line);margin-top:28px}} .ev{{color:var(--muted);font-size:13px}}
.pics{{display:flex;flex-wrap:wrap;gap:8px}} figure{{margin:0}} img{{max-height:360px;max-width:100%}}
figcaption{{color:var(--muted);font-size:12px}}</style></head><body>
<h1>M2 對話人工檢查</h1>
<p>從 {len(scenes)} 個場景共 {len(pool)} 組對話中隨機抽 {len(sample)} 組（seed {a.seed}）。每一組請看三件事。
第一是標註圖上目標與地標的框和編號對不對。第二是每一句話對目標是不是真的成立，而且人看圖也會這樣說。
第三是正解集合有沒有漏掉或多放候選。灰字是生成時用的數字，候選是這句話之前還剩下的物件。
PLAN.md 第 10 節的驗收標準是錯誤率低於 10%。</p>
{('<section><h2>上次標出問題的圖</h2><p>由左到右是舊版到新版，最右邊是這次的結果。</p>'
  + ''.join(recheck) + '</section>') if recheck else ''}
<table><tr><th>#</th><th>對話</th><th>類型</th><th>目標</th><th>對或錯</th><th>備註</th></tr>{''.join(rows)}</table>
{''.join(blocks)}</body></html>"""
open(os.path.join(a.out, "index.html"), "w", encoding="utf-8").write(page)
print(f"{len(sample)} of {len(pool)} dialogues from {len(scenes)} scenes -> {a.out}/index.html")
