"""PLAN 2.3: replay an EPISODE (data/episodes/take_NN.npz from Rokoko/src/episodes.py, 30 Hz, fingers01 + Coil wrist) on the MuJoCo scene.
  python -m robot.replay data/episodes/take_05.npz --obj egg [--hand active|left|right] [--invert] [--fingers real|synthetic] [--assist egg]
fingers01 comes from the recorder's normalisation and its polarity is UNVERIFIED (see docs/PHASE1_REAL_DATA.md): use --invert to flip it.
If data/calib.json exists with {"invert": true|false}, it is applied automatically (unless --invert/--no-calib is given).
Pick point: --pick wrist (lowest wrist, as play_real_data) or --pick closure (onset of the strongest grip, needs calibrated fingers). Approach not tested.
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
    t = z["t"].astype(float); f = z[f"{h}_fingers01"].astype(float).copy(); p = z[f"{h}_wrist_pos"].astype(float)
    if f"{h}_thumb01" in z.files and "thumb01_valid" in z.files and bool(z["thumb01_valid"]):
        f[:, 0] = z[f"{h}_thumb01"].astype(float)   # calibrated solver thumb (series G, contract in docs/contracts.md) replaces column 0
    ok = ~np.isnan(p).any(1)
    g = np.arange(0, t[-1] - t[0], 1.0 / hz)
    fi = np.stack([np.interp(g, t - t[0], f[:, k]) for k in range(5)], 1)
    pi = np.stack([np.interp(g, (t - t[0])[ok], p[ok, k]) for k in range(3)], 1)
    return g, np.clip(fi, 0, 1), pi, h, str(z["series"]), bool(z["calibrated"]) if "calibrated" in z.files else False


def replay(path, obj="cube", hand="active", invert=None, fingers="real", assist=None, hz=60, use_calib=True, pick="wrist", floor=False):
    g, f, p, h, series, calibrated = load_episode(path, hand, hz)
    if invert is None and calibrated: invert = False   # fingers01 already uses data/calib.json (open/closed + sign from series E)
    if invert is None:
        invert = False
        cp = os.path.join(ROOT, "data", "calib.json")
        if use_calib and os.path.exists(cp): invert = bool(json.load(open(cp)).get("invert", False))
    if invert: f = 1 - f
    if fingers == "gain":   # per-take grip gain: the take's strongest grip (98th pct of index..little mean) -> fully closed
        f = np.clip(f / max(np.percentile(f[:, 1:].mean(1), 98), 0.15), 0, 1); fingers = "real"
    r = run_sim(g, f, p, obj, assist, hz, "inverted" if invert else "as_recorded", os.path.basename(path), h, fingers, pick, floor)
    r["series"] = series; r["calibrated"] = calibrated
    return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("episode", nargs="+")
    ap.add_argument("--obj", default="cube", choices=["cube", "egg"]); ap.add_argument("--hand", default="active", choices=["active", "left", "right"])
    ap.add_argument("--invert", action="store_true", default=None); ap.add_argument("--no-calib", action="store_true")
    ap.add_argument("--fingers", default="real", choices=["real", "gain", "synthetic"]); ap.add_argument("--assist", choices=["cup", "egg", "can"])
    ap.add_argument("--pick", default="wrist", choices=["wrist", "closure"], help="grasp moment: lowest wrist (default) or onset of the strongest grip")
    ap.add_argument("--floor", action="store_true", help="wrist never below the grasp height (no pushing the object into the table)")
    a = ap.parse_args()
    for p in a.episode:
        print(json.dumps(replay(p, a.obj, a.hand, a.invert, a.fingers, a.assist, use_calib=not a.no_calib, pick=a.pick, floor=a.floor)))
