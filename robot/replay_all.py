"""Replay matrix over all episodes (PLAN 2.3 report): python -m robot.replay_all [--out docs/replay_matrix.json]
Runs cube with pick {wrist, closure} x fingers {real, gain, synthetic} on every A-D episode, plus egg (series B, gain fingers,
pick=closure) with and without the Force Cushion. Prints per-series lift / break counts."""
import argparse, glob, json, os, sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from robot.replay import replay

CONFIGS = [(o, p, f, a) for p in ("wrist", "closure") for f in ("real", "gain", "synthetic") for o, a in (("cube", None),)] + \
          [("egg", "closure", "gain", None), ("egg", "closure", "gain", "egg"), ("egg", "wrist", "synthetic", None), ("egg", "wrist", "synthetic", "egg")]


def _job(args):
    path, obj, pick, fingers, assist = args
    try: return {**replay(path, obj, fingers=fingers, assist=assist, pick=pick), "assist": assist, "fingers": fingers}
    except Exception as e: return {"take": os.path.basename(path), "error": repr(e), "obj": obj, "pick": pick, "fingers": fingers, "assist": assist}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out"); a = ap.parse_args()
    eps = sorted(glob.glob(os.path.join(ROOT, "data", "episodes", "take_*.npz")))
    import numpy as np
    ser = {e: str(np.load(e, allow_pickle=True)["series"]) for e in eps}
    jobs = []
    for obj, pick, fingers, assist in CONFIGS:
        for e in eps:
            if ser[e] not in "ABCD": continue
            if obj == "egg" and ser[e] != "B": continue
            jobs.append((e, obj, pick, fingers, assist))
    with ProcessPoolExecutor() as ex: res = list(ex.map(_job, jobs))
    tab = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0.0]))   # cfg -> series -> [n, lifted, broken, sum closure4_peak]
    for r in res:
        k = f'{r["obj"]:4s} pick={r["pick"]:7s} fingers={r["fingers"]:9s} assist={r.get("assist") or "-"}'
        s = tab[k][r.get("series", "?")]; s[0] += 1
        if "error" in r: continue
        s[1] += r["lifted"]; s[2] += r["broken"]; s[3] += r.get("closure4_peak", 0)
    for k, d in tab.items():
        print(k, "  ".join(f'{sr}: lift {v[1]}/{v[0]} brk {v[2]} c4pk {v[3]/max(v[0],1):.2f}' for sr, v in sorted(d.items())))
    errs = [r for r in res if "error" in r]
    if errs: print("errors:", len(errs), errs[0])
    if a.out: json.dump(res, open(a.out, "w"), indent=0)


if __name__ == "__main__":
    main()
