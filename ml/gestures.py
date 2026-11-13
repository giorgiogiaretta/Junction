"""Baseline gesture classifier on finger windows. Works on synthetic data now; export numpy weights for the Jetson (py3.6).
Usage: python ml/gestures.py            (trains on synthetic gestures, prints accuracy, writes ml/model.npz)
"""
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

GESTURES = {"open": [0, 0, 0, 0, 0], "fist": [1, 1, 1, 1, 1], "point": [1, 0, 1, 1, 1], "peace": [1, 0, 0, 1, 1], "pinch": [0.8, 0.8, 0, 0, 0]}
NAMES = list(GESTURES)

def features(w):  # w: (N,T,5) -> mean + std + range
    return np.concatenate([w.mean(1), w.std(1), w.max(1) - w.min(1)], axis=1)

def synthetic(n=300, T=30, noise=0.08, seed=0):
    rng = np.random.default_rng(seed); X, y = [], []
    for i, g in enumerate(NAMES):
        base = np.array(GESTURES[g], dtype=np.float32)
        for _ in range(n):
            X.append(np.clip(base + rng.normal(0, noise, (T, 5)), 0, 1)); y.append(i)
    return np.array(X), np.array(y)

if __name__ == "__main__":
    X, y = synthetic(); F = features(X)
    Xtr, Xte, ytr, yte = train_test_split(F, y, test_size=0.25, random_state=0)
    m = LogisticRegression(max_iter=500).fit(Xtr, ytr)
    print("accuracy on synthetic:", round(m.score(Xte, yte), 3))
    np.savez("ml/model.npz", W=m.coef_, b=m.intercept_, names=np.array(NAMES))
