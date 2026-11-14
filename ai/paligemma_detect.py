"""PaliGemma location-token adapter; verified offline, not on the GPU server.

tools/paligemma_server.py currently decodes with skip_special_tokens=True,
which STRIPS <loc....> tokens. Recommended decode-line change: decode with
skip_special_tokens=False and remove only the tokenizer's pad/eos tokens.
Without that server change, ordinary label-only replies yield no boxes.

Boxes use inclusive pixel indices, like ai.perceive's internal blob bbox.
A bbox alone cannot supply its depth-derived mask and height; this module
does not manufacture candidate blobs or make depth/usability claims.
"""

import base64
import io
import re


# Exactly four numeric tokens per semicolon-delimited object. Reject malformed
# objects as a whole rather than recovering a plausible box from stray tokens.
_OBJECT = re.compile(r"\s*" + r"<loc([0-9]{4})>\s*" * 4 + r"([^<>;]+?)\s*")


def parse_detections(text, width, height):
    """Parse y_min,x_min,y_max,x_max on the supplied 0..1023 grid.

    Return {label, bbox: [u0,v0,u1,v1]} dictionaries. Coordinates are rounded
    to nearest pixel, with grid endpoints mapped to 0 and dimension-1.
    Numeric values above 1023 are clamped; incomplete, malformed, unlabelled
    and reversed boxes are ignored. Whitespace in labels is collapsed.
    Invalid image dimensions or non-string text return an empty list.
    """
    if (not isinstance(text, str) or not isinstance(width, int)
            or not isinstance(height, int) or width <= 0 or height <= 0):
        return []
    boxes = []
    for part in text.split(";"):
        match = _OBJECT.fullmatch(part)
        if match is None:
            continue
        y0, x0, y1, x1 = (min(int(v), 1023) for v in match.groups()[:4])
        label = " ".join(match.group(5).split())
        if not label or x1 < x0 or y1 < y0:
            continue
        boxes.append({"label": label, "bbox": [
            round(x0 * (width - 1) / 1023), round(y0 * (height - 1) / 1023),
            round(x1 * (width - 1) / 1023), round(y1 * (height - 1) / 1023),
        ]})
    return boxes


def detect(client, jpeg_bytes, labels=("egg", "orange ball", "drink can")):
    """Send a task prompt via ai.llm.ChatClient; any failure returns [].

    Image dimensions come from the supplied image, without resizing. The
    caller configures transport timeouts/retries; no client or credentials
    are created here. Results are boxes only, with no confidence estimate.
    """
    try:
        from PIL import Image

        if client is None or isinstance(labels, str):
            return []
        labels = tuple(" ".join(label.split()) for label in labels)
        if not labels or any(not label or ";" in label for label in labels):
            return []
        with Image.open(io.BytesIO(jpeg_bytes)) as image:
            width, height = image.size
            image.verify()
        content = [
            {"type": "text", "text": "detect " + " ; ".join(labels)},
            {"type": "image_url", "image_url": {
                "url": "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")}},
        ]
        response = client.chat([{"role": "user", "content": content}], max_tokens=128)
        return parse_detections(response.get("content"), width, height)
    except Exception:
        return []
