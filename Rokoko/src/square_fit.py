"""Fit the 29.7 cm table square to the wrist path of series H (robust: no grasp events needed).
Project the moving wrist samples on their best plane (PCA), fit a square outline (centre, rotation, half-side) by least squares on the distance
to the outline. Reports free side (scale check vs 29.7 cm), residual, plane tilt, square centre in the Coil frame.  python Rokoko/src/square_fit.py
"""
import json
import numpy as np
from scipy.optimize import minimize

SIDE = 0.297

def dist_to_square(P, c, th, a):
    R = np.array([[np.cos(th), np.sin(th)], [-np.sin(th), np.cos(th)]]); q = (P - c) @ R.T
    m = np.maximum(np.abs(q[:, 0]), np.abs(q[:, 1])); return np.abs(m - a)

def fit_square(P2, a0=SIDE / 2, fixed_a=False):
    best = None; ctr0 = (P2.min(0) + P2.max(0)) / 2
    for th0 in np.deg2rad(np.arange(0, 90, 10)):
        x0 = [ctr0[0], ctr0[1], th0] + ([] if fixed_a else [a0])
        f = lambda x: np.mean(dist_to_square(P2, x[:2], x[2], a0 if fixed_a else x[3]) ** 2)
        r = minimize(f, x0, method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-10, "maxiter": 2000})
        if best is None or r.fun < best.fun: best = r
    x = best.x; return {"center2d": x[:2], "theta": float(x[2] % (np.pi / 2)), "half_side": float(a0 if fixed_a else abs(x[3])), "rms": float(np.sqrt(best.fun))}

def label_corners(pos, C3, hz=30, near=0.08, vslow=0.15):
    """Name the 4 fitted corners BL,TL,TR,BR from the visit order (can goes BL>TL>TR>BR>BL; the first slow visit is BL)."""
    v = np.r_[0, np.linalg.norm(np.diff(pos, axis=0), axis=1)] * hz
    d = np.linalg.norm(pos[:, None, :] - C3[None], axis=2); k = d.argmin(1)
    seq = [int(k[i]) for i in range(len(pos)) if d[i, k[i]] < near and v[i] < vslow]
    seq = [c for j, c in enumerate(seq) if j == 0 or c != seq[j - 1]]
    if len(seq) < 2: return None
    steps = [(b - a) % 4 for a, b in zip(seq, seq[1:])]; dirn = 1 if steps.count(1) >= steps.count(3) else -1
    return {n: np.round(C3[(seq[0] + dirn * j) % 4], 3).tolist() for j, n in enumerate(("BL", "TL", "TR", "BR"))}

def analyse(pos, hz=30, vmin=0.05):
    v = np.r_[0, np.linalg.norm(np.diff(pos, axis=0), axis=1)] * hz; mv = pos[v > vmin]
    c = mv.mean(0); u, s, vt = np.linalg.svd(mv - c, full_matrices=False); e1, e2, n = vt
    P2 = (mv - c) @ np.stack([e1, e2], 1)
    free = fit_square(P2); fx = fit_square(P2, fixed_a=True)
    th, a, c2 = free["theta"], free["half_side"], free["center2d"]; Rt = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    C3 = np.array([c + np.array([e1, e2]).T @ (c2 + Rt @ np.array(q) * a) for q in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    return {"corners": label_corners(pos, C3, hz), "side_free_m": round(2 * free["half_side"], 3), "rms_free_m": round(free["rms"], 3), "rms_fixed_297_m": round(fx["rms"], 3),
            "plane_normal_coil": np.round(n, 3).tolist(), "plane_tilt_from_z_deg": round(float(np.degrees(np.arccos(abs(n[2])))), 1),
            "square_center_coil_m": np.round(c + np.array([e1, e2]).T @ free["center2d"], 3).tolist(), "n_moving": int(len(mv))}

if __name__ == "__main__":
    idx = [i for i in json.load(open("data/episodes/index.json")) if i["series"] == "H"]; out = {}
    for i in idx:
        z = np.load(f"data/episodes/take_{i['take']:02d}.npz", allow_pickle=True); h = i["active_hand"]
        r = analyse(z[f"{h}_wrist_pos"]); out[i["take"]] = {"hand": h, **r}
        print(f"take {i['take']} {h:5s} side {r['side_free_m']:.3f} m (rms {r['rms_free_m']:.3f}, fixed-297 rms {r['rms_fixed_297_m']:.3f}) tilt {r['plane_tilt_from_z_deg']:4.1f} deg centre {r['square_center_coil_m']}")
    for h in ("right", "left"):
        s = [v["side_free_m"] for v in out.values() if v["hand"] == h]
        if s: print(f"{h}: side {np.mean(s):.3f} +- {np.std(s):.3f} m over {len(s)} takes (true 0.297)")
    json.dump(out, open("data/square_fit.json", "w"), indent=1)
