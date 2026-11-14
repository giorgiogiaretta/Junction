# Gemma on our own Verda GPU (vLLM) — setup, check, cost discipline

Why: the Google free tier allows **20 requests per day per model** and Gemma through the API took 4-8 s. On our own GPU: no daily quota, no data leaves our machine, open weights (the point of "Best Use of Gemma"), and we can measure real latency.

## 1. Instance (Verda dashboard, Tommaso)
- Linux GPU instance with **>= 80 GB GPU memory** for `gemma-4-26b-a4b-it` in bf16 (mixture of experts: all ~26B weights must fit, ~52 GB + cache), or a smaller GPU with `QUANT=fp8` on H100-class hardware. **Unverified:** exact model size, Hugging Face id and Verda GPU names/prices: check the model card and the instance list before starting.
- Add your SSH key. **Do not open port 8000 to the internet**: use the SSH tunnel below.
- Credits: 200 EUR. Note the hourly price, **stop the instance when idle**, delete it when the demo is done.

## 2. Serve (on the instance)
```
git clone <our repo> && cd Junction            # or scp tools/serve_gemma.sh
export HF_TOKEN=...      # only if the model is gated; your own, never written to a file
export LOCAL_KEY=...     # any secret string; clients must send it
bash tools/serve_gemma.sh                       # vLLM, OpenAI-compatible, listens on 127.0.0.1:8000
```
## 3. Tunnel + check (on the Mac)
```
ssh -N -L 8000:127.0.0.1:8000 <user>@<verda-ip>          # leave it open in its own terminal
export GEMMA_BASE_URL=http://127.0.0.1:8000/v1 GEMMA_MODEL=google/gemma-4-26b-a4b-it GEMMA_API_KEY=<LOCAL_KEY>
python -m ai.check_gemma_local                           # ping + 6 photos + latency
python -m ai.eval_objects imgs --backend gemma --mix --json data/photos_reports/gemma_local.json
python -m ai.crosscheck data/photos_reports/n2.json data/photos_reports/gemma_local.json --names nemotron,gemma-local
```
With `GEMMA_BASE_URL` set, `ai.recognize`, `ai.intent_router`, `ai.advisor` and `ai.eval_objects --backend gemma` use the local server; without it they use Gemma on the Google API.

## 4. What to measure and write down (no claim before the numbers)
Accuracy on the 50 labelled photos vs the Google-API Gemma (49/50, eggs 20/20), median latency, GPU, price per hour, the exact model id used. If the local numbers differ from the API run, say so.

## CORRECTION and decision (14/11 evening): PaliGemma 2 on the GPU, Gemma 4 stays on the API
Tommaso's instruction: serve **`google/paligemma2-3b-mix-224`** (3B, SigLIP + Gemma 2, 224 px input) on the Verda GPU instead of Gemma 4 26B. Done in `tools/serve_gemma.sh` (default `SERVER=paligemma`, served by `tools/paligemma_server.py`: Hugging Face Transformers, OpenAI-compatible, port 8000, SSH tunnel unchanged). `SERVER=vllm MODEL=...` still serves a chat VLM.
Two facts to keep straight (so the pitch stays true):
- **Gemma 4 26B is NOT text-only**: through the Google API it read our photos (49/50, eggs 20/20, `docs/OBJECT_RECOGNITION_RESULTS.md`). It stays our second recogniser via the API. PaliGemma 2 is a *different, smaller* model.
- **PaliGemma 2 is a vision-language model, not a VLA** (it does not output robot actions). It answers short task prompts ("answer en Is this object fragile or rigid?", "detect egg"); it is **not a JSON-following chat model**, so it cannot replace the JSON recognisers or the intent router without a different prompt design. Its 224 px input is small for our photos. Treat it as a fast local second opinion on **fragile vs rigid** until measured: `python -m ai.check_gemma_local` (sanity check on 6 photos, then evaluate on all 50 before any claim).
- **Token hygiene:** `HF_TOKEN` is read from the environment on the instance only. A token pasted in a chat or a doc is compromised: revoke it on Hugging Face after the download and create a new one if needed. Nothing in this repo contains a token.

## Two models on one A100 80 GB (optional, after PaliGemma works)
PaliGemma 2 3B needs ~10 GB. Gemma-4-26B-A4B in bf16 needs ~52 GB + cache, so both fit on an 80 GB A100 if the second one is capped:
```
# terminal 1 on the instance (already running): PaliGemma on 8000
# terminal 2 on the instance:
export LOCAL_KEY=...; SERVER=vllm PORT=8001 GPU_UTIL=0.75 MODEL=google/gemma-4-26b-a4b-it bash tools/serve_gemma.sh     # UNVERIFIED model id
# on the Mac: ssh -N -L 8000:127.0.0.1:8000 -L 8001:127.0.0.1:8001 root@<ip>
export GEMMA_BASE_URL=http://127.0.0.1:8001/v1 GEMMA_MODEL=google/gemma-4-26b-a4b-it GEMMA_API_KEY=<LOCAL_KEY>      # JSON-following chat model: recognisers, router
```
Gemma 4 on our own GPU is the one that can replace the API Gemma for the recognisers and the intent router (it follows JSON); PaliGemma stays the fast fragile/rigid second opinion. Measure both before claiming anything.
