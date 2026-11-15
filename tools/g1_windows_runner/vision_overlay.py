"""Real-G1 run -> demo video: the runner's head-camera recording with what the -CoilVision policy believed at each moment.

    py -3.11 tools/g1_windows_runner/vision_overlay.py --run <aaltonomous runs/giorgio/<time>> [--policy-log data/live/live_policy_v2_vision.jsonl]
        [--press data/live/dex3_press_<time>.jsonl] [--out data/video/g1_real_cv_<time>.mp4]

Per frame (the runner writes one head frame per 30 Hz tick, so frame i = npz row i):
  - every object of the policy's latest CANDIDATES event, projected into the image with the organisers' head calibration
    (aaltonomous Calibration: K + T_pelvis_optical, PROVISIONAL extrinsics): label, finger cap, source
    (camera = recognised by the head camera, cli = command-line fallback, not seen);
  - the current TARGET of each hand (the object that sets that hand's force cap) highlighted;
  - side panel: commanded finger closure per hand, Dex3 fingertip pressure (kPa rise, if --press), arm command vs measured.
Nothing is invented: every label/position/cap shown comes from the policy log at that time. Positions are where the camera saw
the object when it was detected (the projection uses the provisional extrinsics: a few cm off is expected).
"""
import argparse, json, os, sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT_A = r"C:\Users\giorg\Desktop\aaltonomous-humanoid"
COL = {"can_empty": (60, 200, 255), "stress_ball": (80, 220, 80), "egg": (255, 255, 255), "unknown": (180, 180, 180)}


