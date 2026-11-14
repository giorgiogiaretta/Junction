import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from episode_quality import stream_quality


def test_clean_stream():
    ts = [i / 100 for i in range(200)]
    q = stream_quality(ts, [True] * 200)
    assert q["rate_hz"] == 100.0 and q["dropouts"] == 0 and q["coil_ok"] == 1.0 and q["jitter_ms"] < 0.01


def test_dropout_and_coil_loss():
    ts = [i / 100 for i in range(100)] + [1.5 + i / 100 for i in range(100)]   # 0.5 s hole
    q = stream_quality(ts, [True] * 150 + [False] * 50)
    assert q["dropouts"] == 1 and 500 < q["max_gap_ms"] < 520 and q["coil_ok"] == 0.75


def test_short_stream():
    assert stream_quality([0.0], [True]) == {"n": 1}
