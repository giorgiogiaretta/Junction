#!/usr/bin/env bash
# Run ON the Verda GPU instance (Linux, NVIDIA GPU). Serves Gemma through vLLM with an OpenAI-compatible API on 127.0.0.1:8000 (NOT public).
# Then on your Mac:  ssh -N -L 8000:127.0.0.1:8000 <user>@<verda-ip>   and   export GEMMA_BASE_URL=http://127.0.0.1:8000/v1 GEMMA_API_KEY=<LOCAL_KEY>
# Secrets: HF_TOKEN (Hugging Face, if the model is gated) and LOCAL_KEY (any string you choose) come from YOUR environment; they are never written to a file here.
# Memory: Gemma-4-26B-A4B is a mixture-of-experts: all 26B weights must fit (~52 GB in bf16): use an 80 GB GPU, or quantize (QUANT=fp8 on H100-class GPUs).
set -euo pipefail
MODEL="${MODEL:-google/gemma-4-26b-a4b-it}"   # UNVERIFIED Hugging Face id: check the model card first
: "${LOCAL_KEY:?export LOCAL_KEY=<any secret string> first}"
python3 -m pip install -q --upgrade vllm
EXTRA=""; [ -n "${QUANT:-}" ] && EXTRA="--quantization $QUANT"
exec vllm serve "$MODEL" --host 127.0.0.1 --port 8000 --api-key "$LOCAL_KEY" --max-model-len "${MAXLEN:-8192}" --gpu-memory-utilization "${GPU_UTIL:-0.90}" --limit-mm-per-prompt '{"image": 1}' $EXTRA
