"""Offline tests for ai/ (fake transport, no network, no key)."""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from ai.llm import ChatClient, LLMError
from ai.profile_picker import pick_profile


def ok(profile="egg"):
    call = {"id": "1", "type": "function", "function": {"name": "set_grasp_profile", "arguments": json.dumps({"object": "egg", "profile": profile, "reason": "fragile"})}}
    return 200, {"choices": [{"message": {"content": None, "tool_calls": [call]}}]}


def client(seq, **kw):
    it = iter(seq); calls = []
    def tr(url, h, p, t): calls.append(p); return next(it)
    return ChatClient("k", transport=tr, sleep=lambda s: None, rpm=6000, **kw), calls


def test_picks_profile_from_tool_call():
    c, _ = client([ok("egg")]); r = pick_profile(c, hint="x")
    assert r["profile"] == "egg" and r["source"] == "model"


def test_retries_on_429_then_succeeds():
    c, calls = client([(429, {}), (503, {}), ok("cup")]); r = pick_profile(c)
    assert r["profile"] == "cup" and len(calls) == 3


def test_fallback_when_all_fail_and_on_bad_profile():
    c, _ = client([(500, {})] * 6, max_retries=2); r = pick_profile(c, fallback="can")
    assert r["profile"] == "can" and r["source"] == "fallback"
    c2, _ = client([ok("lava")]); assert pick_profile(c2)["source"] == "fallback"


def test_no_key_is_clean_fallback(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False); monkeypatch.delenv("LLM_API_KEY", raising=False)
    r = pick_profile(ChatClient(api_key=None)); assert r["source"] == "fallback" and "no API key" in r["error"]
