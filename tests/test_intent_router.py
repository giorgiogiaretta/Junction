"""Intent router: keyword fast path, strict JSON validation, safety gate, async (offline, fake client)."""
import pathlib, sys, threading, time
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from ai.intent_router import route, route_async, apply_intent, _valid
from ai.llm import ChatClient


def fake(content, delay=0.0):
    def tr(*a):
        time.sleep(delay); return 200, {"choices": [{"message": {"content": content}}]}
    return ChatClient("k", transport=tr, sleep=lambda s: None, rpm=6000, max_retries=0)


def test_extracts_last_action_json_after_a_thought_block():
    from ai.intent_router import _extract
    txt = '<thought>options {"action": "none"} ... maybe {"x": 1} </thought>\n{"action": "change_profile", "target_profile": "rigid"}'
    assert _extract(txt) == {"action": "change_profile", "target_profile": "rigid"}


def test_stop_never_waits_for_a_model():
    called = []
    class Boom:
        def chat(self, *a, **k): called.append(1); raise AssertionError("model must not be called")
    assert route("FERMATI subito", Boom())["via"] == "keyword" and not called and route("emergency stop", Boom())["action"] == "stop"


def test_model_json_is_validated():
    r = route("Oggetto caduto, cambia in modalita' presa forte", fake('Sure {"action": "change_profile", "target_profile": "rigid"} done'))
    assert r["action"] == "change_profile" and r["target_profile"] == "rigid" and r["via"] == "model"
    assert route("x", fake('{"action": "launch_missiles"}'))["action"] == "none"
    assert route("x", fake('{"action": "change_profile", "target_profile": "crush"}'))["action"] == "none"
    assert route("x", fake("garbage"))["via"] == "fallback"


def test_firm_grip_is_refused_for_egg_unknown_and_can_but_allowed_for_ball():
    rigid = {"action": "change_profile", "target_profile": "rigid"}
    assert apply_intent(rigid, "stress_ball") == {"allowed": True, "cap": 1.0, "message": "firm grip: operator override for the stress ball"}
    for obj in ("egg", "mystery", "can"):
        r = apply_intent(rigid, obj); assert not r["allowed"] and r["cap"] <= 0.70, (obj, r)


def test_gentle_and_default_and_stop():
    assert apply_intent({"action": "change_profile", "target_profile": "gentle"}, "stress_ball")["cap"] == 0.68
    assert apply_intent({"action": "change_profile", "target_profile": "default"}, "egg")["cap"] == 0.70
    assert apply_intent({"action": "stop", "target_profile": None}, "egg")["cap"] == 0.0 and not apply_intent({"action": "none", "target_profile": None}, "egg")["allowed"]


def test_route_async_does_not_block():
    done = threading.Event(); out = {}
    t0 = time.time(); route_async("piu' delicato", lambda i: (out.update(i), done.set()), fake('{"action": "change_profile", "target_profile": "gentle"}', delay=0.4)); assert time.time() - t0 < 0.2
    assert done.wait(3) and out["target_profile"] == "gentle"
