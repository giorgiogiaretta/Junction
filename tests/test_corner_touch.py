import sys, pathlib
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "Rokoko" / "src"))
from corner_touch import dwells, corners_from_dwells, report

def test_synthetic_laps():
    s, hz = 0.25, 30; C = [np.array(c) for c in ((0, 0, 0), (0, s, 0), (s, s, 0), (s, 0, 0), (0, 0, 0))] * 2
    th = np.deg2rad(30); R = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]]); pos = []
    for k, c in enumerate(C):
        pos += [c] * int(2.2 * hz)
        if k < len(C) - 1: pos += [c + (C[k + 1] - c) * t for t in np.linspace(0, 1, int(1.2 * hz))]
    pos = np.array(pos) @ R.T + np.array([0.6, -0.3, 0.4]) + np.random.default_rng(1).normal(0, 0.0003, (len(pos), 3))
    r = report(corners_from_dwells(dwells(pos)), 0.25)
    assert "error" not in r and abs(r["scale_vs_tape"] - 1) < 0.05 and abs(r["diag_over_side"] - 1.414) < 0.05
