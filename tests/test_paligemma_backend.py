import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from ai.paligemma import normalise, recognise_bytes, make_client
from ai.llm import ChatClient


def test_normalise_and_not_configured(monkeypatch):
    assert normalise("Egg") == "egg" and normalise("orange ball") == "stress_ball" and normalise("drink can") == "can" and normalise("mouse") == "other"
    monkeypatch.delenv("PALIGEMMA_BASE_URL", raising=False); r = recognise_bytes(make_client(), b"x"); assert r["ok"] is False


def test_vote_without_confidence_and_server_down():
    c = ChatClient("k", transport=lambda *a: (200, {"choices": [{"message": {"content": "an egg"}}]}), sleep=lambda s: None, rpm=6000, max_retries=0)
    r = recognise_bytes(c, b"x"); assert r["object"] == "egg" and r["confidence"] is None and r["ok"]
    d = ChatClient("k", transport=lambda *a: (500, {}), sleep=lambda s: None, rpm=6000, max_retries=0); assert recognise_bytes(d, b"x")["ok"] is False
