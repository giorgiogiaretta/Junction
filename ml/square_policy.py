#!/usr/bin/env python3
"""Series H square pick-and-place: table frame, leg segmentation, small MLP behaviour cloning, leave-one-take-out eval.
Draft by a delegate model (deepseek), reviewed and fixed by Claude (leg off-by-one, rollout start). Honest scope: 10 takes, one operator.
  python ml/square_policy.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from device import pick_device

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
IN_DIM = 14  # pos3 + vel3 + grip1 + (goal-pos)3 + onehot4
OUT_DIM = 4  # dpos3 + grip1


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


def segment_legs(pos, corners, dist_thr=0.06, speed_thr=0.15, fps=FPS):
    """leg in 0..3: (distinct slow visits to corners so far) - 1, clamped; goal = destination corner of that leg (BL>TL, TL>TR, TR>BR, BR>BL)."""
    pos = np.asarray(pos, float)
    n = len(pos)
    vel = np.zeros_like(pos)
    if n > 1:
        vel[1:] = np.diff(pos, axis=0) * fps
    speed = np.linalg.norm(vel, axis=1)
    C = np.stack([corners[k] for k in CORNER_ORDER])
    d = np.linalg.norm(pos[:, None, :] - C[None, :, :], axis=2)
    cand = np.where((d.min(1) < dist_thr) & (speed < speed_thr), d.argmin(1), -1)
    starts, last = [], -1
    for i, ci in enumerate(cand):
        if ci == -1 or ci == last:
            continue
        starts.append(i)
        last = ci
    legs = np.zeros(n, int)
    if starts:
        st = np.asarray(starts, int)
        legs = np.clip((st[None, :] <= np.arange(n)[:, None]).sum(1) - 1, 0, 3)
    goals = np.stack([corners[CORNER_ORDER[(int(l) + 1) % 4]] for l in legs])
    return legs, goals


def make_state(pos, vel, grip, goal, leg):
    oh = np.zeros(4)
    oh[int(leg)] = 1.0
    return np.concatenate([np.asarray(pos, float), np.asarray(vel, float), [float(grip)], np.asarray(goal, float) - np.asarray(pos, float), oh])


def make_dataset(takes, horizon=HORIZON, vel_lag=VEL_LAG):
    Xs, Ys = [], []
    for td in takes:
        pos, grip, legs, goals = td["pos"], td["grip"], td["legs"], td["goals"]
        for t in range(vel_lag, len(pos) - horizon):
            vel = pos[t] - pos[t - vel_lag]  # displacement (m) over vel_lag steps
            Xs.append(make_state(pos[t], vel, grip[t], goals[t], legs[t]))
            Ys.append(np.concatenate([pos[t + horizon] - pos[t], [grip[t + horizon]]]))
    return np.asarray(Xs, np.float32).reshape(-1, IN_DIM), np.asarray(Ys, np.float32).reshape(-1, OUT_DIM)


class MLP(torch.nn.Module):
    def __init__(self, in_dim=IN_DIM, out_dim=OUT_DIM, h=64):
        super().__init__()
        self.net = torch.nn.Sequential(torch.nn.Linear(in_dim, h), torch.nn.ReLU(), torch.nn.Linear(h, h), torch.nn.ReLU(), torch.nn.Linear(h, out_dim))

    def forward(self, x):
        return self.net(x)


def train_mlp(X, Y, dev, epochs=EPOCHS, batch=256, lr=1e-3, seed=0):
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
    x = torch.as_tensor((np.asarray(X, np.float32) - model["mu"]) / model["sd"], dtype=torch.float32, device=model["dev"])
    with torch.no_grad():
        y = model["net"](x).cpu().numpy()
    return y * model["ys"] + model["ym"]


def rollout(model, take, max_steps=150, goal_tol=0.04, reach_tol=0.05, clip_dp=0.10):
    """Closed loop from the first slow visit to BL: 4 legs, goal switches at <goal_tol or after max_steps."""
    C = take["corners"]
    near = np.where(np.linalg.norm(take["pos"] - C["BL"], axis=1) < 0.06)[0]
    i0 = int(near[0]) if len(near) else 0
    pos = take["pos"][i0].astype(float).copy()
    grip = float(take["grip"][i0])
    hist = [pos.copy()]
    reached = []
    for leg in range(4):
        goal = C[CORNER_ORDER[(leg + 1) % 4]]
        for _ in range(max_steps):
            vel = (hist[-1] - hist[-VEL_LAG - 1]) if len(hist) >= VEL_LAG + 1 else np.zeros(3)
            a = predict(model, make_state(pos, vel, grip, goal, leg)[None])[0]
            pos = pos + np.clip(a[:3], -clip_dp, clip_dp)
            grip = float(np.clip(a[3], 0.0, 1.0))
            hist.append(pos.copy())
            if np.linalg.norm(pos - goal) < goal_tol:
                break
        reached.append(bool(np.linalg.norm(pos - goal) < reach_tol))
    return {"legs_reached": reached, "corners_reached": int(sum(reached)), "final_err_cm": 100.0 * float(np.linalg.norm(pos - C["BL"]))}


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


def train_eval(takes, dev, epochs=EPOCHS):
    folds = []
    for k, test in enumerate(takes):
        Xtr, Ytr = make_dataset([t for i, t in enumerate(takes) if i != k])
        Xte, Yte = make_dataset([test])
        model = train_mlp(Xtr, Ytr, dev, epochs=epochs)
        P = predict(model, Xte)
        pos_mae = float(100.0 * np.abs(P[:, :3] - Yte[:, :3]).mean())
        grip_mae = float(np.abs(P[:, 3] - Yte[:, 3]).mean())
        bvel = float(100.0 * np.abs(Xte[:, 3:6] * (HORIZON / VEL_LAG) - Yte[:, :3]).mean())
        bgrip = float(np.abs(Xte[:, 6] - Yte[:, 3]).mean())
        ro = rollout(model, test)
        folds.append({"test_take": test["name"], "hand": test["hand"], "n_train": int(len(Xtr)), "n_test": int(len(Xte)), "pos_mae_cm": pos_mae, "grip_mae": grip_mae,
                      "base_vel_pos_mae_cm": bvel, "base_grip_mae": bgrip, "rollout": ro})
        print(f"[fold] test={test['name']:>3} pos={pos_mae:5.2f}cm (vel-base {bvel:5.2f}) grip={grip_mae:5.3f} (hold-base {bgrip:5.3f}) corners={ro['corners_reached']}/4 final={ro['final_err_cm']:.1f}cm")
    return folds


def main():
    dev = pick_device()
    takes, skipped = load_takes()
    if len(takes) < 3:
        raise SystemExit(f"need >=3 usable H takes, got {len(takes)}")
    print(f"device={dev} takes={len(takes)} scales={[round(t['scale'], 2) for t in takes]}")
    folds = train_eval(takes, dev)
    m = lambda f: float(np.mean([f(x) for x in folds]))
    means = {"n_folds": len(folds), "pos_mae_cm": m(lambda f: f["pos_mae_cm"]), "base_vel_pos_mae_cm": m(lambda f: f["base_vel_pos_mae_cm"]), "grip_mae": m(lambda f: f["grip_mae"]),
             "base_grip_mae": m(lambda f: f["base_grip_mae"]), "rollout_corners_reached": m(lambda f: f["rollout"]["corners_reached"]), "rollout_final_err_cm": m(lambda f: f["rollout"]["final_err_cm"])}
    REPORT.write_text(json.dumps({"device": str(dev), "skipped": skipped, "folds": folds, "means": means}, indent=2))
    print("MEAN:", {k: round(v, 3) for k, v in means.items()})


if __name__ == "__main__":
    main()
