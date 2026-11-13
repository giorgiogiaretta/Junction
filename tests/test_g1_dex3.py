"""G1 Dex3 retargeting: bounds, slew limit, sign/order conventions, all recorded episodes (pure Python)."""
import glob, math, pathlib, sys
import numpy as np
ROOT = pathlib.Path(__file__).parents[1]; sys.path.insert(0, str(ROOT))
from robot.g1_dex3 import G1Dex3Retargeter


def test_sign_and_order_conventions():
    rt = G1Dex3Retargeter()
    for _ in range(40): q = rt.step(left=[0, 1, 1, 1, 1], right=[0, 1, 1, 1, 1])
    names = [j["joint"] for j in rt.joints]
    L = {n: q[i] for i, n in enumerate(names)}
    assert L["left_hand_index_0_joint"] < -1.0 and L["left_hand_middle_1_joint"] < -1.0     # left closes negative
    assert L["right_hand_index_0_joint"] > 1.0 and L["right_hand_middle_1_joint"] > 1.0     # right closes positive
    assert names[3:5] == ["left_hand_middle_0_joint", "left_hand_middle_1_joint"] and names[10:12] == ["right_hand_index_0_joint", "right_hand_index_1_joint"]


def test_open_stays_open_and_ring_little_ignored():
    rt = G1Dex3Retargeter(); a = rt.step(left=[0, 0, 0, 1, 1], right=None)
    b = G1Dex3Retargeter().step(left=[0, 0, 0, 0, 0], right=None)
    assert a == b  # ring/little have no joint


def test_all_episodes_within_filter_bounds_and_slew():
    eps = sorted(glob.glob(str(ROOT / "data" / "episodes" / "take_*.npz")))
    if not eps: return
    worst_step = 0.0
    for e in eps:
        z = np.load(e, allow_pickle=True); rt = G1Dex3Retargeter(); prev = None
        for i in range(len(z["t"])):
            L, R = np.clip(np.nan_to_num(z["left_fingers01"][i]), 0, 1), np.clip(np.nan_to_num(z["right_fingers01"][i]), 0, 1)
            q = rt.step(left=L.tolist(), right=R.tolist())
            assert rt.bounds_ok(q) and not any(math.isnan(v) for v in q), (e, i)
            if prev is not None: worst_step = max(worst_step, max(abs(a - b) for a, b in zip(q, prev)))
            prev = q
    assert worst_step <= rt.max_step + 1e-9, worst_step
    print(f"{len(eps)} episodes, 0 out-of-bounds, worst per-tick step {worst_step:.3f} rad (cap {rt.max_step:.3f})")


def test_dry_backend():
    from robot.hand import make_hand
    h = make_hand("g1dex3", hand="left"); h.set_fingers([0, 1, 1, 0, 0])
    assert len(h.last_q) == 14 and h.rt.bounds_ok(h.last_q)
