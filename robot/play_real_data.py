"""Replay a RECORDED take (data/raw/take_NN.rgmp from Rokoko/src/take.py) through the MuJoCo grasp scene (PLAN Phase 1 integration).
  python -m robot.play_real_data data/raw/take_02.rgmp --obj cube [--hand right] [--polarity auto|client|inverted] [--assist egg]
Pipeline: raw RGMP -> Rokoko/src/analyze_takes.parse (finger angles, Coil Pro wrist position) -> 60 Hz resample ->
  finger closure 0..1 (per-take 5-95 percentile normalisation per finger) -> optional Force Cushion -> Scene.step.
Wrist: Coil Pro position (frame assumed z-up, metres) relative to the PICK POINT. The object is placed under the hand at the
moment of lowest wrist height in the middle of the take (so the approach is NOT tested, only grasp + lift + release).
Finger polarity: angle_of(finger quaternion) may grow or shrink when closing; `auto` picks the polarity under which the hand is
more closed while the wrist is lifting (assumption; verify with a labelled flat-hand / fist recording).
"""
import argparse, json, os, sys
import numpy as np
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "Rokoko", "src"))
from robot.scene import Scene, GRASP_Z, LIFT_MIN


def load_take(path, hand="right", hz=60):
    import analyze_takes as A
    rows = A.parse(path)
    if hand not in rows or len(rows[hand]) < 20: raise SystemExit(f"{path}: no '{hand}' glove data (have {list(rows)})")
    r = rows[hand]
    t = np.array([x[0] for x in r]); t = t - t[0]
    ang = np.array([x[1] for x in r])
    pos = np.array([x[2] if x[2] else [np.nan] * 3 for x in r], float)
    ok = ~np.isnan(pos).any(1)
    g = np.arange(0, t[-1], 1.0 / hz)
    angi = np.stack([np.interp(g, t, ang[:, k]) for k in range(5)], 1)
    posi = np.stack([np.interp(g, t[ok], pos[ok, k]) for k in range(3)], 1) if ok.sum() > 10 else None
    return g, angi, posi


def closure(angi, polarity, wrist_z=None):
    lo, hi = np.percentile(angi, 5, axis=0), np.percentile(angi, 95, axis=0)
    c = np.clip((angi - lo) / (hi - lo + 1e-6), 0, 1)       # client polarity: larger angle = closed
    inv = 1 - c
    if polarity == "client": return c, "client"
    if polarity == "inverted": return inv, "inverted"
    # auto: more closed while the wrist is above its pick height (lift) -> choose that polarity
    if wrist_z is None: return c, "client"
    mid = slice(len(c) // 5, 4 * len(c) // 5); pick = mid.start + int(np.argmin(wrist_z[mid]))
    lift = np.zeros(len(c), bool); lift[pick + 15:] = wrist_z[pick + 15:] > wrist_z[pick] + 0.05
    if lift.sum() < 10: return c, "client"
    return (c, "client") if c[lift].mean() >= inv[lift].mean() else (inv, "inverted")


def play(path, obj="cube", hand="right", polarity="auto", assist=None, hz=60, fingers="real"):
    g, angi, posi = load_take(path, hand, hz)
    if posi is None: return {"take": os.path.basename(path), "error": "no Coil Pro position"}
    z = posi[:, 2]
    clo, pol = closure(angi, polarity, z)
    mid = slice(len(g) // 5, 4 * len(g) // 5); ip = mid.start + int(np.argmin(z[mid]))   # pick point = lowest wrist in the middle
    if fingers == "synthetic":
        # real Coil Pro wrist path + SYNTHETIC grip: fist ramps closed over 0.5 s from the pick, opens when the wrist is back down after the lift
        rose = np.where(z[ip:] > z[ip] + 0.05)[0]; rel_i = len(g) - 1
        if rose.size:
            back = np.where(z[ip + rose[0]:] < z[ip] + 0.03)[0]
            if back.size: rel_i = ip + rose[0] + int(back[0])
        clo = np.zeros_like(clo)
        for i in range(len(g)): clo[i] = np.clip((i - ip) / (0.5 * hz), 0, 1) if i < rel_i else 0.0
        pol = "synthetic"
    rel = posi - posi[ip]
    wrist = np.stack([rel[:, 0], rel[:, 1], GRASP_Z + rel[:, 2]], 1)
    sc = Scene(obj); sc.place_hand(*wrist[0])
    ga = None
    if assist:
        from ml.grasp_assist import GraspAssist; ga = GraspAssist(profile=assist)
    first_touch = None; max_rise = 0.0; held_frames = 0; peak = 0.0; held_after_pick = False
    for i in range(len(g)):
        f = clo[i].tolist()
        if ga: f, _ = ga.apply(f)
        s = sc.step(f, tuple(wrist[i]), 1.0 / hz)
        if first_touch is None and s["force"] > 0.05: first_touch = float(g[i])
        rise = s["obj_z"] - sc.rest_z; max_rise = max(max_rise, rise)
        if i > ip and s["held"]: held_frames += 1
    s = sc.state()
    return {"take": os.path.basename(path), "hand": hand, "obj": obj, "polarity": pol,
            "closure_at_pick": round(float(clo[ip].mean()), 2), "closure_in_lift": round(float(clo[ip + 15:][z[ip + 15:] > z[ip] + 0.05].mean()) if (z[ip + 15:] > z[ip] + 0.05).any() else float("nan"), 2), "dur_s": round(float(g[-1]), 1),
            "pick_t_s": round(float(g[ip]), 1), "wrist_rise_m": round(float(z.max() - z[ip]), 2),
            "touched": first_touch is not None, "first_touch_s": None if first_touch is None else round(first_touch, 1),
            "peak_force_N": round(s["peak_force"], 2), "max_obj_rise_m": round(max_rise, 3),
            "lifted": max_rise > LIFT_MIN, "held_s": round(held_frames / hz, 1), "broken": s["broken"]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("take", nargs="+")
    ap.add_argument("--obj", default="cube", choices=["cube", "egg"]); ap.add_argument("--hand", default="right", choices=["left", "right"])
    ap.add_argument("--polarity", default="auto", choices=["auto", "client", "inverted"]); ap.add_argument("--assist", choices=["cup", "egg", "can"])
    ap.add_argument("--fingers", default="real", choices=["real", "synthetic"], help="synthetic = real wrist path, scripted grip")
    ap.add_argument("--json", help="write results here")
    a = ap.parse_args(); res = []
    for p in a.take:
        r = play(p, a.obj, a.hand, a.polarity, a.assist, fingers=a.fingers); res.append(r); print(json.dumps(r))
    if a.json: json.dump(res, open(a.json, "w"), indent=1)
