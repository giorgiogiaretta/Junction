#!/usr/bin/env python3
"""Overnight multi-cycle data analysis on the GPU (random search, leave-one-take-out CV, honest baselines). Keeps the PC awake while running.
  NIGHT_HOURS=7 python tools/night_gpu.py      -> data/night/trials.jsonl (every trial), data/night/report.md (best per task, refreshed every 20 min)
Tasks (round robin): (P) square policy: arch/horizon/noise-injection sweep, scored by closed-loop corners reached + one-step error;
(I) series-C error->correction detector (window/feature/model sweep, switch-time error); (S) series classifier task-vs-noise (A,B,C,D,H,J).
"""
import ctypes, json, os, random, subprocess, sys, time, traceback
from pathlib import Path
import numpy as np, torch
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "ml")); os.chdir(ROOT)
import square_policy as SP
from device import pick_device
try: ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED: no sleep while this runs
except Exception: pass
HOURS = float(os.environ.get("NIGHT_HOURS", "7")); T0 = time.time(); OUT = ROOT / "data" / "night"; OUT.mkdir(parents=True, exist_ok=True)
dev = pick_device(); rng = random.Random(int(time.time()))


def log(task, cfg, res):
    with open(OUT / "trials.jsonl", "a") as f:
        f.write(json.dumps({"t": round(time.time() - T0), "task": task, "cfg": cfg, "res": res}) + "\n")


# ---------------------------------------------------------------- P: square policy
def make_ds(takes, h, sigma, reps, seed=0):
    g = np.random.default_rng(seed); X, Y = [], []
    for td in takes:
        pos, grip, legs, goals = td["pos"], td["grip"], td["legs"], td["goals"]
        for r in range(reps if sigma > 0 else 1):
            for t in range(SP.VEL_LAG, len(pos) - h):
                eps = g.normal(0, sigma, 3) if sigma > 0 else np.zeros(3); p = pos[t] + eps; vel = pos[t] - pos[t - SP.VEL_LAG]
                X.append(SP.make_state(p, vel, grip[t], goals[t], legs[t])); Y.append(np.concatenate([pos[t + h] - p, [grip[t + h]]]))
    return np.asarray(X, np.float32), np.asarray(Y, np.float32)


class Net(torch.nn.Module):
    def __init__(self, hid, layers):
        super().__init__(); L, d = [], SP.IN_DIM
        for _ in range(layers): L += [torch.nn.Linear(d, hid), torch.nn.ReLU()]; d = hid
        self.net = torch.nn.Sequential(*L, torch.nn.Linear(d, SP.OUT_DIM))

    def forward(self, x): return self.net(x)


def fit(X, Y, c, seed):
    torch.manual_seed(seed); mu, sd, ym, ys = X.mean(0), X.std(0) + 1e-6, Y.mean(0), Y.std(0) + 1e-6
    Xt = torch.as_tensor((X - mu) / sd, dtype=torch.float32, device=dev); Yt = torch.as_tensor((Y - ym) / ys, dtype=torch.float32, device=dev)
    net = Net(c["hid"], c["layers"]).to(dev); opt = torch.optim.AdamW(net.parameters(), lr=c["lr"], weight_decay=c["wd"]); n = len(Xt)
    for _ in range(c["epochs"]):
        perm = torch.randperm(n, device=dev)
        for i in range(0, n, 512):
            idx = perm[i:i + 512]; opt.zero_grad(); torch.nn.functional.mse_loss(net(Xt[idx]), Yt[idx]).backward(); opt.step()
    return {"net": net, "mu": mu, "sd": sd, "ym": ym, "ys": ys, "dev": dev}


def trial_P(takes):
    c = {"hid": rng.choice([64, 128, 256]), "layers": rng.choice([2, 3]), "h": rng.choice([3, 5, 8, 12]), "sigma": rng.choice([0, 0.005, 0.01, 0.02, 0.04]),
         "reps": rng.choice([1, 3, 5]), "epochs": rng.choice([100, 200, 300]), "lr": rng.choice([1e-3, 3e-4]), "wd": rng.choice([0, 1e-4, 1e-2])}
    seed = rng.randrange(1000); mae, base, corners, fin = [], [], [], []
    for k, test in enumerate(takes):
        X, Y = make_ds([t for i, t in enumerate(takes) if i != k], c["h"], c["sigma"], c["reps"], seed); Xt, Yt = make_ds([test], c["h"], 0, 1)
        m = fit(X, Y, c, seed); P = SP.predict(m, Xt)
        mae.append(100 * np.abs(P[:, :3] - Yt[:, :3]).mean()); base.append(100 * np.abs(Xt[:, 3:6] * (c["h"] / SP.VEL_LAG) - Yt[:, :3]).mean())
        ro = SP.rollout(m, test); corners.append(ro["corners_reached"]); fin.append(min(ro["final_err_cm"], 1000))
    log("P", c, {"pos_mae_cm": float(np.mean(mae)), "vel_base_cm": float(np.mean(base)), "corners_reached": float(np.mean(corners)), "final_err_cm": float(np.mean(fin))})


