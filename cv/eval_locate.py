"""Analytical sphere RGB-D geometry sanity check with ORACLE masks/boxes.

This does not evaluate detection, shape inference, real depth, or calibration.
python -m cv.eval_locate --n 20 [--out cv/.cache/locate_synthetic.json]
"""
import argparse
import json
import time
import numpy as np
from cv.locate import locate
from ai.locate import camera_point


def sphere_scene(centre, radius):
    v, u = np.mgrid[:480, :640]
    rays = np.stack([(u-320)/615, (v-240)/615, np.ones_like(u)], -1)
    # Intersect t*ray with a sphere in optical coordinates. t is z-depth, metres.
    a = np.sum(rays*rays, -1)
    b = np.sum(rays * centre, -1)
    disc = b*b-a*(np.dot(centre, centre)-radius*radius)
    mask = disc >= 0
    z = (b-np.sqrt(np.maximum(disc, 0))) / a
    mask &= z > 0
    depth = np.where(mask, np.rint(z*1000), 0).astype(np.uint16)
    rgb = np.zeros((480,640,3), np.uint8)
    rgb[mask] = [235, 235, 235]
    return rgb, depth, mask


def run(n=20, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    translation = np.array([.1, -.2, .3])
    def calibration(u,v,d):
        return np.array(camera_point(u,v,d))+translation
    for index in range(n):
        centre = np.array([rng.uniform(-.12,.12), rng.uniform(-.08,.08), rng.uniform(.4,.9)])
        rgb, depth, mask = sphere_scene(centre, .0325)
        y,x = np.nonzero(mask)
        box = [int(x.min()), int(y.min()), int(x.max())+1, int(y.max())+1]
        for mode in ("oracle_mask", "oracle_bbox"):
            start = time.perf_counter()
            result = locate(rgb, depth, calibration, label="stress_ball", conf=1.,
                            **({"mask": mask} if mode == "oracle_mask" else {"bbox": box}))
            elapsed = time.perf_counter()-start
            err = np.asarray(result["p_pelvis"])-(centre+translation) if result["depth_ok"] else None
            rows.append({"case":index, "mode":mode, "depth_ok":result["depth_ok"],
                         "error_xyz_mm": None if err is None else (1000*err).tolist(),
                         "error_xy_mm": None if err is None else float(1000*np.linalg.norm(err[:2])),
                         "latency_ms":elapsed*1000})
    summary = {}
    for mode in ("oracle_mask", "oracle_bbox"):
        group = [r for r in rows if r["mode"] == mode]
        errors = [r["error_xy_mm"] for r in group if r["depth_ok"]]
        summary[mode] = {"n":len(group), "accepted":len(errors),
                         "median_xy_mm":float(np.median(errors)) if errors else None,
                         "max_xy_mm":max(errors) if errors else None,
                         "median_latency_ms":float(np.median([r["latency_ms"] for r in group]))}
    return {"protocol":"analytical 65mm sphere; perfect segmentation/box; exact pinhole and translation; depth rounded to mm; no detector", "seed":seed, "summary":summary, "rows":rows}


if __name__ == "__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--out")
    args=ap.parse_args()
    if args.n <= 0:
        ap.error("n must be positive")
    result=run(args.n)
    print(json.dumps(result["summary"], indent=2))
    if args.out:
        from pathlib import Path
        Path(args.out).write_text(json.dumps(result,indent=2)+"\n")
