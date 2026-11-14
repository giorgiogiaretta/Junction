"""Explicit experimental CLIP views; original CLIPClassifier stays unchanged.

center: original CLIP center crop; full: full frame padded to square;
hand: bottom 60% of the image, a dataset-specific head/hand framing hypothesis.
None is object localization. Never infer a bbox or metric pose from these crops.
"""
from pathlib import Path
from PIL import Image, ImageOps
from cv.embeddings import CLIPClassifier

VIEWS = ("center", "full", "hand")


def prepare_view(image, view):
    if view not in VIEWS:
        raise ValueError(f"view must be one of {VIEWS}")
    if isinstance(image, (str, Path)):
        with Image.open(image) as source:
            rgb = ImageOps.exif_transpose(source).convert("RGB")
    elif isinstance(image, Image.Image):
        rgb = ImageOps.exif_transpose(image).convert("RGB")
    else:
        raise TypeError("image must be a path or PIL image")
    if view == "hand":
        rgb = rgb.crop((0, int(.4 * rgb.height), rgb.width, rgb.height))
    if view in ("full", "hand"):
        rgb = ImageOps.pad(rgb, (224, 224), method=Image.Resampling.BICUBIC,
                           color=(123, 117, 104))
    return rgb


class ViewClassifier(CLIPClassifier):
    def __init__(self, device="cpu", view="center"):
        if view not in VIEWS:
            raise ValueError(f"view must be one of {VIEWS}")
        super().__init__(device)
        self.view = view

    def encode(self, image):
        return super().encode(prepare_view(image, self.view))
