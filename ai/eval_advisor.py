"""Measure the Grasp Advisor against ground truth: mass error vs a kitchen scale and fragility ranking vs a human ranking.
  python -m ai.eval_advisor data/advisor/truth.csv [--backend nemotron|gemma|gemini] [--photos data/advisor]
truth.csv columns: file,object,mass_g,fragility   (file = photo name inside --photos; fragility = YOUR judgement 0 (rubber ball) .. 1 (raw egg))
Reports per object: model name / mass / fragility vs truth; overall median |mass error| %, Spearman rank correlation of fragility, and how often the cap is conservative.
Needs ~8 objects (egg, banana, apple, tomato, grapes, paper cup, can, ball) photographed from the head camera; weigh each. Small sample: a sanity check, not a benchmark."""
import argparse, csv, os, statistics
from ai.advisor import advise


def spearman(x, y):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]: j += 1
            for k in range(i, j + 1): r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    rx, ry = rank(x), rank(y); mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry)); den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else None


def evaluate(rows, run):
    """rows: dicts file/object/mass_g/fragility; run(file) -> advise() result. Returns (per-object list, summary)."""
    out = []
    for r in rows:
        res = run(r["file"]); a = res["advice"] or {}
        mass_err = None if not a.get("est_mass_g") else abs(a["est_mass_g"] - float(r["mass_g"])) / float(r["mass_g"]) * 100
        out.append({"file": r["file"], "true": r["object"], "model": a.get("object"), "mass_true": float(r["mass_g"]), "mass_est": a.get("est_mass_g"), "mass_err_pct": mass_err,
                    "frag_true": float(r["fragility"]), "frag_est": a.get("fragility"), "cap": res["cap"], "conservative": res["cap"] < 0.7})
    errs = [o["mass_err_pct"] for o in out if o["mass_err_pct"] is not None]
    pairs = [(o["frag_true"], o["frag_est"]) for o in out if o["frag_est"] is not None]
    return out, {"n": len(out), "median_mass_err_pct": statistics.median(errs) if errs else None,
                 "fragility_spearman": spearman([p[0] for p in pairs], [p[1] for p in pairs]) if len(pairs) >= 3 else None,
                 "conservative_share": sum(o["conservative"] for o in out) / max(1, len(out))}


if __name__ == "__main__":
    from ai.eval_objects import make_client, prep_image
    ap = argparse.ArgumentParser(); ap.add_argument("truth"); ap.add_argument("--backend", default="nemotron", choices=["nemotron", "gemini", "gemma"]); ap.add_argument("--photos", default=None); a = ap.parse_args()
    rows = list(csv.DictReader(open(a.truth))); folder = a.photos or os.path.dirname(a.truth)
    c = make_client("nemotron" if a.backend == "nemotron" else "gemini")
    if a.backend == "gemma": c.model = "gemma-4-26b-a4b-it"
    out, s = evaluate(rows, lambda f: advise(c, prep_image(open(os.path.join(folder, f), "rb").read())))
    for o in out: print(f"{o['true']:10s} -> {str(o['model']):14s} mass {o['mass_true']:.0f} g vs ~{o['mass_est']} ({o['mass_err_pct'] and round(o['mass_err_pct'])}%) | fragility {o['frag_true']} vs {o['frag_est']} | cap {o['cap']}")
    print(s)
