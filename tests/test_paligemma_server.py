"""PaliGemma server plumbing with a fake generate (no torch, no GPU): request parsing, prompt mapping, auth, OpenAI response shape, and the ai/ client against it."""
import base64, io, json, pathlib, sys, threading, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).parents[1])); sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "tools"))
from http.server import ThreadingHTTPServer
import paligemma_server as ps


def img_b64():
    from PIL import Image
    b = io.BytesIO(); Image.new("RGB", (8, 8), (200, 30, 30)).save(b, "JPEG"); return base64.b64encode(b.getvalue()).decode()


def test_prompt_mapping():
    assert ps.to_prompt("Is this object fragile or rigid?") == "answer en Is this object fragile or rigid?" and ps.to_prompt("detect egg") == "detect egg"


def test_server_roundtrip_with_the_ai_client():
    seen = {}
    def gen(prompt, image, n): seen["p"] = prompt; seen["size"] = image.size; return "fragile"
    srv = ThreadingHTTPServer(("127.0.0.1", 0), ps.make_handler(gen, "paligemma2-test", key="k")); port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        from ai.llm import ChatClient
        c = ChatClient("k", base_url=f"http://127.0.0.1:{port}/v1", model="x", timeout=10, max_retries=0, rpm=6000)
        m = c.chat([{"role": "user", "content": [{"type": "text", "text": "Is this object fragile or rigid?"}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + img_b64()}}]}], max_tokens=20)
        assert m["content"] == "fragile" and seen["p"].startswith("answer en") and seen["size"] == (8, 8)
        bad = urllib.request.Request(f"http://127.0.0.1:{port}/v1/models", headers={"Authorization": "Bearer wrong"})
        try: urllib.request.urlopen(bad, timeout=5); raise AssertionError("should be 401")
        except urllib.error.HTTPError as e: assert e.code == 401
    finally: srv.shutdown()
