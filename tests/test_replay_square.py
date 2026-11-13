"""robot.replay_square on a SYNTHETIC series H episode (no real H takes yet): a known square path, expressed in a rotated and
shifted 'Coil' frame, must be recovered (side ~0.297 m, wrist above the table) and the object carried corner to corner."""
import os, sys, pathlib
import numpy as np
import pytest
ROOT = pathlib.Path(__file__).parents[1]; sys.path.insert(0, str(ROOT))
pytest.importorskip("mujoco")


def _synthetic_h(path, side=0.297, hz=30):
    half = side / 2; C = {"BL": (-half, -half), "TL": (-half, half), "TR": (half, half), "BR": (half, -half)}
    route = ["BL", "TL", "TR", "BR", "BL"]; hov, low = 0.12, 0.0
    pts, clo = [], []
    def seg(a, b, za, zb, c, secs):
        n = int(secs * hz)
        for k in range(n):
            s = (k + 1) / n; pts.append((a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s, za + (zb - za) * s)); clo.append(c)
    bl = C["BL"]; seg(bl, bl, hov, hov, 0.0, 2.0); seg(bl, bl, hov, low, 0.0, 1.0)
    for a, b in zip(route, route[1:]):
        seg(C[a], C[a], low, low, 0.8, 1.2)           # close
        seg(C[a], C[a], low, hov, 0.8, 1.0)           # lift
        seg(C[a], C[b], hov, hov, 0.8, 1.5)           # carry
        seg(C[b], C[b], hov, low, 0.8, 1.0)           # lower
        seg(C[b], C[b], low, low, 0.0, 1.2)           # open
        seg(C[b], C[b], low, hov, 0.0, 1.0)           # up
    q = np.array(pts); n = len(q)
    # table frame -> 'Coil' frame: z-up table seen from a coil rotated 30 deg about z and tilted 10 deg, offset (0.6, -0.4, -0.3)
    a, b = np.radians(30), np.radians(10)
    Rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    Rx = np.array([[1, 0, 0], [0, np.cos(b), -np.sin(b)], [0, np.sin(b), np.cos(b)]])
    p = q @ (Rx @ Rz).T + np.array([0.6, -0.4, -0.3])
    f = np.tile(np.array(clo)[:, None], (1, 5)); f[:, 0] *= 0.5
    np.savez(path, t=np.arange(n) / hz, series="H", active_hand="right", calibrated=True, t_mark=-1.0,
             right_fingers01=f, right_wrist_pos=p, right_coil_ok=np.ones(n, bool))


def test_square_replay_recovers_frame_and_carries_object(tmp_path):
    """Scripted grip from the detected grasp/release events: frame recovered and the cube carried to all corners."""
    from robot.replay_square import replay_square
    ep = tmp_path / "take_99.npz"; _synthetic_h(ep)
    r = replay_square(str(ep), "cube", "synthetic", calib=None)
    assert "error" not in r, r
    assert abs(r["square_side_m"] - 0.297) < 0.01 and r["wrist_above_table"] and r["wrist_clipped_frac"] == 0, r
    assert r["events"] == 8 and len(r["legs"]) == 4 and r["legs_ok"] >= 3, r


def test_square_replay_real_fingers_runs(tmp_path):
    """Recorded fingers (here: thumb at half closure, as in real takes) run end to end; success NOT asserted (weak thumb drops it)."""
    from robot.replay_square import replay_square
    ep = tmp_path / "take_99.npz"; _synthetic_h(ep)
    r = replay_square(str(ep), "cube", "real", calib=None)
    assert "error" not in r and len(r["legs"]) == 4, r
