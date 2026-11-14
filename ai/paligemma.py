"""PaliGemma 2 (served on our own GPU by tools/paligemma_server.py) as a fast LOCAL recogniser, with a multiple-choice prompt.
Measured 14/11 on our 50 labelled photos through the SSH tunnel (A100 80 GB, 448 px JPEG): 3-option prompt 49/50 (egg 19/20, ball 22/22, can 8/8), median 0.21 s;
free-form "What is the object?" 42/50; binary "Is this object fragile or rigid?" answers 'fragile' for 48/50 photos (balls and cans too): USELESS as a classifier.
PaliGemma is a task-prompt model: it does not follow JSON instructions and gives NO confidence, so it votes with confidence None.
Env: PALIGEMMA_BASE_URL (e.g. http://127.0.0.1:8000/v1 through the tunnel), PALIGEMMA_API_KEY (the LOCAL_KEY of the server), PALIGEMMA_MODEL (informational)."""
import base64, os, time
from ai.llm import ChatClient

QUESTION = "Which object is in the hand: an egg, an orange ball, or a drink can? Answer with one word."


def normalise(answer):
    t = (answer or "").lower()
    if "egg" in t: return "egg"
    if "ball" in t or "orange" in t or "sphere" in t: return "stress_ball"
    if "can" in t or "soda" in t or "drink" in t or "tin" in t: return "can"
    return "other"


def make_client():
    url = os.environ.get("PALIGEMMA_BASE_URL")
    if not url: return None
    return ChatClient(api_key=os.environ.get("PALIGEMMA_API_KEY", "local"), base_url=url, model=os.environ.get("PALIGEMMA_MODEL", "google/paligemma2-3b-mix-224"), timeout=15, max_retries=0, rpm=600)


def recognise_bytes(client, jpeg):
    """-> {'object', 'confidence': None, 'ok', 'raw', 'error'?}. Not configured / server down -> ok False (the ensemble ignores it)."""
    if client is None: return {"object": "other", "confidence": None, "ok": False, "raw": "", "error": "PALIGEMMA_BASE_URL not set"}
    content = [{"type": "text", "text": QUESTION}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()}}]
    try:
        raw = (client.chat([{"role": "user", "content": content}], max_tokens=16).get("content") or "").strip()
        return {"object": normalise(raw), "confidence": None, "ok": True, "raw": raw}
    except Exception as e:
        return {"object": "other", "confidence": None, "ok": False, "raw": "", "error": type(e).__name__}
