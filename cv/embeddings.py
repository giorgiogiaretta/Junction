"""Frozen local CLIP embeddings, fixed zero-shot prompts and linear probe.

No model/threshold selection on the evaluation photos. Scores are uncalibrated.
The probe learns only labels present in training; `other` can also be a rejection,
which is not evidence of unknown-object recognition. No control/robot integration.
"""
from pathlib import Path
import numpy as np

LABELS = ("egg", "stress_ball", "can", "other")
# Fixed before the first embedding benchmark, not selected from photo results.
PROMPTS = {
    "egg": ("a photo of a raw egg.", "a photo of a white chicken egg.",
            "a photo of a person holding an egg."),
    "stress_ball": ("a photo of a stress ball.", "a photo of a soft squeeze ball.",
                    "a photo of a person holding a stress ball."),
    "can": ("a photo of a beverage can.", "a photo of a soda can.",
            "a photo of a person holding a can."),
    "other": ("a photo of another object.", "a photo of an empty hand.",
              "a photo of a background with no object to grasp."),
}
CACHE = Path(__file__).parent / ".cache" / "clip"


def normalize(features):
    values = np.asarray(features, dtype=np.float64)
    return values / np.maximum(np.linalg.norm(values, axis=-1, keepdims=True), 1e-12)


def prediction(probabilities, classes=LABELS, reject_below=0.0):
    """Return top class; optional fixed rejection, never a calibrated safety rule."""
    if not 0 <= reject_below <= 1:
        raise ValueError("reject_below must be in [0, 1]")
    scores = {label: 0.0 for label in LABELS}
    scores.update({str(label): float(score) for label, score in zip(classes, probabilities)})
    label = max(scores, key=scores.get)
    score = scores[label]
    rejected = score < reject_below
    return {"label": "other" if rejected else label, "score": score,
            "scores": scores, "rejected": rejected, "raw_label": label}


class CLIPClassifier:
    """ViT-B/32. Input path or PIL image; no downloads after weights are cached."""
    def __init__(self, device="cpu"):
        if device not in ("cpu", "mps"):
            raise ValueError("device must be cpu or mps")
        import torch
        import clip
        if device == "mps" and not torch.backends.mps.is_available():
            raise RuntimeError("MPS unavailable; no silent fallback")
        self.device = device
        self.model, self.preprocess = clip.load("ViT-B/32", device=device,
                                               download_root=str(CACHE), jit=False)
        self.model.eval()
        with torch.inference_mode():
            text = self.model.encode_text(clip.tokenize(
                [prompt for label in LABELS for prompt in PROMPTS[label]]).to(device)).float()
            text /= text.norm(dim=-1, keepdim=True)
            prototypes = text.reshape(len(LABELS), 3, -1).mean(dim=1)
            prototypes /= prototypes.norm(dim=-1, keepdim=True)
            self.text_features = prototypes.cpu().numpy()
            self.logit_scale = float(self.model.logit_scale.exp().cpu())
        self.synchronize()

    def synchronize(self):
        if self.device == "mps":
            import torch
            torch.mps.synchronize()

    def encode(self, image):
        """Raw 512-D frozen embedding; standard CLIP 224px center-crop transform."""
        import torch
        from PIL import Image, ImageOps
        if isinstance(image, (str, Path)):
            with Image.open(image) as source:
                rgb = ImageOps.exif_transpose(source).convert("RGB")
        elif isinstance(image, Image.Image):
            rgb = ImageOps.exif_transpose(image).convert("RGB")
        else:
            raise TypeError("image must be a path or PIL image")
        tensor = self.preprocess(rgb).unsqueeze(0).to(self.device)
        with torch.inference_mode():
            feature = self.model.encode_image(tensor).float().cpu().numpy()[0]
        self.synchronize()
        return feature

    def zero_shot(self, feature):
        logits = self.logit_scale * (normalize(feature) @ self.text_features.T)
        probabilities = np.exp(logits - logits.max())
        return prediction(probabilities / probabilities.sum())

    def classify(self, image):
        return self.zero_shot(self.encode(image))


def make_probe():
    """Fixed L2 logistic regression on raw embeddings; no global scaling/PCA."""
    from sklearn.linear_model import LogisticRegression
    return LogisticRegression(C=1.0, class_weight="balanced", solver="lbfgs",
                              max_iter=2000, random_state=0)


def cross_validate(features, labels, splits=None):
    """Exactly one held-out prediction per photo; fit only that fold's training set."""
    from sklearn.model_selection import LeaveOneOut
    features, labels = np.asarray(features), np.asarray(labels)
    if len(features) != len(labels) or len(labels) < 2:
        raise ValueError("features and labels must have equal length >= 2")
    splits = LeaveOneOut().split(features) if splits is None else splits
    rows, seen = [], set()
    for fold, (train, test) in enumerate(splits):
        train, test = np.asarray(train, dtype=int), np.asarray(test, dtype=int)
        if set(train) & set(test):
            raise ValueError("training/test overlap")
        if seen & set(test):
            raise ValueError("photo appears in multiple test folds")
        if not len(train) or not len(test) or np.any(train < 0) or np.any(test < 0) or max(train.max(), test.max()) >= len(labels):
            raise ValueError("invalid split indices")
        if len(set(labels[train])) < 2:
            raise ValueError("training fold needs at least two classes")
        probe = make_probe()
        probe.fit(features[train], labels[train])
        for index, probabilities in zip(test, probe.predict_proba(features[test])):
            rows.append({"index": int(index), "fold": fold,
                         "train_indices": train.tolist(),
                         "raw": prediction(probabilities, probe.classes_),
                         "reject_05": prediction(probabilities, probe.classes_, .5)})
        seen.update(test)
    if seen != set(range(len(labels))):
        raise ValueError("every photo must be held out exactly once")
    return sorted(rows, key=lambda row: row["index"])
