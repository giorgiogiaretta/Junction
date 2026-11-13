"""Convert raw takes -> training episodes (npz) at a fixed rate.  python Rokoko/src/episodes.py [data/raw] [--hz 30]
Per take: t (s from start), per hand: fingers01 (N,5) normalised with a GLOBAL per-hand range (5th..95th percentile over all takes, so no
per-take calibration), wrist_pos (N,3 m, Coil Pro frame), wrist_quat (N,4 wxyz), coil_ok (N,). Labels: series, active_hand (larger finger motion),
t_mark (correction start, series C, seconds from start). Output: data/episodes/take_NN.npz + data/episodes/index.json
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from analyze_takes import parse
import calib
cal = calib.load()   # data/calib.json from series E; without it fingers01 uses the global percentile range and polarity is UNKNOWN

hz = float(sys.argv[sys.argv.index("--hz") + 1]) if "--hz" in sys.argv else 30.0
d = next((x for x in sys.argv[1:] if not x.startswith("--") and not x.replace(".", "").isdigit()), "data/raw")
takes = [json.loads(l) for l in open(f"{d}/takes.jsonl")]
raw = {t["take"]: parse(t["file"]) for t in takes}
allang = {"left": [], "right": []}
for r in raw.values():
    for h, rows in r.items():
        if h in allang: allang[h] += [x[1] for x in rows]
rng = {h: (np.percentile(np.array(a), 5, axis=0), np.percentile(np.array(a), 95, axis=0)) for h, a in allang.items() if a}
os.makedirs("data/episodes", exist_ok=True); index = []
for t in takes:
    r = raw[t["take"]]; tt = None; out = {}; act = {}
    for h in ("left", "right"):
        rows = r.get(h)
        if not rows or len(rows) < 20: continue
        ts = np.array([x[0] for x in rows]); ts = ts - ts[0]
        if tt is None: tt = np.arange(0, ts[-1], 1 / hz)
        lo, hi = rng[h]; a = np.array([x[1] for x in rows])
        f01 = calib.to01(a, cal[h]) if h in cal else np.clip((a - lo) / (hi - lo + 1e-6), 0, 1)
        out[h + "_polarity"] = np.array(cal[h]["sign"] if h in cal else [0] * 5, dtype=np.int8)   # +1 bigger angle=closed, -1 inverted, 0 unknown (no calib)
        pos = np.array([x[2] if x[2] else [np.nan] * 3 for x in rows], dtype=float)
        coil = np.array([(x[3] >> 9) & 1 for x in rows], dtype=float)
        out[f"{h}_fingers01"] = np.stack([np.interp(tt, ts, f01[:, k]) for k in range(5)], 1).astype(np.float32)
        out[f"{h}_wrist_pos"] = np.stack([np.interp(tt, ts, pos[:, k]) for k in range(3)], 1).astype(np.float32)
        out[f"{h}_coil_ok"] = np.interp(tt, ts, coil).astype(np.float32)
        fl = a[:, 1:].mean(1); act[h] = float(np.percentile(fl, 95) - np.percentile(fl, 5))   # raw flexion span (index..little), same metric as analyze_takes
    if tt is None: continue
    ah = max(act, key=act.get)
    tm = (t["t_mark"] - t["t_start"]) if t.get("t_mark") else None
    np.savez_compressed(f"data/episodes/take_{t['take']:02d}.npz", t=tt.astype(np.float32), series=t["series"], active_hand=ah, t_mark=-1.0 if tm is None else tm,
             success=-1 if t.get("success") is None else int(t["success"]), obj_pos=np.array(t.get("obj_pos") or [np.nan] * 3, dtype=np.float32), calibrated=bool(cal), **out)
    index.append({"take": t["take"], "series": t["series"], "active_hand": ah, "dur_s": round(float(tt[-1]), 1), "t_mark": tm, "samples": len(tt), "success": t.get("success"), "obj_pos": t.get("obj_pos")})
json.dump(index, open("data/episodes/index.json", "w"), indent=1)
from collections import Counter
print("episodes:", len(index), dict(Counter(i["series"] for i in index)), "| active hand:", dict(Counter(i["active_hand"] for i in index)))
print("by series/hand:", dict(Counter((i["series"], i["active_hand"]) for i in index)))
