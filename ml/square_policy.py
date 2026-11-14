#!/usr/bin/env python3
"""Series H square pick-and-place: table frame, leg segmentation, small MLP behaviour cloning, leave-one-take-out eval.
Draft by a delegate model (deepseek), reviewed and fixed by Claude (leg off-by-one, rollout start). Honest scope: 10 takes, one operator.
  python ml/square_policy.py [--model mlp|knn]      mlp needs torch; knn is numpy only
Fixes (#15): targets are HORIZON-step displacements, so the rollout now applies a/HORIZON per step (it applied the whole
HORIZON-step move every step and flew off by metres); legs advance only on a slow visit to the EXPECTED next corner
(any-corner visits mislabelled legs 1-2); time-in-leg input so the corner dwell is not a fixed point.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
EP_DIR = ROOT / "data" / "episodes"
FIT_JSON = ROOT / "data" / "square_fit.json"
REPORT = ROOT / "data" / "square_policy_report.json"

SIDE_TARGET = 0.294
FPS = 30.0
HORIZON = 5
VEL_LAG = 3
EPOCHS = 300
CORNER_ORDER = ["BL", "TL", "TR", "BR"]  # clockwise cycle used by series H
IN_DIM = 15  # pos3 + vel3 + grip1 + (goal-pos)3 + onehot4 + tleg1
OUT_DIM = 4  # dpos3 + grip1
TLEG_CAP = 3.0  # s: time-in-leg input saturates here
KNN_COLS = [3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14]  # vel, goal-pos, leg, tleg: no absolute position (10 takes), no grip
REACH_TOL = 0.08  # m: the demos themselves get only 5.7-7.5 cm from the fitted BR corner, so 5 cm is unreachable there


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def build_table_frame(fit_entry, wrist_pos, side_target=SIDE_TARGET):
    """Coil frame -> table frame: origin=corner centroid, x=BL->BR, y=BL->TL, z=x cross y; scaled so the square side is side_target."""
    c = {k: np.asarray(fit_entry["corners"][k], float) for k in CORNER_ORDER}
    origin = np.mean(np.stack([c[k] for k in CORNER_ORDER]), axis=0)
    x = _unit(c["BR"] - c["BL"])
    y_raw = c["TL"] - c["BL"]
    y = _unit(y_raw - x * np.dot(y_raw, x))
    z = np.cross(x, y)
    rot = np.stack([x, y, z])  # rows = table axes in Coil frame
    edges = list(zip(CORNER_ORDER, CORNER_ORDER[1:] + CORNER_ORDER[:1]))
    side_mean = float(np.mean([np.linalg.norm(c[a] - c[b]) for a, b in edges]))
    scale = side_target / max(side_mean, 1e-6)

    def to_table(p):
        return ((np.asarray(p, float) - origin) @ rot.T) * scale

    return to_table(wrist_pos), {k: to_table(v) for k, v in c.items()}, scale


def grip_channel(fingers01):
    """Thumb vs mean-of-others: the channel with the larger p95-p5 excursion (H grip is thumb-driven)."""
    f = np.asarray(fingers01, float)
    thumb, others = f[:, 0], f[:, 1:].mean(1)
    exc = lambda x: np.percentile(x, 95) - np.percentile(x, 5)
    return thumb if exc(thumb) >= exc(others) else others


def segment_legs(pos, corners, dist_thr=0.09, speed_thr=0.15, fps=FPS):
    """Ordered state machine: leg 0 starts at the first slow visit to BL, then leg k -> k+1 only on a slow visit to the
    EXPECTED next corner (BL>TL>TR>BR>BL), so passing back near the previous corner no longer advances it. Frames before
    the start are leg 0. dist_thr 9 cm: the wrist stops 6-7.5 cm from the fitted BR corner. goal = leg's destination corner."""
    pos = np.asarray(pos, float)
    n = len(pos)
    vel = np.zeros_like(pos)
    if n > 1:
        vel[1:] = np.diff(pos, axis=0) * fps
    slow = np.linalg.norm(vel, axis=1) < speed_thr
    near = lambda i, k: np.linalg.norm(pos[i] - corners[k]) < dist_thr
    legs = np.zeros(n, int)
    leg, started = 0, False
    for i in range(n):
        if not started:
            started = slow[i] and near(i, "BL")
        elif leg < 3 and slow[i] and near(i, CORNER_ORDER[leg + 1]):
            leg += 1
        legs[i] = leg
    goals = np.stack([corners[CORNER_ORDER[(int(l) + 1) % 4]] for l in legs])
    return legs, goals


