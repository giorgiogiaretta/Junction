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


def test_verda_env_selects_endpoint_and_model(monkeypatch):
    for k in ("NVIDIA_API_KEY", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"): monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("VERDA_INFERENCE_KEY", "dummy")
    c = ChatClient(); assert "datacrunch.io" in c.url and c.model == "nemotron-3.5-super-vl" and c.key == "dummy"


def test_no_key_is_clean_fallback(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False); monkeypatch.delenv("LLM_API_KEY", raising=False); monkeypatch.delenv("VERDA_INFERENCE_KEY", raising=False)
    r = pick_profile(ChatClient(api_key=None)); assert r["source"] == "fallback" and "no API key" in r["error"]


def test_judge_parses_json_and_falls_back():
    from ai.judge import judge_episode, agreement
    good = (200, {"choices": [{"message": {"content": 'Sure: {"verdict": "good", "reason": "held", "phases": []}'}}]})
    c, _ = client([good]); assert judge_episode(c, {"x": 1})["verdict"] == "good"
    c2, _ = client([(200, {"choices": [{"message": {"content": "no json"}}]})]); r = judge_episode(c2, {})
    assert r["verdict"] == "unclear" and r["source"] == "fallback"
    a = agreement(["good", "bad", "good", "unclear"], [1, 0, 0, 1])
    assert a["n"] == 3 and a["accuracy"] == 0.67 and a["unclear_or_unlabelled"] == 1


def test_summarize_real_episode_if_present():
    import glob
    from ai.judge import summarize_episode
    eps = sorted(glob.glob(str(pathlib.Path(__file__).parents[1] / "data" / "episodes" / "take_*.npz")))
    if not eps: return
    s = summarize_episode(eps[0]); assert s["duration_s"] > 1 and 0 <= s["closure_index_to_little"]["peak"] <= 1.5
