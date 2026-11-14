# Frozen CLIP photo classification — 2026-11-14

**Primary result: the linear probe recalls 20/20 eggs in leave-one-photo-out
validation, with zero eggs predicted as stress_ball/can. This is NOT evidence of
safe deployment or generalization.** All photos come from one person, one place,
one day; very similar views can appear on both sides of every split.

The previous negative YOLO-World result is preserved in
[CV_RESULTS.md](../docs/CV_RESULTS.md) and `cv/results/cpu.json`, `mps.json`.

## Fixed protocol

Read `/Users/tommymagelli/Junction/imgs` in place: egg 20, ball 22, can 8, mix 27.
No photos copied, uploaded, or committed. No exact duplicate SHA256 among the 77
files; this does **not** rule out near-duplicate views. Hashes are in the reports.

- Frozen OpenAI CLIP **ViT-B/32**, 512-D image embeddings. Standard CLIP transform:
  EXIF orientation, bicubic resize of shorter edge to 224, 224x224 center crop,
  CLIP normalization. The center crop can remove objects near image edges.
- Zero-shot: three fixed prompts per class (`egg`, `stress_ball`, `can`, `other`),
  normalize each text embedding, average within class, normalize the mean;
  compare normalized image embeddings using CLIP's learned logit scale and softmax.
  Exact prompts are in [embeddings.py](embeddings.py) and both JSON reports.
- Linear probe: raw frozen embeddings, L2 logistic regression, `C=1.0`,
  `class_weight="balanced"`, `lbfgs`, max 2000 iterations. No scaler, PCA, fine-tuning,
  hyperparameter search, prompt search, or threshold selection on these photos.
- **Leave-one-photo-out:** 50 fits, each on 49 labelled photos; predict the one
  held-out photo exactly once. No test photo participates in fitting its probe.
  Frozen embeddings can be extracted before splitting because they learn nothing
  from these images. JSON includes each fold's train indices and their file map.
- Report both raw probe argmax and a predeclared rejection rule: maximum fitted
  class probability <0.5 -> `other`. Scores/threshold are **uncalibrated**. Rejected
  `score` is the maximum known-class score, not an estimated probability of `other`.
- **No labelled `other` photos exist.** Zero-shot has an `other` prompt; the probe
  can learn only the three observed classes and use rejection. Do not relabel mix
  as other: those photos contain the target objects. Mix is excluded from all
  fitting/accuracy and is reported only descriptively. Unknown-class recall and
  false-accept rate are unmeasurable with this dataset.

## Primary metrics (identical CPU and MPS)

| Method | Egg recall | Egg -> stress_ball/can | Egg -> other | All correct |
|---|---:|---:|---:|---:|
| Fixed zero-shot | 13/20 (65%) | 6/20 (30%) | 1/20 | 43/50 (86%) |
| Linear probe, held-out argmax | 20/20 (100%) | 0/20 | 0/20 | 50/50 (100%) |
| Linear probe, held-out + reject <0.5 | 20/20 (100%) | 0/20 | 0/20 | 50/50 (100%) |

`other` is a miss for egg recall, separately counted from the firm-class error;
it is not assumed safe without a downstream policy. Nothing here sends robot
commands. The zero-shot result still fails the desired zero-egg-to-firm criterion.

Zero-shot confusion (rows true, columns predicted):

| True / predicted | egg | stress_ball | can | other |
|---|---:|---:|---:|---:|
| egg | 13 | 6 | 0 | 1 |
| stress_ball | 0 | 22 | 0 | 0 |
| can | 0 | 0 | 8 | 0 |
| other — **no samples** | 0 | 0 | 0 | 0 |

Probe confusion, held-out raw and reject-0.5 both:

| True / predicted | egg | stress_ball | can | other |
|---|---:|---:|---:|---:|
| egg | 20 | 0 | 0 | 0 |
| stress_ball | 0 | 22 | 0 | 0 |
| can | 0 | 0 | 8 | 0 |
| other — **no samples** | 0 | 0 | 0 | 0 |

Zero-shot errors: `egg-003`, `004`, `010`, `012`, `017`, `018` -> stress_ball;
`egg-014` -> other. Ball 22/22 and can 8/8. No probe held-out errors.
Lowest held-out probe top score: CPU 0.677, MPS 0.677; thus the 0.5 rejection
rule rejects **none** of the 50. This does not validate its unknown-object behavior.
Mix zero-shot labels: egg 12, stress_ball 9, can 6 (27 unscored, same on both devices).