def time_in_leg(legs, fps=FPS, cap=TLEG_CAP):
    """Seconds since the current leg started, capped: lets the policy leave the corner dwell instead of copying zero velocity."""
    t = np.zeros(len(legs))
    s = 0
    for i in range(len(legs)):
        if i and legs[i] != legs[i - 1]:
            s = i
        t[i] = min((i - s) / fps, cap)
    return t


def make_state(pos, vel, grip, goal, leg, tleg=0.0):
    oh = np.zeros(4)
    oh[int(leg)] = 1.0
    return np.concatenate([np.asarray(pos, float), np.asarray(vel, float), [float(grip)], np.asarray(goal, float) - np.asarray(pos, float), oh, [float(tleg)]])


def make_dataset(takes, horizon=HORIZON, vel_lag=VEL_LAG):
    Xs, Ys = [], []
    for td in takes:
        pos, grip, legs, goals = td["pos"], td["grip"], td["legs"], td["goals"]
        tl = time_in_leg(legs)
        for t in range(vel_lag, len(pos) - horizon):
            vel = pos[t] - pos[t - vel_lag]  # displacement (m) over vel_lag steps
            Xs.append(make_state(pos[t], vel, grip[t], goals[t], legs[t], tl[t]))
            Ys.append(np.concatenate([pos[t + horizon] - pos[t], [grip[t + horizon]]]))
    return np.asarray(Xs, np.float32).reshape(-1, IN_DIM), np.asarray(Ys, np.float32).reshape(-1, OUT_DIM)


def train_knn(X, Y, k=10, cols=KNN_COLS):
    """Numpy k-nearest-neighbour policy on standardised KNN_COLS: mean of the k neighbours' targets."""
    F = X[:, cols].astype(np.float64)
    mu, sd = F.mean(0), F.std(0) + 1e-6
    return {"kind": "knn", "F": (F - mu) / sd, "Y": np.asarray(Y, np.float64), "mu": mu, "sd": sd, "k": k, "cols": cols}


def train_mlp(X, Y, dev, epochs=EPOCHS, batch=256, lr=1e-3, seed=0):
    import torch

    class MLP(torch.nn.Module):
        def __init__(self, in_dim=IN_DIM, out_dim=OUT_DIM, h=64):
            super().__init__()
            self.net = torch.nn.Sequential(torch.nn.Linear(in_dim, h), torch.nn.ReLU(), torch.nn.Linear(h, h), torch.nn.ReLU(), torch.nn.Linear(h, out_dim))

        def forward(self, x):
            return self.net(x)

    torch.manual_seed(seed)
    mu, sd = X.mean(0), X.std(0) + 1e-6
    ym, ys = Y.mean(0), Y.std(0) + 1e-6
    Xt = torch.as_tensor((X - mu) / sd, dtype=torch.float32, device=dev)
    Yt = torch.as_tensor((Y - ym) / ys, dtype=torch.float32, device=dev)
    net = MLP().to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    n = len(Xt)
    for _ in range(epochs):
        perm = torch.randperm(n, device=dev)
        for i in range(0, n, batch):
            idx = perm[i:i + batch]
            opt.zero_grad()
            torch.nn.functional.mse_loss(net(Xt[idx]), Yt[idx]).backward()
            opt.step()
    return {"net": net, "mu": mu, "sd": sd, "ym": ym, "ys": ys, "dev": dev}


