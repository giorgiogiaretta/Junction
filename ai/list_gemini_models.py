"""List the Gemini models this API key can call (so we use a REAL id instead of guessing '2.5-flash' / '3.x'). Key only from the environment (GEMINI_API_KEY or GOOGLE_API_KEY), sent in the x-goog-api-key header (never in the URL).
  python -m ai.list_gemini_models [--match 3]      -> prints id, input limit and whether it supports generateContent
Then: export GEMINI_MODEL=<id>"""
import argparse, json, os, sys, urllib.request

URL = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200"

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--match", default=""); a = ap.parse_args()
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key: sys.exit("error: export GEMINI_API_KEY (or GOOGLE_API_KEY) in this terminal")
    try:
        d = json.load(urllib.request.urlopen(urllib.request.Request(URL, headers={"x-goog-api-key": key}), timeout=30))
    except Exception as e:
        sys.exit(f"request failed: {type(e).__name__} (key invalid or no network)")   # the error text is not echoed (could contain the key)
    for m in d.get("models", []):
        name = m["name"].split("/", 1)[-1]
        if a.match in name and "generateContent" in m.get("supportedGenerationMethods", []):
            print(f"{name:45s} in={m.get('inputTokenLimit')} out={m.get('outputTokenLimit')}  {m.get('displayName', '')}")
