"""Post-grasp judge with Google Gemini (google-genai SDK): reads a WHOLE episode and says whether the hand-off / grasp worked.

  python -m ai.judge_gemini data/episodes/take_05.npz            # one episode (.npz) or a samples .jsonl
  python -m ai.judge_gemini --all data/episodes [--out report.md] [--compare data/overnight/<run>/judge.jsonl]
Per episode it prints exactly:  HandOff riuscito: True|False, Motivo: <one or two sentences>
and writes a markdown report (default data/judge_gemini_report.md).

Input: data/episodes/take_NN.npz (30 Hz: <hand>_fingers01, <hand>_wrist_pos, t, series, active_hand, success, optional hand_in_head)
or a .jsonl with one dict per sample ({"t", "fingers": [5], "wrist_position": [x,y,z], optional "hand_in_head": [x,y,z]}).
The episode is sent at full resolution (capped at ~15 Hz) as compact JSON; the thumb channel is dropped (calibrated span too small to trust).
Key: GEMINI_API_KEY or GOOGLE_API_KEY from the environment only (never printed). Model: GEMINI_MODEL, default gemini-2.5-flash (UNVERIFIED id).

HONESTY: our human labels only say 'object not dropped' (success=true on 32 episodes); there are NO labelled failures, so this judge has no
measured precision. 'HandOff riuscito' is the model's reading of finger closure + wrist motion, not ground truth. On API errors or invalid
JSON the result is 'unclear' (source=fallback): it is printed as False with the reason 'NON VALUTATO', and marked unclear in the report."""
import argparse, glob, json, math, os, sys, time

DEFAULT_MODEL = "gemini-3.1-flash-lite"  # id listed by ai.list_gemini_models for our key; GEMINI_MODEL overrides, MODEL_CHAIN is the fallback order
MAX_HZ = 15.0

SYSTEM = ("You judge one recorded robot-teleoperation episode made with Rokoko smartgloves and a Coil Pro wrist tracker. "
          "TASK: the operator reaches an object (egg, stress ball or can), closes the fingers on it, holds it while the wrist moves, then releases. "
          "You get the WHOLE episode as rows [t_seconds, index, middle, ring, little (finger closure 0=open..1=closed), wrist x, y, z (metres, Coil frame)"
          ", optional hand_in_head x, y, z]. The thumb channel is unreliable and omitted; series A is a flat hand on a box (low closure is normal there). "
          "Answer 'handoff_success' = true only if the rows show a grip (closure clearly above its resting value) that is held while the wrist moves and "
          "then released; false if there is no grip, the grip is lost mid-motion, or the motion happens without a grip. Judge only from the numbers, "
          "write 'reason' in one or two short sentences, and list the phases you can see with their start time in seconds.")

RESPONSE_SCHEMA = {  # UNVERIFIED against the live API (plain JSON-schema dict accepted by google-genai)
    "type": "OBJECT",
    "properties": {
        "handoff_success": {"type": "BOOLEAN"},
        "reason": {"type": "STRING"},
        "phases": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"name": {"type": "STRING"}, "t_start": {"type": "NUMBER"}},
                                              "required": ["name", "t_start"]}},
    },
    "required": ["handoff_success", "reason"],
}


def _r(x, nd=3):
    """Round; NaN/inf/None -> None (json.dumps would emit NaN, invalid JSON for the model)."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if math.isfinite(x) else None


def _downsample(n, t, max_hz=MAX_HZ):
    """Indices keeping at most max_hz samples per second."""
    keep, last = [], None
    for i in range(n):
        ti = t[i]
        if last is None or ti - last >= 1.0 / max_hz - 1e-9:
            keep.append(i); last = ti
    return keep


def load_episode(path):
    """-> dict(name, series, hand, human_label, has_head, columns, rows). rows = [t, idx, mid, ring, lit, wx, wy, wz(, hx, hy, hz)]."""
    name = os.path.basename(path)
    if path.endswith(".jsonl"):
        raw = [json.loads(l) for l in open(path) if l.strip()]
        raw = [d for d in raw if d.get("fingers") is not None]
        if not raw: raise ValueError(f"{name}: no samples with 'fingers'")
        t0 = float(raw[0].get("t", 0.0)); t = [float(d.get("t", i / 30.0)) - t0 for i, d in enumerate(raw)]
        fing = [d["fingers"][1:5] for d in raw]
        wr = [d.get("wrist_position") or [None] * 3 for d in raw]
        hh = [d.get("hand_in_head") for d in raw] if any(d.get("hand_in_head") for d in raw) else None
        series, hand, label = str(raw[0].get("series", "?")), str(raw[0].get("hand", "?")), -1
    else:
        import numpy as np
        z = np.load(path, allow_pickle=True)
        hand = str(z["active_hand"]); t = (z["t"].astype(float) - float(z["t"][0])).tolist()
        fing = z[f"{hand}_fingers01"].astype(float)[:, 1:5].tolist(); wr = z[f"{hand}_wrist_pos"].astype(float).tolist()
        series = str(z["series"]); label = int(z["success"]) if "success" in z.files else -1
        hh = None
        for k in ("hand_in_head", f"{hand}_hand_in_head"):
            if k in z.files: hh = z[k].astype(float).tolist(); break
    idx = _downsample(len(t), t)
    rows = []
    for i in idx:
        row = [_r(t[i], 2)] + [_r(v) for v in fing[i]] + [_r(v) for v in (wr[i] + [None] * 3)[:3]]
        if hh is not None: row += [_r(v) for v in (hh[i] + [None] * 3)[:3]]
        rows.append(row)
    cols = ["t_s", "index", "middle", "ring", "little", "wrist_x_m", "wrist_y_m", "wrist_z_m"] + (["head_to_hand_x_m", "head_to_hand_y_m", "head_to_hand_z_m"] if hh is not None else [])
    return {"name": name, "series": series, "hand": hand, "human_label": label, "has_head": hh is not None, "columns": cols, "rows": rows}


def payload_json(ep):
    """Compact JSON string sent to the model (the whole episode, no aggregates)."""
    return json.dumps({"episode": ep["name"], "series": ep["series"], "hand": ep["hand"], "columns": ep["columns"], "rows": ep["rows"]}, separators=(",", ":"))


def make_client():
    """google-genai client from the environment. Returns None if no key (caller prints a clean error)."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key: return None
    from google import genai
    return genai.Client(api_key=key)


