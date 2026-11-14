# Local open-vocabulary detector: negative baseline (2026-11-14)

**YOLO-World-S v2: 12/50 correct (24%) on both CPU and MPS. Not a suitable
replacement for the object picker in this configuration: 14/20 eggs are called
`stress_ball`, the dangerous error direction.** No robot integration was changed.

## Protocol and measured results

Read the original `/Users/tommymagelli/Junction/imgs` in place: ball 22, can 8,
egg 20, mix 27. No photos copied or committed. One complete pass per device,
three warmup frames before each pass. Fixed prompts `egg`, `stress ball`, `can`;
confidence 0.25, Ultralytics input size 640, pretrained `yolov8s-worldv2.pt`.
No training, prompt sweep, confidence tuning, or hand crop on this evaluation set.

Same scoring schema as `ai/eval_objects.py`: canonical labels, folder/name truth,
single highest-confidence box as the main object, no retained box -> `other`,
confusion matrix and grasp-profile agreement through `ai.object_profile.behaviour`.
All 27 mix photos are unscored. Images are EXIF-oriented and passed to Ultralytics'
resize/letterbox; unlike the VLM evaluator, there is no 1024px JPEG re-encode.

| Folder | CPU correct | MPS correct | Accuracy |
|---|---:|---:|---:|
| ball | 9/22 | 9/22 | 40.9% |
| can | 3/8 | 3/8 | 37.5% |
| egg | 0/20 | 0/20 | 0.0% |
| Total scored | 12/50 | 12/50 | 24.0% |

Grasp-profile agreement: **12/50 (24%)**. Failed frames: **0/77** for each device;
empty detections are valid outputs, not execution failures. Both devices produced
the same main labels on all 77 images. Mix main labels: stress_ball 7, can 5,
egg 5, other 10 (not accuracy).

Confusion matrix, identical on CPU and MPS:

| Expected / predicted | egg | stress_ball | can | other |
|---|---:|---:|---:|---:|
| egg | 0 | 14 | 0 | 6 |
| stress_ball | 0 | 9 | 0 | 13 |
| can | 0 | 0 | 3 | 5 |
| other (no labelled samples) | 0 | 0 | 0 | 0 |

Apple MacBook Pro Mac14,9, **M2 Pro, 10 CPU cores, 16 GB**, macOS 27.0.1 arm64,
Python 3.12.3, Ultralytics 8.4.212, torch 2.15.0, torchvision 0.29.2, Pillow 13.0.0.
Wall time per scored photo includes disk decode, EXIF handling, preprocessing,
inference, output conversion and explicit MPS synchronization. It excludes model
loading, text embeddings, and three warmup calls. Batch size is one.

| Device | Median | Mean | Max | Model setup | Three warmups total |
|---|---:|---:|---:|---:|---:|
| CPU | 66.1 ms | 67.1 ms | 86.8 ms | 27.18 s* | 0.252 s |
| MPS | 37.8 ms | 38.0 ms | 50.8 ms | 4.48 s | 4.072 s |

*First CPU setup includes downloads; MPS setup uses cached weights and still
encodes text on CPU before inference moves to MPS. These are short, sequential
runs on an active laptop, not isolated throughput/load tests. Dependency installation
was finishing during the CPU experiment. No CPU fallback flag was enabled for MPS.
VLM latency in the earlier Nemotron report was not measured comparably, so no
cross-model speedup is claimed. Its reported accuracy was 48/50 (96%).

## Where it fails

- Egg -> stress_ball: `egg-002,003,004,006,007,008,009,010,011,012,013,014,019,020`.
  Scores span the values in the per-photo JSON; they are not calibrated probabilities.
  Visual spot-check: `egg-012` is a white, stamped egg in the fingertips. The CPU box
  `[908,1421,1160,1686]` encloses it, yet the predicted label is stress_ball (0.649).
  Thus at least this error is semantic, not a missing object box.
- Egg -> other: `egg-001,005,015,016,017,018` (no box survives 0.25).
- Ball -> other: `ball-002,004,005,006,007,010,013,014,017,019,020,021,022`.
- Can -> other: `can-002,003,004,005,007`. Visual spot-check: in `can-002` a hand
  partly occludes the can; no retained box. Occlusion is a plausible contributor,
  not an experimentally isolated cause.

The full filenames, scores, boxes, per-frame latency, error accounting, and
profile agreement are in [CPU JSON](../cv/results/cpu.json) and
[MPS JSON](../cv/results/mps.json); generated reports: [CPU](../cv/results/cpu.md),
[MPS](../cv/results/mps.md). No ground-truth boxes exist, so no mAP/IoU or localization
accuracy is asserted. Fifty photos from one person/place/day do not demonstrate
generalization; there are no labelled negative/other examples. This experiment
cannot establish safe grasp selection, even when a detection has a high score.

## Reproduce and downloads

Setup and commands: [cv/README.md](../cv/README.md). Interface:
`from cv.detect import detect; detect(image)` -> list of `{label, score, bbox}`;
`Detector(device="mps")` selects MPS explicitly. API uses original oriented-image
pixel xyxy boxes; no tracking, camera calibration, metric coordinates or UDP output.
Giorgio's `vision/README.md` was read from `origin/vision-pipeline` because that file
is absent from this checkout/main; its temporal table/hand tracking is not duplicated.

Public weights are stored only in ignored `cv/.cache/`:

| File | Exact bytes | Approx. MiB | Source |
|---|---:|---:|---|
| yolov8s-worldv2.pt | 25,923,032 | 24.7 | [Ultralytics release v8.4.0](https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8s-worldv2.pt) |
| clip/ViT-B-32.pt | 353,976,522 | 337.6 | [OpenAI CLIP weight](https://openaipublic.azureedge.net/clip/models/40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af/ViT-B-32.pt) |

SHA256 respectively:
`9b2c17ab6124a913e9b3a5c170617920d91b0f01111a8479da69f00e2cf27792`,
`40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af`.
CLIP code is pinned to Ultralytics/CLIP commit
`7ffa84b3bfa40c42ecc1c77147a855e69cb2dd40` in `cv/requirements.txt`.
Model usage follows the [official YOLO-World documentation](https://docs.ultralytics.com/models/yolo-world/).
First setup needs internet for packages/weights; photo inference is local, no keys
or remote AI calls. Weights, environment and photo data are not committed.

Initial installation failed because the disk was full; after the user freed space,
installation and both full evaluations succeeded. No user files were deleted.

Validation: `PYTHONDONTWRITEBYTECODE=1 cv/.venv/bin/python -m pytest tests -q`
-> **94 passed**, one pre-existing Pillow deprecation warning. Five CV tests cover
scoring, mix exclusion, empty/failed detections, parameter validation, canonical
labels, box ordering and EXIF coordinates. Full-suite extras installed only into
the local environment: mujoco, pyserial, pymodbus, google-genai. Local socket tests
need execution outside the restricted network sandbox; no live AI/hardware calls.
A cached `detect(egg-012.jpg)` smoke test also passed with network access blocked.
