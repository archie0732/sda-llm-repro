"""Human check of V2 (VisDial Type B): did the model's final `where` point at the described object?

The release has only per-turn counts for Type B, no boxes or target ids, so the last step of V2 needs a
person. For each dialogue the page shows every user sentence with the released count and the model's
count, the model's final `where` text, the views it names (large) and all 8 views (small). The person
marks 指對 / 指錯 / 看不出來; choices are kept in the browser and downloaded as JSON
(results/v2_check/answers.json). Same idea as make_human_sheet.py.

Output: results/v2_check/index.html (+ img/). Holds the authors' images: keep local, not in git.

python scripts/make_v2_check.py
"""
import argparse
import glob
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sdarepro.visdial import load_type_b  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--root", default="third_party/SDA-LLM/Dataset")
ap.add_argument("--raw", default="results/raw_visdial")
ap.add_argument("--out", default="results/v2_check")
a = ap.parse_args()
os.makedirs(os.path.join(a.out, "img"), exist_ok=True)

recs = {}
for p in sorted(glob.glob(os.path.join(a.raw, "trackB_count__*.jsonl"))):
    for r in map(json.loads, open(p)):
        recs[r["dialogue_id"]] = r   # one repeat for V2; a later file would win
folders = sorted(os.path.dirname(p) for p in glob.glob(os.path.join(a.root, "Type_B_Dataset", "**", "*Multi-turn_dialogue.csv"),
                                                      recursive=True))
items = []
for f in folders:
    b = load_type_b(f)
    sid = b["scene_id"].replace("visdial_", "")
    for i, im in enumerate(b["images"]):
        path = os.path.join(a.out, "img", f"{sid}_view{i}.jpg")
        if not os.path.exists(path):
            im.save(path, quality=85)
    for d in b["dialogues"]:
        r = recs.get(d["dialogue_id"])
        if r is None:
            continue
        where = r["turns"][-1]["where"] or ""
        named = sorted({int(x) for x in re.findall(r"views?\s*(\d+(?:\s*(?:,|and|&)\s*\d+)*)", where, re.I)
                        for x in re.findall(r"\d+", x)} & set(range(len(b["images"]))))
        items.append({"id": d["dialogue_id"].replace("visdial_", ""), "scene": sid, "n": len(b["images"]), "named": named,
                      "turns": [{"text": t["text"], "gt": t["count"], "pred": rt["pred"]} for t, rt in zip(d["turns"], r["turns"])],
                      "where": where})

cards = ""
for k, it in enumerate(items, start=1):
    rows = "".join(f"<tr><td>{html.escape(t['text'])}</td><td>{t['gt']}</td><td>{t['pred'] if t['pred'] is not None else '無法解析'}</td></tr>"
                   for t in it["turns"])
    big = "".join(f'<figure><a href="img/{it["scene"]}_view{v}.jpg" target="_blank"><img class="big" src="img/{it["scene"]}_view{v}.jpg"></a>'
                  f"<figcaption>view {v}（模型提到的）</figcaption></figure>" for v in it["named"])
    small = "".join(f'<a href="img/{it["scene"]}_view{v}.jpg" target="_blank" title="view {v}"><img class="small" src="img/{it["scene"]}_view{v}.jpg">'
                    f"<span>{v}</span></a>" for v in range(it["n"]))
    radios = "".join(f'<label><input type="radio" name="{it["id"]}" value="{v}"> {v}</label>' for v in ("指對", "指錯", "看不出來"))
    cards += f"""<section class="q" id="q{k}"><h3>{k}. {html.escape(it['id'])}</h3>
<table><tr><th>使用者的話</th><th>作者的數量</th><th>模型的數量</th></tr>{rows}</table>
<p class="where"><b>模型最後的 where</b> {html.escape(it['where'])}</p>
<div class="big-row">{big or '<p class="muted">where 裡沒有提到 view 編號，請看下面全部 8 張</p>'}</div>
<div class="strip">{small}</div>
<div class="ans">{radios} <input class="note" data-id="{html.escape(it['id'])}" placeholder="備註（可不填）" size="40"></div></section>"""

