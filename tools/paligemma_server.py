"""Minimal OpenAI-compatible server for PaliGemma 2 (Hugging Face Transformers). Run ON the Verda GPU; listens on 127.0.0.1:8000 (reach it through the SSH tunnel).
  HF_TOKEN=... LOCAL_KEY=... python3 tools/paligemma_server.py [--model google/paligemma2-3b-mix-224] [--port 8000]
Why not vLLM chat: PaliGemma is a task-prompt model (no chat template): "answer en <question>", "caption en", "detect <thing>". This server maps the LAST user message of an OpenAI
chat request to such a prompt (adds "answer en " unless it already starts with a task word) and returns the generated text in the OpenAI response shape, so ai/ code works unchanged
(GEMMA_BASE_URL=http://127.0.0.1:8000/v1). Image = data: URI in an image_url part. HF_TOKEN is read from the ENVIRONMENT by huggingface_hub (never written anywhere).
NOT a JSON-following chat model: use it for short questions ("Is this object fragile or rigid?", "What is the object?"), not for the JSON recognisers.
Untested here: needs a GPU box with torch + transformers (+ the licence accepted on the HF account)."""
import argparse, base64, io, json, os, re, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TASKS = ("answer", "caption", "describe", "detect", "segment", "ocr", "question", "cap")


def to_prompt(text):
    t = (text or "").strip()
    return t if t.lower().startswith(TASKS) else "answer en " + t


def parse_request(body):
    """OpenAI chat body -> (prompt, PIL.Image|None) from the last user message."""
    msgs = [m for m in body.get("messages", []) if m.get("role") == "user"]
    if not msgs: raise ValueError("no user message")
    content = msgs[-1].get("content"); texts, img = [], None
    for part in (content if isinstance(content, list) else [{"type": "text", "text": content or ""}]):
        if part.get("type") == "text": texts.append(part.get("text", ""))
        elif part.get("type") == "image_url":
            url = (part.get("image_url") or {}).get("url", "")
            m = re.match(r"data:image/[a-zA-Z+]+;base64,(.*)", url, re.S)
            if m:
                from PIL import Image
                img = Image.open(io.BytesIO(base64.b64decode(m.group(1)))).convert("RGB")
    return to_prompt(" ".join(texts)), img


def load_generate(model_id):
    import torch
    from transformers import AutoProcessor, PaliGemmaForConditionalGeneration
    dev = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    model = PaliGemmaForConditionalGeneration.from_pretrained(model_id, torch_dtype=torch.bfloat16 if dev == "cuda" else torch.float16).to(dev).eval()
    proc = AutoProcessor.from_pretrained(model_id); lock = threading.Lock()
    def generate(prompt, image, max_new_tokens=48):
        with lock, torch.inference_mode():
            inp = proc(text=prompt, images=image, return_tensors="pt").to(dev)
            out = model.generate(**inp, max_new_tokens=max_new_tokens, do_sample=False)
            return proc.decode(out[0][inp["input_ids"].shape[-1]:], skip_special_tokens=True).strip()
    return generate


def make_handler(generate, model_name, key=None):
    class H(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def _authed(self): return not key or self.headers.get("Authorization") == f"Bearer {key}"
        def do_GET(self):
            if not self._authed(): return self._send(401, {"error": "unauthorized"})
            if self.path.rstrip("/").endswith("/models"): return self._send(200, {"data": [{"id": model_name, "object": "model"}]})
            self._send(404, {"error": "not found"})
        def do_POST(self):
            if not self._authed(): return self._send(401, {"error": "unauthorized"})
            if not self.path.rstrip("/").endswith("/chat/completions"): return self._send(404, {"error": "not found"})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()); prompt, img = parse_request(body)
                if img is None: return self._send(400, {"error": "PaliGemma needs an image_url part"})
                t = time.time(); text = generate(prompt, img, min(int(body.get("max_tokens") or 48), 128))
            except Exception as e: return self._send(500, {"error": type(e).__name__})
            self._send(200, {"id": "pg-1", "object": "chat.completion", "created": int(time.time()), "model": model_name, "latency_s": round(time.time() - t, 3),
                             "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}]})
        def log_message(self, *a): pass
    return H


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--model", default=os.environ.get("MODEL", "google/paligemma2-3b-mix-224")); ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1"); a = ap.parse_args()
    gen = load_generate(a.model); print(f"serving {a.model} on {a.host}:{a.port}", flush=True)
    ThreadingHTTPServer((a.host, a.port), make_handler(gen, a.model, os.environ.get("LOCAL_KEY"))).serve_forever()