def _config():
    from google.genai import types
    return types.GenerateContentConfig(system_instruction=SYSTEM, response_mime_type="application/json", response_schema=RESPONSE_SCHEMA,
                                       temperature=0.0, max_output_tokens=2048)


def _parse(resp):
    parsed = getattr(resp, "parsed", None)
    r = parsed if isinstance(parsed, dict) else None
    if r is None:
        txt = (getattr(resp, "text", None) or "").strip()
        r = json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
    if not isinstance(r.get("handoff_success"), bool): raise ValueError("handoff_success missing or not a boolean")
    return {"handoff_success": r["handoff_success"], "reason": str(r.get("reason", "")).strip(), "phases": r.get("phases") or [], "source": "model"}


# Free tier (verified 14/11 on our key): 20 requests PER DAY per model (RESOURCE_EXHAUSTED ... PerDay, retryDelay ~18 h) and a per-minute cap. A daily 429 is NOT retried:
# the model is marked exhausted for this process and the next one of the chain is tried. Per-minute 429 / 503 / network errors: exponential backoff + jitter.
MODEL_CHAIN = ["gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-2.5-flash"]   # ids listed by `python -m ai.list_gemini_models` for our key
_EXHAUSTED = set()


def _kind(e):
    """Classify an SDK/API exception WITHOUT echoing its text (it could contain the key): 'daily' | 'rate' | 'transient' | 'other'."""
    t = (str(e) + " " + type(e).__name__).lower()
    if "429" in t or "resource_exhausted" in t or "quota" in t:
        return "daily" if ("perday" in t or "per day" in t or "daily" in t) else "rate"
    if "503" in t or "unavailable" in t or "overloaded" in t or "timeout" in t or "ssl" in t or "connection" in t: return "transient"
    return "other"


def judge_episode(client, ep, model=None, retries=3, sleep=time.sleep, config=None, chain=None, jitter=lambda: __import__("random").random() * 0.5):
    """-> {handoff_success: True|False|None, reason, phases, source: 'model'|'fallback', model?, error?}. None = unclear (all models failed / quota / invalid JSON)."""
    models = [model] if model else ([os.environ["GEMINI_MODEL"]] if os.environ.get("GEMINI_MODEL") else (chain or MODEL_CHAIN))
    contents = payload_json(ep); last = "unknown error"
    for m in models:
        if m in _EXHAUSTED: last = "daily quota exhausted for " + m; continue
        for attempt in range(retries):
            try:
                resp = client.models.generate_content(model=m, contents=contents, config=config if config is not None else _config())
                r = _parse(resp); r["model"] = m; return r
            except (ValueError, KeyError, TypeError, AttributeError) as e:  # invalid / malformed JSON
                last = f"invalid response: {e}"; kind = "other"
            except Exception as e:  # API / network error: do not echo anything that could contain the key
                kind = _kind(e); last = f"api error ({kind})"
            if kind == "daily": _EXHAUSTED.add(m); break          # no point retrying: go to the next model
            if attempt < retries - 1: sleep(min(30, 2 ** attempt * (4 if kind == "rate" else 1)) + jitter())
        else:
            if kind == "other": break                           # invalid JSON / unknown error is not a quota problem: do not burn the other models' quota
    return {"handoff_success": None, "reason": "", "phases": [], "source": "fallback", "error": last}


def judge_async(client, ep, on_done, **kw):
    """Non-blocking judge for the end of a recording: runs in a daemon thread (never stalls the simulator) and calls on_done(result)."""
    import threading
    def run():
        try: on_done(judge_episode(client, ep, **kw))
        except Exception as e: on_done({"handoff_success": None, "reason": "", "phases": [], "source": "fallback", "error": type(e).__name__})
    t = threading.Thread(target=run, daemon=True); t.start(); return t


