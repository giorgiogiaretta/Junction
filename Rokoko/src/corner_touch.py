"""Series J (touch the 4 corners, same posture, 2 s each): corner positions in the Coil frame from the DWELLS of the wrist path, no can, no outline fit.
  python Rokoko/src/corner_touch.py [tape side cm]   -> data/corner_touch.json. Optional: pass the side you MEASURED with the tape (default 29.4).
Dwell = wrist speed < 0.04 m/s for >= 1.0 s. Dwells are clustered into 4 corners; first dwell = BL (visit order BL>TL>TR>BR>BL).
"""
import json, sys
import numpy as np

def dwells(pos, hz=30, vmax=0.04, tmin=1.0):
    v = np.r_[0, np.linalg.norm(np.diff(pos, axis=0), axis=1)] * hz
    v = np.convolve(v, np.ones(5) / 5, mode="same"); slow = v < vmax; out, st = [], None
    for k, x in enumerate(slow):
        if x and st is None: st = k
        if (not x or k == len(slow) - 1) and st is not None:
            if (k - st) / hz >= tmin: out.append((st, k, pos[st:k].mean(0)))
            st = None
    return out

def corners_from_dwells(dw, radius=0.07):
    cl = []                                              # clusters in order of first visit
    for _, _, p in dw:
        for c in cl:
            if np.linalg.norm(c["mean"] - p) < radius: c["pts"].append(p); c["mean"] = np.mean(c["pts"], 0); break
        else: cl.append({"pts": [p], "mean": p})
    return cl

def report(cl, side=0.294):
    if len(cl) != 4: return {"error": f"found {len(cl)} clusters, expected 4", "sizes": [len(c["pts"]) for c in cl]}
    names = ["BL", "TL", "TR", "BR"]; C = {n: c["mean"] for n, c in zip(names, cl)}
    sides = {a + "-" + b: float(np.linalg.norm(C[a] - C[b])) for a, b in (("BL", "TL"), ("TL", "TR"), ("TR", "BR"), ("BR", "BL"))}
    diag = {"BL-TR": float(np.linalg.norm(C["BL"] - C["TR"])), "TL-BR": float(np.linalg.norm(C["TL"] - C["BR"]))}
    spread = [float(np.mean([np.linalg.norm(p - c["mean"]) for p in c["pts"]])) for c in cl]
    m = float(np.mean(list(sides.values())))
    return {"corners": {k: np.round(v, 4).tolist() for k, v in C.items()}, "sides_m": {k: round(v, 3) for k, v in sides.items()}, "diagonals_m": {k: round(v, 3) for k, v in diag.items()},
            "diag_over_side": round(float(np.mean(list(diag.values())) / m), 3), "mean_side_m": round(m, 3), "scale_vs_tape": round(m / side, 3),
            "repeat_spread_cm": [round(100 * s, 1) for s in spread], "visits_per_corner": [len(c["pts"]) for c in cl]}

if __name__ == "__main__":
    side = float(sys.argv[1]) / 100 if len(sys.argv) > 1 else 0.294
    idx = [i for i in json.load(open("data/episodes/index.json")) if i["series"] == "J"]; out = {}
    for i in idx:
        z = np.load(f"data/episodes/take_{i['take']:02d}.npz", allow_pickle=True); h = i["active_hand"]
        r = report(corners_from_dwells(dwells(z[f"{h}_wrist_pos"])), side); out[i["take"]] = {"hand": h, **r}
        print(f"take {i['take']} {h}:", r if "error" in r else f"sides {r['sides_m']} diag/side {r['diag_over_side']} (square: 1.414) scale vs {side*100:.1f} cm = {r['scale_vs_tape']} spread {r['repeat_spread_cm']} cm")
    json.dump(out, open("data/corner_touch.json", "w"), indent=1)