## Latency on this Mac

M2 Pro MacBook Pro, 10 CPU cores, 16 GB, macOS 27.0.1 arm64, Python 3.12.3.
Torch 2.15.0, torchvision 0.29.2, CLIP 1.0 (pinned fork commit in requirements),
Pillow 13.0.0, NumPy 2.5.4, scikit-learn 1.9.1; CPU uses default torch thread count.

One sequential pass per method/device; batch one. Wall time includes image open,
EXIF, transform, frozen image encoder, CPU feature transfer and classification.
MPS is explicitly synchronized. Model/text setup and three warmups are excluded;
photo SHA256 hashing is outside the timed region. No competing CV benchmark ran.
Probe timing uses a full-data fit **only for timing**, re-encodes every image and
never supplies the held-out accuracy numbers. Probe fitting is not per-frame work.

| Device / method | Median | Mean | Max |
|---|---:|---:|---:|
| CPU zero-shot | 57.6 ms | 58.1 ms | 61.6 ms |
| CPU probe | 57.1 ms | 57.6 ms | 63.9 ms |
| MPS zero-shot | 46.1 ms | 46.2 ms | 50.5 ms |
| MPS probe | 45.0 ms | 45.5 ms | 57.3 ms |

Cached model/text setup: CPU 5.10 s, MPS 6.67 s. Three warmup frames: CPU 0.194 s,
MPS 0.584 s. Fifty CPU logistic fits/predictions: 8.36 s in the CPU run and 1.23 s
in the MPS run (the probe itself always runs on CPU; these are separate processes,
not a claimed GPU training speedup). Short active-laptop measurements, not a
sustained-load guarantee. MPS was unavailable inside the sandbox; the successful
MPS run used host Metal access, with no CPU fallback. CPU ran with networking blocked.

## Overfitting and what is still unproven

The probe also scores 50/50 on its own training data; this resubstitution number
is **not validation**. Even with no observed train/LOO gap, 512-D embeddings with
only 49 training images per fold can exploit background, hand, lighting, object
instance and near-identical poses. Photo-level CV measures interpolation within
this session. It cannot measure transfer to a new operator, location, day, egg,
ball/can type, head camera, or a true unknown object. Counting these correlated
photos as independent trials would give misleading safety confidence bounds.

Next evidence needed: new sessions split by person/day/location/object instance,
kept untouched until final evaluation, plus real labelled negatives. Select any
rejection/safety threshold only on a separate training/calibration set. Neither
0/20 observed firm errors nor 100% photo-CV egg recall proves zero deployment risk.

## Reproduce and inspect

```sh
cv/.venv/bin/pip install -r cv/requirements-embeddings.txt
PYTHONDONTWRITEBYTECODE=1 cv/.venv/bin/python -m cv.eval_embeddings /Users/tommymagelli/Junction/imgs --device cpu --out cv/results/clip_cpu.json
PYTHONDONTWRITEBYTECODE=1 cv/.venv/bin/python -m cv.eval_embeddings /Users/tommymagelli/Junction/imgs --device mps --out cv/results/clip_mps.json
cv/.venv/bin/python -m pytest tests/test_cv_embeddings.py -q
```

Full outputs: [CPU](results/clip_cpu.json), [MPS](results/clip_mps.json). Separate
keys name zero-shot, held-out raw/rejected, and resubstitution/timing-only results
so training performance cannot be mistaken for held-out performance. No inference
errors occurred; errors abort this benchmark rather than silently dropping photos.

Uses the already-cached `cv/.cache/clip/ViT-B-32.pt`: **353,976,522 bytes (337.6 MiB)**,
SHA256 `40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af`,
[public weight source](https://openaipublic.azureedge.net/clip/models/40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af/ViT-B-32.pt).
No additional model weights downloaded or committed. Method reference:
[OpenAI CLIP zero-shot and linear-probe examples](https://github.com/openai/CLIP).

Validation: `PYTHONDONTWRITEBYTECODE=1 cv/.venv/bin/python -m pytest tests -q`
-> **100 passed**, one existing Pillow deprecation warning. Ten CV tests total,
five new embedding tests: train/test separation, complete held-out coverage,
invalid split rejection, egg-to-firm versus egg-to-other accounting, and synthetic
out-of-sample separability. Full-suite local-socket tests run outside the restricted
sandbox; no live AI/hardware calls. CLIP emits a torch.jit.load deprecation warning;
no convergence or inference warnings/errors occurred in the successful benchmarks.
