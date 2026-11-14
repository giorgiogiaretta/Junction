"""Local photo benchmark using ai.eval_objects labels and grasp-profile schema.

python -m cv.eval_photos /Users/tommymagelli/Junction/imgs --device cpu --mix
Timing includes file decode, EXIF, preprocessing, inference, postprocessing and
MPS synchronization. Model construction/text embedding and warmup are separate.
"""
import argparse
import collections
import importlib.metadata
import json
import platform
import statistics
import time
from pathlib import Path

from ai.eval_objects import LABELS, expected_label, report
from ai.object_profile import behaviour
from cv.detect import DEFAULT_WEIGHTS, PROMPTS, Detector


def photo_files(folder, include_mix=False):
    root = Path(folder)
    files = sorted(p for p in root.glob("*/*")
                   if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    files += sorted(p for p in root.iterdir()
                    if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    return sorted(p for p in files if expected(p) is not None or
                  (include_mix and p.parent.name.lower() == "mix"))


def expected(path):
    # mix is always unscored, even if a filename starts with a class name.
    return None if Path(path).parent.name.lower() == "mix" else expected_label(str(path))


def evaluate(detector, folder, include_mix=False):
    rows = []
    for path in photo_files(folder, include_mix):
        exp = expected(path)
        detector.synchronize()
        start = time.perf_counter()
        try:
            detections = detector.detect(path)
            detector.synchronize()
            best = max(detections, key=lambda d: d["score"]) if detections else None
            row = {"object": best["label"] if best else "other",
                   "confidence": best["score"] if best else None,
                   "ok": True, "detections": detections}
        except Exception as exc:
            row = {"object": "other", "confidence": None, "ok": False,
                   "detections": [], "error": f"{type(exc).__name__}: {exc}"}
        row.update(latency_s=time.perf_counter() - start,
                   file=str(path.relative_to(folder)), expected=exp)
        row["profile_ok"] = None if exp is None else behaviour(row["object"])["profile"] == behaviour(exp)["profile"]
        rows.append(row)
        print(f"{row['file']}: {row['object']} ({row['latency_s']:.3f}s)", flush=True)
    return rows


def summary(rows):
    labelled = [r for r in rows if r["expected"] is not None]
    folders = {}
    for name in sorted({Path(r["file"]).parent.name for r in labelled}):
        group = [r for r in labelled if Path(r["file"]).parent.name == name]
        correct = sum(r["object"] == r["expected"] for r in group)
        folders[name] = {"correct": correct, "total": len(group), "accuracy": correct / len(group)}
    lat = sorted(r["latency_s"] for r in labelled)
    return {"folders": folders, "correct": sum(r["object"] == r["expected"] for r in labelled),
            "total": len(labelled), "failed": sum(not r["ok"] for r in rows),
            "latency_s": {"median": statistics.median(lat), "mean": statistics.mean(lat),
                          "max": max(lat)} if lat else None,
            "confusion": {e: dict(collections.Counter(r["object"] for r in labelled if r["expected"] == e)) for e in LABELS}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--device", choices=["cpu", "mps"], default="cpu")
    parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--mix", action="store_true")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    files = photo_files(args.folder, args.mix)
    if not files:
        parser.error("no eligible photos found")
    start = time.perf_counter()
    detector = Detector(args.weights, args.device, args.confidence, args.imgsz)
    load_s = time.perf_counter() - start
    start = time.perf_counter()
    for _ in range(3):
        detector.detect(files[0])
        detector.synchronize()
    warmup_s = time.perf_counter() - start
    rows = evaluate(detector, args.folder, args.mix)
    metadata = {"device": args.device, "weights": args.weights.name, "prompts": PROMPTS,
                "confidence": args.confidence, "imgsz": args.imgsz,
                "load_s": load_s, "warmup_3_frames_s": warmup_s,
                "platform": platform.platform(), "python": platform.python_version(),
                "packages": {p: importlib.metadata.version(p) for p in ("ultralytics", "torch", "torchvision", "pillow")},
                "timing": "decode + preprocess + inference + postprocess + synchronization; warmup excluded"}
    result = {"metadata": metadata, "summary": summary(rows), "rows": rows}
    markdown = report(rows, f"YOLO-World-S / {args.device}") + "\n\nPer-folder: " + json.dumps(result["summary"]["folders"])
    print(markdown)
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + "\n")
    if args.out:
        args.out.write_text(markdown + "\n")
    return 1 if result["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
