# Local photo detector

This module only detects single-frame bounding boxes. Giorgio's `vision/` pipeline
tracks objects/hands over time and maps them into the calibrated table frame; it
is separate and is not replaced here. No robot commands or grasp safety decisions.

From the `Junction-cv` worktree (Python 3.12):

```sh
python3.12 -m venv cv/.venv
cv/.venv/bin/pip install -r cv/requirements.txt
export YOLO_CONFIG_DIR="$PWD/cv/.cache/ultralytics"
export MPLCONFIGDIR="$PWD/cv/.cache/matplotlib"
export XDG_CACHE_HOME="$PWD/cv/.cache"
cv/.venv/bin/python -c 'from ultralytics import settings; from pathlib import Path; settings.update({"weights_dir": str(Path("cv/.cache").resolve()), "sync": False})'
cv/.venv/bin/python -m cv.eval_photos /Users/tommymagelli/Junction/imgs --mix --device cpu --json cv/results/cpu.json
cv/.venv/bin/python -m cv.eval_photos /Users/tommymagelli/Junction/imgs --mix --device mps --json cv/results/mps.json
cv/.venv/bin/python -m pytest tests/test_cv_*.py -q
```

First use downloads public detector and text-encoder weights; no keys, no photo
uploads. Weights/cache/environment are ignored, photos are read in place.

```python
from cv.detect import detect, Detector
boxes = detect("/absolute/path/photo.jpg")  # cached CPU default
mps_detector = Detector(device="mps")
boxes = mps_detector.detect("/absolute/path/photo.jpg")
```

Each result is `{label, score, bbox}`; labels are `egg`, `stress_ball`, `can`.
The text prompts are exactly `egg`, `stress ball`, `can`. Boxes are float pixel
`[x1,y1,x2,y2]` in the EXIF-oriented original image, sorted by descending score.
Confidence threshold is 0.25 and model input size 640. Empty list means no retained
detection; inference/load errors raise exceptions. MPS is explicit, never silently
replaced by CPU. The module-level default is lazy and is intended for serial calls.

Evaluation mirrors `ai/eval_objects.py`: highest-scoring detection is the single
predicted object, no box becomes `other`; compare canonical labels and grasp
profiles. Folder truth is weak supervision: all 27 `mix` images are unscored.
The evaluator records all boxes, errors and per-photo timing in JSON, plus per-folder
accuracy/confusion. Failed frames remain in the accuracy denominator and cause a
nonzero exit status. CLI model-loading failures also return nonzero.

Timing excludes model loading/text embeddings and three warmup frames, and includes
image decoding, EXIF handling, preprocessing, inference, postprocessing and MPS
synchronization. This differs from VLM HTTP latency. Original photos are passed to
Ultralytics' own resize/letterbox preprocessing; there is no 1024px JPEG re-encode.
No ground-truth boxes exist, so these results measure image-level classification,
not localization accuracy, mAP, tracking quality, or safe grasp performance.

## Frozen-embedding classifier (separate from detection)

[Embedding results and reproduction](EMBEDDING_RESULTS.md) compare fixed CLIP
zero-shot and leave-one-photo-out linear probing. Install
`cv/requirements-embeddings.txt` in the same environment. YOLO results remain intact.

```python
from cv.embeddings import CLIPClassifier, make_probe, prediction
import numpy as np

encoder = CLIPClassifier(device="cpu")  # or explicit "mps"
result = encoder.classify("/absolute/path/photo.jpg")  # zero-shot, four prompts/classes
# For a probe, fit ONLY your training split, never the held-out photos:
# x_train = np.stack([encoder.encode(p) for p in training_paths])
# probe = make_probe().fit(x_train, training_labels)
# feature = encoder.encode(held_out_path)
# result = prediction(probe.predict_proba(feature[None, :])[0], probe.classes_, .5)
```

Results have `label`, `score`, `scores`, `raw_label`, `rejected`. This is whole-image
classification, without boxes. The probe can learn only labels present in training;
`other` rejection is not validated on real unknowns. No trained probe is presented
as a deployable safety policy. Use `cv.eval_embeddings` for held-out evaluation.

## RGB-D localization and stricter model validation

- [cv.locate contract and geometry checks](LOCATE_RESULTS.md): reuse `ai.locate`
  with validated aligned RGB-D, caller-supplied calibration and explicit mask/box
  or detector. No camera-frame fallback or robot commands; real <=1 cm accuracy
  is not established.
- [Purged-block model comparison](ROBUSTNESS_RESULTS.md): the earlier 100% photo
  LOO score drops under a stronger split. `ViewClassifier(view="full")` is an
  explicit experimental full-frame candidate, not a changed classifier default.

Full-suite validation for this update: 158 passed, 4 skipped, one pre-existing
Pillow deprecation warning (`PYTHONDONTWRITEBYTECODE=1 cv/.venv/bin/python -m pytest tests -q`).
