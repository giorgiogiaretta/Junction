"""Offline tests: object -> profile table and the photo evaluation (fake recogniser, no network)."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from ai.object_profile import behaviour, normalize
from ai.eval_objects import evaluate, report, expected_label, recognize
from ai.llm import ChatClient


def test_normalize_and_behaviour():
    assert normalize("a raw hen egg") == "egg" and normalize("Coca-Cola can") == "can" and normalize("stress ball") == "stress_ball"
    assert normalize("banana") == "other"
    assert behaviour("egg")["profile"] == "egg" and behaviour("egg")["max_closure"] < behaviour("can")["max_closure"]
    u = behaviour("mystery"); assert not u["known"] and u["profile"] == "cup"  # unknown -> conservative, never full closure


def test_expected_label_from_filename():
    assert expected_label("x/egg_01.jpg") == "egg" and expected_label("x/stress_ball_head_3.png") == "stress_ball" and expected_label("x/zzz.jpg") is None


def test_evaluate_and_report(tmp_path):
    for n in ("egg_1.jpg", "egg_2.jpg", "can_1.jpg", "stress_ball_1.jpg"): (tmp_path / n).write_bytes(b"x")
    answers = {"egg_1.jpg": "egg", "egg_2.jpg": "can", "can_1.jpg": "can", "stress_ball_1.jpg": "stress_ball"}
    cur = {"i": 0}; files = sorted(answers)
    def fake(client, img, mime): f = files[cur["i"]]; cur["i"] += 1; return {"object": answers[f], "confidence": 0.9, "latency_s": 0.4, "ok": True}
    rows = evaluate(None, str(tmp_path), recog=fake); md = report(rows, "fake")
    assert len(rows) == 4 and "accuracy: 75%" in md and "egg_2.jpg->can" in md


def test_recognize_parses_json_and_survives_failure():
    ok = (200, {"choices": [{"message": {"content": 'x {"object": "egg", "confidence": 0.8} y'}}]})
    c = ChatClient("k", transport=lambda *a: ok, sleep=lambda s: None, rpm=6000); r = recognize(c, b"img")
    assert r["object"] == "egg" and r["ok"]
    c2 = ChatClient("k", transport=lambda *a: (500, {}), sleep=lambda s: None, rpm=6000, max_retries=0); r2 = recognize(c2, b"img")
    assert r2["object"] == "other" and not r2["ok"]
