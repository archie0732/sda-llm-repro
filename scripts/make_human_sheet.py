"""Human answer sheet for VisDial Office Type A (PLAN.md 5.0, V1 human baseline).

Writes results/human_office/index.html with the 8 annotated views and the 15 dialogues. The person
answers under the same protocol as the model (runner.run_dialogue): after each sentence pick every
object that still matches, the next sentence is shown only if more than one was picked, and the
dialogue stops at the first single pick. Answers stay hidden until the "對答案" button, which scores
with the same T_A formula as metrics.score_type_a. "下載作答紀錄" saves a JSON that can be put in
results/human_office/answers.json for comparison with the model.

The page holds the authors' images (no licence file): keep it local, never publish it.

python scripts/make_human_sheet.py
"""
import argparse
import base64
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sdarepro.prompts import view_caption  # noqa: E402
from sdarepro.visdial import load_type_a  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--root", default="third_party/SDA-LLM/Dataset")
ap.add_argument("--out", default="results/human_office")
a = ap.parse_args()

ps = load_type_a(os.path.join(a.root, "Type_A_Dataset", "Office"))
os.makedirs(os.path.join(a.out, "img"), exist_ok=True)
for i, im in enumerate(ps.images_annot):
    im.save(os.path.join(a.out, "img", f"view_{i}.jpg"), quality=90)


def order(t):
    m = re.match(r"(\D+?)\s*(\d*)$", t)
    return (m.group(1), int(m.group(2) or 0)) if m else (t, 0)


tags = sorted((o.tag for o in ps.ctx.objects), key=lambda t: (not t.startswith("chair"), order(t)))
tag_of = {o.obj_id: o.tag for o in ps.ctx.objects}
questions = [{"id": d["dialogue_id"].split("-")[-1], "turns": [t["text"] for t in d["turns"]]} for d in ps.dialogues]
# the answers are only encoded, so a glance at the page source does not give them away
key = base64.b64encode(json.dumps({d["dialogue_id"].split("-")[-1]: tag_of[d["target"]]
                                   for d in ps.dialogues}).encode()).decode()

views = "".join(f'<figure><a href="img/view_{i}.jpg" target="_blank"><img src="img/view_{i}.jpg" alt="view {i}"></a>'
                f"<figcaption>{html.escape(view_caption(i, h))}</figcaption></figure>"
                for i, h in enumerate(ps.view_headings_rel))

