"""Cross-check two recognisers on the same photos (two-key principle: independent model families must agree before the hand squeezes hard).
  python -m ai.crosscheck data/photos_reports/n2.json data/photos_reports/gma2.json [--names nemotron,gemma]
Inputs: per-photo JSON rows from `python -m ai.eval_objects ... --json`. Reports agreement, the disagreements (-> HUMAN REVIEW), and, when ground truth exists, whether each
disagreement caught a real single-model error. Agreement is not accuracy: two models can be wrong together (none observed on our 50 photos, but one person/place/day)."""
import argparse, json


def crosscheck(rows_a, rows_b):
    a = {r["file"]: r for r in rows_a}; b = {r["file"]: r for r in rows_b}; files = sorted(set(a) & set(b))
    lab = [f for f in files if a[f].get("expected")]; mix = [f for f in files if not a[f].get("expected")]
    dis = [f for f in files if a[f]["object"] != b[f]["object"]]
    both_wrong_same = [f for f in lab if a[f]["object"] == b[f]["object"] != a[f]["expected"]]
    caught = [f for f in dis if f in lab and (a[f]["object"] == a[f]["expected"]) != (b[f]["object"] == b[f]["expected"])]
    return {"n": len(files), "labelled": len(lab), "agree": len(files) - len(dis), "disagreements": [(f, a[f]["object"], b[f]["object"], a[f].get("expected")) for f in dis],
            "labelled_agree": sum(a[f]["object"] == b[f]["object"] for f in lab), "mix_agree": sum(a[f]["object"] == b[f]["object"] for f in mix), "mix_n": len(mix),
            "errors_caught_by_disagreement": len(caught), "errors_total_single_model": sum(1 for f in lab if (a[f]["object"] == a[f]["expected"]) != (b[f]["object"] == b[f]["expected"])),
            "both_wrong_same_answer": both_wrong_same}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("a"); ap.add_argument("b"); ap.add_argument("--names", default="A,B"); x = ap.parse_args()
    na, nb = x.names.split(","); r = crosscheck(json.load(open(x.a)), json.load(open(x.b)))
    print(f"{na} vs {nb}: agree {r['agree']}/{r['n']} (labelled {r['labelled_agree']}/{r['labelled']}, unlabelled mix {r['mix_agree']}/{r['mix_n']})")
    print(f"single-model errors on labelled photos: {r['errors_total_single_model']}, flagged by disagreement: {r['errors_caught_by_disagreement']}, both wrong the same way: {len(r['both_wrong_same_answer'])}")
    for f, oa, ob, t in r["disagreements"]: print(f"  REVIEW {f}: {na}={oa} {nb}={ob} truth={t}")
