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


def test_select_k_uses_only_training_takes(monkeypatch):
    seen = []
    monkeypatch.setattr(SP, "make_dataset", lambda ts: (seen.append([t["name"] for t in ts]) or (None, None)))
    monkeypatch.setattr(SP, "train_knn", lambda X, Y, k: k)
    monkeypatch.setattr(SP, "rollout", lambda m, t: {"corners_reached": 4 if m == 20 else 2, "closest_cm": [5.0] * 4})
    k, inner = SP.select_k([{"name": n} for n in "abc"], ks=(10, 20))
    assert k == 20 and inner == {10: 6, 20: 12}
    assert all(len(s) == 2 for s in seen)


def test_pick_place_schedule_grips_only_at_grasp_height():
    # board 14:29: close only once z ~ 0 (descend open), release only after lowering back; legs cut at closest approach
    h = 0.15; G = np.array([[-h, h], [h, h], [h, -h], [-h, -h]]); S = np.array([[-h, -h]] + G.tolist())
    xyz, leg = [], []
    for k in range(4):   # each leg overshoots its corner by 10 cm
        d = (S[k + 1] - S[k]) / np.linalg.norm(S[k + 1] - S[k])
        for s in np.linspace(0, 2 * h + 0.10, 40): xyz.append([*(S[k] + d * s), 0.0]); leg.append(k)
    p, g = SP.pick_place_schedule(np.array(xyz), np.array(leg), goals=G)
    closed = g >= 0.5
    on = np.where(closed[1:] & ~closed[:-1])[0] + 1; off = np.where(~closed[1:] & closed[:-1])[0] + 1
    assert len(on) == 4 and len(off) == 4
    assert np.all(p[on, 2] <= 0.01) and np.all(p[off, 2] <= 0.01)
    assert np.allclose(p[off, :2], G, atol=0.02)


def test_pick_place_schedule_home_snaps_only_near_misses():
    # --home: a leg ending within home_m of its pad is carried onto it before release; a farther miss is left alone
    G = np.array([[0.0, 0.15], [0.15, 0.15]])
    xyz = np.array([[0, -0.15, 0], [0, 0.10, 0], [0, 0.10, 0], [0.15, 0.0, 0]])   # leg 0 ends 5 cm short, leg 1 15 cm short
    leg = np.array([0, 0, 1, 1])
    p, g = SP.pick_place_schedule(xyz, leg, goals=G, home_m=0.08)
    off = np.where((g[:-1] >= 0.5) & (g[1:] < 0.5))[0] + 1
    assert len(off) == 2 and np.allclose(p[off[0], :2], G[0], atol=1e-6)
    assert np.allclose(p[off[1], :2], [0.15, 0.0], atol=1e-6) and np.all(p[off, 2] <= 0.01)
    p0, g0 = SP.pick_place_schedule(xyz, leg, goals=G)
    off0 = np.where((g0[:-1] >= 0.5) & (g0[1:] < 0.5))[0] + 1
    assert np.allclose(p0[off0[0], :2], [0, 0.10], atol=1e-6)


def test_pick_place_schedule_home_snaps_first_pick():
    # --home also homes the first grasp onto the start pad (goals[-1], the square closes) when the policy starts near it
    G = np.array([[-0.15, 0.15], [-0.15, -0.15]])
    xyz = np.array([[-0.10, -0.15, 0], [-0.15, 0.15, 0], [-0.15, 0.15, 0], [-0.15, -0.15, 0]])   # starts 5 cm off the start pad
    leg = np.array([0, 0, 1, 1])
    p, g = SP.pick_place_schedule(xyz, leg, goals=G, home_m=0.08)
    on = int(np.argmax(g >= 0.5))
    assert np.allclose(p[on, :2], G[-1], atol=1e-6) and p[on, 2] <= 0.01
    p0, g0 = SP.pick_place_schedule(xyz, leg, goals=G)
    assert np.allclose(p0[int(np.argmax(g0 >= 0.5)), :2], [-0.10, -0.15], atol=1e-6)
