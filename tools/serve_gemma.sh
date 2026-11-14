#!/usr/bin/env bash
# Run ON the Verda GPU instance (Linux + NVIDIA GPU). Listens on 127.0.0.1:8000 ONLY (reach it through the SSH tunnel; do not open the port).
#   SERVER=paligemma (default)  PaliGemma 2 3B mix 224 through tools/paligemma_server.py (Hugging Face Transformers, OpenAI-compatible)
#   SERVER=vllm                 any chat VLM through vLLM, e.g. MODEL=google/gemma-4-26b-a4b-it (UNVERIFIED id; ~52 GB: needs an 80 GB GPU or QUANT=fp8)
# Secrets come from YOUR environment and are never written to a file: HF_TOKEN (licence accepted on that Hugging Face account) and LOCAL_KEY (any string you choose).
# Mac side:  ssh -N -L 8000:127.0.0.1:8000 <user>@<verda-ip>   then   export GEMMA_BASE_URL=http://127.0.0.1:8000/v1 GEMMA_API_KEY=<LOCAL_KEY> GEMMA_MODEL=<MODEL>
set -euo pipefail
SERVER="${SERVER:-paligemma}"
: "${LOCAL_KEY:?export LOCAL_KEY=<any secret string> first}"
if [ "$SERVER" = "paligemma" ]; then
  MODEL="${MODEL:-google/paligemma2-3b-mix-224}"
  : "${HF_TOKEN:?export HF_TOKEN=<your Hugging Face token> first (licence accepted for $MODEL)}"
  python3 -m pip install -q --upgrade torch transformers accelerate pillow sentencepiece protobuf
  cd "$(dirname "$0")/.."
  exec env MODEL="$MODEL" python3 tools/paligemma_server.py --model "$MODEL" --host 127.0.0.1 --port 8000
else
  MODEL="${MODEL:-google/gemma-4-26b-a4b-it}"
  python3 -m pip install -q --upgrade vllm
  EXTRA=""; [ -n "${QUANT:-}" ] && EXTRA="--quantization $QUANT"
  exec vllm serve "$MODEL" --host 127.0.0.1 --port 8000 --api-key "$LOCAL_KEY" --max-model-len "${MAXLEN:-8192}" --gpu-memory-utilization "${GPU_UTIL:-0.90}" --limit-mm-per-prompt '{"image": 1}' $EXTRA
fi
