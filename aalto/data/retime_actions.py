"""Make every action in a LeRobot dataset copy pass the Aalto safety filter (0 clips).

Per episode, in frame order: clamp each target into the URDF limits shrunk by a margin (filter: 0.05 arm,
0.02 hand; here 0.06 / 0.03), then rate-limit the command change per tick to arm 0.9 rad/s and hand 2.7 rad/s
(10 % under the filter caps of 1.0 / 3.0 rad/s, which are measured from the LAST COMMAND).

Usage: python retime_actions.py <dataset_root> <joint_spec.yaml>   (rewrites <root>/data/*/*.parquet in place)
"""
import glob
import os
import sys

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

root, spec_path = sys.argv[1], sys.argv[2]
spec = yaml.safe_load(open(spec_path))
lo = np.array([j["lower"] for j in spec["arm"]] + [j["lower"] for j in spec["hand"]], np.float64)
hi = np.array([j["upper"] for j in spec["arm"]] + [j["upper"] for j in spec["hand"]], np.float64)
assert lo.shape == (28,), lo.shape
margin = np.r_[np.full(14, 0.06), np.full(14, 0.03)]
margin = np.minimum(margin, 0.25 * (hi - lo))  # same rule as the filter: never invert a narrow range
lo, hi = lo + margin, hi - margin
DT = 1.0 / 30.0
step = np.r_[np.full(14, 0.9 * DT), np.full(14, 2.7 * DT)]

files = sorted(glob.glob(os.path.join(root, "data", "*", "*.parquet")))
assert files, f"no parquet files under {root}/data"
tot = changed = 0
max_dev = np.zeros(28)
for f in files:
    t = pq.read_table(f)
    ep = t["episode_index"].to_numpy()
    fi = t["frame_index"].to_numpy()
    A = np.stack(t["action"].to_numpy(zero_copy_only=False)).astype(np.float64)
    out = A.copy()
    for e in np.unique(ep):
        idx = np.where(ep == e)[0]
        idx = idx[np.argsort(fi[idx])]
        a = np.clip(A[idx], lo, hi)
        y = np.empty_like(a)
        y[0] = a[0]
        for k in range(1, len(a)):
            y[k] = y[k - 1] + np.clip(a[k] - y[k - 1], -step, step)
        out[idx] = y
        if len(y) > 1:
            v = np.abs(np.diff(y, axis=0)).max(0)
            assert (v <= step + 1e-9).all(), (e, v)
    dev = np.abs(out - A)
    tot += len(A)
    changed += int((dev > 1e-6).any(1).sum())
    max_dev = np.maximum(max_dev, dev.max(0))
    field = t.schema.field("action")
    arr = pa.array([r.astype(np.float32) for r in out], type=field.type)
    t = t.set_column(t.schema.get_field_index("action"), field, arr)
    os.remove(f)  # new inode: never write through a hard link to the original dataset
    pq.write_table(t, f)

print(f"retimed {changed}/{tot} frames ({100 * changed / tot:.1f} %); "
      f"max deviation arm {max_dev[:14].max():.3f} rad, hand {max_dev[14:].max():.3f} rad")
