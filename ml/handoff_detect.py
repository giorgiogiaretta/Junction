"""HandOff detector on series C: error phase (before MARK) vs correction phase (after MARK) from the hand trajectory.
Honest scope: 10 takes, one operator, the MARK is human-timed (+-0.5 s). Leave-one-take-out CV. Reports window accuracy vs majority baseline,
and the error (s) of the estimated switch time vs the MARK.   python ml/handoff_detect.py
"""
import json, numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

HZ, W = 30, 30                                  # 1 s window
idx = [i for i in json.load(open("data/episodes/index.json")) if i["series"] == "C"]

def windows(z, h):
    p = z[f"{h}_wrist_pos"]; f = z[f"{h}_fingers01"][:, 1:].mean(1); t = z["t"]; X, T = [], []
    for k in range(W, len(p), 3):
        pw, fw = p[k - W:k], f[k - W:k]; step = np.linalg.norm(np.diff(pw, axis=0), axis=1)
        path = step.sum() + 1e-6; disp = np.linalg.norm(pw[-1] - pw[0])
        X.append([fw.mean(), fw.std(), fw[-1] - fw[0], step.mean() * HZ, step.max() * HZ, disp / path, pw[-1, 2] - p[0, 2], pw[-1, 2] - pw[0, 2]]); T.append(t[k - 1])
    return np.array(X), np.array(T)

data = []
for i in idx:
    z = np.load(f"data/episodes/take_{i['take']:02d}.npz", allow_pickle=True); X, T = windows(z, i["active_hand"])
    y = (T >= float(z["t_mark"])).astype(int); data.append((i["take"], X, T, y, float(z["t_mark"])))
accs, base, aucs, errs = [], [], [], []
for model_name, mk in (("logreg", lambda: LogisticRegression(max_iter=2000)), ("gboost", lambda: GradientBoostingClassifier(n_estimators=80, max_depth=2, random_state=0))):
    accs, base, aucs, errs = [], [], [], []
    for j, (tk, Xt, Tt, yt, tm) in enumerate(data):
        Xtr = np.concatenate([d[1] for k, d in enumerate(data) if k != j]); ytr = np.concatenate([d[3] for k, d in enumerate(data) if k != j])
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6; m = mk().fit((Xtr - mu) / sd, ytr)
        pr = m.predict_proba((Xt - mu) / sd)[:, 1]; accs.append(((pr > 0.5) == yt).mean()); base.append(max(ytr.mean(), 1 - ytr.mean()) if False else (yt == int(ytr.mean() > 0.5)).mean())
        if len(set(yt)) == 2: aucs.append(roc_auc_score(yt, pr))
        # change point: split minimising disagreement between prediction and a step function
        best = min(range(1, len(pr)), key=lambda c: (pr[:c] > 0.5).sum() + (pr[c:] < 0.5).sum()); errs.append(abs(Tt[best] - tm))
    print(f"{model_name}: window acc={np.mean(accs):.2f} (majority-class baseline {np.mean(base):.2f})  AUC={np.mean(aucs):.2f}  switch-time error median={np.median(errs):.1f}s mean={np.mean(errs):.1f}s  (n={len(data)} takes)")
