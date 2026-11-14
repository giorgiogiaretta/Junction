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
