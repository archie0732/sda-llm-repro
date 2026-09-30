"""Whiteboard label check for VisDial Office (A11-A13 look off by one against the drawn labels).

Crops every whiteboard box of the authors' LabelMe files out of the 8 raw views, shows each crop with
its view and label next to the full view, the map coordinates from Object_coordinate_points.csv, and
the four whiteboard dialogues. The person marks which labelled board each clue (heart, writing, cable)
is next to; the choices are saved in the browser and can be downloaded as JSON
(results/visdial_check/whiteboards_answers.json).

Output: results/visdial_check/whiteboards.html (+ wb/ images). Holds the authors' images: keep local.

python scripts/make_whiteboard_sheet.py
"""
import argparse
import csv
import glob
import html
import json
import os
import re
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sdarepro.annotate import _font  # noqa: E402
from sdarepro.visdial import load_type_a  # noqa: E402
from sdarepro.vlm import norm_name  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--scene", default="third_party/SDA-LLM/Dataset/Type_A_Dataset/Office")
ap.add_argument("--out", default="results/visdial_check")
ap.add_argument("--pad", type=float, default=0.3, help="crop margin as a fraction of the box size")
a = ap.parse_args()
os.makedirs(os.path.join(a.out, "wb"), exist_ok=True)

coords = {}
for r in csv.reader(open(os.path.join(a.scene, "Object_coordinate_points.csv"), encoding="utf-8-sig")):
    if r and r[0].startswith("whiteboard"):
        coords[norm_name(r[0])] = (r[1], r[2])

