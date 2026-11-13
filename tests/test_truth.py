"""PLAN 1.4 truth test: synthetic/recorded hand_state stream -> retarget (Force Cushion) -> MuJoCo headless.
Asserts the physical outcomes and reports pipeline latency p50/p95. Latency here = compute time per packet (parse + assist + sim step),
not network or glove latency."""
import sys, pathlib
ROOT = pathlib.Path(__file__).parents[1]; sys.path.insert(0, str(ROOT))
from robot.pipeline import Pipeline, synthetic_stream


def run(obj, profile):
    p = Pipeline(obj, profile)
    last = None
    for pkt in synthetic_stream():
        last = p.process(pkt)
    return last, p.latency_stats()


def test_cube_lifted():
    s, lat = run("cube", None)
    assert s["lifted"] and s["held"], s


def test_egg_breaks_without_cushion():
    s, _ = run("egg", None)
    assert s["broken"] is True, s


def test_egg_lifted_intact_with_cushion():
    s, lat = run("egg", "egg")
    assert s["held"] and not s["broken"], s
    assert s["peak_force"] > 0.2  # actually gripped, not just stuck
    print(f"latency p50={lat['p50']:.2f} ms p95={lat['p95']:.2f} ms n={lat['n']}")


def test_latency_stats_reported():
    _, lat = run("cube", None)
    assert lat["n"] > 200 and 0 < lat["p50"] <= lat["p95"]
    assert lat["p95"] < 100  # sanity bound for this machine; real budget set after hardware measurement


def test_coil_pro_wrist_overrides_fallback():
    """With wrist_position the hand follows the Coil Pro (relative to first sample), not the mock path."""
    p = Pipeline("cube", None)
    for i in range(120):
        z = 0.0 if i < 60 else -0.1  # operator lowers the wrist by 10 cm
        p.process({"t": 0, "fingers": [0] * 5, "wrist_position": [0.0, 0.0, z]})
    assert abs(p.scene.hand_pos()[2] - (0.26 - 0.1)) < 0.03
