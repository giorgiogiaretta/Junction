"""Phase-1 integration with REAL recordings (data/raw/take_NN.rgmp, series A, both gloves + Coil Pro).
What this does and does NOT establish:
 - real Coil Pro wrist path + scripted grip: the sim cube is lifted and held (tests the wrist trajectory + physics)
 - real finger angles: run end to end, but NO grasp is produced (finger polarity/normalisation unresolved) - recorded, not asserted as success."""
import os, sys, pathlib, pytest
ROOT = pathlib.Path(__file__).parents[1]; sys.path.insert(0, str(ROOT))
TAKES = [ROOT / "data" / "raw" / f"take_{i:02d}.rgmp" for i in (1, 3, 4, 5)]
pytestmark = pytest.mark.skipif(not all(t.exists() for t in TAKES), reason="recorded takes not present")


def test_real_wrist_path_with_scripted_grip_lifts_cube():
    from robot.play_real_data import play
    res = [play(str(t), "cube", "right", fingers="synthetic") for t in TAKES]
    assert all(r["touched"] for r in res), res
    assert all(r["lifted"] and r["held_s"] > 1.0 for r in res), res


def test_real_fingers_run_end_to_end_both_polarities():
    from robot.play_real_data import play
    for pol in ("client", "inverted"):
        r = play(str(TAKES[0]), "cube", "right", polarity=pol)
        assert "error" not in r and r["dur_s"] > 5, r
