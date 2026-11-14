"""Pick the Force Cushion profile with the vision-language model and publish it to the running demo (UDP 127.0.0.1:14070).
  python -m ai.pick_profile --image frame.jpg            # one image
  python -m ai.pick_profile --camera 0                   # grab one webcam frame (needs opencv-python)
  python -m ai.pick_profile --text "a paper cup of water"  # no image
  python -m ai.pick_profile --set egg                    # skip the model, set directly (also the manual fallback)
  python -m ai.pick_profile --image head.jpg --hand-in-head 0.05 0.10 0.45 [--intrinsics cam.json] [--axes x,y,z] [--window-m 0.30]
      # pre-grasp CROP (ai/crop.py): project the hand (hand position in the head-sensor frame, metres) into the head-camera image and send
      # ONLY the crop around it to the model. Intrinsics default to ASSUMED GoPro-like values; missing/invalid data -> the full image is sent.
Needs VERDA_INFERENCE_KEY (or NVIDIA_API_KEY) except with --set. If Nemotron fails and GEMINI_API_KEY/GOOGLE_API_KEY is set, Gemini is asked
the same question (--backup gemini, default; 'backup' field in the result). If both fail the fallback profile is published (default 'cup',
conservative) and the result says source=fallback. Model answers go through profile_picker.apply_safety (only ever softer)."""
import argparse, json, os, socket
from ai.llm import ChatClient
from ai.profile_picker import pick_profile, CROP_PROMPT


def grab(cam):
    import cv2
    cap = cv2.VideoCapture(cam); ok, fr = cap.read(); cap.release()
    if not ok: raise SystemExit("camera frame failed")
    return cv2.imencode(".jpg", fr)[1].tobytes()


def build_parser():
    ap = argparse.ArgumentParser(); ap.add_argument("--image"); ap.add_argument("--camera", type=int); ap.add_argument("--text", default="")
    ap.add_argument("--set", choices=["cup", "egg", "can", "none"]); ap.add_argument("--fallback", default="cup", choices=["cup", "egg", "can", "none"])
    ap.add_argument("--backup", default="gemini", choices=["gemini", "off"], help="second provider when the first fails (needs GEMINI_API_KEY)")
    ap.add_argument("--hand-in-head", type=float, nargs=3, metavar=("X", "Y", "Z"), help="hand position in the head-sensor frame, metres (pre-grasp crop)")
    ap.add_argument("--intrinsics", help="camera intrinsics JSON {fx,fy,cx,cy,width,height}; default: ASSUMED GoPro-like values")
    ap.add_argument("--axes", default="x,y,z", help="map head-frame axes to camera x(right),y(down),z(forward), e.g. x,-y,z")
    ap.add_argument("--window-m", type=float, default=0.30, help="physical side of the crop window at the hand's depth")
    ap.add_argument("--port", type=int, default=14070)
    return ap


def prepare(image, a):
    """(image_bytes, prompt, crop_info|None). With --hand-in-head the image is replaced by the crop around the hand (full image on any fallback)."""
    if image is None or a.hand_in_head is None: return image, None, None
    from ai.crop import crop_around_hand, load_intrinsics
    K = load_intrinsics(a.intrinsics)
    r = crop_around_hand(image, a.hand_in_head, K, a.window_m, a.axes)
    info = {k: r[k] for k in ("bbox", "cropped", "reason", "pixel", "depth_m", "intrinsics_assumed")}
    return r["image"], CROP_PROMPT, info


def gemini_client():
    """Gemini via its OpenAI-compatible endpoint (same client as ai/eval_objects.py), or None without a key."""
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")): return None
    from ai.eval_objects import make_client
    return make_client("gemini")


def main(argv=None, client=None, backup_client=None):
    a = build_parser().parse_args(argv)
    crop = None
    if a.set: res = {"object": "manual", "profile": a.set, "source": "manual"}
    else:
        img = open(a.image, "rb").read() if a.image else (grab(a.camera) if a.camera is not None else None)
        img, prompt, crop = prepare(img, a)
        # fail fast: a dead endpoint (Verda, 2026-11-14) must not block the grasp for minutes (was 60 s x 5 attempts)
        res = pick_profile(client or ChatClient(timeout=20, max_retries=1), img, a.text, a.fallback, prompt=prompt)
        if res["source"] == "fallback" and a.backup == "gemini":
            bc = backup_client or gemini_client()
            if bc is not None:
                r2 = pick_profile(bc, img, a.text, a.fallback, prompt=prompt)
                r2["backup"] = "gemini"; r2["primary_error"] = res.get("error")
                res = r2
        if crop is not None: res["crop"] = crop
        if res["source"] == "model":  # G1 support flag from g1/object_profiles.json (e.g. can: not graspable by the G1, vision only)
            from ai.object_profile import behaviour
            b = behaviour(res.get("object"))
            if b.get("supported") is False:
                res["supported"] = False; res["why"] = b.get("why", "")
    socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(json.dumps({"profile": res["profile"]}).encode(), ("127.0.0.1", a.port))
    print(json.dumps(res))
    return res


if __name__ == "__main__":
    main()