def predict(model, X):
    if model.get("kind") == "knn":
        q = (np.asarray(X, np.float64)[:, model["cols"]] - model["mu"]) / model["sd"]
        d = ((model["F"][None] - q[:, None]) ** 2).sum(-1)
        return model["Y"][np.argsort(d, 1)[:, :model["k"]]].mean(1)
    import torch
    x = torch.as_tensor((np.asarray(X, np.float32) - model["mu"]) / model["sd"], dtype=torch.float32, device=model["dev"])
    with torch.no_grad():
        y = model["net"](x).cpu().numpy()
    return y * model["ys"] + model["ym"]


def rollout(model, take, max_steps=150, goal_tol=0.04, reach_tol=REACH_TOL, clip_dp=0.02, horizon=HORIZON):
    """Closed loop from the first slow visit to BL, 4 legs. The goal switches when the wrist is within goal_tol, when it
    has stalled (<5 mm in 0.5 s, after the TLEG_CAP dwell), or after max_steps (5 s); a leg counts as reached if its
    closest approach was < reach_tol. The model predicts a horizon-step move, so each 1/30 s step applies a/horizon.
    clip_dp 2 cm/step = 0.6 m/s, above any demo speed."""
    C = take["corners"]
    near = np.where(np.linalg.norm(take["pos"] - C["BL"], axis=1) < 0.06)[0]
    i0 = int(near[0]) if len(near) else 0
    pos = take["pos"][i0].astype(float).copy()
    grip = float(take["grip"][i0])
    hist = [pos.copy()]
    reached, closest = [], []
    for leg in range(4):
        goal = C[CORNER_ORDER[(leg + 1) % 4]]
        best = np.inf
        for s in range(max_steps):
            vel = (hist[-1] - hist[-VEL_LAG - 1]) if len(hist) >= VEL_LAG + 1 else np.zeros(3)
            a = predict(model, make_state(pos, vel, grip, goal, leg, min(s / FPS, TLEG_CAP))[None])[0]
            pos = pos + np.clip(a[:3] / horizon, -clip_dp, clip_dp)
            grip = float(np.clip(a[3], 0.0, 1.0))
            hist.append(pos.copy())
            best = min(best, float(np.linalg.norm(pos - goal)))
            stalled = s > TLEG_CAP * FPS and np.linalg.norm(hist[-1] - hist[-16]) < 0.005
            if best < goal_tol or stalled:
                break
        reached.append(bool(best < reach_tol))
        closest.append(round(100.0 * best, 1))
    return {"legs_reached": reached, "corners_reached": int(sum(reached)), "closest_cm": closest, "final_err_cm": 100.0 * float(np.linalg.norm(pos - C["BL"]))}


def demo_closest_cm(take):
    """Ceiling: how close the human demo itself got to each leg's corner (cm)."""
    out = []
    for leg in range(4):
        m = take["legs"] == leg
        g = take["corners"][CORNER_ORDER[(leg + 1) % 4]]
        out.append(round(100.0 * float(np.linalg.norm(take["pos"][m] - g, axis=1).min()), 1) if m.any() else None)
    return out


def load_takes():
    index = json.loads((EP_DIR / "index.json").read_text())
    fit = json.loads(FIT_JSON.read_text())
    takes, skipped = [], []
    for e in index:
        if str(e.get("series", "")).upper() != "H":
            continue
        tk, hand = str(e["take"]), e.get("active_hand")
        fe = fit.get(tk)
        fpath = EP_DIR / f"take_{int(tk):02d}.npz"
        if hand not in ("left", "right") or not fe or not fe.get("corners") or not fpath.exists():
            skipped.append(tk)
            print(f"[warn] take {tk} skipped (no corners in square_fit.json / npz / hand)")
            continue
        z = np.load(fpath, allow_pickle=True)
        pos, corners, scale = build_table_frame(fe, z[f"{hand}_wrist_pos"])
        grip = grip_channel(z[f"{hand}_fingers01"])
        legs, goals = segment_legs(pos, corners)
        takes.append({"name": tk, "hand": hand, "pos": pos, "grip": np.asarray(grip, float), "legs": legs, "goals": goals, "corners": corners, "scale": float(scale)})
    return takes, skipped


