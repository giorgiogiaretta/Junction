"""B4 bridge: image label -> profile cap -> G1 Dex3 MuJoCo grasp. Skipped when the G1 model is not fetched (run g1/sim/g1_sim.py once)."""
import os, pathlib, sys, pytest
ROOT = pathlib.Path(__file__).parents[1]; sys.path.insert(0, str(ROOT))
pytestmark = pytest.mark.skipif(not (ROOT / "data" / "g1sim" / "assets_g1" / "g1_body29_hand14.xml").exists(), reason="G1 model not fetched")


def test_egg_capped_is_held_and_intact_uncapped_breaks():
    from robot.e2e_g1 import simulate
    r = simulate("egg", "egg")
    assert r["capped"]["held"] and not r["capped"]["broken"] and r["uncapped"]["broken"]


def test_egg_mistaken_for_ball_is_still_safe():
    from robot.e2e_g1 import simulate
    r = simulate("egg", "stress_ball")
    assert r["capped"]["held"] and not r["capped"]["broken"]


def test_can_is_vision_only():
    from robot.e2e_g1 import simulate
    assert "capped" not in simulate("can", "can")
