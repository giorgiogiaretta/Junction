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