# ---------------------------------------------------------------- I / S: windows
def load_eps(series):
    idx = [i for i in json.load(open(ROOT / "data/episodes/index.json")) if i["series"] in series]; out = []
    for i in idx:
        z = np.load(ROOT / f"data/episodes/take_{i['take']:02d}.npz", allow_pickle=True); h = i["active_hand"]
        out.append({"take": i["take"], "series": i["series"], "pos": z[f"{h}_wrist_pos"], "f": z[f"{h}_fingers01"], "t": z["t"], "tm": float(z["t_mark"])})
    return out


def win_feats(e, W, step=3):
    p, f, X, T = e["pos"], e["f"], [], []
    for k in range(W, len(p), step):
        pw, fw = p[k - W:k], f[k - W:k]; st = np.linalg.norm(np.diff(pw, axis=0), axis=1); path = st.sum() + 1e-6
        X.append(np.concatenate([fw.mean(0), fw.std(0), fw[-1] - fw[0], [st.mean() * 30, st.max() * 30, np.linalg.norm(pw[-1] - pw[0]) / path, pw[-1, 2] - pw[0, 2]]])); T.append(e["t"][k - 1])
    return np.array(X, np.float32), np.array(T)


def mlp_clf(X, y, hid, ep, seed, nc):
    torch.manual_seed(seed); mu, sd = X.mean(0), X.std(0) + 1e-6; Xt = torch.as_tensor((X - mu) / sd, dtype=torch.float32, device=dev); yt = torch.as_tensor(y, dtype=torch.long, device=dev)
    net = torch.nn.Sequential(torch.nn.Linear(X.shape[1], hid), torch.nn.ReLU(), torch.nn.Linear(hid, hid), torch.nn.ReLU(), torch.nn.Linear(hid, nc)).to(dev)
    opt = torch.optim.AdamW(net.parameters(), 1e-3, weight_decay=1e-3)
    for _ in range(ep): opt.zero_grad(); torch.nn.functional.cross_entropy(net(Xt), yt).backward(); opt.step()
    return lambda Z: torch.softmax(net(torch.as_tensor((Z - mu) / sd, dtype=torch.float32, device=dev)), 1).detach().cpu().numpy()


def trial_I(eps):
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    c = {"W": rng.choice([15, 30, 45, 60]), "model": rng.choice(["logreg", "gboost", "mlp"]), "hid": rng.choice([32, 64, 128]), "ep": rng.choice([200, 500, 1000])}
    seed = rng.randrange(1000); errs, accs = [], []; D = [(e, *win_feats(e, c["W"])) for e in eps]
    for k, (e, Xt, Tt) in enumerate(D):
        Xtr = np.concatenate([d[1] for j, d in enumerate(D) if j != k]); ytr = np.concatenate([(d[2] >= d[0]["tm"]).astype(int) for j, d in enumerate(D) if j != k])
        if c["model"] == "mlp": pr = mlp_clf(Xtr, ytr, c["hid"], c["ep"], seed, 2)(Xt)[:, 1]
        else:
            mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
            m = (LogisticRegression(max_iter=3000) if c["model"] == "logreg" else GradientBoostingClassifier(n_estimators=100, max_depth=2, random_state=seed)).fit((Xtr - mu) / sd, ytr)
            pr = m.predict_proba((Xt - mu) / sd)[:, 1]
        y = (Tt >= e["tm"]).astype(int); accs.append(((pr > .5) == y).mean())
        best = min(range(1, len(pr)), key=lambda q: (pr[:q] > .5).sum() + (pr[q:] < .5).sum()); errs.append(abs(Tt[best] - e["tm"]))
    log("I", c, {"switch_err_s_median": float(np.median(errs)), "switch_err_s_mean": float(np.mean(errs)), "win_acc": float(np.mean(accs))})


