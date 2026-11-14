"""Ensemble voting, fragile-first rule, timeouts and the link to cap_for (offline, fake backends)."""
import pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from ai.recognize import decide, recognise, collect


def reg(**answers):
    def mk(a):
        def run(img):
            if a == "boom": raise RuntimeError("down")
            if a == "slow": time.sleep(3)
            o, c = a; return {"object": o, "confidence": c, "ok": True}
        return run
    return {k: mk(v) for k, v in answers.items()}


def test_two_confident_balls_unlock_full_force():
    d = recognise(b"x", ("a", "b"), reg(a=("stress_ball", 0.97), b=("stress_ball", 0.93))); assert d["object"] == "stress_ball" and d["agree"] == 2 and d["cap"] == 1.0


def test_any_egg_vote_wins_even_against_a_ball_majority():
    d = recognise(b"x", ("a", "b", "c"), reg(a=("stress_ball", 0.99), b=("stress_ball", 0.99), c=("egg", 0.8)))
    assert d["object"] == "egg" and d["cap"] == 0.70


def test_one_confident_ball_alone_does_not_unlock():
    d = recognise(b"x", ("a",), reg(a=("stress_ball", 0.99))); assert d["cap"] == 0.70


def test_dead_and_slow_backends_do_not_block_or_count():
    t = time.time(); d = recognise(b"x", ("a", "b", "c"), reg(a=("egg", 0.9), b="boom", c="slow"), timeout=0.5)
    assert d["object"] == "egg" and d["n_ok"] == 1 and time.time() - t < 2.5
    assert {v["name"]: v["error"] for v in d["votes"] if not v["ok"]} == {"b": "RuntimeError", "c": "timeout"}


def test_no_answer_is_conservative():
    d = recognise(b"x", ("a",), reg(a="boom")); assert d["object"] == "other" and d["cap"] == 0.68
