"""Analyze raw takes: python Rokoko/src/analyze_takes.py [data/raw] [--series A]
Per take and hand: duration, rate, Coil Pro validity, wrist position range (coil frame, metres), grasp detection from finger flexion
and the wrist height change while grasping (lift proxy). Prints a table + writes data/raw/analysis.json.
"""
import json, math, os, struct, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import rgmp_client as R

H = struct.Struct("<dI")
FRAMES = ["thumb", "index", "middle", "ring", "little"]

def raw_bytes(path):
    b = bytearray()
    with open(path, "rb") as f:
        while len(h := f.read(H.size)) == H.size:
            t, n = H.unpack(h); b += f.read(n)
    return bytes(b)

def parse(path):
    b, i, lay, hands, out = raw_bytes(path), 0, {}, {}, {}
    while i + 8 <= len(b):
        typ, ln = struct.unpack_from("<II", b, i)
        if i + 8 + ln > len(b): break
        p = b[i + 8:i + 8 + ln]; i += 8 + ln
        if typ == 1:
            sd = json.loads(p.decode("utf-8")); d = sd["device_id"]; lay[d] = R.build_layout(sd)
            hands[d] = (sd.get("device_info") or {}).get("hand", "?"); out.setdefault(hands[d], [])
        elif typ == 2:
            d = struct.unpack_from("<I", p, 0)[0]
            if d not in lay: continue
            _, name, ts, items = R.decode(lay[d], p)
            if name != "default": continue
            ang, pos, flags = [0.0] * 5, None, 0
            for s, v in items:
                tf, mt, ref = s["target_frame"], s["measure_type"], s.get("reference_frame")
                if mt == "TRANSFORM" and tf.endswith("finger_sensor"): ang[FRAMES.index(tf.split("_")[0])] = R.angle_of(R.quat(v))
                elif mt == "TRANSFORM" and tf == "arm_sensor" and ref == "coil_pro": pos = v[:3]
                elif mt == "STATUS_FLAGS" and tf == "arm_sensor": flags = int(v[0])
            out[hands[d]].append((ts / 1e6, ang, pos, flags))
    return out

def analyze(hand_rows):
    t = np.array([r[0] for r in hand_rows]); a = np.array([r[1] for r in hand_rows])
    pos = np.array([r[2] if r[2] else [np.nan] * 3 for r in hand_rows]); fl = np.array([r[3] for r in hand_rows])
    dur = t[-1] - t[0]; flex = a[:, 1:].mean(1)                  # index..little mean flexion (rad)
    lo, hi = np.percentile(flex, 5), np.percentile(flex, 95); span = hi - lo
    grasp = flex > lo + 0.6 * span if span > 0.3 else np.zeros(len(flex), bool)   # needs real closing movement
    coil_ok = float(((fl >> 9) & 1).mean()); flip = float(((fl >> 10) & 1).mean()); sat = float(((fl >> 8) & 1).mean())
    r = {"frames": len(t), "dur_s": round(float(dur), 1), "rate_hz": round(len(t) / max(dur, 1e-6), 1), "coil_present": round(coil_ok, 2),
         "flip_decided": round(flip, 2), "emf_saturated": round(sat, 2), "flex_span_rad": round(float(span), 2), "grasp_s": round(float(grasp.sum() / (len(t) / max(dur, 1e-6))), 1),
         "pos_range_m": [round(float(np.nanmax(pos[:, k]) - np.nanmin(pos[:, k])), 2) for k in range(3)]}
    if grasp.any() and not np.isnan(pos[grasp]).all():
        g = pos[grasp]; r["pos_while_grasp_mean_m"] = [round(float(np.nanmean(g[:, k])), 2) for k in range(3)]
        base = np.nanmedian(pos[:max(10, int(0.1 * len(t)))], axis=0)
        r["rise_from_rest_while_grasp_m"] = [round(float(np.nanmax(np.abs(g[:, k] - base[k]))), 2) for k in range(3)]
    return r

if __name__ == "__main__":
    d = next((x for x in sys.argv[1:] if not x.startswith("--")), "data/raw")
    ser = sys.argv[sys.argv.index("--series") + 1] if "--series" in sys.argv else None
    takes = [json.loads(l) for l in open(f"{d}/takes.jsonl")]; res = {}
    for t in takes:
        if ser and t["series"] != ser: continue
        rows = parse(t["file"]); res[t["take"]] = {"series": t["series"], "hands": {h: analyze(r) for h, r in rows.items() if len(r) > 20}}
        for h, r in res[t["take"]]["hands"].items():
            print(f"take {t['take']:02d} {t['series']} {h:5s} dur={r['dur_s']:5.1f}s rate={r['rate_hz']:5.1f} coil={r['coil_present']:.2f} flip={r['flip_decided']:.2f} sat={r['emf_saturated']:.2f} "
                  f"flexspan={r['flex_span_rad']:.2f} grasp={r['grasp_s']:.1f}s rise={r.get('rise_from_rest_while_grasp_m')}")
    json.dump(res, open(f"{d}/analysis.json", "w"), indent=1)
