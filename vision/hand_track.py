"""Hand keypoints with MediaPipe Hands -> wrist (landmark 0) and index fingertip (landmark 8) in table coordinates.
Both points are projected on the table plane (z=0): the fingertip is usually a few cm above it, so values are only
approximate in height but fine for the XY comparison with the gloves. Up to 2 hands; slot 0/1 = MediaPipe label
Left/Right as reported (MediaPipe assumes a mirrored selfie image, so for an un-mirrored camera the label is swapped:
treat the slots as 'hand A / hand B' and use `nearest_to` to pick the working hand)."""
import cv2
import numpy as np

WRIST, INDEX_TIP = 0, 8

class HandTracker:
    def __init__(self, max_hands=2, det_conf=0.3, track_conf=0.3, complexity=1):
        import mediapipe as mp
        self.h = mp.solutions.hands.Hands(static_image_mode=False, max_num_hands=max_hands, model_complexity=complexity,
                                          min_detection_confidence=det_conf, min_tracking_confidence=track_conf)

    def pixels(self, bgr):
        """Returns list of dict(label, score, wrist=(u,v), index=(u,v), all=(21,2)) in pixels of `bgr`."""
        H, W = bgr.shape[:2]
        r = self.h.process(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        out = []
        for lm, hd in zip(r.multi_hand_landmarks or [], r.multi_handedness or []):
            pts = np.array([[p.x * W, p.y * H] for p in lm.landmark])
            c = hd.classification[0]
            out.append(dict(label=c.label, score=float(c.score), wrist=pts[WRIST], index=pts[INDEX_TIP], all=pts))
        return out

    def update(self, bgr, calib, to_ref=None):
        """-> dict(wrist (2,2) metres, index (2,2) metres, score (2,)), NaN for a missing slot. `to_ref`: optional 3x3 mapping
        the frame's pixels into the calibration image (moving camera)."""
        wr = np.full((2, 2), np.nan); ix = np.full((2, 2), np.nan); sc = np.zeros(2)
        for h in self.pixels(bgr):
            s = 0 if h["label"] == "Left" else 1
            if sc[s] >= h["score"]: continue
            p = np.array([h["wrist"], h["index"]])
            if to_ref is not None: p = cv2.perspectiveTransform(p.reshape(-1, 1, 2), to_ref).reshape(-1, 2)
            t = calib.pixel_to_table(p)
            wr[s], ix[s], sc[s] = t[0], t[1], h["score"]
        return dict(wrist=wr, index=ix, score=sc)

def nearest_to(wrist, ref_xy):
    """Index (0/1) of the hand whose wrist is nearest to ref_xy (e.g. the can), or None if no hand is visible."""
    d = np.hypot(*(wrist - np.asarray(ref_xy)[None]).T)
    return None if np.all(np.isnan(d)) else int(np.nanargmin(d))
