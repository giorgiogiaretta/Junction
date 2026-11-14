"""No downloads or inference: verify scoring and failure accounting."""
from pathlib import Path

from cv.eval_photos import evaluate, expected, photo_files, summary


class FakeDetector:
    def synchronize(self):
        pass

    def detect(self, path):
        if path.stem == "egg-error":
            raise RuntimeError("inference failed")
        if path.parent.name == "can":
            return []
        return [{"label": "can", "score": .3, "bbox": [0, 0, 1, 1]},
                {"label": "stress_ball", "score": .8, "bbox": [2, 2, 3, 3]}]


def test_mix_never_scored_even_with_label_prefix():
    assert expected(Path("mix/egg-001.jpg")) is None
    assert expected(Path("ball/ball-001.jpg")) == "stress_ball"
    assert expected(Path("egg/egg-001.jpg")) == "egg"


def test_metrics_count_empty_and_failed_predictions(tmp_path):
    for name in ("ball/ball-001.JPG", "egg/egg-error.jpg", "can/can-001.png", "mix/egg-001.jpg"):
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.touch()
    assert len(photo_files(tmp_path)) == 3
    rows = evaluate(FakeDetector(), tmp_path, include_mix=True)
    result = summary(rows)
    assert result["correct"] == 1
    assert result["total"] == 3
    assert result["failed"] == 1
    assert result["confusion"]["egg"] == {"other": 1}
    assert result["folders"]["ball"]["accuracy"] == 1
    assert next(r for r in rows if r["file"].startswith("mix/"))["profile_ok"] is None
    can = next(r for r in rows if r["expected"] == "can")
    assert can["ok"] and can["object"] == "other"
    assert all(r["latency_s"] >= 0 for r in rows)


def test_empty_summary():
    assert summary([])["latency_s"] is None
    assert summary([])["total"] == 0
