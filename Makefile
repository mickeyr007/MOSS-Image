.DEFAULT_GOAL := help

MOSS_PYTHON ?= python3.12
COMFYUI_ROOT ?= $(CURDIR)/local/ComfyUI
COMFY_EDIT_PLUGIN := $(COMFYUI_ROOT)/custom_nodes/ComfyUI-Moss-Image-Edit

.PHONY: help setup download start test comfy-setup comfy-edit-setup comfy-edit-download comfy-start comfy-edit-check

help:
	@printf 'MOSS-Image (Apple Silicon)\n'
	@printf 'Gradio:\n'
	@printf '  make setup     Install the Python environment\n'
	@printf '  make download  Download MOSS-Image-SFT weights\n'
	@printf '  make start     Start the local Gradio UI\n'
	@printf '  make test      Run MPS runtime tests\n'
	@printf 'ComfyUI image editing:\n'
	@printf '  make comfy-setup          Install ComfyUI and MOSS nodes\n'
	@printf '  make comfy-edit-setup     Install and check the MOSS Edit plugin\n'
	@printf '  make comfy-edit-download  Download the four editing model files\n'
	@printf '  make comfy-edit-check     Check plugin and model files\n'
	@printf '  make comfy-start          Start ComfyUI at http://127.0.0.1:8189\n'

setup:
	MOSS_PYTHON="$(MOSS_PYTHON)" bash scripts/setup-mac.sh

download:
	@test -x .venv/bin/hf || { echo 'Run make setup first.' >&2; exit 1; }
	.venv/bin/hf download OpenMOSS-Team/MOSS-Image-SFT --local-dir models/MOSS-Image-SFT

start:
	bash scripts/gradio-mac.sh

test:
	@test -x .venv/bin/python || { echo 'Run make setup first.' >&2; exit 1; }
	.venv/bin/python -m unittest discover -s tests -p test_mps_runtime.py -v

comfy-setup:
	COMFYUI_ROOT="$(COMFYUI_ROOT)" MOSS_PYTHON="$(MOSS_PYTHON)" bash comfyui/local/setup.sh

comfy-edit-setup:
	@test -x "$(COMFYUI_ROOT)/.venv/bin/python" || { echo 'Run make comfy-setup first.' >&2; exit 1; }
	@if [ ! -e "$(COMFY_EDIT_PLUGIN)" ]; then git clone https://github.com/Chenkin-x/ComfyUI-Moss-Image-Edit.git "$(COMFY_EDIT_PLUGIN)"; fi
	@test -f "$(COMFY_EDIT_PLUGIN)/install.py" || { echo 'MOSS Edit plugin is missing install.py.' >&2; exit 1; }
	"$(COMFYUI_ROOT)/.venv/bin/python" "$(COMFY_EDIT_PLUGIN)/install.py" --comfyui "$(COMFYUI_ROOT)"

comfy-edit-download:
	@test -x "$(COMFYUI_ROOT)/.venv/bin/hf" || { echo 'Run make comfy-setup first.' >&2; exit 1; }
	"$(COMFYUI_ROOT)/.venv/bin/hf" download Comfy-Org/MOSS-Image diffusion_models/moss_image_sft_int8_convrot.safetensors text_encoders/qwen3.5_9b_int8_convrot.safetensors vae/flux2-vae_small.safetensors --local-dir "$(COMFYUI_ROOT)/models"
	"$(COMFYUI_ROOT)/.venv/bin/hf" download chinoll/Moss-Image-Edit adapter_model.safetensors --local-dir "$(COMFYUI_ROOT)/models/model_patches"

comfy-edit-check:
	@test -x "$(COMFYUI_ROOT)/.venv/bin/python" || { echo 'Run make comfy-setup first.' >&2; exit 1; }
	@test -f "$(COMFY_EDIT_PLUGIN)/install.py" || { echo 'Run make comfy-edit-setup first.' >&2; exit 1; }
	"$(COMFYUI_ROOT)/.venv/bin/python" "$(COMFY_EDIT_PLUGIN)/install.py" --comfyui "$(COMFYUI_ROOT)"
	@for model in diffusion_models/moss_image_sft_int8_convrot.safetensors text_encoders/qwen3.5_9b_int8_convrot.safetensors vae/flux2-vae_small.safetensors model_patches/adapter_model.safetensors; do \
		test -s "$(COMFYUI_ROOT)/models/$$model" || { echo "Missing model: $$model (run make comfy-edit-download)." >&2; exit 1; }; \
	done

comfy-start:
	@test -x "$(COMFYUI_ROOT)/.venv/bin/python" || { echo 'Run make comfy-setup first.' >&2; exit 1; }
	COMFYUI_ROOT="$(COMFYUI_ROOT)" bash comfyui/local/run.sh --lowvram --use-split-cross-attention
