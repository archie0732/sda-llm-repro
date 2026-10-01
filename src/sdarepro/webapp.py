"""Local web page for live Track V dialogues (scripts/live_web.py). Same rules and records as the terminal version:
every action goes through sdarepro.live.LiveSession.

Safety rules (CLAUDE.md 6 and 10, PLAN.md 5.0):
- served on 127.0.0.1 only, with a Host header check against DNS rebinding;
- the API key is read by ClaudeClient inside this process only, never sent to the page, written or printed;
- the authors' images are served from results/visdial_check/target_only/ (git-ignored), never copied to docs/.

Experiment mode runs Office A0-A14 into results/raw_visdial/live__<model>__r<rep>.jsonl. Demo mode (any image
set, any sentence) writes to results/demo/ (git-ignored), so it never mixes with the experiment data.
"""

import os
import threading
import time
from typing import Optional

from .live import (DryRunClient, InputRejected, LiveSession, check_input, experiment_session, is_ee, question_id,
                   read_records, summary, translated_targets, usage_cost)

STATIC = os.path.join(os.path.dirname(__file__), "web")
SETS = ("chair", "whiteboard", "all")


def create_app(ps, model: str, rep: int = 1, dry_run: bool = False, out_dir: str = "results/raw_visdial",
               demo_dir: str = "results/demo", img_dir: str = "results/visdial_check/target_only",
               targets_path: str = "results/visdial_target_fix.json", max_round: int = 10,
               allowed_hosts: tuple = ("127.0.0.1", "localhost"), client=None):
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.trustedhost import TrustedHostMiddleware
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel

    model_name = "dry_run" if dry_run else model
    exp_out = os.path.join(out_dir, f"live__{model_name.replace('/', '_')}__r{rep}.jsonl")
    demo_out = os.path.join(demo_dir, f"demo__{model_name.replace('/', '_')}__{time.strftime('%Y%m%d')}.jsonl")
    targets = translated_targets(targets_path, ps.name_map)
    dlgs = {question_id(d): d for d in ps.dialogues}
    order = sorted(dlgs, key=lambda q: int(q[1:]))
    tag = {o.obj_id: o.tag for o in ps.ctx.objects}
    label = {o.obj_id: o.label for o in ps.ctx.objects}

    # images: written once per start into the git-ignored folder, served from there
    os.makedirs(img_dir, exist_ok=True)
    image_sets = {"chair": ps.class_only_annot["chair"], "whiteboard": ps.class_only_annot["whiteboard"],
                  "all": ps.images_annot}
    for s, ims in image_sets.items():
        for i, im in enumerate(ims):
            im.save(os.path.join(img_dir, f"office_{s}_view_{i}.jpg"), quality=92)
    dup = set(ps.dup_views or [])

    def boxes_for(s: str) -> list[list[dict]]:
        out = []
        for v, vb in enumerate(ps.view_boxes):
            keep = [] if (s != "all" and v in dup) else [
                {"id": o, "tag": tag[o], "box": b} for o, b in sorted(vb.items()) if s == "all" or label[o] == s]
            out.append(keep)
        return out

    lock = threading.Lock()
    state = {"client": client, "exp": {}, "demo": None, "demo_n": 0}

    def real_client():
        if state["client"] is None:
            from .vlm import ClaudeClient      # reads SDA_API_KEY here, in the server process only
            state["client"] = ClaudeClient(model=model)
        return state["client"]

    def exp_session(q: str) -> LiveSession:
        if q not in dlgs:
            raise HTTPException(404, f"no question {q}")
        if q not in state["exp"]:
            state["exp"][q] = experiment_session(ps, dlgs[q], exp_out, model_name, rep, targets,
                                                 client=None if dry_run else real_client(), dry_run=dry_run,
                                                 max_round=max_round)
        return state["exp"][q]

    def view(s: LiveSession, mode: str, image_set: str) -> dict:
        d = s.state()
        d.update(mode=mode, image_set=image_set, q=question_id(s.dlg) if s.dlg else None)
        if s.dlg:
            d.update(target_tag=tag[s.target], author_tag=tag[s.author_target], first=s.dlg["turns"][0]["text"],
                     n_sentences=len(s.dlg["turns"]))
        if s.end:
            d["end"] = {k: s.end.get(k) for k in ("reason", "rounds", "found", "T_A_kcsv")}
            d["end"]["final"] = [tag.get(i, str(i)) for i in s.end["final_ids"]]
        return d

    def progress() -> dict:
        recs = read_records(exp_out)
        per = {q: {"status": "todo", "rounds": 0} for q in order}
        for r in recs:
            q = r["dialogue_id"].split("-")[-1]
            if q not in per:
                continue
            if r["type"] == "turn":
                per[q]["rounds"] = max(per[q]["rounds"], r["round"])
                if per[q]["status"] == "todo":
                    per[q]["status"] = "active"
            elif r["type"] == "end":
                per[q]["status"] = "found" if r.get("found") else "missed"
                per[q]["rounds"] = r["rounds"]
        demo_recs = [r for r in read_records(demo_out)]
        return {"questions": [{"q": q, **per[q]} for q in order], "summary": summary(recs),
                "usage": usage_cost(recs), "demo_usage": usage_cost(demo_recs)}

    def act(fn):
        try:
            with lock:
                return fn()
        except InputRejected as e:
            raise HTTPException(422, e.reason)
        except HTTPException:
            raise
        except Exception as e:   # API errors: the message never contains the key
            raise HTTPException(502, f"{type(e).__name__}: {str(e)[:300]}")

    app = FastAPI(title="SDA-LLM live dialogue (local)", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    class Text(BaseModel):
        text: str

    class DemoNew(BaseModel):
        image_set: str = "chair"

    @app.get("/")
    def index():
        return FileResponse(os.path.join(STATIC, "index.html"))

    @app.get("/img/{image_set}/{i}.jpg")
    def image(image_set: str, i: int):
        if image_set not in SETS or not 0 <= i < len(ps.view_boxes):
            raise HTTPException(404)
        return FileResponse(os.path.join(img_dir, f"office_{image_set}_view_{i}.jpg"))

    @app.get("/api/meta")
    def meta():
        return {"model": model_name, "rep": rep, "dry_run": dry_run, "records": exp_out.replace(os.sep, "/"),
                "demo_records": demo_out.replace(os.sep, "/"), "max_round": max_round,
                "views": [{"w": im.width, "h": im.height, "heading": round(h)}
                          for im, h in zip(ps.images_annot, ps.view_headings_rel)],
                "boxes": {s: boxes_for(s) for s in SETS},
                "questions": [{"q": q, "first": dlgs[q]["turns"][0]["text"], "n_sentences": len(dlgs[q]["turns"]),
                               "image_set": label[dlgs[q]["target"]]} for q in order]}

    @app.get("/api/progress")
    def get_progress():
        return progress()

    @app.post("/api/q/{q}/open")
    def open_q(q: str, start: int = 1):
        """start=0 only shows the question (page load never spends money), start=1 sends the first sentence."""
        def run():
            s = exp_session(q)
            if start and s.first_sentence() and not s.ended:
                s.send(s.first_sentence(), auto=True)
            return {"session": view(s, "experiment", label[s.dlg["target"]]), "progress": progress()}
        return act(run)

    @app.post("/api/q/{q}/send")
    def send_q(q: str, body: Text):
        def run():
            s = exp_session(q)
            if is_ee(body.text):
                s.stop()
            else:
                s.send(body.text)
            return {"session": view(s, "experiment", label[s.dlg["target"]]), "progress": progress()}
        return act(run)

    @app.post("/api/q/{q}/ee")
    def ee_q(q: str):
        def run():
            s = exp_session(q)
            s.stop()
            return {"session": view(s, "experiment", label[s.dlg["target"]]), "progress": progress()}
        return act(run)

    @app.post("/api/check")
    def check(body: Text):
        return {"reason": None if is_ee(body.text) else check_input(body.text)}

    @app.post("/api/demo/new")
    def demo_new(body: DemoNew):
        def run():
            if body.image_set not in SETS:
                raise HTTPException(404, f"no image set {body.image_set}")
            state["demo_n"] += 1
            ims = image_sets[body.image_set]
            cls = None if body.image_set == "all" else body.image_set
            tags = [o.tag for o in sorted(ps.ctx.objects, key=lambda o: o.obj_id) if cls is None or o.label == cls]
            c = DryRunClient(tags) if dry_run else real_client()
            did = f"demo-{time.strftime('%H%M%S')}-{state['demo_n']}"
            state["demo"] = (LiveSession(c, ps, demo_out, model_name, rep, images=ims, bare_class=cls,
                                         max_round=max_round, check=False, dialogue_id=did,
                                         extra={"mode": "demo", "image_set": body.image_set}), body.image_set)
            return {"session": view(state["demo"][0], "demo", body.image_set), "progress": progress()}
        return act(run)

    def demo_or_404():
        if state["demo"] is None:
            raise HTTPException(404, "start a demo conversation first")
        return state["demo"]

    @app.post("/api/demo/send")
    def demo_send(body: Text):
        def run():
            s, image_set = demo_or_404()
            if is_ee(body.text):
                s.stop()
            else:
                s.send(body.text)
            return {"session": view(s, "demo", image_set), "progress": progress()}
        return act(run)

    @app.post("/api/demo/ee")
    def demo_ee():
        def run():
            s, image_set = demo_or_404()
            s.stop()
            return {"session": view(s, "demo", image_set), "progress": progress()}
        return act(run)

    @app.exception_handler(HTTPException)
    def http_error(request, exc: HTTPException):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    return app