def session(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    last, prev = [], None
    for r in rows:
        t = r.get("t")
        if t is None: continue
        if prev is not None and t < prev - 5: last = []
        last.append(r); prev = t
    return last


def calib():
    sys.path.insert(0, ROOT_A)
    from aaltonomous.interface.calibration import Calibration
    cal = Calibration.load(); return np.asarray(cal.cams["head"].K, float), np.asarray(cal._T("head"), float)


def project(K, T, p):
    Ti = np.linalg.inv(T); q = Ti[:3, :3] @ np.asarray(p, float) + Ti[:3, 3]
    if q[2] <= 0.05: return None
    return int(K[0, 0] * q[0] / q[2] + K[0, 2]), int(K[1, 1] * q[1] / q[2] + K[1, 2])


def press_series(path, hand_q_meas, wall):
    """Dex3 pressure log -> per-frame fingertip kPa (max over pads 1/3/5) per hand, time-aligned on the measured hand joints."""
    rows = [json.loads(l) for l in open(path)]
    out = {}
    for k, side in enumerate(("left", "right")):
        R = [r for r in rows if r["hand"] == side]
        t = np.array([r["t"] for r in R]); P = np.array([r["pressure"] for r in R]); q = np.array([r["q"] for r in R])
        real = P[0] != 30000.0; base = np.median(P[t < 1.0], 0); D = (P - base) / 1000.0; D[:, ~real] = 0
        pad = D.sum(2); out[side] = (t, pad, q)
    # align: the runner's measured hand q (npz) vs the logger's q, both from rt/dex3/*/state
    t, _, q = out["left"]; s1 = np.abs(q).sum(1); s2 = np.abs(hand_q_meas[:, :7]).sum(1)
    grid = np.arange(0, t[-1], 1 / 30.0); a = np.interp(grid, t, s1); b = np.interp(np.arange(len(s2)) / 30.0, wall - wall[0], s2)
    best, off = -1e9, 0.0
    for k in range(0, max(1, len(a) - len(b) // 2)):
        n = min(len(b), len(a) - k)
        if n < 100: break
        c = -np.mean((a[k:k + n] - b[:n]) ** 2)
        if c > best: best, off = c, k / 30.0
    return out, off


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True); ap.add_argument("--policy-log", default=os.path.join(ROOT, "data/live/live_policy_v2_vision.jsonl"))
    ap.add_argument("--press"); ap.add_argument("--out"); ap.add_argument("--title", default="REAL Unitree G1 - Rokoko gloves + Coil - head camera")
    a = ap.parse_args()
    z = np.load(os.path.join(a.run, "episode_000.npz")); wall = z["wall"] - z["wall"][0]
    cap = cv2.VideoCapture(os.path.join(a.run, "episode_000.mp4")); nf = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    S = session(a.policy_log); ev = [r for r in S if "event" in r]
    cands = [(r["t"], r["objects"]) for r in ev if r["event"] == "CANDIDATES"]
    targets = [(r["t"], r["hand"], r["object"], r["cap"], r["src"], r["dist_cm"]) for r in ev if r["event"] == "TARGET"]
    vis = [r for r in ev if r["event"] == "VISION"]
    K, T = calib()
    press, off = (press_series(a.press, z["hand_q"], z["wall"]) if a.press else (None, 0.0))
    if press: print(f"[overlay] pressure log aligned: runner t=0 is logger t={off:.2f} s", flush=True)
    out = a.out or os.path.join(ROOT, "data", "video", "g1_real_cv_" + os.path.basename(os.path.normpath(a.run)) + ".mp4")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    W, H, PW = 640, 480, 320
    vw = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), 30, (W + PW, H + 40))
    font = cv2.FONT_HERSHEY_SIMPLEX
    for i in range(min(nf, len(wall))):
        ok, fr = cap.read()
        if not ok: break
        t = float(wall[i]); img = fr.copy()
        cur = None
        for tc, o in cands:
            if tc <= t: cur = o
        tg = {}
        for tt, h, n, c, src, d in targets:
            if tt <= t: tg[h] = (n, c, src, d)
        if cur is not None:
            seen = {}
            for side, lst in cur.items():
                for n, src, c, p in lst: seen[(n, src, tuple(np.round(p, 2)))] = (n, src, c, p)
            for n, src, c, p in seen.values():
                uv = project(K, T, p)
                if uv is None: continue
                col = COL.get(n, (200, 200, 200)); hit = [h for h, v in tg.items() if v[0] == n and abs(v[1] - c) < 1e-6 or (v[0] == n and src == v[2])]
                cv2.circle(img, uv, 26 if hit else 18, col, 3 if src == "camera" else 1, cv2.LINE_AA)
                lab = f"{n} cap {c:.2f} [{'CAMERA' if src == 'camera' else 'fallback, not seen'}]"
                cv2.putText(img, lab, (uv[0] - 80, uv[1] - 32), font, 0.45, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(img, lab, (uv[0] - 80, uv[1] - 32), font, 0.45, col, 1, cv2.LINE_AA)
        panel = np.full((H, PW, 3), 28, np.uint8); y = 26
        cv2.putText(panel, f"t = {t:6.1f} s", (12, y), font, 0.6, (255, 255, 255), 1, cv2.LINE_AA); y += 30
        for k, side in enumerate(("left", "right")):
            cv2.putText(panel, side.upper() + " HAND", (12, y), font, 0.55, (255, 220, 120), 1, cv2.LINE_AA); y += 22
            if side in tg:
                n, c, src, d = tg[side]
                cv2.putText(panel, f"target {n}", (12, y), font, 0.48, COL.get(n, (220, 220, 220)), 1, cv2.LINE_AA); y += 18
                cv2.putText(panel, f"cap {c:.2f} ({'camera' if src == 'camera' else 'fallback'}), {d:.0f} cm", (12, y), font, 0.45, (220, 220, 220), 1, cv2.LINE_AA); y += 20
            else: y += 38
            hc = z["hand_q_cmd"][i, 7 * k: 7 * k + 7]; clo = float(np.clip(np.abs(hc).max() / 1.55, 0, 1))
            cv2.putText(panel, "finger closure cmd", (12, y), font, 0.42, (200, 200, 200), 1, cv2.LINE_AA)
            cv2.rectangle(panel, (150, y - 10), (150 + int(150 * clo), y), (80, 200, 255), -1); cv2.rectangle(panel, (150, y - 10), (300, y), (90, 90, 90), 1); y += 20
            if press:
                tt, pad, _ = press[side]; j = int(np.clip(np.searchsorted(tt, t + off), 0, len(tt) - 1)); kp = float(max(pad[j, [1, 3, 5]].max(), pad[j, 6], 0))
                cv2.putText(panel, f"fingertip pressure {kp:4.1f} kPa", (12, y), font, 0.42, (200, 200, 200), 1, cv2.LINE_AA)
                cv2.rectangle(panel, (12, y + 4), (12 + int(min(1, kp / 15) * 288), y + 12), (90, 90, 255), -1); y += 26
            y += 10
        ea = np.abs(z["arm_q_cmd"][i] - z["arm_q"][i]).mean()
        cv2.putText(panel, f"arm |cmd - measured| {ea:.3f} rad", (12, y), font, 0.42, (200, 200, 200), 1, cv2.LINE_AA); y += 22
        if vis:
            v = vis[0]; cv2.putText(panel, f"vision: {v.get('engine')}", (12, y), font, 0.4, (160, 160, 160), 1, cv2.LINE_AA); y += 16
            cv2.putText(panel, f"first detection {v.get('latency_s')} s", (12, y), font, 0.4, (160, 160, 160), 1, cv2.LINE_AA)
        cv2.putText(panel, "thick ring = seen by the camera", (12, H - 30), font, 0.4, (160, 160, 160), 1, cv2.LINE_AA)
        cv2.putText(panel, "thin ring = fallback position", (12, H - 12), font, 0.4, (160, 160, 160), 1, cv2.LINE_AA)
        top = np.full((40, W + PW, 3), 15, np.uint8); cv2.putText(top, a.title, (12, 27), font, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        vw.write(np.vstack([top, np.hstack([img, panel])]))
    vw.release(); print(f"[overlay] {out} ({i + 1} frames)", flush=True)


if __name__ == "__main__":
    main()
