"""Behaviour-cloning baseline: predict the hand closure (index..little mean, 0 open..1 closed, calibrated) from the recent wrist trajectory.
Honest scope: wrist pose only (object position is not measured), train/test split BY TAKE. Compares against a constant-mean predictor.
  python ml/bc_baseline.py [--series ABC] [--epochs 300]      device: CUDA (MSI) > MPS (MacBook M2) > CPU (ml/device.py)
"""
import json, os, sys, time
import numpy as np, torch, torch.nn as nn
sys.path.insert(0, os.path.dirname(__file__))
from device import pick_device

W = 15                                         # window (30 Hz -> 0.5 s)
ser = sys.argv[sys.argv.index("--series") + 1] if "--series" in sys.argv else "ABC"
epochs = int(sys.argv[sys.argv.index("--epochs") + 1]) if "--epochs" in sys.argv else 300
idx = [i for i in json.load(open("data/episodes/index.json")) if i["series"] in ser]

def feats(z, h):
    p = z[f"{h}_wrist_pos"].astype(np.float32); f = z[f"{h}_fingers01"][:, 1:].mean(1)
    p = p - p[0]                               # relative to where the hand started
    X, Y = [], []
    for t in range(W, len(p)):
        w = p[t - W:t]; v = w[-1] - w[-5]
        X.append(np.concatenate([w[-1], v, w[-1] - w[0], [np.linalg.norm(v)]])); Y.append(f[t])
    return np.array(X, np.float32), np.array(Y, np.float32)

tr, te = [], []
for i in idx:
    z = np.load(f"data/episodes/take_{i['take']:02d}.npz", allow_pickle=True); X, Y = feats(z, i["active_hand"])
    (te if i["take"] % 5 == 0 else tr).append((X, Y))
Xtr, Ytr = map(np.concatenate, zip(*tr)); Xte, Yte = map(np.concatenate, zip(*te))
mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
dev = pick_device(); torch.manual_seed(0)
net = nn.Sequential(nn.Linear(Xtr.shape[1], 64), nn.ReLU(), nn.Linear(64, 64), nn.ReLU(), nn.Linear(64, 1)).to(dev)
opt = torch.optim.Adam(net.parameters(), 3e-3)
tx = torch.tensor((Xtr - mu) / sd, device=dev); ty = torch.tensor(Ytr, device=dev)
t0 = time.time()
for e in range(epochs):
    opt.zero_grad(); loss = nn.functional.mse_loss(net(tx).squeeze(1), ty); loss.backward(); opt.step()
with torch.no_grad(): pred = net(torch.tensor((Xte - mu) / sd, device=dev)).squeeze(1).cpu().numpy()
mae, base = np.abs(pred - Yte).mean(), np.abs(Ytr.mean() - Yte).mean()
print(f"device={dev} series={ser} train_eps={len(tr)} test_eps={len(te)} samples={len(Xtr)}/{len(Xte)} time={time.time()-t0:.1f}s")
print(f"closure MAE: model={mae:.3f}  constant-mean baseline={base:.3f}  ({'better' if mae < base else 'NOT better'} than baseline by {100*(base-mae)/base:.0f}%)")
corr = np.corrcoef(pred, Yte)[0, 1]; print(f"correlation pred vs true on held-out takes: {corr:.2f}")
