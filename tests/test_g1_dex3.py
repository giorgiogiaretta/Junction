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


def test_max_closure_caps_every_joint(monkeypatch):
    """PREFLIGHT first robot run: full fist must command at most 10% of each joint's open->closed range (thumb included)."""
    full = G1Dex3Retargeter(max_closure=1.0); cap = G1Dex3Retargeter(max_closure=0.1)
    monkeypatch.setenv("G1_MAX_CLOSURE", "0.1"); env = G1Dex3Retargeter()
    for _ in range(60):
        qf = full.step(left=[1] * 5, right=[1] * 5); qc = cap.step(left=[1] * 5, right=[1] * 5); qe = env.step(left=[1] * 5, right=[1] * 5)
    assert qc == qe
    for j, f, c in zip(full.joints, qf, qc):
        o = G1Dex3Retargeter._open(j)
        assert abs(c - o) <= 0.1 * abs(f - o) + 1e-9, j["joint"]
    assert any(abs(c - G1Dex3Retargeter._open(j)) > 0 for j, c in zip(full.joints, qc))   # still moves


def test_dry_backend():
    from robot.hand import make_hand
    h = make_hand("g1dex3", hand="left"); h.set_fingers([0, 1, 1, 0, 0])
    assert len(h.last_q) == 14 and h.rt.bounds_ok(h.last_q)


def test_thumb0_pinned_open_and_mirrored_if_ever_closed():
    """#65: thumb_0 never leaves open; if it were ever closed, left and right go opposite ways (symmetric-bounds tie-break)."""
    rt = G1Dex3Retargeter(); names = [j["joint"] for j in rt.joints]
    i0 = {s: names.index(s + "_hand_thumb_0_joint") for s in ("left", "right")}
    open0 = {s: rt.q[i] for s, i in i0.items()}
    for f in ([1] * 5, [0] * 5, [0.5] * 5, None):
        for _ in range(40): q = rt.step(left=f, right=f)
        assert all(q[i] == open0[s] for s, i in i0.items())
    assert rt._closed(rt.idx["left_hand_thumb_0_joint"]) < 0 < rt._closed(rt.idx["right_hand_thumb_0_joint"])
