"""Live Track V dialogue, shared by the terminal (scripts/live_dialogue.py) and the web page (scripts/live_web.py).

The protocol follows the authors' Code/VLM.ipynb (PLAN.md 5.0, live protocol):
- the first sentence of the answer file is sent automatically, the person types the next ones;
- `ee` ends the question (VLM.ipynb cell 0 lines 47-48);
- after the round in which the round counter passes `max_round` (10) the question ends (lines 75-78,
  `if i > 10`, so at most 11 rounds);
- an answer with exactly one ID also ends it (our addition: the authors' code waits for the person).
The views box only the target's class (C6 images). The system prompt is prompts.SYSTEM_LIVE.

The person may only describe what is visible: no ID numbers, no "view 3", no "the third photo"
(`check_input`). Every round is appended to the JSONL file as soon as the reply arrives, an `end` record
closes a question, and a new session for the same question rebuilds the conversation from the stored
texts, so an interrupted question continues without repeating any API call.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Callable, Optional

from .metrics import score_type_a
from .prompts import SYSTEM_LIVE, view_caption
from .vlm import Reply, VLMClient, ids_from, norm_name, parse_json

# USD per million tokens, the same defaults as scripts/summarize_visdial.py (input, output, cache read, cache write)
PRICES = (2.0, 10.0, 0.2, 2.5)
TIME_FIELDS = ("t_user", "t_reply", "time")   # the only fields that differ between two identical runs

FORBIDDEN = re.compile(r"\d|\b(views?|images?|pictures?|photos?|frames?|tags?|ids?)\b|第.*張|張圖|號", re.I)
RULE_MSG = "只能描述看得到的特徵，不能用數字、編號或第幾張圖，請重新輸入。"


class InputRejected(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def check_input(text: str) -> Optional[str]:
    """Why a typed sentence breaks the answering rules (PLAN.md 5.0), or None when it is allowed."""
    if not text.strip():
        return "請輸入一句話。"
    if FORBIDDEN.search(text):
        return RULE_MSG
    return None


def is_ee(text: str) -> bool:
    return text.strip().lower() == "ee"


def translated_targets(path: str, name_map: dict) -> dict:
    """{'A11': obj_id, ...}: the authors' whiteboard targets in our labels (results/visdial_target_fix.json)."""
    if not path or not os.path.exists(path):
        return {}
    out = {}
    for q, v in json.load(open(path, encoding="utf-8")).items():
        out[q] = name_map[norm_name(v["target"] if isinstance(v, dict) else v)]
    return out