page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>V2 where 檢查</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#ddd;--card:#f6f6f6;--acc:#0b57d0}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#161616;--fg:#eee;--muted:#aaa;--line:#444;--card:#222;--acc:#8ab4f8}}}}
:root[data-theme="dark"]{{--bg:#161616;--fg:#eee;--muted:#aaa;--line:#444;--card:#222;--acc:#8ab4f8}}
*{{box-sizing:border-box}}
body{{background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,sans-serif;margin:0 auto;max-width:1280px;padding:16px}}
section.q{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:14px 0}}
table{{border-collapse:collapse}} td,th{{border:1px solid var(--line);padding:3px 8px;text-align:left}}
.where{{border-left:3px solid var(--acc);padding-left:8px}} .muted{{color:var(--muted)}}
.big-row{{display:flex;flex-wrap:wrap;gap:8px}} figure{{margin:0}} img.big{{max-height:420px;max-width:100%}}
figcaption{{color:var(--muted);font-size:12px}} .strip{{display:flex;flex-wrap:wrap;gap:4px;margin:6px 0}}
.strip a{{position:relative;color:#fff}} img.small{{height:90px}} .strip span{{position:absolute;left:3px;top:0;text-shadow:0 0 3px #000}}
.ans label{{margin-right:14px}} .bar{{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);z-index:1}}
button{{font:inherit;padding:4px 12px}}
</style></head><body>
<h1>V2 模型最後指的物件檢查</h1>
<p>作者的 Type B 只公開每一句話符合的物件數，沒有框也沒有目標編號，所以最後一句模型指的是不是對的物件要人看。
每一組列出每句話、作者的數量、模型的數量，以及模型最後的 where 文字。上面的大圖是 where 提到的視角，下面一排是全部 8 張，點圖可以開大圖。
請選指對、指錯或看不出來，全部做完按「下載」存成 answers.json，放到 results/v2_check/。</p>
<div class="bar"><span id="progress"></span> <button id="dl">下載 answers.json</button></div>
{cards}
<script>
const IDS = {json.dumps([it["id"] for it in items])}, STORE = "v2-where-check-v1";
let S = {{}};
try {{ S = JSON.parse(localStorage.getItem(STORE) || "{{}}"); }} catch (e) {{ S = {{}}; }}
function save() {{ try {{ localStorage.setItem(STORE, JSON.stringify(S)); }} catch (e) {{}} }}
function prog() {{ document.getElementById("progress").textContent = `已判斷 ${{IDS.filter(i => S[i] && S[i].verdict).length}} / ${{IDS.length}} 組`; }}
IDS.forEach(id => {{
  S[id] = S[id] || {{}};
  document.querySelectorAll(`input[name="${{CSS.escape(id)}}"]`).forEach(r => {{
    if (S[id].verdict === r.value) r.checked = true;
    r.onchange = () => {{ S[id].verdict = r.value; save(); prog(); }};
  }});
}});
document.querySelectorAll("input.note").forEach(n => {{
  const id = n.dataset.id; n.value = S[id].note || ""; n.oninput = () => {{ S[id].note = n.value; save(); }};
}});
document.getElementById("dl").onclick = () => {{
  const b = new Blob([JSON.stringify({{saved: new Date().toISOString(), answers: S}}, null, 1)], {{type: "application/json"}});
  const u = URL.createObjectURL(b), el = document.createElement("a"); el.href = u; el.download = "answers.json"; el.click();
}};
prog();
</script></body></html>"""
open(os.path.join(a.out, "index.html"), "w", encoding="utf-8").write(page)
print(f"{len(items)} dialogues, {sum(1 for it in items if not it['named'])} without a view number -> {a.out}/index.html")
