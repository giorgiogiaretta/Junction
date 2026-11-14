"""PLAN 3.3 (offline judge): summarise a recorded episode (data/episodes/take_NN.npz) as text, ask the LLM for a verdict, measure agreement
with the human labels from ml/label.py (`success`: 1/0, -1 = unknown). Works with any ai.llm.ChatClient (Nemotron, Gemini via an OpenAI-compatible URL).
Text-only for now (finger closure + wrist path stats); video frames are added when the recorder (#13) provides them.
CAUTION: human labels so far are 'object not dropped' = success=true for takes 1-32, so agreement on them is trivial until failure
examples exist. Report precision/recall per class, never only accuracy."""
import json, os
import numpy as np
from ai.llm import ChatClient, LLMError

SYSTEM = ("You judge robot-demonstration episodes recorded with Rokoko smartgloves and a Coil Pro. Reply with ONLY a JSON object: "
          '{"verdict": "good"|"bad"|"unclear", "reason": short string, "phases": [{"name": "approach|grasp|lift|place|release", "t_start": s}]}. '
          "Judge only from the numbers given; say 'unclear' if they do not allow a decision.")


SYSTEM_V2 = ("You judge robot-demonstration episodes recorded with Rokoko smartgloves and a Coil Pro wrist tracker. TASK: the operator picks up an object "
             "(finger closure rises, wrist goes down then up) and holds/moves it without dropping it. 'good' = the timeline shows a grip (closure of index..little clearly above its "
             "resting value) that is held while the wrist moves, then released; 'bad' = no grip, grip lost mid-motion, or motion without a grip; 'unclear' only if the timeline is "
             "too flat or too short to decide. Note: the thumb channel is unreliable and ignored; series A used a flat hand on a box (low closure is normal there). "
             'Reply with ONLY JSON: {"verdict": "good"|"bad"|"unclear", "reason": short string, "phases": [{"name": "approach|grasp|lift|place|release", "t_start": s}]}.')


def timeline(path, step=0.5):
    """Coarse time series (every `step` s): index..little closure and wrist height relative to the take minimum, plus xy travel."""
    z = np.load(path, allow_pickle=True); h = str(z["active_hand"]); t = z["t"].astype(float); t = t - t[0]
    c4 = z[f"{h}_fingers01"].astype(float)[:, 1:].mean(1); p = z[f"{h}_wrist_pos"].astype(float)
    out = []
    for tt in np.arange(0, t[-1], step):
        i = int(np.searchsorted(t, tt)); i = min(i, len(t) - 1)
        out.append({"t": round(float(tt), 1), "closure": _r(c4[i]), "wrist_z_m": _r(p[i, 2] - np.nanmin(p[:, 2]))})
    return out


def _r(x, nd=2):
    """Round, NaN/inf -> None (json.dumps would emit NaN, which is not valid JSON for the model)."""
    x = float(x); return round(x, nd) if np.isfinite(x) else None


def summarize_episode(path, version=1):
    """version 1: aggregate stats only. version 2: the same plus the 0.5 s timeline (what SYSTEM_V2 asks the model to read)."""
    z =np.load(path, allow_pickle=True)
    h = str(z["active_hand"]); t = z["t"].astype(float); t = t - t[0]
    f = z[f"{h}_fingers01"].astype(float); p = z[f"{h}_wrist_pos"].astype(float)
    c4 = f[:, 1:].mean(1)  # thumb excluded: its calibrated span is too small to trust
    lo, hi = np.nanmin(p, 0), np.nanmax(p, 0)
    return {"episode": os.path.basename(path), "series": str(z["series"]), "hand": h, "duration_s": round(float(t[-1]), 1),
            "calibrated": bool(z["calibrated"]), "closure_index_to_little": {"peak": _r(np.nanmax(c4)), "mean": _r(np.nanmean(c4)),
            "t_of_peak_s": _r(t[int(np.nanargmax(c4))], 1)},
            "wrist_range_m": [_r(b - a) for a, b in zip(lo, hi)], "wrist_rise_m": _r(hi[2] - lo[2]),
            "handoff_mark_s": _mark(z), **({"timeline": timeline(path)} if version >= 2 else {})}


def _mark(z):
    """Human MARK time (old takes only). New takes (lead-in, no markers) have no/NaN t_mark -> None: judge segments from the data."""
    if "t_mark" not in z.files: return None
    try: m = float(z["t_mark"])
    except (TypeError, ValueError): return None
    return None if not np.isfinite(m) or m < 0 else round(m, 1)


def judge_episode(client, summary, system=SYSTEM):
    """Returns {'verdict','reason','phases','source'}; source='fallback' (verdict 'unclear') on any failure."""
    try:
        msg = client.chat([{"role": "system", "content": system}, {"role": "user", "content": json.dumps(summary)}], max_tokens=6000)
        txt = (msg.get("content") or "").strip()
        txt = txt[txt.index("{"): txt.rindex("}") + 1]
        r = json.loads(txt)
        if r.get("verdict") not in ("good", "bad", "unclear"): raise ValueError("bad verdict")
        return {"verdict": r["verdict"], "reason": r.get("reason", ""), "phases": r.get("phases", []), "source": "model"}
    except (LLMError, ValueError, KeyError) as e:
        return {"verdict": "unclear", "reason": "", "phases": [], "source": "fallback", "error": str(e)}


def agreement(verdicts, labels):
    """verdicts: list of 'good'|'bad'|'unclear'; labels: list of 1|0|-1 (human). Only labelled, decided items count.
    Returns n, accuracy, per-class precision/recall, and how many were unclear/unlabelled."""
    pairs = [(v, l) for v, l in zip(verdicts, labels) if l in (0, 1) and v in ("good", "bad")]
    tp = sum(v == "good" and l == 1 for v, l in pairs); fp = sum(v == "good" and l == 0 for v, l in pairs)
    fn = sum(v == "bad" and l == 1 for v, l in pairs); tn = sum(v == "bad" and l == 0 for v, l in pairs)
    d = lambda a, b: round(a / b, 2) if b else None
    return {"n": len(pairs), "accuracy": d(tp + tn, len(pairs)), "good": {"precision": d(tp, tp + fp), "recall": d(tp, tp + fn)},
            "bad": {"precision": d(tn, tn + fn), "recall": d(tn, tn + fp)},
            "unclear_or_unlabelled": len(verdicts) - len(pairs), "label_balance": {"positive": sum(l == 1 for _, l in pairs), "negative": sum(l == 0 for _, l in pairs)}}


if __name__ == "__main__":
    import argparse, glob
    ap = argparse.ArgumentParser(); ap.add_argument("episodes", nargs="*", default=sorted(glob.glob("data/episodes/take_*.npz")))
    ap.add_argument("--out", default="data/judge.jsonl"); ap.add_argument("--version", type=int, default=2, choices=[1, 2]); a = ap.parse_args()
    c = ChatClient(); rows = []
    for p in a.episodes:
        s = summarize_episode(p, a.version); r = judge_episode(c, s, SYSTEM_V2 if a.version == 2 else SYSTEM); rows.append((s, r, int(np.load(p, allow_pickle=True)["success"])))
        print(s["episode"], r["verdict"], r["source"])
    with open(a.out, "w") as f:
        for s, r, l in rows: f.write(json.dumps({"summary": s, "judge": r, "human": l}) + "\n")
    print(json.dumps(agreement([r["verdict"] for _, r, _ in rows], [l for _, _, l in rows])))
