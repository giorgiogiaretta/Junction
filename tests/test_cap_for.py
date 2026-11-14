"""Ball full force only when sure; egg/unknown never."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from ai.object_profile import cap_for_votes as cap_for, behaviour


def test_ball_full_force_needs_confidence_and_agreement():
    assert cap_for("stress_ball", 0.95, agree=2) == 1.0
    assert cap_for("stress_ball", 0.85, agree=2) == behaviour("stress_ball")["max_closure"] == 0.70
    assert cap_for("stress_ball", 0.99, agree=1) == 0.70       # one confident model is not enough
    assert cap_for("stress_ball", None, agree=3) == 0.70


def test_manual_set_unlocks_ball():
    assert cap_for("stress_ball", manual=True) == 1.0


def test_egg_and_unknown_never_full_force():
    assert cap_for("egg", 1.0, agree=5, manual=True) == 0.70
    assert cap_for("mystery", 1.0, agree=5, manual=True) == 0.68
    assert cap_for("can", 1.0, agree=5) < 1.0
