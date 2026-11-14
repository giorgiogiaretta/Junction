"""B3 safety matrix: for every (true object, predicted label) pair the closure assigned to the label must neither crush nor drop the true object.
Numbers: g1/object_profiles.json (hold) and GRASP_REPORT break closures in ai/object_profile.BREAK_CLOSURE: PROVISIONAL sim values, not measurements."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from ai import object_profile as op

HOLD_MARGIN = 0.02
SUPPORTED = ("egg", "stress_ball")          # the can is not graspable by the G1 in this posture (unsupported)
LABELS = ("egg", "stress_ball", "other")    # what the recogniser can say for these objects


def outcome(true_obj, label):
    cap = op.behaviour(label)["max_closure"]; hold, brk = op._band(true_obj)
    if brk is not None and cap >= brk: return "crush"
    if hold is not None and cap < hold + HOLD_MARGIN: return "drop"   # at exactly the hold closure the grip is marginal
    return "ok"


def test_matrix_has_no_crush_and_no_drop_for_supported_objects():
    bad = {(t, l): outcome(t, l) for t in SUPPORTED for l in LABELS if outcome(t, l) != "ok"}
    assert not bad, bad


def test_egg_called_stress_ball_is_safe_now():
    assert outcome("egg", "stress_ball") == "ok" and outcome("stress_ball", "egg") == "ok"


def test_robust_cap_is_below_break_with_margin_and_above_hold():
    cap, ok = op.robust_cap(("egg", "stress_ball")); assert ok and 0.65 <= cap <= 0.75 - op.MARGIN + 1e-9


def test_unsupported_can_is_flagged_not_graspable():
    assert op.behaviour("can").get("supported") is False   # kept for vision only; never sent to the robot as a grasp