def trial_S(eps):
    from sklearn.ensemble import GradientBoostingClassifier
    c = {"W": rng.choice([30, 60, 90]), "model": rng.choice(["gboost", "mlp"]), "hid": rng.choice([64, 128]), "ep": rng.choice([300, 800])}
    seed = rng.randrange(1000); names = sorted({e["series"] for e in eps}); cid = {n: i for i, n in enumerate(names)}
    D = [(e, *win_feats(e, c["W"], 6)) for e in eps]; correct = tot = noise_ok = noise_tot = 0
    for k, (e, Xt, Tt) in enumerate(D):
        Xtr = np.concatenate([d[1] for j, d in enumerate(D) if j != k]); ytr = np.concatenate([np.full(len(d[1]), cid[d[0]["series"]]) for j, d in enumerate(D) if j != k])
        if c["model"] == "mlp": pr = mlp_clf(Xtr, ytr, c["hid"], c["ep"], seed, len(names))(Xt)
        else:
            mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6; m = GradientBoostingClassifier(n_estimators=60, max_depth=2, random_state=seed).fit((Xtr - mu) / sd, ytr)
            pr = np.zeros((len(Xt), len(names))); pr[:, m.classes_] = m.predict_proba((Xt - mu) / sd)
        pred = pr.argmax(1); correct += int((pred == cid[e["series"]]).sum()); tot += len(pred)
        if e["series"] == "D": noise_ok += int((pred == cid["D"]).sum()); noise_tot += len(pred)
    cnt = {n: sum(len(d[1]) for d in D if d[0]["series"] == n) for n in names}
    log("S", c, {"window_acc": correct / tot, "noise_recall": noise_ok / max(noise_tot, 1), "classes": names, "majority": max(cnt.values()) / sum(cnt.values())})


# ---------------------------------------------------------------- report
def report():
    p = OUT / "trials.jsonl"; rows = [json.loads(l) for l in open(p)] if p.exists() else []
    L = [f"# Night report (elapsed {(time.time() - T0) / 3600:.1f} h, {len(rows)} trials, device {dev})\n"]
    for task, title in (("P", "Square policy (best = most corners reached in closed loop, then lowest final error)"), ("I", "C error->correction switch-time error (s, lower better)"), ("S", "Series classifier window accuracy (higher better)")):
        R = [r for r in rows if r["task"] == task and "error" not in r["res"]]
        if not R: continue
        if task == "P": R.sort(key=lambda r: (-r["res"]["corners_reached"], r["res"]["final_err_cm"]))
        elif task == "I": R.sort(key=lambda r: r["res"]["switch_err_s_median"])
        else: R.sort(key=lambda r: -r["res"]["window_acc"])
        L.append(f"## {title}: {len(R)} trials"); L += [f"- {r['res']} | {r['cfg']}" for r in R[:5]]
        if task == "P": L.append(f"- mean velocity-extrapolation one-step error over trials: {np.mean([r['res']['vel_base_cm'] for r in R]):.2f} cm")
    errs = [r for r in rows if "error" in r["res"]]
    if errs: L.append(f"\n{len(errs)} failed trials, last error: {errs[-1]['res']['error']}")
    (OUT / "report.md").write_text("\n".join(L) + "\n")


def main():
    takes, _ = SP.load_takes(); epsC = load_eps({"C"}); epsS = load_eps(set("ABCDHJ")); last = 0; i = 0
    print(f"night job: {HOURS} h on {dev}, H takes {len(takes)}, C {len(epsC)}, all {len(epsS)}", flush=True)
    while time.time() - T0 < HOURS * 3600:
        task = "PIS"[i % 3]; i += 1
        try: {"P": lambda: trial_P(takes), "I": lambda: trial_I(epsC), "S": lambda: trial_S(epsS)}[task]()
        except Exception: log(task, {}, {"error": traceback.format_exc()[-300:]})
        if time.time() - last > 1200: report(); last = time.time(); print(f"[{(time.time() - T0) / 3600:.2f} h] trials={i}", flush=True)
    report()
    msg = f"[Giorgio's Claude] night job finished: {i} trials, see data/night/report.md (local file on Giorgio's MSI)."
    try: subprocess.run(["C:/Program Files/Git/bin/bash.exe", "-c", "export PATH=$PATH:/c/Program\\ Files/GitHub\\ CLI; cd '" + ROOT.as_posix() + "' && tools/board post \"$0\"", msg], timeout=120)
    except Exception: pass


if __name__ == "__main__":
    main()
