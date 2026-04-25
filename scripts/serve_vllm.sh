#!/usr/bin/env bash
# Launch vLLM OpenAI-compatible server for Qwen2.5-32B-Instruct on a single H200.
# Assumes vllm is installed (pip install vllm) and the HF model cache is writable.

set -euo pipefail

# Triton JIT needs a C compiler visible as `gcc`. Conda-forge gcc is installed
# as x86_64-conda-linux-gnu-gcc; symlink to `gcc` and pin CC so subprocesses
# inherit a working toolchain. See docs/insights/pilot.md §1.2.
if ! command -v gcc >/dev/null 2>&1; then
    if [ -x /opt/conda/bin/x86_64-conda-linux-gnu-gcc ]; then
        ln -sf /opt/conda/bin/x86_64-conda-linux-gnu-gcc /opt/conda/bin/gcc
    fi
fi
export PATH="/opt/conda/bin:${PATH}"
export CC="${CC:-$(command -v gcc)}"

MODEL="${EVO_MODEL:-Qwen/Qwen2.5-32B-Instruct}"
PORT="${EVO_PORT:-8000}"
HOST="${EVO_HOST:-0.0.0.0}"
MAX_LEN="${EVO_MAX_LEN:-8192}"
GPU_UTIL="${EVO_GPU_UTIL:-0.90}"

echo "Serving ${MODEL} on ${HOST}:${PORT} (max_model_len=${MAX_LEN}, gpu_util=${GPU_UTIL})"

exec uv run python -m vllm.entrypoints.openai.api_server \
    --model "${MODEL}" \
    --host "${HOST}" \
    --port "${PORT}" \
    --dtype bfloat16 \
    --max-model-len "${MAX_LEN}" \
    --gpu-memory-utilization "${GPU_UTIL}" \
    --enable-prefix-caching \
    --no-enable-log-requests
