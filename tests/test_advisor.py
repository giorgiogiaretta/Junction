"""Grasp Advisor: JSON cleaning, conservative mapping, failure -> conservative (offline, fake transport)."""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from ai.advisor import advise, advice_cap, clean, CONSERVATIVE, SHARED
from ai.llm import ChatClient


def client(content, status=200):
    body = {"choices": [{"message": {"content": content}}]}
    return ChatClient("k", transport=lambda *a: (status, body if status == 200 else {}), sleep=lambda s: None, rpm=6000, max_retries=0)


def test_banana_style_advice_maps_to_shared_cap_and_never_above():
    raw = {"object": "banana", "material": "fruit", "rigid": False, "fragility": 0.5, "est_mass_g": 120, "est_size_mm": [180, 35, 35], "handling": "hold the middle", "confidence": 0.9}
    r = advise(client("ok " + json.dumps(raw)), b"img"); assert r["cap"] == SHARED and not r["needs_operator_confirm"] and r["advice"]["est_mass_g"] == 120


def test_very_fragile_or_low_confidence_is_conservative_and_asks():
    assert advice_cap(clean({"object": "tomato", "fragility": 0.8, "confidence": 0.9}))["cap"] == CONSERVATIVE
    assert advice_cap(clean({"object": "thing", "fragility": 0.2, "confidence": 0.4}))["needs_operator_confirm"]


def test_failure_and_garbage_are_conservative():
    assert advise(client("", status=500), b"x")["cap"] == CONSERVATIVE
    assert advise(client("not json"), b"x")["cap"] == CONSERVATIVE
    assert clean({"fragility": "lots"})["fragility"] is None and advice_cap(None)["cap"] == CONSERVATIVE


def test_clamps_out_of_range_numbers():
    c = clean({"object": "x", "fragility": 7, "est_mass_g": -5, "confidence": 3}); assert c["fragility"] == 1.0 and c["est_mass_g"] == 0.0 and c["confidence"] == 1.0
