# cv.locate: validated RGB-D adapter (2026-11-14)

`from cv.locate import locate` exposes the requested head-camera localisation
contract without duplicating `ai.locate`'s geometry. It sends no robot commands.

```python
from cv.locate import locate

result = locate(head_rgb, head_depth,
                pixel_to_pelvis=lambda u,v,d: cal.pixel_to_pelvis("head",u,v,d),
                label="egg", conf=.8, bbox=[u0,v0,u1,v1])
# Optional explicit detector; no detector runs or downloads by default:
# from cv.detect import Detector
# result = locate(head_rgb, head_depth, pixel_to_pelvis=calibrated,
#                 detector=Detector(device="cpu").detect)
```

Inputs must be aligned `HxWx3 uint8 RGB` and `HxW uint16` depth in **millimetres**,
zero invalid. The caller supplies the true optical-pixel-to-pelvis transform;
this adapter cannot establish that calibration is physically correct. It checks
that transform outputs are finite 3-vectors and that the depth ray is nondegenerate.
It never places camera-frame coordinates into `p_pelvis` when calibration is absent.

Boxes are **half-open pixel xyxy** (`0 <= x0 < x1 <= width`), compatible with
`cv.detect`; conversion to `ai.locate`'s inclusive endpoints is internal. Optional
mask is aligned boolean HxW. Caller-supplied box/mask requires a known label
(`egg`, `stress_ball`, `can`, `can_empty`). `can_empty` requires an external label;
a can's appearance does not establish emptiness. Detector-only `can_empty`
outputs are normalized to `can` unless the caller explicitly supplied `can_empty`. Missing caller confidence is
reported as 0, not invented.

Without a box or mask, an explicitly injected detector is required. It receives
a PIL RGB image and returns `[{label, score, bbox}]`; the highest score >= the
fixed `min_confidence` (default .25) is selected. This threshold applies only to
the detector path; explicit box/mask confidence remains caller-supplied. A supplied label filters candidates.
Missing detections, low scores, unsupported classes or detector exceptions return
`object="unknown"`, `depth_ok=False`, and no pose. No colour-only fallback or
whole-image CLIP-to-box shortcut is enabled. The negative YOLO benchmark remains
valid: its optional use here is an interface capability, not an accuracy endorsement.

Output includes the board fields `object`, `conf`, `bbox`, `p_pelvis`,
`axis_pelvis`, `depth_ok`, plus `frame`, `p_surface`, `n_depth`, `why`, and successful
`evidence` (`mask`, `bbox`, `detector_bbox`). Malformed inputs, too little depth,
nonfinite geometry, calibration errors and rejected depth consistency **clear the
pose**. A box alone never produces an object axis. A supplied mask permits the
existing projected PCA axis; its sign is ambiguous and it is not full 3-D shape
reconstruction. `depth_ok` is a consistency check, not proof that a box targets the
right object or that its coordinates are safe for grasping.

The geometry still inherits `ai.locate` assumptions: median central depth,
nominal size/radius to shift visible surface to object centre, optional table-z
snap, and lighting-sensitive colour support inside a box. Wrong size, background
inside a box, occlusion, misalignment or calibration error can produce biased
positions. No measured <=1 cm guarantee on the G1 is claimed.

## Controlled sanity check, not detector evaluation

`cv/eval_locate.py` analytically renders a **65 mm sphere** at 20 seeded optical
positions: x in [-.12,.12] m, y in [-.08,.08] m, z in [.4,.9] m, fx=fy=615,
cx=320, cy=240, 640x480. Depth is rounded to millimetres. The supplied calibration
is exact pinhole projection plus a known translation. Segmentation and bounding
boxes are **oracle ground truth**, the label is supplied, and background depth is
invalid. No neural detector runs. These numbers test plumbing/nominal geometry,
not classification, real sensor noise, camera calibration, or G1 scene accuracy.

| Oracle evidence | Accepted | Median xy error | Max xy error | Median adapter time |
|---|---:|---:|---:|---:|
| Perfect mask | 20/20 | 0.807 mm | 1.521 mm | 9.35 ms |
| Perfect bbox | 20/20 | 0.817 mm | 1.370 mm | 7.90 ms |

Mac M2 Pro, same `cv/.venv` as the CLIP benchmark. Timing covers only the adapter,
not rendering, detection, image decoding or any downstream action. No table snap
used. The existing `g1/sim/perceive.py` and `ai/locate_bench.py` were read but not
modified or run: their G1-specific accuracy is not replaced by this sphere check.
The real `imgs/` photos contain no depth, so they cannot validate 3-D localisation.

```sh
PYTHONDONTWRITEBYTECODE=1 cv/.venv/bin/python -m pytest tests/test_cv_locate.py -q
PYTHONDONTWRITEBYTECODE=1 cv/.venv/bin/python -m cv.eval_locate --n 20 --out cv/.cache/locate_synthetic.json
```

19 unit tests pass: calibrated known geometry, explicit evidence/calibration,
PIL detector boundary, empty/low-confidence detector results, invalid boxes,
mask/depth shape and dtype, empty/mixed depths, broken transforms, and clearing
coordinates on rejection. Tests use synthetic fixtures and injected detectors,
without model downloads, keys, hardware or writes outside the allowed CV files.

Recorded measurements: [locate_synthetic.json](results/locate_synthetic.json).
