"""Exploratory view comparison + purged contiguous-photo blocked CV.

This is NOT an independent test set: the same session has already been inspected.
Do not select a view and relabel its score as unbiased validation performance.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import numpy as np

from cv.embeddings import cross_validate
from cv.eval_embeddings import metrics, latency
from cv.eval_photos import photo_files, expected
from cv.model_views import ViewClassifier, VIEWS


def purged_photo_splits(labels, folds=5, gap=2):
    """Per-class consecutive filename blocks; remove two adjacent images per side.

Order is a proxy, not known capture chronology or independent session identity.
Each photo is tested once, and none of its +/- gap class-order neighbours train.
"""
    labels = np.asarray(labels)
    if folds < 2 or gap < 0:
        raise ValueError("folds >=2 and gap >=0 required")
    by_class = {label: np.flatnonzero(labels == label) for label in np.unique(labels)}
    if any(len(indices) < folds for indices in by_class.values()):
        raise ValueError("each class needs at least folds photos")
    chunks = {label: np.array_split(np.arange(len(indices)), folds)
              for label, indices in by_class.items()}
    for fold in range(folds):
        test, excluded = [], set()
        for label, indices in by_class.items():
            positions = chunks[label][fold]
            test.extend(indices[positions].tolist())
            lo, hi = max(0, positions[0] - gap), min(len(indices), positions[-1] + gap + 1)
            excluded.update(indices[lo:hi].tolist())
        train = sorted(set(range(len(labels))) - excluded)
        if len(set(labels[train])) != len(by_class):
            raise ValueError("purge leaves a training class empty")
        yield np.asarray(train), np.asarray(sorted(test))


def run(folder, device):
    files = photo_files(folder, include_mix=False)
    labels = [expected(path) for path in files]
    if not files or any(label is None for label in labels):
        raise ValueError("labelled photos required")
    splits = list(purged_photo_splits(labels))
    encoder = ViewClassifier(device, "center")
    results = {}
    for view in VIEWS:
        encoder.view = view
        for _ in range(3):
            encoder.classify(files[0])
        features, rows = [], []
        for path, label in zip(files, labels):
            encoder.synchronize()
            start = time.perf_counter()
            feature = encoder.encode(path)
            result = encoder.zero_shot(feature)
            elapsed = time.perf_counter() - start
            features.append(feature)
            rows.append(dict(result, expected=label, file=path.relative_to(folder).as_posix(), latency_s=elapsed))
        oof = cross_validate(features, labels, splits)
        raw, rejected = [], []
        for row in oof:
            common = {"file": files[row['index']].relative_to(folder).as_posix(),
                      "expected": labels[row['index']], "fold": row['fold']}
            raw.append(dict(row['raw'], **common))
            rejected.append(dict(row['reject_05'], **common))
        results[view] = {"zero_shot": {"metrics": metrics(rows), "rows": rows, "latency": latency([r['latency_s'] for r in rows])},
                         "purged_block_probe": {"metrics": metrics(raw), "rows": raw},
                         "purged_block_reject_05": {"metrics": metrics(rejected), "rows": rejected}}
        print(view, {name: result['metrics'] for name, result in results[view].items()}, flush=True)
    return {"metadata": {"date_utc": datetime.now(timezone.utc).isoformat(), "device": device,
                         "protocol": "exploratory 3 fixed views, 5 per-class contiguous filename blocks, purge +/-2 adjacent same-class photos",
                         "views": {"center": "original CLIP", "full": "full RGB frame padded to 224 square",
                                   "hand": "bottom 60% RGB padded to 224 square; dataset-specific hypothesis"},
                         "model": "same frozen ViT-B/32, fixed prompts and C=1 balanced logistic probe as #99",
                         "independent_test": False, "other_samples": 0},
            "photos": [{"file": p.relative_to(folder).as_posix(), "label": y, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                       for p, y in zip(files, labels)],
            "folds": [{"train": a.tolist(), "test": b.tolist()} for a,b in splits],
            "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.write_text(json.dumps(run(args.folder, args.device), indent=2) + "\n")
