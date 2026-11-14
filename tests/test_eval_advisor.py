import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from ai.eval_advisor import evaluate, spearman


def test_spearman_and_summary():
    assert abs(spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1.0) < 1e-9 and abs(spearman([1, 2, 3], [3, 2, 1]) + 1.0) < 1e-9
    rows = [{"file": "a", "object": "egg", "mass_g": 60, "fragility": 1.0}, {"file": "b", "object": "ball", "mass_g": 30, "fragility": 0.0}, {"file": "c", "object": "banana", "mass_g": 120, "fragility": 0.5}]
    fake = {"a": (0.9, 55), "b": (0.1, 40), "c": (0.4, 150)}
    run = lambda f: {"advice": {"object": f, "fragility": fake[f][0], "est_mass_g": fake[f][1]}, "cap": 0.68 if fake[f][0] >= 0.75 else 0.7}
    out, s = evaluate(rows, run); assert s["fragility_spearman"] == 1.0 and s["n"] == 3 and abs(s["median_mass_err_pct"] - 25.0) < 1e-6 and out[0]["conservative"]
