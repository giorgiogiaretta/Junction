"""No weights/downloads: test held-out evaluation and egg-risk accounting."""
import numpy as np
import pytest
from cv.embeddings import cross_validate, normalize, prediction
from cv.eval_embeddings import metrics


def test_rejection_is_not_egg_recall_or_unknown_probability():
    result = prediction([.45, .35, .2], ["egg", "stress_ball", "can"], .5)
    assert result["label"] == "other" and result["raw_label"] == "egg"
    assert result["score"] == .45 and result["scores"]["other"] == 0
    rows = [{"file": str(i), "expected": "egg", "label": label}
            for i, label in enumerate(["egg", "other", "can", "stress_ball"])]
    rows += [{"file": "mix", "expected": None, "label": "egg"}]
    summary = metrics(rows)
    assert summary["egg_recall"] == .25
    assert summary["egg_to_firm"] == 2
    assert summary["egg_to_other"] == 1
    assert summary["other_recall"] is None
    assert summary["n"] == 4


def test_normalization_and_invalid_rejection():
    assert np.allclose(normalize([3, 4]), [.6, .8])
    assert np.all(np.isfinite(normalize([0, 0])))
    with pytest.raises(ValueError):
        prediction([1], ["egg"], 1.1)


def test_each_prediction_uses_only_training_photos(monkeypatch):
    fitted = []

    class Probe:
        classes_ = np.array(["egg", "can"])

        def fit(self, x, y):
            self.train_ids = set(x[:, 0])
            fitted.append(self.train_ids)
            return self

        def predict_proba(self, x):
            assert not (set(x[:, 0]) & self.train_ids)
            return np.tile([.8, .2], (len(x), 1))

    monkeypatch.setattr("cv.embeddings.make_probe", Probe)
    x, y = np.arange(4)[:, None], ["egg", "egg", "can", "can"]
    rows = cross_validate(x, y)
    assert len(fitted) == len(rows) == 4
    assert [row["index"] for row in rows] == list(range(4))
    for row in rows:
        assert row["index"] not in row["train_indices"]
        assert len(row["train_indices"]) == 3


def test_bad_splits_rejected():
    x, y = np.arange(4)[:, None], ["egg", "egg", "can", "can"]
    with pytest.raises(ValueError, match="overlap"):
        cross_validate(x, y, [(np.array([0, 1, 2]), np.array([0]))])
    with pytest.raises(ValueError, match="exactly once"):
        cross_validate(x, y, [(np.array([0, 2]), np.array([1]))])


def test_probe_learns_separated_features_out_of_sample():
    x = np.array([[2, 0], [3, 0], [2.5, 0], [0, 2], [0, 3], [0, 2.5]])
    y = ["egg"] * 3 + ["can"] * 3
    rows = cross_validate(x, y)
    assert [r["raw"]["label"] for r in rows] == y