page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Office 人類作答</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#ddd;--card:#f6f6f6;--ok:#1a7f37;--bad:#c62828;--acc:#0b57d0}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#161616;--fg:#eee;--muted:#aaa;--line:#444;--card:#222;--ok:#57c46b;--bad:#ef7070;--acc:#8ab4f8}}}}
:root[data-theme="dark"]{{--bg:#161616;--fg:#eee;--muted:#aaa;--line:#444;--card:#222;--ok:#57c46b;--bad:#ef7070;--acc:#8ab4f8}}
*{{box-sizing:border-box}}
body{{background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,sans-serif;margin:0 auto;max-width:1280px;padding:16px}}
.views{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:8px}}
figure{{margin:0}} img{{width:100%;display:block;border-radius:4px}} figcaption{{color:var(--muted);font-size:12px}}
section.q{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin:14px 0}}
.turn{{margin:6px 0}} .turn b{{color:var(--acc)}} .opts{{display:flex;flex-wrap:wrap;gap:4px 12px;margin:6px 0}}
.opts label{{white-space:nowrap}} button{{font:inherit;padding:4px 12px;margin-right:6px;cursor:pointer}}
.picked{{color:var(--muted)}} .done{{font-weight:600}} .ok{{color:var(--ok)}} .bad{{color:var(--bad)}}
table{{border-collapse:collapse;margin-top:8px}} td,th{{border:1px solid var(--line);padding:3px 8px;text-align:left}}
.bar{{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);z-index:1}}
</style></head><body>
<h1>Office 人類作答</h1>
<p>這是作者公開的 Office 場景，共 15 題，跟模型拿到的是同樣的 8 張標註圖。規則也跟模型一樣。每一題一次只給一句話，
請勾選所有還符合描述的物件，再按「送出這一句」。只勾一個就代表你決定了，這題結束。勾兩個以上會出現下一句，
句子用完就結束。送出後不能改。全部做完再按最下面的「對答案」。點圖可以開大圖。</p>
<div class="views">{views}</div>
<div class="bar"><span id="progress"></span></div>
<div id="qs"></div>
<p><button id="check">對答案</button><button id="dl">下載作答紀錄</button><button id="reset">全部重來</button></p>
<div id="result"></div>
<script>
const Q = {json.dumps(questions, ensure_ascii=False)};
const TAGS = {json.dumps(tags, ensure_ascii=False)};
const KEY = "{key}";
const STORE = "office-human-v1";
let S = {{}};
try {{ S = JSON.parse(localStorage.getItem(STORE) || "{{}}"); }} catch (e) {{ S = {{}}; }}
function save() {{ try {{ localStorage.setItem(STORE, JSON.stringify(S)); }} catch (e) {{}} }}
function st(id) {{ return S[id] || (S[id] = {{picks: [], done: false, started: Date.now()}}); }}
function esc(s) {{ return s.replace(/[&<>]/g, c => ({{"&": "&amp;", "<": "&lt;", ">": "&gt;"}}[c])); }}
function render() {{
  const box = document.getElementById("qs"); box.innerHTML = "";
  let n = 0;
  Q.forEach((q, qi) => {{
    const s = st(q.id); if (s.done) n++;
    const sec = document.createElement("section"); sec.className = "q";
    let h = `<h3>第 ${{qi + 1}} 題</h3>`;
    s.picks.forEach((p, i) => {{
      h += `<div class="turn"><b>第 ${{i + 1}} 句</b> ${{esc(q.turns[i])}}<div class="picked">你選了 ${{p.map(esc).join("、") || "（沒有選）"}}</div></div>`;
    }});
    if (s.done) {{
      h += `<div class="done">這題作答結束</div>`;
    }} else {{
      const i = s.picks.length;
      h += `<div class="turn"><b>第 ${{i + 1}} 句</b> ${{esc(q.turns[i])}}</div><div class="opts">` +
        TAGS.map(t => `<label><input type="checkbox" value="${{esc(t)}}"> ${{esc(t)}}</label>`).join("") +
        `</div><button data-q="${{qi}}">送出這一句</button>`;
    }}
    sec.innerHTML = h; box.appendChild(sec);
  }});
  document.getElementById("progress").textContent = `已完成 ${{n}} / ${{Q.length}} 題`;
  box.querySelectorAll("button[data-q]").forEach(b => b.onclick = () => {{
    const q = Q[+b.dataset.q], s = st(q.id);
    const picks = [...b.parentElement.querySelectorAll("input:checked")].map(x => x.value);
    if (!picks.length) {{ alert("請至少勾一個"); return; }}
    s.picks.push(picks);
    if (picks.length === 1 || s.picks.length >= q.turns.length) {{ s.done = true; s.finished = Date.now(); }}
    save(); render();
  }});
}}
function score() {{
  const ans = JSON.parse(atob(KEY));
  let rows = "", sum = {{found: 0, SR: 0, AS: 0, TA: 0}};
  Q.forEach((q, qi) => {{
    const s = st(q.id), t = ans[q.id], P = s.picks, k = q.turns.length, a = P.length;
    const found = s.done && a > 0 && P[a - 1].length === 1 && P[a - 1][0] === t;
    let SR = 0, AS = 0;
    if (found) {{ SR = (k - (a - 1)) / k; AS = P.reduce((x, p) => x + (p.includes(t) ? 1 / p.length : 0), 0) / a; }}
    const TA = 0.8 * SR + 0.2 * AS;
    sum.found += found; sum.SR += SR; sum.AS += AS; sum.TA += TA;
    rows += `<tr><td>${{qi + 1}}</td><td>${{esc(t)}}</td><td>${{P.map(p => p.map(esc).join("、")).join(" → ") || "未作答"}}</td>` +
      `<td class="${{found ? "ok" : "bad"}}">${{found ? "對" : "錯"}}</td><td>${{a}}/${{k}}</td><td>${{TA.toFixed(2)}}</td></tr>`;
  }});
  const n = Q.length;
  document.getElementById("result").innerHTML =
    `<p>找對 ${{sum.found}} / ${{n}} 題，SR ${{(sum.SR / n).toFixed(3)}}，AS ${{(sum.AS / n).toFixed(3)}}，T_A ${{(sum.TA / n).toFixed(3)}}。` +
    `論文 GPT-4o 的 Office 是 SR 0.866、AS 0.835、T_A 0.86。</p>` +
    `<table><tr><th>題</th><th>正解</th><th>你的回答</th><th>結果</th><th>用了幾句</th><th>T_A</th></tr>${{rows}}</table>`;
}}
document.getElementById("check").onclick = () => {{
  const left = Q.filter(q => !st(q.id).done).length;
  if (left && !confirm(`還有 ${{left}} 題沒做完，要直接對答案嗎？`)) return;
  score();
}};
document.getElementById("dl").onclick = () => {{
  const blob = new Blob([JSON.stringify({{saved: new Date().toISOString(), answers: S}}, null, 1)], {{type: "application/json"}});
  const u = URL.createObjectURL(blob), el = document.createElement("a");
  el.href = u; el.download = "answers.json"; el.click(); URL.revokeObjectURL(u);
}};
document.getElementById("reset").onclick = () => {{
  if (confirm("確定清除全部作答？")) {{ S = {{}}; save(); document.getElementById("result").innerHTML = ""; render(); }}
}};
render();
</script></body></html>"""
open(os.path.join(a.out, "index.html"), "w", encoding="utf-8").write(page)
print(f"{len(questions)} questions, {len(tags)} tags -> {a.out}/index.html")