def format_line(res):
    """Exactly 'HandOff riuscito: True|False, Motivo: ...'. Unclear (fallback) prints False with a NON VALUTATO reason."""
    if res["handoff_success"] is None:
        return f"HandOff riuscito: False, Motivo: NON VALUTATO ({res.get('error', 'errore')})"
    return f"HandOff riuscito: {res['handoff_success']}, Motivo: {res['reason']}"


def compare_with_nemotron(results, jsonl_path):
    """Raw agreement with a Nemotron judge jsonl ({"summary": {"episode"}, "judge": {"verdict": good|bad|unclear}}). good->True, bad->False, unclear skipped.
    -> {'n', 'agree', 'agreement', 'disagreements': [(episode, gemini, nemotron)]}. Agreement is NOT accuracy: neither judge has ground truth."""
    nem = {}
    for line in open(jsonl_path):
        if not line.strip(): continue
        d = json.loads(line); v = d.get("judge", {}).get("verdict")
        if v in ("good", "bad"): nem[d["summary"]["episode"]] = (v == "good")
    pairs = [(n, r["handoff_success"], nem[n]) for n, r in results.items() if r["handoff_success"] is not None and n in nem]
    dis = [p for p in pairs if p[1] != p[2]]
    return {"n": len(pairs), "agree": len(pairs) - len(dis), "agreement": (round((len(pairs) - len(dis)) / len(pairs), 2) if pairs else None), "disagreements": dis}


def report(eps, results, model, cmp=None):
    out = [f"# Gemini post-grasp judge ({model}, model id UNVERIFIED)", "",
           "Only labels so far: success=true ('object not dropped'); NO labelled failures, so no precision. Verdicts are the model's reading, not ground truth.", "",
           "| episode | series | human label | Gemini | source | reason |", "|---|---|---|---|---|---|"]
    for ep in eps:
        r = results[ep["name"]]; v = "unclear" if r["handoff_success"] is None else str(r["handoff_success"])
        hl = {1: "not dropped", 0: "failed"}.get(ep["human_label"], "-")
        out.append(f"| {ep['name']} | {ep['series']} | {hl} | {v} | {r['source']} | {(r['reason'] or r.get('error', '')).replace('|', '/')[:160]} |")
    n = len(results); u = sum(r["handoff_success"] is None for r in results.values()); t = sum(r["handoff_success"] is True for r in results.values())
    out += ["", f"{n} episodes: {t} True, {n - t - u} False, {u} unclear."]
    pos = [e for e in eps if e["human_label"] == 1 and results[e["name"]]["handoff_success"] is not None]
    if pos: out.append(f"Among {len(pos)} human-positive episodes judged: {sum(results[e['name']]['handoff_success'] for e in pos)} True (recall on positives only).")
    if cmp:
        out += ["", f"## Compare with Nemotron: raw agreement {cmp['agree']}/{cmp['n']}" + (f" = {cmp['agreement']:.0%}" if cmp['agreement'] is not None else ""),
                "Disagreements (human review): " + (", ".join(f"{n} (Gemini {g}, Nemotron {m})" for n, g, m in cmp["disagreements"]) or "none")]
    return "\n".join(out)


def main(argv=None, client=None):
    ap = argparse.ArgumentParser(description="Gemini post-grasp judge on whole episodes")
    ap.add_argument("paths", nargs="*"); ap.add_argument("--all", help="folder of take_*.npz episodes"); ap.add_argument("--model")
    ap.add_argument("--out", default="data/judge_gemini_report.md"); ap.add_argument("--compare", help="Nemotron judge jsonl, e.g. data/overnight/<run>/judge.jsonl")
    a = ap.parse_args(argv)
    paths = list(a.paths) + (sorted(glob.glob(os.path.join(a.all, "take_*.npz"))) if a.all else [])
    if not paths: ap.error("give an episode path or --all <folder>")
    if client is None:
        client = make_client()
        if client is None:
            print("error: no API key: export GEMINI_API_KEY (or GOOGLE_API_KEY) in this terminal", file=sys.stderr); return 1
    model = a.model or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
    eps, results = [], {}
    for p in paths:
        try: ep = load_episode(p)
        except (OSError, ValueError, KeyError) as e:
            print(f"{os.path.basename(p)}: cannot read episode ({e})", file=sys.stderr); continue
        res = judge_episode(client, ep, model); eps.append(ep); results[ep["name"]] = res
        print(f"== {ep['name']}"); print(format_line(res))
    cmp = compare_with_nemotron(results, a.compare) if a.compare else None
    md = report(eps, results, model, cmp)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    open(a.out, "w").write(md + "\n"); print(f"report: {a.out}")
    if cmp: print(f"agreement with Nemotron: {cmp['agree']}/{cmp['n']}; disagreements: {len(cmp['disagreements'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