def train_eval(takes, dev, epochs=EPOCHS, kind="mlp"):
    folds = []
    for k, test in enumerate(takes):
        Xtr, Ytr = make_dataset([t for i, t in enumerate(takes) if i != k])
        Xte, Yte = make_dataset([test])
        model = train_knn(Xtr, Ytr) if kind == "knn" else train_mlp(Xtr, Ytr, dev, epochs=epochs)
        P = predict(model, Xte)
        pos_mae = float(100.0 * np.abs(P[:, :3] - Yte[:, :3]).mean())
        grip_mae = float(np.abs(P[:, 3] - Yte[:, 3]).mean())
        bvel = float(100.0 * np.abs(Xte[:, 3:6] * (HORIZON / VEL_LAG) - Yte[:, :3]).mean())
        bgrip = float(np.abs(Xte[:, 6] - Yte[:, 3]).mean())
        ro = rollout(model, test)
        folds.append({"test_take": test["name"], "hand": test["hand"], "n_train": int(len(Xtr)), "n_test": int(len(Xte)), "pos_mae_cm": pos_mae, "grip_mae": grip_mae,
                      "base_vel_pos_mae_cm": bvel, "base_grip_mae": bgrip, "rollout": ro, "demo_closest_cm": demo_closest_cm(test)})
        print(f"[fold] test={test['name']:>3} pos={pos_mae:5.2f}cm (vel-base {bvel:5.2f}) grip={grip_mae:5.3f} (hold-base {bgrip:5.3f}) corners={ro['corners_reached']}/4 "
              f"closest={ro['closest_cm']} demo={demo_closest_cm(test)} final={ro['final_err_cm']:.1f}cm")
    return folds


def main():
    kind = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "mlp"
    if kind == "knn":
        dev = "cpu"
    else:
        from device import pick_device
        dev = pick_device()
    takes, skipped = load_takes()
    if len(takes) < 3:
        raise SystemExit(f"need >=3 usable H takes, got {len(takes)}")
    print(f"model={kind} device={dev} takes={len(takes)} scales={[round(t['scale'], 2) for t in takes]} reach_tol={REACH_TOL * 100:.0f}cm")
    folds = train_eval(takes, dev, kind=kind)
    m = lambda f: float(np.mean([f(x) for x in folds]))
    means = {"n_folds": len(folds), "pos_mae_cm": m(lambda f: f["pos_mae_cm"]), "base_vel_pos_mae_cm": m(lambda f: f["base_vel_pos_mae_cm"]), "grip_mae": m(lambda f: f["grip_mae"]),
             "base_grip_mae": m(lambda f: f["base_grip_mae"]), "rollout_corners_reached": m(lambda f: f["rollout"]["corners_reached"]),
             "rollout_all4_folds": int(sum(f["rollout"]["corners_reached"] == 4 for f in folds)), "rollout_final_err_cm": m(lambda f: f["rollout"]["final_err_cm"]),
             "demo_legs_within_tol": m(lambda f: sum(d is not None and d < 100 * REACH_TOL for d in f["demo_closest_cm"]))}
    out = REPORT if kind == "mlp" else REPORT.with_name(f"square_policy_report_{kind}.json")
    out.write_text(json.dumps({"model": kind, "device": str(dev), "reach_tol_m": REACH_TOL, "skipped": skipped, "folds": folds, "means": means}, indent=2))
    print("MEAN:", {k: round(v, 3) for k, v in means.items()})


if __name__ == "__main__":
    main()
