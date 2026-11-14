"""ml/square_policy: ordered leg segmentation and horizon-scaled rollout (numpy only, no torch, no data files)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ml"))
import square_policy as SP

C = {"BL": np.array([-0.15, -0.15, 0.0]), "TL": np.array([-0.15, 0.15, 0.0]), "TR": np.array([0.15, 0.15, 0.0]), "BR": np.array([0.15, -0.15, 0.0])}


def path(points, n_move=30, n_dwell=20):
    out = [np.repeat(points[0][None], n_dwell, 0)]
    for a, b in zip(points, points[1:]):
        out.append(a + (b - a) * np.linspace(0, 1, n_move)[:, None])
        out.append(np.repeat(b[None], n_dwell, 0))
    return np.concatenate(out)


def test_segment_ignores_return_to_previous_corner():
    # BL -> TL -> back to BL (slow) -> TL -> TR: the BL revisit must not advance the leg
    pos = path([C["BL"], C["TL"], C["BL"], C["TL"], C["TR"]])
    legs, goals = SP.segment_legs(pos, C)
    assert legs.max() == 2 and np.all(np.diff(legs) >= 0)
    assert np.allclose(goals[-1], C["BR"])


def test_rollout_applies_horizon_step_per_tick(monkeypatch):
    def pred(model, X):   # oracle: the horizon-step move toward the goal, as make_dataset targets are

        dg = X[:, 7:10]; n = np.linalg.norm(dg, axis=1, keepdims=True)
        step = np.minimum(n, 0.01) * dg / np.maximum(n, 1e-9)        # 1 cm per tick
        return np.c_[step * SP.HORIZON, np.zeros(len(X))]
    monkeypatch.setattr(SP, "predict", pred)
    take = {"corners": C, "pos": path([C["BL"], C["TL"]]), "grip": np.zeros(100)}
    ro = SP.rollout(None, take)
    assert ro["corners_reached"] == 4 and ro["final_err_cm"] < 5
    assert len(SP.make_state(np.zeros(3), np.zeros(3), 0, np.ones(3), 0, 1.0)) == SP.IN_DIM
