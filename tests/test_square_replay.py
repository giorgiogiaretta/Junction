"""Series H square replay on a SYNTHETIC take: a scripted can transport around the square, expressed in a rotated + offset Coil frame."""
import numpy as np
import pytest
pytest.importorskip("mujoco")
from robot.replay_square import run_square, table_frame, ORDER, SIDE


def _rot(a, b):
    ca, sa, cb, sb = np.cos(a), np.sin(a), np.cos(b), np.sin(b)
    return np.array([[ca, -sa, 0], [sa, ca, 0], [0, 0, 1]]) @ np.array([[1, 0, 0], [0, cb, -sb], [0, sb, cb]])


def synthetic_take(hz=60):
    """Table-frame script: rest, then per leg descend, close, lift, carry, descend, open. Returns g, clo, coil pos, coil corners."""
    h = SIDE / 2; xy = {"BL": (-h, -h), "TL": (-h, h), "TR": (h, h), "BR": (h, -h)}
    lo, hi = 0.0, 0.10                      # wrist height above its grasp level (table frame)
    pts, clo = [], []
    def seg(a, b, za, zb, c0, c1, s):
        for i in range(int(s * hz)):
            u = i / (s * hz); pts.append([a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, za + (zb - za) * u]); clo.append(c0 + (c1 - c0) * u)
    seg(xy["BL"], xy["BL"], hi, hi, 0, 0, 1.0)
    for k in range(4):
        a, b = xy[ORDER[k]], xy[ORDER[(k + 1) % 4]]
        seg(a, a, hi, lo, 0, 0, 0.8); seg(a, a, lo, lo, 0, 1, 0.6); seg(a, a, lo, hi, 1, 1, 0.8)
        seg(a, b, hi, hi, 1, 1, 1.5); seg(b, b, hi, lo, 1, 1, 0.8); seg(b, b, lo, lo, 1, 0, 0.6); seg(b, b, lo, hi, 0, 0, 0.8)
    q = np.array(pts); c = np.repeat(np.array(clo)[:, None], 5, 1)
    R, off = _rot(0.7, 0.3), np.array([-0.6, 0.4, -0.3])
    coil = q @ R.T + off
    corners = {k: (np.array([*xy[k], lo]) @ R.T + off).tolist() for k in ORDER}
    return np.arange(len(q)) / hz, c, coil, corners


def test_table_frame_recovers_rotation():
    g, c, coil, corners = synthetic_take()
    ctr, R = table_frame(corners)
    assert np.allclose(R.T @ R, np.eye(3), atol=1e-9)
    assert np.allclose(R[:, 2], _rot(0.7, 0.3)[:, 2], atol=1e-6)    # table normal


def test_synthetic_square_legs():
    g, c, coil, corners = synthetic_take()
    r = run_square(g, c, coil, corners, fingers="events")
    assert r["grasps"] == 4 and r["releases"] == 4
    assert r["legs_ok"] >= 3, r
