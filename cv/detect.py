"""YOLO-World single-frame detector. No tracking, network API, or grasp control.

Input: file path or PIL image. Output: score-sorted dictionaries with canonical
label (egg/stress_ball/can), score and [x1,y1,x2,y2] pixel bbox in the EXIF-oriented
original image. Empty detections return []; loading/inference errors propagate.
First construction downloads public weights if absent; subsequent calls are local.
"""
from functools import lru_cache
from pathlib import Path

PROMPTS = ("egg", "stress ball", "can")
LABELS = ("egg", "stress_ball", "can")
DEFAULT_WEIGHTS = Path(__file__).parent / ".cache" / "yolov8s-worldv2.pt"


class Detector:
    def __init__(self, weights=DEFAULT_WEIGHTS, device="cpu", confidence=0.25, imgsz=640):
        if device not in ("cpu", "mps"):
            raise ValueError("device must be cpu or mps")
        if not 0 < confidence <= 1 or imgsz <= 0:
            raise ValueError("confidence must be in (0,1]; imgsz must be positive")
        import torch
        from ultralytics import YOLOWorld
        if device == "mps" and not torch.backends.mps.is_available():
            raise RuntimeError("MPS requested but unavailable; no silent CPU fallback")
        self.device, self.confidence, self.imgsz = device, confidence, imgsz
        self.model = YOLOWorld(str(weights))
        self.model.set_classes(list(PROMPTS))

    def synchronize(self):
        if self.device == "mps":
            import torch
            torch.mps.synchronize()

    def detect(self, image):
        from PIL import Image, ImageOps
        if isinstance(image, (str, Path)):
            with Image.open(image) as source:
                rgb = ImageOps.exif_transpose(source).convert("RGB")
        elif isinstance(image, Image.Image):
            rgb = ImageOps.exif_transpose(image).convert("RGB")
        else:
            raise TypeError("image must be a path or PIL.Image.Image")
        result = self.model.predict(rgb, device=self.device, conf=self.confidence,
                                    imgsz=self.imgsz, verbose=False, save=False)[0]
        boxes = result.boxes
        detections = [{"label": LABELS[int(cls)], "score": float(score),
                       "bbox": [float(v) for v in bbox]}
                      for cls, score, bbox in zip(boxes.cls.cpu().tolist(),
                                                  boxes.conf.cpu().tolist(),
                                                  boxes.xyxy.cpu().tolist())]
        return sorted(detections, key=lambda row: row["score"], reverse=True)


@lru_cache(maxsize=1)
def _default_detector():
    return Detector()


def detect(image):
    """CPU default, cached model, confidence >= .25; see Detector for MPS/config."""
    return _default_detector().detect(image)
