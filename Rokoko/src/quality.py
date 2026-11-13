"""Quality metrics for a recording made with: rgmp_client.py --jsonl data/x.jsonl   (works for 1 or 2 gloves)
Usage: python Rokoko/src/quality.py data/x.jsonl
Reports per hand: frames, duration, mean rate, dropouts (>2.5x nominal gap), jitter (std of gap), motion range per finger.
"""
import json, sys
from collections import defaultdict
import numpy as np

rows = defaultdict(list)
for line in open(sys.argv[1]):
    r = json.loads(line); rows[r.get("hand", "?")].append(r)
for hand, rs in rows.items():
    t = np.array([r["ts_us"] for r in rs]) / 1e6; a = np.array([r["angles"] for r in rs])
    gaps = np.diff(t); nom = np.median(gaps) if len(gaps) else 0
    drops = int((gaps > 2.5 * nom).sum()) if nom else 0
    print(f"[{hand}] frames={len(rs)} dur={t[-1]-t[0]:.1f}s rate={len(rs)/max(t[-1]-t[0],1e-6):.1f}Hz "
          f"dropouts={drops} jitter={gaps.std()*1000:.2f}ms backward_ts={(gaps<=0).sum()}")
    print("   finger range (rad):", np.round(a.max(0) - a.min(0), 2).tolist())
if len(rows) == 2:
    h1, h2 = list(rows); n1, n2 = len(rows[h1]), len(rows[h2])
    print(f"two-hand balance: {h1}={n1} {h2}={n2} (large mismatch => one glove dropping)")
