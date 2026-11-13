"""Per-glove finger calibration from series E takes (5 s flat open hand, MARK, 5 s fist).  python Rokoko/src/calib.py [data/raw]
Writes data/calib.json: {hand: {open:[5], closed:[5], sign:[5 of +1/-1], span:[5], n_takes}}. sign=+1 means a bigger raw angle = closed.
fingers01 = clip((angle - open) / (closed - open), 0, 1), valid for any sign. Medians over the stable part of each phase (1 s margin).
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))


def derive(d="data/raw"):
    from analyze_takes import parse
    takes = [json.loads(l) for l in open(f"{d}/takes.jsonl")]
    acc = {"left": ([], []), "right": ([], [])}
    for t in takes:
        if t["series"] != "E" or not t.get("t_mark"): continue
        for h, rows in parse(t["file"]).items():
            if h not in acc or len(rows) < 20: continue
            ts = np.array([x[0] for x in rows]); a = np.array([x[1] for x in rows])
            tm = t["t_mark"] - t["t_start"]
            o = (ts > ts[0] + 1) & (ts < tm - 1); c = (ts > tm + 1) & (ts < ts[-1] - 0.5)
            if o.sum() > 10 and c.sum() > 10: acc[h][0].append(np.median(a[o], 0)); acc[h][1].append(np.median(a[c], 0))
    out = {}
    for h, (o, c) in acc.items():
        if not o: continue
        o, c = np.mean(o, 0), np.mean(c, 0)
        out[h] = {"open": o.tolist(), "closed": c.tolist(), "sign": [1 if x >= 0 else -1 for x in c - o],
                  "span": np.abs(c - o).tolist(), "n_takes": len(acc[h][0])}
    return out


def load(path="data/calib.json"):
    return json.load(open(path)) if os.path.exists(path) else {}


def to01(angles, cal):
    """angles (N,5) raw -> (N,5) closure 0 open..1 closed using one hand's calib entry."""
    o, c = np.array(cal["open"]), np.array(cal["closed"])
    d = c - o
    return np.clip((np.asarray(angles) - o) / np.where(np.abs(d) < 1e-3, 1e-3, d), 0, 1)


if __name__ == "__main__":
    cal = derive(sys.argv[1] if len(sys.argv) > 1 else "data/raw")
    if not cal: sys.exit("no usable series E takes (need MARK, 5 s open + 5 s fist)")
    json.dump(cal, open("data/calib.json", "w"), indent=1)
    for h, v in cal.items():
        print(h, "n=%d" % v["n_takes"], "sign", v["sign"], "span(rad)", [round(x, 2) for x in v["span"]])
        if min(v["span"][1:]) < 0.3: print("  WARNING: small span, fist/open not distinct enough; re-record")
