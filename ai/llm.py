"""Minimal OpenAI-compatible chat client for NVIDIA Build (Nemotron) or any compatible endpoint. stdlib only.
Env: NVIDIA_API_KEY (or LLM_API_KEY), LLM_BASE_URL (default https://integrate.api.nvidia.com/v1), LLM_MODEL.
The default model id below is UNVERIFIED: confirm the exact Nemotron 3.5 Super VL id with the NVIDIA mentors and set LLM_MODEL.
Never used in the control loop: slow (seconds) and rate limited (~40 RPM per key on the free tier). Each person uses their OWN key.
`transport` is injectable for tests: callable(url, headers, payload_dict, timeout) -> (status, response_dict)."""
import json, os, random, threading, time, urllib.error, urllib.request

DEFAULT_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "nvidia/nemotron-3.5-super-vl"  # UNVERIFIED id


def _http(url, headers, payload, timeout):
    req = urllib.request.Request(url, json.dumps(payload).encode(), headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: body = json.loads(e.read().decode())
        except Exception: body = {}
        return e.code, body


class LLMError(Exception): pass


class ChatClient:
    def __init__(self, api_key=None, base_url=None, model=None, rpm=30, max_retries=4, timeout=20, transport=_http, sleep=time.sleep):
        self.key = api_key or os.environ.get("NVIDIA_API_KEY") or os.environ.get("LLM_API_KEY")
        self.url = (base_url or os.environ.get("LLM_BASE_URL") or DEFAULT_URL).rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL") or DEFAULT_MODEL
        self.min_gap, self.retries, self.timeout, self.transport, self.sleep = 60.0 / rpm, max_retries, timeout, transport, sleep
        self._last, self._lock, self.calls = 0.0, threading.Lock(), 0

    def chat(self, messages, tools=None, temperature=0.0, max_tokens=512):
        """Returns the first choice message dict ({'content', 'tool_calls'?}). Retries 429/5xx/timeouts with exponential backoff + jitter."""
        if not self.key: raise LLMError("no API key (set NVIDIA_API_KEY)")
        payload = {"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if tools: payload["tools"] = tools
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        last = None
        for attempt in range(self.retries + 1):
            with self._lock:  # simple client-side rate limit
                wait = self._last + self.min_gap - time.time()
                if wait > 0: self.sleep(wait)
                self._last = time.time()
            self.calls += 1
            try:
                status, body = self.transport(self.url + "/chat/completions", headers, payload, self.timeout)
            except (TimeoutError, OSError) as e:
                status, body, last = 599, {}, f"network: {e}"
            if status == 200 and body.get("choices"): return body["choices"][0]["message"]
            last = last or f"HTTP {status}: {str(body)[:200]}"
            if status not in (429, 500, 502, 503, 504, 599): break
            self.sleep(min(30, (2 ** attempt)) + random.random() * 0.25)
            last = None
        raise LLMError(last or "failed")
