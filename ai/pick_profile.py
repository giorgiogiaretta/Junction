"""Pick the Force Cushion profile with the vision-language model and publish it to the running demo (UDP 127.0.0.1:14070).
  python -m ai.pick_profile --image frame.jpg            # one image
  python -m ai.pick_profile --camera 0                   # grab one webcam frame (needs opencv-python)
  python -m ai.pick_profile --text "a paper cup of water"  # no image
  python -m ai.pick_profile --set egg                    # skip the model, set directly (also the manual fallback)
Needs VERDA_INFERENCE_KEY (or NVIDIA_API_KEY) except with --set. On any model failure the fallback profile is published (default 'none'),
and the result says source=fallback."""
import argparse, json, socket
from ai.llm import ChatClient
from ai.profile_picker import pick_profile


def grab(cam):
    import cv2
    cap = cv2.VideoCapture(cam); ok, fr = cap.read(); cap.release()
    if not ok: raise SystemExit("camera frame failed")
    return cv2.imencode(".jpg", fr)[1].tobytes()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--image"); ap.add_argument("--camera", type=int); ap.add_argument("--text", default="")
    ap.add_argument("--set", choices=["cup", "egg", "can", "none"]); ap.add_argument("--fallback", default="none", choices=["cup", "egg", "can", "none"])
    ap.add_argument("--port", type=int, default=14070); a = ap.parse_args()
    if a.set: res = {"object": "manual", "profile": a.set, "source": "manual"}
    else:
        img = open(a.image, "rb").read() if a.image else (grab(a.camera) if a.camera is not None else None)
        res = pick_profile(ChatClient(timeout=60), img, a.text, a.fallback)
    socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(json.dumps({"profile": res["profile"]}).encode(), ("127.0.0.1", a.port))
    print(json.dumps(res))
