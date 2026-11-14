"""Offline tests: judge v2 really sends the timeline, and the two-backend comparison (fake transports, no network, no key)."""
import json, pathlib, sys
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from ai.llm import ChatClient
from ai.judge import summarize_episode, SYSTEM_V2
from ai.compare_judges import compare, kappa, make_client, markdown


def fake_episode(tmp_path, nan=False):
    t = np.arange(0, 3, 0.1); n = len(t)
    f = np.zeros((n, 5)); f[10:20, 1:] = 0.8
    p = np.zeros((n, 3)); p[:, 2] = np.linspace(0, 0.2, n)
    if nan: p[5, 2] = np.nan; f[0, 1:] = np.nan
    path = tmp_path / "take_99.npz"
    np.savez(path, t=t, active_hand="right", right_fingers01=f, right_wrist_pos=p, series="X", calibrated=True, success=1)
    return str(path)


def test_v2_summary_contains_timeline_v1_does_not(tmp_path):
    ep = fake_episode(tmp_path)
    assert "timeline" not in summarize_episode(ep, 1)
    tl = summarize_episode(ep, 2)["timeline"]
    assert len(tl) == 6 and tl[0]["t"] == 0.0 and max(r["closure"] for r in tl) == 0.8


def test_timeline_nan_becomes_null_valid_json(tmp_path):
    s = summarize_episode(fake_episode(tmp_path, nan=True), 2)
    json.loads(json.dumps(s, allow_nan=False))  # raises if any NaN slipped through
    assert s["timeline"][0]["closure"] is None


def scripted(verdicts):
    it = iter(verdicts); sent = []
    def tr(url, h, p, t):
        sent.append((url, h, p)); return 200, {"choices": [{"message": {"content": json.dumps({"verdict": next(it), "reason": "r"})}}]}
    return ChatClient("k", transport=tr, sleep=lambda s: None, rpm=6000), sent


def test_compare_two_models_report():
    a, sent_a = scripted(["good", "good", "bad", "good"]); b, _ = scripted(["good", "bad", "bad", "unclear"])
    sums = [{"episode": f"e{i}", "timeline": []} for i in range(4)]
    rows, rep = compare(sums, [1, 1, 0, -1], {"nemotron": a, "gemini": b}, SYSTEM_V2)
    assert len(rows) == 4 and rows[1]["gemini"]["verdict"] == "bad"
    assert rep["models"]["nemotron"]["agreement_with_human"]["good"]["recall"] == 1.0
    assert rep["models"]["gemini"]["agreement_with_human"]["good"]["recall"] == 0.5
    assert rep["model_vs_model"]["raw_agreement"] == 0.5 and rep["model_vs_model"]["disagreements"] == ["e1", "e3"]
    assert sent_a[0][2]["messages"][0]["content"] == SYSTEM_V2  # the v2 prompt is what is sent
    assert "Cohen's kappa" in markdown(rep) and "| nemotron | gemini |" in markdown(rep)


def test_kappa():
    assert kappa(["good", "bad"] * 5, ["good", "bad"] * 5) == 1.0
    assert kappa(["good"] * 4, ["good"] * 4) == 1.0
    assert kappa(["good", "bad", "good", "bad"], ["bad", "good", "bad", "good"]) == -1.0
    assert kappa([], []) is None


def test_gemini_never_gets_nvidia_key(monkeypatch):
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "LLM_BASE_URL", "LLM_MODEL"): monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", "nv-secret"); monkeypatch.setenv("VERDA_INFERENCE_KEY", "verda-secret")
    g = make_client("gemini"); assert g.key is None and "generativelanguage" in g.url
    rows, rep = compare([{"episode": "e0"}], [1], {"gemini": g}, SYSTEM_V2)
    assert rows[0]["gemini"]["source"] == "fallback" and "no API key" in rows[0]["gemini"]["error"]
    monkeypatch.setenv("GEMINI_API_KEY", "g-key"); assert make_client("gemini").key == "g-key"
