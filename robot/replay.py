"""PLAN 2.3: replay an EPISODE (data/episodes/take_NN.npz from Rokoko/src/episodes.py, 30 Hz, fingers01 + Coil wrist) on the MuJoCo scene.
  python -m robot.replay data/episodes/take_05.npz --obj egg [--hand active|left|right] [--invert] [--fingers real|synthetic] [--assist egg]
fingers01 comes from the recorder's normalisation and its polarity is UNVERIFIED (see docs/PHASE1_REAL_DATA.md): use --invert to flip it.
If data/calib.json exists with {"invert": true|false}, it is applied automatically (unless --invert/--no-calib is given).
Same pick-point convention as play_real_data (object under the hand at the lowest wrist point; approach not tested).
"""
import argparse, json, os, sys
import numpy as np
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from robot.play_real_data import run_sim


def load_episode(path, hand="active", hz=60):
    z = np.load(path, allow_pickle=True)
    h = str(z["active_hand"]) if hand == "active" else hand
    if h not in ("left", "right"): h = "right"
    t = z["t"].astype(float); f = z[f"{h}_fingers01"].astype(float); p = z[f"{h}_wrist_pos"].astype(float)
    ok = ~np.isnan(p).any(1)
    g = np.arange(0, t[-1] - t[0], 1.0 / hz)
    fi = np.stack([np.interp(g, t - t[0], f[:, k]) for k in range(5)], 1)
    pi = np.stack([np.interp(g, (t - t[0])[ok], p[ok, k]) for k in range(3)], 1)
    return g, np.clip(fi, 0, 1), pi, h, str(z["series"]), bool(z["calibrated"]) if "calibrated" in z.files else False


def replay(path, obj="cube", hand="active", invert=None, fingers="real", assist=None, hz=60, use_calib=True):
    g, f, p, h, series, calibrated = load_episode(path, hand, hz)
    if invert is None and calibrated: invert = False   # fingers01 already uses data/calib.json (open/closed + sign from series E)
    if invert is None:
        invert = False
        cp = os.path.join(ROOT, "data", "calib.json")
        if use_calib and os.path.exists(cp): invert = bool(json.load(open(cp)).get("invert", False))
    if invert: f = 1 - f
    r = run_sim(g, f, p, obj, assist, hz, "inverted" if invert else "as_recorded", os.path.basename(path), h, fingers)
    r["series"] = series; r["calibrated"] = calibrated
    return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("episode", nargs="+")
    ap.add_argument("--obj", default="cube", choices=["cube", "egg"]); ap.add_argument("--hand", default="active", choices=["active", "left", "right"])
    ap.add_argument("--invert", action="store_true", default=None); ap.add_argument("--no-calib", action="store_true")
    ap.add_argument("--fingers", default="real", choices=["real", "synthetic"]); ap.add_argument("--assist", choices=["cup", "egg", "can"])
    a = ap.parse_args()
    for p in a.episode:
        print(json.dumps(replay(p, a.obj, a.hand, a.invert, a.fingers, a.assist, use_calib=not a.no_calib)))
