"""Offline tests: safety rules of the pre-grasp profile picker + Gemini backup (fake transports, no network, no key)."""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
import pytest
from ai.llm import ChatClient
from ai.profile_picker import pick_profile, apply_safety


def answer(obj, profile, conf=None):
    args = {"object": obj, "profile": profile, "reason": "r"}
    if conf is not None: args["confidence"] = conf
    call = {"id": "1", "type": "function", "function": {"name": "set_grasp_profile", "arguments": json.dumps(args)}}
    return 200, {"choices": [{"message": {"content": None, "tool_calls": [call]}}]}


def client(seq, sent=None):
    it = iter(seq)
    def tr(url, h, p, t):
        if sent is not None: sent.append(p)
        return next(it)
    return ChatClient("k", transport=tr, sleep=lambda s: None, rpm=6000, max_retries=0)


@pytest.mark.parametrize("obj,prof,conf,want", [
    ("stress ball", "can", 0.95, "can"),     # confident ball: keep
    ("stress ball", "can", 0.80, "egg"),     # unsure ball: could be an egg -> egg
    ("white ball", "none", None, "egg"),     # no confidence on a ball -> egg
    ("can", "can", 0.90, "can"),
    ("can", "can", 0.40, "cup"),             # low confidence -> never firmer than cup
    ("block", "none", None, "cup"),
    ("egg", "egg", 0.30, "egg"),             # already the softest: untouched
])
def test_safety_rules(obj, prof, conf, want):
    r = pick_profile(client([answer(obj, prof, conf)]))
    assert r["profile"] == want and r["source"] == "model"
    if want != prof: assert r["model_profile"] == prof and r["safety"]


def test_safety_never_makes_grip_firmer_and_can_be_disabled():
    for p in ("egg", "cup", "can", "none"):
        for c in (None, 0.1, 0.7, 0.99):
            out = apply_safety({"object": "ball", "profile": p, "source": "model", "confidence": c})["profile"]
            assert ["egg", "cup", "can", "none"].index(out) <= ["egg", "cup", "can", "none"].index(p)
    assert pick_profile(client([answer("ball", "can", 0.5)]), safety=False)["profile"] == "can"


def test_default_fallback_is_conservative_cup():
    r = pick_profile(client([(500, {})])); assert r["profile"] == "cup" and r["source"] == "fallback"


class FakeSocketModule:
    AF_INET = SOCK_DGRAM = 0
    def __init__(self, sent): self.sent = sent
    def socket(self, *a):
        sent = self.sent
        class S:
            def sendto(self, data, addr): sent.append(json.loads(data))
        return S()


def test_cli_uses_gemini_backup_when_primary_fails(monkeypatch):
    from ai import pick_profile as cli
    sent = []; monkeypatch.setattr(cli, "socket", FakeSocketModule(sent))
    r = cli.main(["--text", "x"], client=client([(599, {})]), backup_client=client([answer("can", "can", 0.9)]))
    assert r["backup"] == "gemini" and r["source"] == "model" and r["profile"] == "can" and sent == [{"profile": "can"}]
    r = cli.main(["--text", "x", "--backup", "off"], client=client([(599, {})]), backup_client=client([answer("can", "can", 0.9)]))
    assert r["source"] == "fallback" and r["profile"] == "cup" and "backup" not in r


def test_cli_without_gemini_key_skips_backup(monkeypatch):
    from ai import pick_profile as cli
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY"): monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(cli, "socket", FakeSocketModule([]))
    r = cli.main(["--text", "x"], client=client([(599, {})]))
    assert r["source"] == "fallback" and r["profile"] == "cup"
