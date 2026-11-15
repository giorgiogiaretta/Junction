"""Command -> measured lag of the G1 arms from the organisers' runner logs (READ ONLY, offline).

Usage:
    py -3.11 tools/g1_windows_runner/lag_report.py [RUNS_DIR_OR_EPISODE ...] [--backend real] [--md] [--windows 20]

Default input: C:/Users/giorg/Desktop/aaltonomous-humanoid/runs/giorgio (every */episode_000.npz).
Per run it prints:
  loop period (runner tick, from `wall`): median / p95 / max [ms], ticks per second
  lag_xc   : cross-correlation of command vs measured joint VELOCITY (resampled at 100 Hz on wall time), median over
             the joints that move, [s]
  lag_fit  : the delay L that minimises RMS(q(t) - cmd(t - L)), per-joint offset removed, over moving joints [s]
  err      : median |cmd - q| over moving joints and time [rad]; p95 too
  win      : lag_fit in consecutive windows (default 20 s): a lag that GROWS from ~0 at the start to a plateau means a
             queue filling up (stale state), a constant lag means a slow plant / low gains.
  clips    : ticks the runner's safety filter clipped.
Fields used: t, wall, arm_q, arm_q_cmd, clipped, mode (runner.py Recorder). arm_q_cmd is the POST-filter command,
arm_q is what rt/lowstate reported to the runner process.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

DEFAULT = Path(r"C:/Users/giorg/Desktop/aaltonomous-humanoid/runs/giorgio")
FS = 100.0          # resample rate [Hz]
MAX_LAG = 3.0       # search window [s]
MOVE_STD = 0.05     # a joint "moves" if its command std over the run exceeds this [rad]


def _resample(wall, x, fs=FS):
    tt = np.arange(wall[0], wall[-1], 1.0 / fs)
    return tt, np.stack([np.interp(tt, wall, x[:, j]) for j in range(x.shape[1])], 1)


def lag_xcorr(cmd, q, fs=FS, max_lag=MAX_LAG):
    """Lag [s] maximising the normalised cross-correlation of the two velocity signals (q lags cmd: lag > 0)."""
    vc, vq = np.diff(cmd) * fs, np.diff(q) * fs
    vc, vq = vc - vc.mean(), vq - vq.mean()
    n = len(vc)
    best, best_k = -np.inf, 0
    for k in range(0, min(int(max_lag * fs), n - 10)):
        a, b = vc[: n - k], vq[k:]
        den = np.sqrt((a * a).sum() * (b * b).sum())
        if den <= 0:
            continue
        c = (a * b).sum() / den
        if c > best:
            best, best_k = c, k
    return best_k / fs, best


def lag_fit(cmd, q, fs=FS, max_lag=MAX_LAG):
    """Delay L [s] minimising the RMS of q(t) - cmd(t-L) about its per-joint mean (a constant offset such as gravity
    sag with the low arm gains does not bias the estimate), over all given joints (cmd, q: [T, J])."""
    n = len(cmd)
    best, best_k = np.inf, 0
    for k in range(0, min(int(max_lag * fs), n - 10)):
        r = q[k:] - cmd[: n - k]
        e = np.sqrt(np.mean((r - r.mean(0)) ** 2))
        if e < best:
            best, best_k = e, k
    return best_k / fs, best


def analyse(npz: Path, win_s=20.0):
    z = np.load(npz, allow_pickle=True)
    wall = np.asarray(z["wall"], float)
    q, cmd = np.asarray(z["arm_q"], float), np.asarray(z["arm_q_cmd"], float)
    run = {}
    rj = npz.parent / "run.json"
    if rj.exists():
        try:
            run = json.loads(rj.read_text())
        except Exception:
            pass
    dt = np.diff(wall) * 1e3
    r = {"run": npz.parent.name, "backend": run.get("backend", "?"),
         "policy": (run.get("policy_metadata") or {}).get("name", "?"),
         "n": len(wall), "dur_s": round(float(wall[-1] - wall[0]), 1),
         "per_med": round(float(np.median(dt)), 1), "per_p95": round(float(np.percentile(dt, 95)), 1),
         "per_max": round(float(dt.max()), 1), "hz": round(len(wall) / max(wall[-1] - wall[0], 1e-9), 1),
         "clips": int(np.asarray(z["clipped"]).sum()), "stale_or_stop": int((np.asarray(z["mode"]) > 0).sum())}
    if len(wall) < 60 or r["dur_s"] < 3:
        return {**r, "note": "too short"}
    tt, C = _resample(wall, cmd)
    _, Q = _resample(wall, q)
    mov = [j for j in range(14) if C[:, j].std() > MOVE_STD]
    r["moving"] = len(mov)
    if not mov:
        return {**r, "note": "arms did not move"}
    xc = [lag_xcorr(C[:, j], Q[:, j]) for j in mov]
    good = [l for l, c in xc if c > 0.3]
    r["lag_xc"] = round(float(np.median(good)), 2) if good else None
    r["lag_xc_per_joint"] = {int(j): round(l, 2) for j, (l, c) in zip(mov, xc) if c > 0.3}
    r["lag_fit"], _ = lag_fit(C[:, mov], Q[:, mov])
    e = np.abs(C[:, mov] - Q[:, mov])
    r["err_med"], r["err_p95"] = round(float(np.median(e)), 3), round(float(np.percentile(e, 95)), 3)
    n_w = int(win_s * FS)
    wins = []
    for s in range(0, len(tt) - n_w // 2, n_w):
        Cw, Qw = C[s: s + n_w, mov], Q[s: s + n_w, mov]
        if len(Cw) < FS * 5 or Cw.std(0).max() < MOVE_STD / 2:
            wins.append(None)
            continue
        wins.append(round(lag_fit(Cw, Qw, max_lag=min(MAX_LAG, len(Cw) / FS / 3))[0], 2))
    r["win"] = wins
    return r


def find(paths):
    out = []
    for p in paths:
        p = Path(p)
        if p.is_file():
            out.append(p)
        else:
            out += sorted(p.glob("*/episode_000.npz"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="*", default=[str(DEFAULT)])
    ap.add_argument("--backend", default=None, help="only runs with this backend (real / mock / sim)")
    ap.add_argument("--md", action="store_true", help="markdown table")
    ap.add_argument("--windows", type=float, default=20.0, help="window length for the lag-over-time column [s]")
    ap.add_argument("--json", default=None, help="also write all results to this JSON file")
    a = ap.parse_args(argv)
    rows = []
    for f in find(a.paths):
        try:
            r = analyse(f, a.windows)
        except Exception as e:  # corrupt / interrupted episode
            r = {"run": f.parent.name, "backend": "?", "note": f"error {e}"}
        if a.backend and r.get("backend") != a.backend:
            continue
        rows.append(r)
    cols = ["run", "backend", "dur_s", "hz", "per_med", "per_p95", "per_max", "lag_xc", "lag_fit", "err_med",
            "err_p95", "clips", "win"]
    if a.md:
        print("| " + " | ".join(cols) + " |")
        print("|" + "---|" * len(cols))
    for r in rows:
        if "note" in r and "lag_fit" not in r:
            vals = [str(r.get(c, "")) for c in cols[:7]] + [r["note"]] + [""] * (len(cols) - 8)
        else:
            vals = [str(r.get(c, "")) if c != "win" else " ".join("-" if w is None else f"{w:.2f}" for w in r["win"])
                    for c in cols]
        print(("| " + " | ".join(vals) + " |") if a.md else "  ".join(vals))
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1, default=float))
    lagged = [r for r in rows if r.get("lag_fit") is not None and r.get("backend") == "real"]
    if lagged:
        print(f"\nreal runs with motion: {len(lagged)}; median lag_fit {np.median([r['lag_fit'] for r in lagged]):.2f} s,"
              f" median loop p95 {np.median([r['per_p95'] for r in lagged]):.0f} ms", file=sys.stderr)
    return rows


if __name__ == "__main__":
    main()
