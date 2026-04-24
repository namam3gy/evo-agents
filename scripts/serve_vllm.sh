#!/usr/bin/env bash
# Launch vLLM OpenAI-compatible server for Qwen2.5-32B-Instruct on a single H200.
# Assumes vllm is installed (pip install vllm) and the HF model cache is writable.

set -euo pipefail

MODEL="${EVO_MODEL:-Qwen/Qwen2.5-32B-Instruct}"
PORT="${EVO_PORT:-8000}"
HOST="${EVO_HOST:-0.0.0.0}"
MAX_LEN="${EVO_MAX_LEN:-8192}"
GPU_UTIL="${EVO_GPU_UTIL:-0.90}"

echo "Serving ${MODEL} on ${HOST}:${PORT} (max_model_len=${MAX_LEN}, gpu_util=${GPU_UTIL})"

exec python -m vllm.entrypoints.openai.api_server \
    --model "${MODEL}" \
    --host "${HOST}" \
    --port "${PORT}" \
    --dtype bfloat16 \
    --max-model-len "${MAX_LEN}" \
    --gpu-memory-utilization "${GPU_UTIL}" \
    --enable-prefix-caching \
    --disable-log-requests
