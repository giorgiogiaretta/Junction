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


def test_circuit_breaker_skips_a_backend_after_three_failures_and_recovers():
    from ai import recognize as R
    R.reset_breakers(); calls = []
    def dead(img): calls.append(1); raise RuntimeError("down")
    reg = {"dead": dead, "ok": lambda img: {"object": "egg", "confidence": 0.9, "ok": True}}
    for _ in range(3): R.collect(b"x", ["dead", "ok"], reg, timeout=2.0)
    assert len(calls) == 3 and R._breaker_open("dead")
    v = {x["name"]: x for x in R.collect(b"x", ["dead", "ok"], reg, timeout=2.0)}
    assert len(calls) == 3 and v["dead"]["error"] == "breaker_open" and v["ok"]["ok"]      # not called again
    assert not R._breaker_open("dead", now=__import__("time").time() + 31)                  # re-tried after the cool-down
    R.reset_breakers()


def test_decision_log_is_written_and_can_be_disabled(tmp_path, monkeypatch):
    from ai import recognize as R
    monkeypatch.setenv("RECOGNISE_LOG", str(tmp_path / "log.jsonl")); R.reset_breakers()
    d = R.recognise(b"x", ("a",), {"a": lambda i: {"object": "egg", "confidence": 0.9, "ok": True}}); assert d["object"] == "egg"
    import json; row = json.loads((tmp_path / "log.jsonl").read_text().splitlines()[0]); assert row["object"] == "egg" and row["votes"][0]["name"] == "a"
    monkeypatch.setenv("RECOGNISE_LOG", "off"); R.recognise(b"x", ("a",), {"a": lambda i: {"object": "egg", "confidence": 0.9, "ok": True}}); assert len((tmp_path / "log.jsonl").read_text().splitlines()) == 1
