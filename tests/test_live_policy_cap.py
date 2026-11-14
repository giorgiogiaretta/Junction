"""g1/live_policy.py takes its closure cap ONLY from ai.object_profile.cap_for (single table). No hardware, no aaltonomous needed."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from g1.live_policy import cap


def test_fallback_is_conservative():
    assert cap({"source": "fallback"})["max_closure"] <= 0.70


def test_manual_ball_full_force():
    assert cap({"source": "manual", "object_key": "stress_ball"})["max_closure"] == 1.0


def test_egg_never_full_force():
    for p in ({"source": "manual", "object_key": "egg"}, {"source": "model", "object": "egg", "confidence": 0.99}):
        assert cap(p)["max_closure"] < 0.75          # egg breaks at 0.75 in the sim


def test_single_confident_model_ball_not_full():
    assert cap({"source": "model", "object": "stress ball", "confidence": 0.95})["max_closure"] < 1.0


def test_manual_none_is_unknown():
    r = cap({"source": "manual", "object_key": "none"})
    assert r["object"] == "other" and r["max_closure"] <= 0.70
