"""Series H replay (known geometry): an empty can is moved around a 29.7 cm square BL -> TL -> TR -> BR -> BL; replay the real wrist
track in the sim with the square measured by Rokoko/src/square_calib.py (data/square_calib.json, corners in the Coil frame).
  python -m robot.replay_square data/episodes/take_NN.npz [--fingers gain|events|real] [--corners take|pooled]
Coil frame -> table frame: origin = square centre, x = left->right, y = operator->far side, z = up (normal). Hand height: the wrist
height at the grasp corners is mapped to the sim grasp height (wrist-to-palm offset is unknown), and the wrist never goes below it.
Result per leg: can distance to the target corner after the release; success if < LEG_TOL_M and the can is still upright.
fingers: gain = recorded closure scaled so the take's 98th pct = closed; events = closed between the grasp/release events
(square_calib.events), i.e. the real wrist with a clean grip; real = recorded closure as is.
This is a proxy: the sim hand grips from above with a horizontal palm; the human grips the can from the side.
"""
import argparse, json, os, sys
import numpy as np
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from robot.scene import Scene, OBJ_HALF_Z, TABLE_Z

SIDE = 0.297
ORDER = ["BL", "TL", "TR", "BR"]
CAN_GRASP_HAND_Z = 0.085     # hand body height for a can on the table (palm just above the can top, fingertips around mid-can)
LEG_TOL_M = 0.06
UPRIGHT_TOL_M = 0.01
EVENTS_GRIP = 0.6            # closure for fingers=events. Synthetic sweep: 0.5-0.7 -> 4/4 legs upright, err < 2 cm; 1.0 squeezes, the can tips at release


def table_frame(corners):
    """corners {BL,TL,TR,BR: xyz in the Coil frame} -> (centre, R) with R columns = table x, y, z axes in the Coil frame."""
    C = {k: np.asarray(corners[k], float) for k in ORDER}
    ctr = np.mean([C[k] for k in ORDER], 0)
    ex = (C["TR"] + C["BR"]) / 2 - (C["TL"] + C["BL"]) / 2; ex /= np.linalg.norm(ex)
    ey = (C["TL"] + C["TR"]) / 2 - (C["BL"] + C["BR"]) / 2; ey -= ex * (ey @ ex); ey /= np.linalg.norm(ey)
    return ctr, np.stack([ex, ey, np.cross(ex, ey)], 1)


def to_table(p, corners):
    ctr, R = table_frame(corners)
    return (p - ctr) @ R


def grip_events(closure, hz):
    """(grasp_idx, release_idx) lists from Giorgio's square_calib.events (same thresholds as the calibration)."""
    sys.path.insert(0, os.path.join(ROOT, "Rokoko", "src"))
    from square_calib import events
    ev = events(closure, hz=hz)
    return [i for k, i in ev if k == "grasp"], [i for k, i in ev if k == "release"]


def run_square(g, clo, posi, corners, fingers="gain", hz=60, name=""):
    """g (N,) s, clo (N,5) closure 0..1, posi (N,3) Coil-frame wrist, corners: Coil-frame square. Returns per-leg results."""
    q = to_table(posi, corners)
    c4 = clo[:, 1:].mean(1)
    gi, ri = grip_events(c4, hz)
    zc = np.mean([to_table(np.asarray(corners[k], float)[None], corners)[0, 2] for k in ORDER])   # wrist height at the corners
    hand = np.stack([q[:, 0], q[:, 1], CAN_GRASP_HAND_Z + np.maximum(q[:, 2] - zc, 0.0)], 1)
    if fingers == "gain":
        clo = np.clip(clo / max(np.percentile(c4, 98), 0.15), 0, 1)
    elif fingers == "events":
        on = np.zeros(len(g))
        for a, b in zip(gi, ri): on[a:b] = EVENTS_GRIP
        ramp = max(1, int(0.1 * hz))   # short close/open ramps instead of a 1-frame step
        clo = np.repeat(np.convolve(on, np.ones(ramp) / ramp, mode="full")[:len(g)][:, None], 5, 1)
    half = SIDE / 2
    target = {"BL": (-half, -half), "TL": (-half, half), "TR": (half, half), "BR": (half, -half)}
    # Each leg is scored on its own: fresh scene, can upright at the leg's start corner, replay from 1 s before the grasp to
    # 0.5 s after the release. Otherwise one tipped can (this top-grip hand cannot regrasp a lying can) fails every later leg.
    legs, peak = [], 0.0
    for k in range(4):
        src, tgt = ORDER[k], ORDER[(k + 1) % 4]
        if k >= len(gi) or k >= len(ri) or ri[k] <= gi[k]:
            legs.append({"leg": f"{src}->{tgt}", "release_t_s": None, "ok": False}); continue
        a = max(gi[k] - int(1.0 * hz), ri[k - 1] if k else 0); b = min(ri[k] + int(0.5 * hz), len(g) - 1)
        sc = Scene("can", obj_xy=target[src], pedestal=False); sc.place_hand(*hand[a])
        rise = 0.0
        for i in range(a, b + 1):
            sc.step(clo[i].tolist(), tuple(hand[i]), 1.0 / hz); rise = max(rise, float(sc.obj_pos()[2] - sc.rest_z))
        o = sc.obj_pos(); d = float(np.linalg.norm(o[:2] - target[tgt])); peak = max(peak, sc.peak_force)
        legs.append({"leg": f"{src}->{tgt}", "release_t_s": round(float(g[ri[k]]), 1), "err_m": round(d, 3), "max_rise_m": round(rise, 3),
                     "upright": bool(abs(o[2] - sc.rest_z) < UPRIGHT_TOL_M), "ok": bool(d < LEG_TOL_M and rise > 0.03)})
    return {"take": name, "fingers": fingers, "grasps": len(gi), "releases": len(ri), "legs_ok": sum(l["ok"] for l in legs),
            "legs_upright": sum(bool(l.get("upright")) for l in legs), "legs": legs, "peak_force_N": round(peak, 2)}


def load_corners(take, mode="take"):
    cal = json.load(open(os.path.join(ROOT, "data", "square_calib.json")))
    if mode == "pooled":
        return {k: np.mean([r["corners"][k] for r in cal.values()], 0) for k in ORDER}
    return cal[str(take)]["corners"]


def replay_square(path, fingers="gain", corners="take", hz=60):
    from robot.replay import load_episode
    g, f, p, h, series, _ = load_episode(path, "active", hz)
    take = int(os.path.basename(path).split("_")[1].split(".")[0])
    r = run_square(g, f, p, load_corners(take, corners), fingers, hz, os.path.basename(path))
    r.update(series=series, hand=h, corners=corners); return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("episode", nargs="+")
    ap.add_argument("--fingers", default="gain", choices=["gain", "events", "real"]); ap.add_argument("--corners", default="take", choices=["take", "pooled"])
    a = ap.parse_args()
    for p in a.episode: print(json.dumps(replay_square(p, a.fingers, a.corners)))
