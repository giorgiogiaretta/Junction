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


def summarize_episode(path):
    z = np.load(path, allow_pickle=True)
    h = str(z["active_hand"]); t = z["t"].astype(float); t = t - t[0]
    f = z[f"{h}_fingers01"].astype(float); p = z[f"{h}_wrist_pos"].astype(float)
    c4 = f[:, 1:].mean(1)  # thumb excluded: its calibrated span is too small to trust
    lo, hi = np.nanmin(p, 0), np.nanmax(p, 0)
    return {"episode": os.path.basename(path), "series": str(z["series"]), "hand": h, "duration_s": round(float(t[-1]), 1),
            "calibrated": bool(z["calibrated"]), "closure_index_to_little": {"peak": round(float(c4.max()), 2), "mean": round(float(c4.mean()), 2),
            "t_of_peak_s": round(float(t[int(np.argmax(c4))]), 1)},
            "wrist_range_m": [round(float(b - a), 2) for a, b in zip(lo, hi)], "wrist_rise_m": round(float(hi[2] - lo[2]), 2),
            "handoff_mark_s": _mark(z)}


def _mark(z):
    """Human MARK time (old takes only). New takes (lead-in, no markers) have no/NaN t_mark -> None: judge segments from the data."""
    if "t_mark" not in z.files: return None
    try: m = float(z["t_mark"])
    except (TypeError, ValueError): return None
    return None if not np.isfinite(m) or m < 0 else round(m, 1)


def judge_episode(client, summary):
    """Returns {'verdict','reason','phases','source'}; source='fallback' (verdict 'unclear') on any failure."""
    try:
        msg = client.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(summary)}], max_tokens=300)
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
    ap.add_argument("--out", default="data/judge.jsonl"); a = ap.parse_args()
    c = ChatClient(); rows = []
    for p in a.episodes:
        s = summarize_episode(p); r = judge_episode(c, s); rows.append((s, r, int(np.load(p, allow_pickle=True)["success"])))
        print(s["episode"], r["verdict"], r["source"])
    with open(a.out, "w") as f:
        for s, r, l in rows: f.write(json.dumps({"summary": s, "judge": r, "human": l}) + "\n")
    print(json.dumps(agreement([r["verdict"] for _, r, _ in rows], [l for _, _, l in rows])))
