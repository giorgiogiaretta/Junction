"""Public API boundary checks; no model weights downloaded."""
import pytest
from cv.detect import Detector


def test_invalid_options_fail_before_loading_weights():
    with pytest.raises(ValueError, match="device"):
        Detector(device="cuda")
    for confidence in (0, -1, 1.1):
        with pytest.raises(ValueError, match="confidence"):
            Detector(confidence=confidence)
    with pytest.raises(ValueError, match="imgsz"):
        Detector(imgsz=0)


def test_bbox_contract_sorting_and_exif_orientation(tmp_path):
    from types import SimpleNamespace
    from PIL import Image

    class Values:
        def __init__(self, values):
            self.values = values

        def cpu(self):
            return self

        def tolist(self):
            return self.values

    class Model:
        def predict(self, image, **kwargs):
            assert image.mode == "RGB"
            assert image.size == (20, 40)  # EXIF rotation of original 40x20
            assert kwargs["device"] == "cpu"
            assert kwargs["conf"] == .25
            boxes = SimpleNamespace(cls=Values([0, 1]), conf=Values([.3, .9]),
                                    xyxy=Values([[1, 2, 3, 4], [5, 6, 10, 20]]))
            return [SimpleNamespace(boxes=boxes)]

    path = tmp_path / "photo.jpg"
    image = Image.new("RGB", (40, 20))
    exif = image.getexif()
    exif[274] = 6
    image.save(path, exif=exif)
    detector = Detector.__new__(Detector)
    detector.model, detector.device = Model(), "cpu"
    detector.confidence, detector.imgsz = .25, 640
    result = detector.detect(path)
    assert result == [{"label": "stress_ball", "score": .9, "bbox": [5., 6., 10., 20.]},
                      {"label": "egg", "score": .3, "bbox": [1., 2., 3., 4.]}]
    with pytest.raises(TypeError):
        detector.detect(object())
