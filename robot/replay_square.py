"""Series H replay (known geometry): an empty can moved around a 29.7 cm square BL -> TL -> TR -> BR -> BL, replayed in the sim
in ONE fixed table frame measured from the take itself (no per-pick re-anchoring, unlike robot.replay).
  python -m robot.replay_square data/episodes/take_NN.npz [--obj cube|egg] [--fingers real|gain|synthetic] [--calib data/square_calib.json]
Table frame: corners (Coil frame) from Rokoko/src/square_calib.py (wrist pose at grasp/release events, or data/square_calib.json
via --calib); origin = square centre, x = BL->BR (right), y = BL->TL (forward), z = table normal (up, sign fixed by the clockwise
corner order). One 6x6 cm pad per measured corner (the A4 markers), the object starts on BL.
Object: the 4 cm sim CUBE stands in for the can: the toy hand cannot hold a 66 mm, 15 g can (ejected at every grasp height
tried, 0.10-0.18 m), so this tests the wrist path + table frame + grip timing, not can grasping. Height: palm at GRASP_Z_FOR[obj] when the wrist is at
its median grasp/release height. Score: after each release, distance of the object from the target corner (TL, TR, BR, BL).
Pads are 6 cm wide because the toy hand's grip is asymmetric (1 thumb vs 4 fingers) and shifts the object ~2.5 cm toward
the thumb; on the 3 cm default pedestal it would fall off at the first release. Limits: the hand is a 3-DOF slide (no wrist rotation), so orientation of the real hand is ignored; the sim can/hand are idealised.
"""
import argparse, json, os, sys
import numpy as np
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "Rokoko", "src"))
from robot.scene import Scene, GRASP_Z_FOR
from robot.replay import load_episode

ORDER = ["BL", "TL", "TR", "BR"]
TARGETS = ["TL", "TR", "BR", "BL"]   # where the object should be after release k
TOL_M = 0.05


def table_frame(corners, wrist):
    """corners: {BL,TL,TR,BR: xyz in Coil frame}. Returns (centre, R 3x3 rows = x right, y forward, z up, info)."""
    C = {k: np.asarray(corners[k], float) for k in ORDER}; M = np.stack([C[k] for k in ORDER]); ctr = M.mean(0)
    n = np.linalg.svd(M - ctr)[2][2]
    r = (C["BR"] - C["BL"]) + (C["TR"] - C["TL"]); r -= r.dot(n) * n; r /= np.linalg.norm(r)
    f0 = (C["TL"] - C["BL"]) + (C["TR"] - C["BR"])
    flipped = False
    if np.cross(n, r).dot(f0) < 0: n = -n; flipped = True   # right-handed (x right, y forward, z up) from the clockwise order
    f = np.cross(n, r)
    above = float(np.nanmedian((wrist - ctr) @ n))
    return ctr, np.stack([r, f, n]), {"normal_flipped": flipped, "wrist_median_height_m": round(above, 3), "wrist_above_table": above > 0}


def grip_events(closure, hz):
    from square_calib import events
    return events(closure, hz)


def synthetic_grip(n, ev, hz, ramp_s=0.3):
    c = np.zeros(n); state = 0.0; k = 0; evs = sorted(ev, key=lambda e: e[1])
    for i in range(n):
        while k < len(evs) and evs[k][1] <= i: state = 1.0 if evs[k][0] == "grasp" else 0.0; k += 1
        c[i] = state
    w = max(1, int(ramp_s * hz)); return np.clip(np.convolve(c, np.ones(w) / w, mode="full")[:n], 0, 1)


def replay_square(path, obj="cube", fingers="real", calib=None, hz=60, hand="active"):
    from square_calib import corners_from
    g, f, p, h, series, calibrated = load_episode(path, hand, hz)
    if fingers == "gain": f = np.clip(f / max(np.percentile(f[:, 1:].mean(1), 98), 0.15), 0, 1)
    c4 = f[:, 1:].mean(1); ev = grip_events(c4, hz)
    take = int(os.path.basename(path).split("_")[1].split(".")[0])
    corners, src = None, "self"
    if calib and os.path.exists(calib):
        d = json.load(open(calib)); e = d.get(str(take))
        if e: corners, src = e["corners"], calib
        elif d: corners, src = {k: np.mean([v["corners"][k] for v in d.values()], 0).tolist() for k in ORDER}, calib + " (mean of takes)"
    if corners is None:
        corners, info = corners_from(p, c4, hz)
        if corners is None: return {"take": os.path.basename(path), "error": f"not enough grasp/release events {info}"}
    ctr, R, finfo = table_frame(corners, p)
    q = (p - ctr) @ R.T
    gi = [i for _, i in ev]; h0 = float(np.median(q[gi, 2])) if gi else float(np.min(q[:, 2]))
    wrist = np.stack([q[:, 0], q[:, 1], GRASP_Z_FOR[obj] + (q[:, 2] - h0)], 1)
    cq = {k: ((np.asarray(corners[k]) - ctr) @ R.T)[:2] for k in ORDER}
    if fingers == "synthetic": f = np.repeat(synthetic_grip(len(g), ev, hz)[:, None], 5, 1)
    sc = Scene(obj, obj_xy=tuple(cq["BL"]), pedestals=tuple(tuple(v) for v in cq.values()), ped_half=(0.03, 0.03))
    sc.place_hand(*wrist[0])
    rel = sorted(i for k, i in ev if k == "release"); checks = {min(i + int(0.5 * hz), len(g) - 1): n for n, i in enumerate(rel[:4])}
    legs = []
    for i in range(len(g)):
        sc.step(f[i].tolist(), tuple(wrist[i]), 1.0 / hz)
        if i in checks:
            tgt = TARGETS[checks[i]]; o = sc.obj_pos(); err = float(np.linalg.norm(o[:2] - cq[tgt]))
            legs.append({"target": tgt, "err_m": round(err, 3), "ok": err < TOL_M})
    o = sc.obj_pos()
    side = np.mean([np.linalg.norm(cq[a] - cq[b]) for a, b in zip(ORDER, ORDER[1:] + ORDER[:1])])
    clipped = float(np.mean((np.abs(wrist[:, 0]) > 0.4) | (np.abs(wrist[:, 1]) > 0.4) | (wrist[:, 2] < 0.05) | (wrist[:, 2] > 0.4)))
    return {"take": os.path.basename(path), "series": series, "hand": h, "obj": obj, "fingers": fingers, "calib_src": src,
            "events": len(ev), "square_side_m": round(float(side), 3), **finfo, "wrist_clipped_frac": round(clipped, 3),
            "legs": legs, "legs_ok": sum(l["ok"] for l in legs), "final_obj_xy": np.round(o[:2], 3).tolist(),
            "peak_force_N": round(sc.peak_force, 2)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("episode", nargs="+")
    ap.add_argument("--obj", default="cube", choices=["cube", "egg"]); ap.add_argument("--fingers", default="real", choices=["real", "gain", "synthetic"])
    ap.add_argument("--calib", default=os.path.join(ROOT, "data", "square_calib.json")); ap.add_argument("--hand", default="active", choices=["active", "left", "right"])
    a = ap.parse_args()
    for e in a.episode: print(json.dumps(replay_square(e, a.obj, a.fingers, a.calib, hand=a.hand)))
