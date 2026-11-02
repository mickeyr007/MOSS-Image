#!/usr/bin/env bash
set -euo pipefail
moss_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
export COMFYUI_ROOT="${COMFYUI_ROOT:-$moss_root/local/ComfyUI}"
COMFY_VENV_ARGS=()
if [[ $# -ne 0 ]]; then
  printf "Usage: bash comfyui/local/setup.sh\n" >&2
  exit 2
fi
if [[ ! -e "$COMFYUI_ROOT" ]]; then
  mkdir -p "$(dirname -- "$COMFYUI_ROOT")"
  git clone https://github.com/Comfy-Org/ComfyUI.git "$COMFYUI_ROOT"
fi
if [[ ! -f "$COMFYUI_ROOT/main.py" ]]; then
  printf "Not a ComfyUI checkout: %s\n" "$COMFYUI_ROOT" >&2
  exit 1
fi
cd "$COMFYUI_ROOT"
mkdir -p local
if [[ -f local/env.sh ]]; then
  source local/env.sh
fi
moss_python="${MOSS_PYTHON:-python3.12}"
uv venv --python "$moss_python" --allow-existing "${COMFY_VENV_ARGS[@]+"${COMFY_VENV_ARGS[@]}"}" .venv
if [[ -n "${COMFY_SETUP:-}" ]]; then
  bash "$COMFY_SETUP"
fi
uv pip install --python .venv/bin/python \
  --link-mode copy -r requirements.txt
.venv/bin/python "$moss_root/comfyui/install.py" --comfy-root "$COMFYUI_ROOT"
