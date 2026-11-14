import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from ai.crosscheck import crosscheck


def row(f, o, e): return {"file": f, "object": o, "expected": e}


def test_disagreement_catches_single_model_errors_and_counts_common_mistakes():
    a = [row("1", "egg", "egg"), row("2", "stress_ball", "egg"), row("3", "can", "can"), row("4", "can", "stress_ball"), row("5", "egg", None)]
    b = [row("1", "egg", "egg"), row("2", "egg", "egg"), row("3", "can", "can"), row("4", "can", "stress_ball"), row("5", "other", None)]
    r = crosscheck(a, b)
    assert r["n"] == 5 and r["agree"] == 3 and r["errors_total_single_model"] == 1 and r["errors_caught_by_disagreement"] == 1
    assert r["both_wrong_same_answer"] == ["4"] and r["mix_n"] == 1 and r["mix_agree"] == 0
