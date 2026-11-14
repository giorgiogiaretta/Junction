"""Colour-rule baseline (orange = stress ball, white blob = egg, gold elongated blob = can) on imgs/ with scipy blobs. UNTUNED first attempt: 38/50 (76%).
Not a replacement for the VLM: white sleeves/lights, orange background items and small objects break it. python -m ai.color_baseline [folder]"""
import sys
import numpy as np, glob, os, collections
from PIL import Image
from scipy import ndimage as ndi

def blobs(mask, min_area):
    mask = ndi.binary_opening(mask, iterations=1)
    lab, n = ndi.label(mask)
    out = []
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        m = lab[sl] == i; a = int(m.sum())
        if a < min_area: continue
        h, w = m.shape; out.append({"area": a, "aspect": max(h, w) / max(1, min(h, w)), "fill": a / (h * w), "cy": (sl[0].start + sl[0].stop) / 2, "cx": (sl[1].start + sl[1].stop) / 2})
    return sorted(out, key=lambda b: -b["area"])

def classify(path, P):   # path or file-like object
    im = Image.open(path).convert("RGB"); im.thumbnail((400, 400)); h = np.array(im.convert("HSV")).astype(int)
    H, S, V = h[..., 0], h[..., 1], h[..., 2]
    orange = blobs((H >= 6) & (H <= 22) & (S > P["os"]) & (V > 130), P["omin"])
    white = blobs((S < P["ws"]) & (V > P["wv"]), P["wmin"])
    gold = blobs((H >= 22) & (H <= 36) & (S > 110) & (V > 110), P["gmin"])
    ob = [b for b in orange if b["aspect"] < 1.7 and b["fill"] > 0.45]
    wb = [b for b in white if b["area"] < P["wmax"] and b["aspect"] < 1.9 and b["fill"] > 0.5]
    gb = [b for b in gold if b["aspect"] >= 1.5]
    cands = []
    if ob: cands.append(("stress_ball", ob[0]["area"] * 1.0))
    if gb: cands.append(("can", gb[0]["area"] * 0.9))
    if wb: cands.append(("egg", wb[0]["area"] * 0.8))
    return max(cands, key=lambda c: c[1])[0] if cands else "other"

def classify_bytes(data, P=None):
    """Colour-rule label for image bytes: 'stress_ball' | 'egg' | 'can' | 'other' (76% on imgs/, untuned)."""
    import io   # decoded in memory: a NamedTemporaryFile cannot be reopened by name on Windows (Giorgio, board 17:46 -> ok=False)
    return classify(io.BytesIO(data), P or DEFAULT_P)


DEFAULT_P = {"os": 150, "omin": 120, "ws": 45, "wv": 215, "wmin": 150, "wmax": 9000, "gmin": 250}

if __name__ == "__main__":
    ROOT = sys.argv[1] if len(sys.argv) > 1 else "imgs"
    P = {"os": 150, "omin": 120, "ws": 45, "wv": 215, "wmin": 150, "wmax": 9000, "gmin": 250}
    FOLDER = {"ball": "stress_ball", "egg": "egg", "can": "can"}
    rows = []
    for d, lab in FOLDER.items():
        for f in sorted(glob.glob(os.path.join(ROOT, d, "*.jpg"))):
            rows.append((f, lab, classify(f, P)))
    for name, sel in (("even", lambda i: i % 2 == 0), ("odd", lambda i: i % 2 == 1), ("all", lambda i: True)):
        sub = [r for i, r in enumerate(rows) if sel(i)]
        acc = sum(r[1] == r[2] for r in sub) / len(sub)
        c = collections.Counter((r[1], r[2]) for r in sub)
        print(name, len(sub), "acc %.0f%%" % (acc * 100), {k: v for k, v in sorted(c.items())})
