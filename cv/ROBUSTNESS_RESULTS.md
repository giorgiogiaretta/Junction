# Model improvement and a stricter photo split (2026-11-14)

**The earlier 50/50 leave-one-photo-out score was too optimistic for the intended
use.** With contiguous photo blocks held out and nearby photos removed from
training, the original CLIP probe scores **43/50, egg recall 18/20**. A full-frame
padded view improves this experiment to **47/50, egg recall 19/20**. It still makes
one egg-to-firm-label error and is not a validated safety policy.

## What changed

`cv.model_views.ViewClassifier` exposes three explicit input views using the same
frozen ViT-B/32, text prompts and logistic probe from #99:

- `center`: original CLIP center crop.
- `full`: preserve the full image, fit/pad to 224x224 with approximate CLIP-mean
  RGB padding (123,117,104). No field of view is discarded.
- `hand`: keep the bottom 60% then fit/pad to 224x224. This is a hypothesis about
  these head/hand photos, not hand detection or a universally correct crop.

The original detector, classifier defaults and earlier results are unchanged.
This comparison was designed after seeing the earlier results and uses the same
photos: it is **exploratory development**, not an untouched test set. All three
variants are reported; no hyperparameter/prompt/threshold sweep was performed.
Choosing the best variant here adds selection optimism. Test it on new sessions
before adopting it as a default. No additional model weights were downloaded.

## Split and leakage checks

The original 50 labelled photos are read directly from
`/Users/tommymagelli/Junction/imgs`. For each class, sorted filenames are divided
into five consecutive blocks. In each fold one block per class is held out;
**two adjacent same-class photos on either side are also excluded from training**.
Each photo is predicted exactly once by a probe that has not trained on it or
those neighbours. Training/test counts: 33/11, 27/11, 28/10, 30/9, 35/9.

Filename order is only a proxy for nearby captures, not verified chronology or
true session grouping. Background, operator and object instance remain shared
across every fold. This stronger split can expose fragility but still cannot
measure independent-session generalization. Mix is not used and there are zero
labelled `other` examples. Rejection below 0.5 remains fixed and uncalibrated.

## Results on this Mac (CPU)

| View | Zero-shot correct | Zero-shot egg recall | Block probe correct | Block probe egg recall | Egg -> stress_ball/can |
|---|---:|---:|---:|---:|---:|
| Original center | 43/50 | 13/20 | 43/50 | 18/20 | 2/20 |
| Full-frame padded | 44/50 | 14/20 | 47/50 | 19/20 | 1/20 |
| Bottom-60% padded | 45/50 | 15/20 | 47/50 | 18/20 | 2/20 |

Adding fixed probe rejection (<0.5): center remains 43/50, egg18/20; full becomes
42/50, egg17/20 (one egg firm-label error, two eggs rejected); hand becomes 45/50,
egg18/20 (one egg firm-label error, one egg rejected). A rejection is a miss for
egg recall. It is not assumed to imply safe downstream behavior.

`egg_to_firm` is a label-error count, not a robot-force measurement; ai/robot
policies can further soften decisions. Nothing in this experiment changes them.

Zero-shot end-to-end median latency: center 62.9 ms, full 61.2 ms, hand 52.6 ms.
Means: 67.1, 62.0, 54.5 ms; maxima: 215.2, 78.8, 91.4 ms. These are single-pass
measurements on an active M2 Pro, not isolated timing guarantees. All include
file decode, view preparation, CLIP encoding, feature transfer and text scoring;
three warmups per view, model/text setup excluded. Block-probe fitting is offline;
no new probe end-to-end latency claim is made by this script. Previous probe
latencies are documented separately in `EMBEDDING_RESULTS.md`.

## Reproduce and use explicitly

```sh
PYTHONDONTWRITEBYTECODE=1 cv/.venv/bin/python -m cv.eval_robustness /Users/tommymagelli/Junction/imgs --device cpu --out cv/results/robustness_cpu.json
cv/.venv/bin/python -m pytest tests/test_cv_robustness.py -q
```

```python
from cv.model_views import ViewClassifier
candidate = ViewClassifier(device="cpu", view="full")
result = candidate.classify("/absolute/path/photo.jpg")  # zero-shot
features = candidate.encode("/absolute/path/photo.jpg") # for a separately fitted probe
```

[Complete results](results/robustness_cpu.json) contain confusion matrices, every
prediction/score, errors, file hashes and split membership for all nine combinations
(three views x zero-shot/raw probe/rejecting probe). The same cached CLIP weights
and pinned embedding requirements apply; no photos or embeddings are committed.
Three new tests verify disjoint/complete folds, neighbour exclusion, and explicit
crop behavior. The needed next data remains a new person/place/day and real
unknown-object negatives, not more random splits of these 50 photos.
