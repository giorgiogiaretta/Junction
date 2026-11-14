"""Offline tests for ai/judge_gemini.py: fake google-genai client, no network, no key."""
import json, pathlib, sys
import numpy as np
ROOT = pathlib.Path(__file__).parents[1]; sys.path.insert(0, str(ROOT))
from ai import judge_gemini as jg


class Resp:
    def __init__(self, text=None, parsed=None): self.text, self.parsed = text, parsed


class FakeClient:
    """Mimics client.models.generate_content(model=, contents=, config=)."""
    def __init__(self, answers):
        self.answers, self.calls = list(answers), []
        self.models = self
    def generate_content(self, model, contents, config=None):
        self.calls.append((model, contents, config)); a = self.answers.pop(0)
        if isinstance(a, Exception): raise a
        return a


def episode(tmp_path, nan=False, head=False, n=90):
    t = np.arange(n) / 30.0; f = np.zeros((n, 5)); f[30:60, :] = 0.8
    p = np.zeros((n, 3)); p[:, 2] = np.linspace(0, 0.2, n)
    if nan: f[0, 1] = np.nan; p[3, 2] = np.nan
    kw = {"right_hand_in_head": np.tile([0.1, 0.0, 0.4], (n, 1))} if head else {}
    path = tmp_path / "take_99.npz"
    np.savez(path, t=t, active_hand="right", right_fingers01=f, right_wrist_pos=p, left_fingers01=f, left_wrist_pos=p, series="B", success=1, **kw)
    return str(path)


GOOD = Resp(text=json.dumps({"handoff_success": True, "reason": "grip held while the wrist lifts", "phases": [{"name": "grasp", "t_start": 1.0}]}))


def test_whole_episode_sent_not_aggregates_nan_null_and_thumb_dropped(tmp_path):
    ep = jg.load_episode(episode(tmp_path, nan=True))
    assert ep["columns"][:5] == ["t_s", "index", "middle", "ring", "little"] and len(ep["rows"][0]) == 8 and ep["human_label"] == 1
    assert 40 <= len(ep["rows"]) <= 46  # 90 samples at 30 Hz capped to ~15 Hz -> ~45 rows, not a few aggregates
    s = jg.payload_json(ep); json.loads(s)  # valid JSON
    assert "NaN" not in s and "null" in s


def test_head_columns_when_hand_in_head_present(tmp_path):
    ep = jg.load_episode(episode(tmp_path, head=True))
    assert ep["has_head"] and ep["columns"][-3:] == ["head_to_hand_x_m", "head_to_hand_y_m", "head_to_hand_z_m"] and len(ep["rows"][0]) == 11


def test_jsonl_samples(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join(json.dumps({"t": 100 + i / 30, "fingers": [0, 0.1, 0.2, 0.3, 0.4], "wrist_position": [0, 0, i * 0.01]}) for i in range(60)))
    ep = jg.load_episode(str(p)); assert ep["rows"][0][1:5] == [0.1, 0.2, 0.3, 0.4] and len(ep["rows"]) in (30, 31)


def test_judge_ok_exact_line_and_model_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "my-model"); c = FakeClient([GOOD])
    r = jg.judge_episode(c, jg.load_episode(episode(tmp_path)), config="cfg")
    assert r["handoff_success"] is True and r["source"] == "model" and c.calls[0][0] == "my-model" and c.calls[0][2] == "cfg"
    assert jg.format_line(r) == "HandOff riuscito: True, Motivo: grip held while the wrist lifts"


def test_retry_on_api_error_then_ok_and_fallback_after_retries(tmp_path):
    ep = jg.load_episode(episode(tmp_path)); sleeps = []
    c = FakeClient([RuntimeError("secret-key-xyz boom"), GOOD]); r = jg.judge_episode(c, ep, retries=3, sleep=sleeps.append, config="c")
    assert r["handoff_success"] is True and len(c.calls) == 2 and sleeps
    c2 = FakeClient([RuntimeError("secret-key-xyz")] * 3); r2 = jg.judge_episode(c2, ep, retries=3, sleep=lambda s: None, config="c")
    assert r2["handoff_success"] is None and r2["source"] == "fallback" and "secret-key-xyz" not in json.dumps(r2)  # error text never echoed
    assert jg.format_line(r2).startswith("HandOff riuscito: False, Motivo: NON VALUTATO")


def test_invalid_json_retried_then_unclear(tmp_path):
    ep = jg.load_episode(episode(tmp_path)); c = FakeClient([Resp(text="not json"), Resp(text='{"handoff_success": "yes"}'), Resp(text="")])
    r = jg.judge_episode(c, ep, retries=3, sleep=lambda s: None, config="c"); assert r["handoff_success"] is None and len(c.calls) == 3


def test_parsed_dict_is_accepted(tmp_path):
    c = FakeClient([Resp(parsed={"handoff_success": False, "reason": "no grip"})])
    assert jg.judge_episode(c, jg.load_episode(episode(tmp_path)), config="c")["handoff_success"] is False


def test_compare_with_nemotron(tmp_path):
    f = tmp_path / "judge.jsonl"
    f.write_text("\n".join(json.dumps({"summary": {"episode": e}, "judge": {"verdict": v}}) for e, v in (("a", "good"), ("b", "bad"), ("c", "good"), ("d", "unclear"))))
    res = {"a": {"handoff_success": True}, "b": {"handoff_success": True}, "c": {"handoff_success": None}, "d": {"handoff_success": True}}
    c = jg.compare_with_nemotron(res, str(f)); assert c["n"] == 2 and c["agree"] == 1 and c["disagreements"] == [("b", True, False)]


def test_main_missing_key_exit_1(monkeypatch, capsys):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False); monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert jg.main(["data/episodes/take_01.npz"]) == 1 and "no API key" in capsys.readouterr().err


def test_main_end_to_end_with_fake_client_writes_report(tmp_path, capsys):
    out = tmp_path / "r.md"; ep = episode(tmp_path)
    rc = jg.main([ep, "--out", str(out)], client=FakeClient([GOOD])); o = capsys.readouterr().out
    assert rc == 0 and "HandOff riuscito: True, Motivo: grip held" in o and "no precision" in out.read_text()
