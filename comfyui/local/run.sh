#!/usr/bin/env bash
set -euo pipefail
moss_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
export COMFYUI_ROOT="${COMFYUI_ROOT:-$moss_root/local/ComfyUI}"
cd "$COMFYUI_ROOT"
COMFY_ARGS=()
if [[ -f local/env.sh ]]; then
  source local/env.sh
fi
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}"
export HF_HUB_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
exec .venv/bin/python "${COMFY_ENTRYPOINT:-main.py}" \
  --listen "${COMFY_HOST:-127.0.0.1}" --port "${COMFY_PORT:-8189}" \
  --disable-auto-launch --disable-metadata --fp32-vae \
  --preview-method latent2rgb --disable-api-nodes "${COMFY_ARGS[@]+"${COMFY_ARGS[@]}"}" "$@"
