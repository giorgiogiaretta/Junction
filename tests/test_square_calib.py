import sys, pathlib
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "Rokoko" / "src"))
from square_calib import corners_from, fit, SIDE

def synth(hz=30, R=None, off=(0.5, -0.4, 0.3)):
    s = SIDE; tab = {"BL": (0, 0, 0), "TL": (0, s, 0), "TR": (s, s, 0), "BR": (s, 0, 0)}; order = ["BL", "TL", "TR", "BR", "BL"]
    pos, cl = [], []
    def seg(a, b, n, c0, c1):
        for k in range(n): t = k / max(1, n - 1); pos.append(np.array(a) * (1 - t) + np.array(b) * t); cl.append(c0 * (1 - t) + c1 * t)
    for i in range(4):
        a, b = np.array(tab[order[i]]), np.array(tab[order[i + 1]])
        seg(a, a, int(1.0 * hz), 0, 0); seg(a, a, int(0.4 * hz), 0, 1)          # rest then grasp at A
        seg(a, b, int(2.5 * hz), 1, 1); seg(b, b, int(0.4 * hz), 1, 0)          # carry to B, release
    pos = np.array(pos); R = np.eye(3) if R is None else R
    return (pos @ R.T) + np.array(off), np.array(cl)

def test_square_recovered_scale_and_sides():
    th = np.deg2rad(37); R = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
    pos, cl = synth(R=R); pos = pos + np.random.default_rng(0).normal(0, 0.002, pos.shape)
    cs, info = corners_from(pos, cl); assert cs is not None and info["grasps"] == 4 and info["releases"] == 4
    r = fit(cs); assert abs(r["scale_vs_A4"] - 1.0) < 0.1
    assert all(abs(v - SIDE) < 0.04 for v in r["side_lengths_m"].values())
    assert r["plane_flatness_m"] < 0.02