crops, seen = [], set()
for p in sorted(glob.glob(os.path.join(a.scene, "Object_Bounding_Box", "color_image_*.json")),
                key=lambda q: int(re.findall(r"(\d+)\.json$", q)[0])):
    v = int(re.findall(r"(\d+)\.json$", p)[0])
    shapes = [s for s in json.load(open(p))["shapes"] if s["label"].lower().startswith("whiteboard")]
    if not shapes:
        continue
    img = Image.open(os.path.join(a.scene, "RGB_image", f"color_image_{v}.jpg")).convert("RGB")
    full = img.copy()
    d = ImageDraw.Draw(full)
    font = _font(max(18, img.width // 40))
    for s in shapes:
        (x0, y0), (x1, y1) = s["points"][:2]
        x0, x1, y0, y1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
        d.rectangle([x0, y0, x1, y1], outline=(230, 25, 75), width=5)
        d.text((x0 + 6, y0 + 4), s["label"], fill=(230, 25, 75), font=font)
        pw, ph = (x1 - x0) * a.pad, (y1 - y0) * a.pad
        box = (max(0, int(x0 - pw)), max(0, int(y0 - ph)), min(img.width, int(x1 + pw)), min(img.height, int(y1 + ph)))
        crop = img.crop(box)
        cd = ImageDraw.Draw(crop)
        cd.rectangle([x0 - box[0], y0 - box[1], x1 - box[0], y1 - box[1]], outline=(230, 25, 75), width=4)
        name = f"wb/view{v}_{norm_name(s['label'])}.jpg"
        crop.save(os.path.join(a.out, name), quality=90)
        key = (norm_name(s["label"]), tuple(round(t) for t in (x0, y0, x1, y1)))
        crops.append({"view": v, "label": s["label"], "img": name, "box": [round(t) for t in (x0, y0, x1, y1)],
                      "same_box_as_earlier_view": key in seen})
        seen.add(key)
    full.thumbnail((720, 720))
    full.save(os.path.join(a.out, f"wb/view{v}_full.jpg"), quality=88)

ps = load_type_a(a.scene)
tag = {o.obj_id: o.tag for o in ps.ctx.objects}
wb_dlgs = [(d["dialogue_id"].split("-")[-1], tag[d["target"]], [t["text"] for t in d["turns"]])
           for d in ps.dialogues if tag[d["target"]].startswith("whiteboard")]
labels = sorted({c["label"] for c in crops}, key=lambda s: int(re.sub(r"\D", "", s) or 0))
labels_txt = [re.sub(r"(\D+)(\d+)", r"\1 \2", s) for s in labels]

cards = ""
for c in crops:
    note = "（跟前一張圖的框座標完全相同）" if c["same_box_as_earlier_view"] else ""
    cards += (f'<div class="card"><h3>view {c["view"]}，標籤 {html.escape(c["label"])}{note}</h3>'
              f'<div class="pair"><figure><img src="{c["img"]}"><figcaption>框放大（紅框是作者的標註框，外擴 {int(a.pad * 100)}%）</figcaption></figure>'
              f'<figure><img src="wb/view{c["view"]}_full.jpg"><figcaption>整張 view {c["view"]}</figcaption></figure></div>'
              f'<p class="muted">框 x {c["box"][0]}–{c["box"][2]}，y {c["box"][1]}–{c["box"][3]}</p></div>')
coord_rows = "".join(f"<tr><td>{html.escape(l)}</td><td>{' , '.join(coords[norm_name(l)]) if norm_name(l) in coords else '（CSV 裡沒有）'}</td></tr>"
                     for l in labels_txt)
dlg_rows = "".join(f"<tr><td>{q}</td><td>{html.escape(' / '.join(t))}</td><td>{html.escape(tgt)}</td></tr>" for q, tgt, t in wb_dlgs)
clues = [("heart", "愛心"), ("writing", "寫字"), ("cable", "電線")]
opts = labels_txt + ["看不出來"]
q_html = "".join(f'<div class="clue"><b>{zh}</b> 在哪一塊白板旁邊（或上面）？ ' +
                 "".join(f'<label><input type="radio" name="{k}" value="{html.escape(o)}"> {html.escape(o)}</label>' for o in opts) +
                 "</div>" for k, zh in clues)

page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>白板標籤檢查</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#ddd;--card:#f6f6f6}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#161616;--fg:#eee;--muted:#aaa;--line:#444;--card:#222}}}}
:root[data-theme="dark"]{{--bg:#161616;--fg:#eee;--muted:#aaa;--line:#444;--card:#222}}
body{{background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,sans-serif;margin:0 auto;max-width:1200px;padding:16px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:14px 0}}
.pair{{display:flex;flex-wrap:wrap;gap:10px}} figure{{margin:0;flex:1 1 320px}} img{{max-width:100%;max-height:420px;display:block}}
figcaption,.muted{{color:var(--muted);font-size:12px}} table{{border-collapse:collapse}} td,th{{border:1px solid var(--line);padding:3px 8px}}
.clue{{margin:8px 0}} .clue label{{margin-right:12px;white-space:nowrap}} button{{font:inherit;padding:4px 12px}}
</style></head><body>
<h1>Office 白板標籤檢查</h1>
<p>A11 到 A13 你跟 Claude 各自作答的答案相同，都跟作者的正解差一號，而且作者的座標 CSV 沒有 whiteboard_2。
下面是作者標註檔裡每一個白板框，左邊是放大圖，右邊是整張圖。請看完後在最下面選愛心、寫字、電線各在哪一塊白板旁邊，
再按「下載」存成 whiteboards_answers.json。這一步只是確認，正解還沒有改。</p>
<h2>作者的四題白板對話</h2>
<table><tr><th>題</th><th>對話</th><th>作者正解</th></tr>{dlg_rows}</table>
<h2>作者座標 CSV 裡的白板</h2>
<table><tr><th>標籤</th><th>地圖座標 (x, y)</th></tr>{coord_rows}</table>
<h2>每一個白板框</h2>
{cards}
<h2>你的判斷</h2>
<div id="qs">{q_html}</div>
<p>備註 <input id="note" size="80"></p>
<p><button id="dl">下載 whiteboards_answers.json</button></p>
<script>
const KEYS = {json.dumps([k for k, _ in clues])}, STORE = "office-whiteboards-v1";
let S = {{}};
try {{ S = JSON.parse(localStorage.getItem(STORE) || "{{}}"); }} catch (e) {{ S = {{}}; }}
function save() {{ try {{ localStorage.setItem(STORE, JSON.stringify(S)); }} catch (e) {{}} }}
KEYS.forEach(k => document.querySelectorAll(`input[name="${{k}}"]`).forEach(r => {{
  if (S[k] === r.value) r.checked = true;
  r.onchange = () => {{ S[k] = r.value; save(); }};
}}));
const note = document.getElementById("note"); note.value = S.note || ""; note.oninput = () => {{ S.note = note.value; save(); }};
document.getElementById("dl").onclick = () => {{
  const b = new Blob([JSON.stringify({{saved: new Date().toISOString(), ...S}}, null, 1)], {{type: "application/json"}});
  const u = URL.createObjectURL(b), el = document.createElement("a"); el.href = u; el.download = "whiteboards_answers.json"; el.click();
}};
</script></body></html>"""
open(os.path.join(a.out, "whiteboards.html"), "w", encoding="utf-8").write(page)
print(f"{len(crops)} whiteboard boxes in views {sorted({c['view'] for c in crops})} -> {a.out}/whiteboards.html")
