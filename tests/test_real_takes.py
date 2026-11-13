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


EPI = [ROOT / "data" / "episodes" / f"take_{i:02d}.npz" for i in (12, 13, 14, 15, 16)]


@pytest.mark.skipif(not all(e.exists() for e in EPI), reason="episodes not built")
def test_episode_replay_cushion_protects_egg_on_real_wrist_paths():
    """Series B (fragile) real wrist paths + scripted grip: Force Cushion cuts egg breakage (real fingers still not usable)."""
    from robot.replay import replay
    no = [replay(str(e), "egg", fingers="synthetic") for e in EPI]
    yes = [replay(str(e), "egg", fingers="synthetic", assist="egg") for e in EPI]
    assert sum(r["broken"] for r in no) >= 4, no
    assert sum(r["broken"] for r in yes) <= 1, yes
    assert sum(r["lifted"] for r in yes) >= 3, yes


CAL = [ROOT / "data" / "episodes" / f"take_{i:02d}.npz" for i in (7, 17, 23)]


@pytest.mark.skipif(not all(e.exists() for e in CAL), reason="episodes not built")
def test_calibrated_real_fingers_replay_end_to_end():
    """Calibrated (series E) real fingers, grasp moment = grip onset, per-take gain: runs end to end on calibrated episodes.
    Lift is NOT asserted: 2/32 A-C overall (see docs/PHASE1_REAL_DATA.md), without obj_pos the pick point is a guess."""
    from robot.replay import replay
    res = [replay(str(e), "cube", fingers="gain", pick="closure") for e in CAL]
    assert all(r["calibrated"] and r["closure4_peak"] > 0.8 for r in res), res
