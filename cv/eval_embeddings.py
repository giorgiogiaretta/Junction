"""Compare fixed CLIP zero-shot and per-photo leave-one-out linear probing.

python -m cv.eval_embeddings /Users/tommymagelli/Junction/imgs --device cpu --out cv/results/clip_cpu.json
Only supervised photos enter probe fitting or cross-validation; mix is unscored.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import statistics
import time

import numpy as np
from cv.embeddings import LABELS, PROMPTS, CACHE, CLIPClassifier, cross_validate, make_probe, prediction
from cv.eval_photos import expected, photo_files


def metrics(rows):
    scored = [r for r in rows if r["expected"] is not None]
    confusion = {e: {p: 0 for p in LABELS} for e in LABELS}
    for row in scored:
        confusion[row["expected"]][row["label"]] += 1
    eggs = sum(confusion["egg"].values())
    correct = sum(confusion[label][label] for label in LABELS)
    return {"n": len(scored), "correct": correct,
            "accuracy": correct / len(scored) if scored else None,
            "egg_recall": confusion["egg"]["egg"] / eggs if eggs else None,
            "egg_correct": confusion["egg"]["egg"], "egg_total": eggs,
            "egg_to_firm": confusion["egg"]["can"] + confusion["egg"]["stress_ball"],
            "egg_to_other": confusion["egg"]["other"],
            "other_recall": (confusion["other"]["other"] / sum(confusion["other"].values())
                             if sum(confusion["other"].values()) else None),
            "confusion": confusion,
            "wrong": [{"file": r["file"], "expected": r["expected"], "label": r["label"]}
                      for r in scored if r["expected"] != r["label"]]}


def latency(values):
    return {"median_ms": 1000 * statistics.median(values),
            "mean_ms": 1000 * statistics.mean(values), "max_ms": 1000 * max(values)}


def evaluate(folder, device):
    files = photo_files(folder, include_mix=True)
    if not files:
        raise ValueError("no eligible photos")
    load_start = time.perf_counter()
    encoder = CLIPClassifier(device)
    load_s = time.perf_counter() - load_start
    warm_start = time.perf_counter()
    for _ in range(3):
        encoder.classify(files[0])
    warmup_s = time.perf_counter() - warm_start
    features, zs_rows = [], []
    for path in files:
        encoder.synchronize()
        start = time.perf_counter()
        feature = encoder.encode(path)
        encoded = time.perf_counter()
        result = encoder.zero_shot(feature)
        elapsed = time.perf_counter() - start
        features.append(feature)
        zs_rows.append(dict(result, file=str(path.relative_to(folder)), expected=expected(path),
                            encode_s=encoded-start, latency_s=elapsed,
                            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        print(f"{path.name}: {result['label']} {elapsed*1000:.1f} ms", flush=True)
    indices = [i for i, row in enumerate(zs_rows) if row["expected"] is not None]
    x = np.asarray(features)[indices]
    y = np.asarray([zs_rows[i]["expected"] for i in indices])
    start = time.perf_counter()
    oof = cross_validate(x, y)
    cv_s = time.perf_counter()-start
    raw_rows, reject_rows = [], []
    for fold in oof:
        source = zs_rows[indices[fold["index"]]]
        common = {"file": source["file"], "expected": source["expected"],
                  "fold": fold["fold"], "train_indices": fold["train_indices"]}
        raw_rows.append(dict(fold["raw"], **common))
        reject_rows.append(dict(fold["reject_05"], **common))
    # Final full-data probe is for timing/mix diagnostics only, NEVER OOF scoring.
    probe = make_probe().fit(x, y)
    train_rows = [dict(prediction(p, probe.classes_), expected=str(label), file=raw_rows[i]["file"])
                  for i, (p, label) in enumerate(zip(probe.predict_proba(x), y))]
    probe_rows = []
    for path, source in zip(files, zs_rows):
        encoder.synchronize()
        start = time.perf_counter()
        feature = encoder.encode(path)
        probabilities = probe.predict_proba(feature[None, :])[0]
        result = prediction(probabilities, probe.classes_, .5)
        elapsed = time.perf_counter() - start
        probe_rows.append(dict(result, file=source["file"], expected=source["expected"], latency_s=elapsed))
    packages = {p: importlib.metadata.version(p) for p in ("torch", "torchvision", "clip", "pillow", "numpy", "scikit-learn")}
    return {
        "metadata": {"date_utc": datetime.now(timezone.utc).isoformat(), "device": device,
                     "model": "CLIP ViT-B/32", "weights_bytes": (CACHE / "ViT-B-32.pt").stat().st_size,
                     "platform": platform.platform(), "python": platform.python_version(), "packages": packages,
                     "prompts": PROMPTS, "preprocess": "EXIF transpose; official CLIP bicubic resize + 224 center crop + normalization",
                     "probe": "raw frozen 512-D embeddings; LogisticRegression C=1, balanced, lbfgs, max_iter=2000",
                     "cv": "leave-one-photo-out; no hyperparameter selection; no mix in training",
                     "rejection": "max probe probability < 0.5 -> other, fixed uncalibrated threshold",
                     "load_and_text_s": load_s, "warmup_3_s": warmup_s, "cv_fit_predict_s": cv_s},
        "zero_shot": {"metrics": metrics(zs_rows), "rows": zs_rows,
                      "latency": latency([r["latency_s"] for r in zs_rows if r["expected"] is not None])},
        "probe_loo_raw": {"metrics": metrics(raw_rows), "rows": raw_rows},
        "probe_loo_reject_05": {"metrics": metrics(reject_rows), "rows": reject_rows},
        "probe_resubstitution_NOT_validation": metrics(train_rows),
        "probe_full_fit_timing_NOT_validation": {
            "latency": latency([r["latency_s"] for r in probe_rows if r["expected"] is not None]),
            "mix_rows": [r for r in probe_rows if r["expected"] is None]},
        "cv_index_to_file": [r["file"] for r in raw_rows],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.folder, args.device)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    for method in ("zero_shot", "probe_loo_raw", "probe_loo_reject_05"):
        print(method, json.dumps(result[method]["metrics"]))


if __name__ == "__main__":
    main()
