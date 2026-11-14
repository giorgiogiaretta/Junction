"""Computer-vision ensemble: several independent recognisers vote on the object in ONE frame; the decision feeds ai.object_profile.cap_for_votes().
  python -m ai.recognize photo.jpg [--backends gemini,gemma,nemotron,color] [--publish]
Backends (each optional, run in parallel with a hard timeout so a dead endpoint never stalls the grasp):
  gemini   -> $GEMINI_MODEL (default gemini-3.5-flash), key GEMINI_API_KEY
  gemma    -> $GEMMA_MODEL (default gemma-4-26b-a4b-it), same Google key (open-weights model)
  nemotron -> Verda/NVIDIA endpoint, key VERDA_INFERENCE_KEY
  color    -> local colour rule (no network, 76% on our photos): orange = ball, white blob = egg, gold elongated = can
Decision rule (FRAGILE-FIRST): any ok vote 'egg' with confidence >= 0.6 (or unknown confidence) -> egg; otherwise the object with most votes (ties -> higher mean confidence).
`agree` = number of votes for the winner, `confidence` = mean confidence of those votes (None when no vote has one). No ok vote -> 'other' -> conservative cap.
A stress ball only gets full force through cap_for_votes(conf >= 0.9 and agree >= 2)."""
import argparse, concurrent.futures as cf, json, os, socket, time
from ai.object_profile import cap_for_votes, behaviour

TIMEOUT_S = 15.0
EGG_VETO_CONF = 0.6


def _vlm(backend):
    def run(img):
        from ai.eval_objects import make_client, recognize
        c = make_client(backend); c.timeout = 12; c.retries = 1
        if backend == "gemini" and os.environ.get("GEMINI_MODEL") is None: c.model = "gemini-3.5-flash"
        if backend == "gemma": c.model = os.environ.get("GEMMA_MODEL", "gemma-4-26b-a4b-it"); c.url = c.url  # same Google endpoint/key as Gemini
        r = recognize(c, img, fast=(backend == "nemotron"))
        return {"object": r["object"], "confidence": r["confidence"], "ok": r["ok"], "error": r.get("error")}
    return run


def _gemma_run(img):
    from ai.eval_objects import make_client, recognize
    c = make_client("gemini"); c.model = os.environ.get("GEMMA_MODEL", "gemma-4-26b-a4b-it"); c.timeout = 12; c.retries = 1
    r = recognize(c, img, fast=False)
    return {"object": r["object"], "confidence": r["confidence"], "ok": r["ok"], "error": r.get("error")}


def _color(img):
    from ai.color_baseline import classify_bytes
    return {"object": classify_bytes(img), "confidence": None, "ok": True}


BACKENDS = {"gemini": _vlm("gemini"), "gemma": _gemma_run, "nemotron": _vlm("nemotron"), "color": _color}


def collect(img, backends, registry=None, timeout=TIMEOUT_S):
    """Run the chosen backends in parallel; returns a list of votes {name, object, confidence, ok, latency_s, error?}. A backend that times out or raises is an ok=False vote."""
    reg = registry or BACKENDS; votes = []
    ex = cf.ThreadPoolExecutor(max_workers=max(1, len(backends)))
    futs = {ex.submit(_timed, reg[n], img): n for n in backends if n in reg}
    done, pending = cf.wait(futs, timeout=timeout)
    for f in done:
        try: v = f.result()
        except Exception as e: v = {"object": "other", "confidence": None, "ok": False, "error": type(e).__name__, "latency_s": None}
        v["name"] = futs[f]; votes.append(v)
    for f in pending: votes.append({"name": futs[f], "object": "other", "confidence": None, "ok": False, "error": "timeout", "latency_s": None})
    ex.shutdown(wait=False, cancel_futures=True)
    return sorted(votes, key=lambda v: v["name"])


def _timed(fn, img):
    t = time.time(); v = fn(img); v["latency_s"] = round(time.time() - t, 2); return v


def decide(votes):
    """Fragile-first majority vote -> {'object','confidence','agree','n_ok','reason'}."""
    ok = [v for v in votes if v.get("ok")]
    if not ok: return {"object": "other", "confidence": None, "agree": 0, "n_ok": 0, "reason": "no recogniser answered"}
    eggs = [v for v in ok if v["object"] == "egg" and (v["confidence"] is None or v["confidence"] >= EGG_VETO_CONF)]
    if eggs: win, why = "egg", "fragile-first: at least one recogniser says egg"
    else:
        count = {}
        for v in ok: count.setdefault(v["object"], []).append(v)
        def score(k):
            cs = [v["confidence"] for v in count[k] if v["confidence"] is not None]
            return (len(count[k]), sum(cs) / len(cs) if cs else 0.0)
        win, why = max(count, key=score), "majority vote"
    agreeing = [v for v in ok if v["object"] == win]; cs = [v["confidence"] for v in agreeing if v["confidence"] is not None]
    return {"object": win, "confidence": round(sum(cs) / len(cs), 3) if cs else None, "agree": len(agreeing), "n_ok": len(ok), "reason": why}


def recognise(img, backends=("gemini", "gemma", "nemotron", "color"), registry=None, timeout=TIMEOUT_S):
    votes = collect(img, list(backends), registry, timeout); d = decide(votes)
    d["cap"] = cap_for_votes(d["object"], d["confidence"], d["agree"]); d["profile"] = behaviour(d["object"])["profile"]; d["votes"] = votes
    return d


if __name__ == "__main__":
    from ai.eval_objects import prep_image
    ap = argparse.ArgumentParser(); ap.add_argument("image"); ap.add_argument("--backends", default="gemini,gemma,nemotron,color")
    ap.add_argument("--publish", action="store_true", help="send {profile} to UDP 127.0.0.1:14070"); ap.add_argument("--json", action="store_true"); a = ap.parse_args()
    d = recognise(prep_image(open(a.image, "rb").read()), a.backends.split(","))
    if a.json: print(json.dumps(d, indent=1))
    else:
        for v in d["votes"]: print(f"  {v['name']:9s} {v['object']:12s} conf={v['confidence']} ok={v['ok']} {v.get('latency_s')}s {v.get('error') or ''}")
        print(f"DECISION: {d['object']} (agree {d['agree']}/{d['n_ok']}, conf {d['confidence']}) -> profile {d['profile']}, cap {d['cap']}  [{d['reason']}]")
    if a.publish: socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(json.dumps({"profile": d["profile"], "object": d["object"], "max_closure": d["cap"]}).encode(), ("127.0.0.1", 14070))
