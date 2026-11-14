"""Pick the Force Cushion profile with the vision-language model and publish it to the running demo (UDP 127.0.0.1:14070).
  python -m ai.pick_profile --image frame.jpg            # one image
  python -m ai.pick_profile --camera 0                   # grab one webcam frame (needs opencv-python)
  python -m ai.pick_profile --text "a paper cup of water"  # no image
  python -m ai.pick_profile --set egg                    # skip the model, set directly (also the manual fallback)
  python -m ai.pick_profile --image head.jpg --hand-in-head 0.05 0.10 0.45 [--intrinsics cam.json] [--axes x,y,z] [--window-m 0.30]
      # pre-grasp CROP (ai/crop.py): project the hand (hand position in the head-sensor frame, metres) into the head-camera image and send
      # ONLY the crop around it to the model. Intrinsics default to ASSUMED GoPro-like values; missing/invalid data -> the full image is sent.
Needs VERDA_INFERENCE_KEY (or NVIDIA_API_KEY) except with --set. On any model failure the fallback profile is published (default 'none'),
and the result says source=fallback."""
import argparse, json, socket
from ai.llm import ChatClient
from ai.profile_picker import pick_profile, CROP_PROMPT


def grab(cam):
    import cv2
    cap = cv2.VideoCapture(cam); ok, fr = cap.read(); cap.release()
    if not ok: raise SystemExit("camera frame failed")
    return cv2.imencode(".jpg", fr)[1].tobytes()


def build_parser():
    ap = argparse.ArgumentParser(); ap.add_argument("--image"); ap.add_argument("--camera", type=int); ap.add_argument("--text", default="")
    ap.add_argument("--set", choices=["cup", "egg", "can", "none"]); ap.add_argument("--fallback", default="none", choices=["cup", "egg", "can", "none"])
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


def main(argv=None, client=None):
    a = build_parser().parse_args(argv)
    crop = None
    if a.set: res = {"object": "manual", "profile": a.set, "source": "manual"}
    else:
        img = open(a.image, "rb").read() if a.image else (grab(a.camera) if a.camera is not None else None)
        img, prompt, crop = prepare(img, a)
        res = pick_profile(client or ChatClient(timeout=60), img, a.text, a.fallback, prompt=prompt)
        if crop is not None: res["crop"] = crop
    socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(json.dumps({"profile": res["profile"]}).encode(), ("127.0.0.1", a.port))
    print(json.dumps(res))
    return res


if __name__ == "__main__":
    main()