def read_records(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def usage_cost(records: list[dict]) -> dict:
    u = [sum(r.get(k, 0) or 0 for r in records if r.get("type") == "turn") for k in ("in", "out", "cache_read", "cache_write")]
    return {"input": u[0], "output": u[1], "cache_read": u[2], "cache_write": u[3],
            "usd": sum(x * p for x, p in zip(u, PRICES)) / 1e6}


def _append(path: str, rec: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


class DryRunClient(VLMClient):
    """No API call. Round 1 lists the target and one more object of the shown class, later rounds only the target.
    Without a target (demo) it lists the first two tags, then the first one."""

    name = "dry_run"
    model = "dry_run"

    def __init__(self, tags: list[str], target_tag: Optional[str] = None):
        self.tags, self.target_tag = list(tags), target_tag
        self.calls: list[tuple[str, list[dict]]] = []

    def respond(self, system: str, messages: list[dict]) -> Reply:
        self.calls.append((system, list(messages)))
        rnd = sum(m["role"] == "user" for m in messages)
        first = self.target_tag or (self.tags[0] if self.tags else "")
        other = next((t for t in self.tags if t != first), first)
        if rnd == 1:
            r = {"candidate_ids": [first, other], "count": 2, "reason": f"dry run: {first} and {other} both fit"}
        else:
            r = {"candidate_ids": [first], "count": 1, "reason": f"dry run: {first} fits everything said so far"}
        text = json.dumps(r)
        return Reply(text=text, parsed=parse_json(text))


class LiveSession:
    """One question (or one demo conversation). All rules and the JSONL format live here."""

    def __init__(self, client: VLMClient, ps, out: str, model: str, rep: int = 1, dlg: Optional[dict] = None,
                 target: Optional[int] = None, images: Optional[list] = None, bare_class: Optional[str] = None,
                 max_round: int = 10, check: bool = True, dialogue_id: Optional[str] = None,
                 extra: Optional[dict] = None):
        self.client, self.ps, self.out, self.model, self.rep = client, ps, out, model, rep
        self.dlg, self.max_round, self.check, self.extra = dlg, max_round, check, extra or {}
        self.dialogue_id = dialogue_id or dlg["dialogue_id"]
        self.author_target = dlg["target"] if dlg else None
        self.target = target if target is not None else self.author_target
        self.bare_class = bare_class
        self.tag = {o.obj_id: o.tag for o in ps.ctx.objects}
        self.blocks = []
        for i, (img, h) in enumerate(zip(images, ps.view_headings_rel)):
            self.blocks += [{"type": "text", "text": view_caption(i, h)}, {"type": "image", "image": img}]
        self.messages: list[dict] = []
        self.turns: list[dict] = []
        self.end: Optional[dict] = None
        for r in read_records(out):
            if r.get("dialogue_id") != self.dialogue_id:
                continue
            if r["type"] == "turn":
                self._push(r["user"], r["reply"])
                self.turns.append(r)
            elif r["type"] == "end":
                self.end = r
        if self.end is None and self.turns:     # interrupted after a reply that should have ended the question
            if len(self.turns[-1]["ids"]) == 1:
                self._finish("single")
            elif self.rounds > self.max_round:
                self._finish("max_round")

    # ------------------------------------------------------------------ state
    @property
    def rounds(self) -> int:
        return len(self.turns)

    @property
    def ended(self) -> bool:
        return self.end is not None

    @property
    def preds(self) -> list[list[int]]:
        return [t["ids"] for t in self.turns]

    def first_sentence(self) -> Optional[str]:
        return self.dlg["turns"][0]["text"] if self.dlg and not self.turns else None

    def _push(self, text: str, reply: str) -> None:
        self.messages.append({"role": "user", "content": (self.blocks if not self.messages else [])
                              + [{"type": "text", "text": f"User: {text}"}]})
        self.messages.append({"role": "assistant", "content": [{"type": "text", "text": reply}]})

    # ------------------------------------------------------------------ actions
    def send(self, text: str, auto: bool = False) -> dict:
        """One round: the person's sentence (or the automatic first one) and the model's reply."""
        if self.ended:
            raise RuntimeError(f"{self.dialogue_id} has already ended ({self.end['reason']})")
        text = text.strip()
        if not auto and self.check:
            reason = check_input(text)
            if reason:
                raise InputRejected(reason)
        t_user = time.time()
        msgs = self.messages + [{"role": "user", "content": (self.blocks if not self.messages else [])
                                 + [{"type": "text", "text": f"User: {text}"}]}]
        r = self.client.respond(SYSTEM_LIVE, msgs)
        ids = ids_from(r.parsed, self.ps.name_map, self.bare_class)
        rec = {"type": "turn", "dialogue_id": self.dialogue_id, "model": self.model, "rep": self.rep,
               "round": self.rounds + 1, "user": text, "auto": auto, "reply": r.text, "ids": ids,
               "candidates": [self.tag.get(i, str(i)) for i in ids], "reason": (r.parsed or {}).get("reason", ""),
               "t_user": t_user, "t_reply": time.time(), "in": r.input_tokens, "out": r.output_tokens,
               "cache_read": r.cache_read_tokens, "cache_write": r.cache_write_tokens, **self.extra}
        _append(self.out, rec)
        self._push(text, r.text)
        self.turns.append(rec)
        if len(ids) == 1:
            self._finish("single")
        elif self.rounds > self.max_round:
            self._finish("max_round")
        return rec

    def stop(self) -> dict:
        """The person typed `ee`."""
        if self.ended:
            return self.end
        return self._finish("ee")

    def _finish(self, reason: str) -> dict:
        rec = {"type": "end", "dialogue_id": self.dialogue_id, "model": self.model, "rep": self.rep,
               "reason": reason, "rounds": self.rounds, "final_ids": self.preds[-1] if self.turns else [],
               "time": time.time(), **self.extra}
        if self.target is not None:
            # found and rounds do not depend on k; T_A uses k = sentences in the answer file (PLAN.md 7)
            k = len(self.dlg["turns"]) if self.dlg else max(1, self.rounds)
            s = score_type_a(self.target, self.preds, k=k)
            sr = max(0.0, s["SR"])
            rec.update(csv_turns=k, target=self.target, author_target=self.author_target, found=s["found"],
                       T_A_kcsv=(0.8 * sr + 0.2 * s["AS"]) if s["found"] else 0.0)
        _append(self.out, rec)
        self.end = rec
        return rec

    def state(self) -> dict:
        return {"dialogue_id": self.dialogue_id, "rounds": self.rounds, "ended": self.ended,
                "end": self.end, "turns": [{k: t[k] for k in ("round", "user", "auto", "ids", "candidates", "reason")}
                                           for t in self.turns]}


def drive_terminal(session: LiveSession, ask: Callable[[str], str], say: Callable[[str], None] = print) -> dict:
    """The terminal loop of VLM.ipynb on top of a session; the web page calls the same session methods."""
    tag = session.tag
    if session.first_sentence():
        say("Round 1 Dialogue")
        say(f"Me (from the answer file): {session.first_sentence()}")
        rec = session.send(session.first_sentence(), auto=True)
        say(f"{session.model}: {rec['candidates']}  ({rec['reason']})")
    elif session.turns and not session.ended:
        say(f"resuming after round {session.rounds}")
    while not session.ended:
        say(f"Round {session.rounds + 1} Dialogue")
        text = ask("請輸入描述（輸入 'ee' 來結束）：")
        if is_ee(text):
            session.stop()
            break
        try:
            rec = session.send(text)
        except InputRejected as e:
            say("  " + e.reason)
            continue
        say(f"{session.model}: {rec['candidates']}  ({rec['reason']})")
    e = session.end
    if e["reason"] == "max_round":
        say("please ask again")
    if "found" in e:
        say(f"  -> end ({e['reason']}) after {e['rounds']} round(s), final {[tag[i] for i in e['final_ids']]}, "
            f"target {tag[e['target']]}, {'found' if e['found'] else 'not found'}")
    return e


def summary(records: list[dict]) -> dict:
    """Found rate and mean rounds (independent of k) plus T_A with k = answer-file length."""
    ends = [r for r in records if r.get("type") == "end" and "found" in r]
    if not ends:
        return {"finished": 0}
    n = len(ends)
    return {"finished": n, "found": sum(r["found"] for r in ends) / n, "mean_rounds": sum(r["rounds"] for r in ends) / n,
            "T_A_kcsv": sum(r["T_A_kcsv"] for r in ends) / n}


def question_id(dlg: dict) -> str:
    return dlg["dialogue_id"].split("-")[-1]


def experiment_session(ps, dlg: dict, out: str, model: str, rep: int = 1, targets: Optional[dict] = None,
                       client: Optional[VLMClient] = None, dry_run: bool = False, max_round: int = 10) -> LiveSession:
    """An Office question as in the experiment: C6 images of the target's class, the translated target (A11-A14)."""
    target = (targets or {}).get(question_id(dlg), dlg["target"])
    cls = next(o.label for o in ps.ctx.objects if o.obj_id == dlg["target"])
    if dry_run:
        tags = [o.tag for o in sorted(ps.ctx.objects, key=lambda o: o.obj_id) if o.label == cls]
        client = DryRunClient(tags, next(o.tag for o in ps.ctx.objects if o.obj_id == target))
    return LiveSession(client, ps, out, model, rep, dlg=dlg, target=target, images=ps.class_only_annot[cls],
                       bare_class=cls, max_round=max_round)
