#!/usr/bin/env bash
# Launch vLLM OpenAI-compatible server for Qwen2.5-32B-Instruct on a single H200.
# Assumes vllm is installed (pip install vllm) and the HF model cache is writable.

set -euo pipefail

# Triton JIT needs a C compiler visible as `gcc`. Container reservations are
# ephemeral so apt-installed gcc does NOT persist across sessions; check on
# every startup and install if missing. See docs/insights/pilot.md §1.2.
if ! command -v gcc >/dev/null 2>&1; then
    if [ -x /opt/conda/bin/x86_64-conda-linux-gnu-gcc ]; then
        ln -sf /opt/conda/bin/x86_64-conda-linux-gnu-gcc /opt/conda/bin/gcc
    else
        echo "[serve_vllm] gcc not found — installing via apt (one-time)"
        apt-get update -qq >/dev/null 2>&1 || true
        apt-get install -y -qq gcc 2>&1 | tail -2
    fi
fi
export PATH="/opt/conda/bin:${PATH}:/usr/bin"
export CC="${CC:-$(command -v gcc)}"
if [ -z "${CC}" ]; then
    echo "[serve_vllm] FATAL: still no gcc on PATH after install attempt" >&2
    exit 1
fi
echo "[serve_vllm] using CC=${CC}"

# Pin to GPU index 0 by default — that is this project's reserved device per
# the workspace CLAUDE.md. GPU 1 is reserved for vlm_budget_eval / agent_
# budget_eval. Override with CUDA_VISIBLE_DEVICES=... in the parent env.
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
echo "[serve_vllm] CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES}"

MODEL="${EVO_MODEL:-Qwen/Qwen2.5-32B-Instruct}"
PORT="${EVO_PORT:-8000}"
HOST="${EVO_HOST:-0.0.0.0}"
# 16384 fits FinanceBench long-context controller prompts (brief +
# multi-agent tape summaries can hit ~7-8k tokens at n_train=10).
MAX_LEN="${EVO_MAX_LEN:-16384}"
GPU_UTIL="${EVO_GPU_UTIL:-0.55}"

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
