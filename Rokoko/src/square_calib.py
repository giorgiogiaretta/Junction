"""Estimate the table square in the Coil Pro frame from series H episodes (can moved BL -> TL -> TR -> BR -> BL, clockwise).
Idea: a photo cannot give the coil offset precisely, but the wrist pose in the Coil frame at each grasp/release does: 4 corners, each visited twice.
  python Rokoko/src/square_calib.py [take ...]  -> data/square_calib.json (+ printed report vs the known 29.7 cm side)
Uses data/episodes/take_NN.npz (calibrated fingers01 of the active hand, wrist_pos). Closure edges = grasp (up) / release (down).
"""
import json, os, sys
import numpy as np

SIDE = 0.297

def events(closure, hz=30, hi_frac=0.55, lo_frac=0.35, min_gap_s=1.0):
    c = np.convolve(closure, np.ones(5) / 5, mode="same"); top = np.percentile(c, 95); bot = np.percentile(c, 5)
    hi, lo = bot + hi_frac * (top - bot), bot + lo_frac * (top - bot)
    state, ev, last = False, [], -1e9
    for i, v in enumerate(c):
        if not state and v > hi and (i - last) / hz > min_gap_s: state = True; ev.append(("grasp", i)); last = i
        elif state and v < lo and (i - last) / hz > min_gap_s: state = False; ev.append(("release", i)); last = i
    return ev

def corners_from(pos, closure, hz=30):
    ev = events(closure, hz); g = [i for k, i in ev if k == "grasp"]; r = [i for k, i in ev if k == "release"]
    if len(g) < 4 or len(r) < 4: return None, {"grasps": len(g), "releases": len(r)}
    g, r = g[:4], r[:4]
    P = lambda i: pos[min(i, len(pos) - 1)]
    # grasp0/release3 = BL, release0/grasp1 = TL, release1/grasp2 = TR, release2/grasp3 = BR
    pairs = {"BL": (P(g[0]), P(r[3])), "TL": (P(r[0]), P(g[1])), "TR": (P(r[1]), P(g[2])), "BR": (P(r[2]), P(g[3]))}
    return {k: ((a + b) / 2).tolist() for k, (a, b) in pairs.items()}, {"grasps": len(g), "releases": len(r)}

def fit(corners):
    C = {k: np.array(v) for k, v in corners.items()}
    sides = {"BL-TL": np.linalg.norm(C["TL"] - C["BL"]), "TL-TR": np.linalg.norm(C["TR"] - C["TL"]), "TR-BR": np.linalg.norm(C["BR"] - C["TR"]), "BR-BL": np.linalg.norm(C["BL"] - C["BR"])}
    M = np.stack(list(C.values())); ctr = M.mean(0); u, s, vt = np.linalg.svd(M - ctr); normal = vt[2]
    return {"side_lengths_m": {k: round(float(v), 3) for k, v in sides.items()}, "mean_side_m": round(float(np.mean(list(sides.values()))), 3),
            "scale_vs_A4": round(float(np.mean(list(sides.values())) / SIDE), 2), "table_normal_coil_frame": np.round(normal, 3).tolist(),
            "plane_flatness_m": round(float(s[2] / np.sqrt(4)), 3), "square_center_coil_frame_m": np.round(ctr, 3).tolist(),
            "BL_in_coil_frame_m": np.round(C["BL"], 3).tolist()}

if __name__ == "__main__":
    idx = [i for i in json.load(open("data/episodes/index.json")) if i["series"] == "H"]
    want = {int(a) for a in sys.argv[1:]}; res = {}
    for i in idx:
        if want and i["take"] not in want: continue
        z = np.load(f"data/episodes/take_{i['take']:02d}.npz", allow_pickle=True); h = i["active_hand"]
        cl = z[f"{h}_fingers01"][:, 1:].mean(1); pos = z[f"{h}_wrist_pos"]
        cs, info = corners_from(pos, cl)
        if cs is None: print(f"take {i['take']} {h}: not enough grasp/release events {info}"); continue
        res[i["take"]] = {"hand": h, "events": info, "corners": cs, **fit(cs)}
        r = res[i["take"]]; print(f"take {i['take']} {h}: sides {r['side_lengths_m']} scale vs A4 {r['scale_vs_A4']} normal {r['table_normal_coil_frame']} BL {r['BL_in_coil_frame_m']}")
    if res:
        sc = [r["scale_vs_A4"] for r in res.values()]; print(f"{len(res)} takes: scale vs A4 mean {np.mean(sc):.2f} sd {np.std(sc):.2f}")
        json.dump(res, open("data/square_calib.json", "w"), indent=1)
