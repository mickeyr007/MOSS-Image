# Standalone bootstrap: keep this file after cleanup.
.DEFAULT_GOAL := help
SHELL := /bin/bash
REPO := https://github.com/mickeyr007/MOSS-Image.git
BRANCH := feature/macos-apple-silicon-support
.PHONY: help setup restore start verify status clean gradio-start
help:
	@printf 'make setup | restore | start | verify | status | clean\n'
setup:
	@set -euo pipefail; \
	if [[ ! -f recovery/recover.py ]]; then \
	  test "$$(uname -s)/$$(uname -m)" = Darwin/arm64; \
	  command -v git >/dev/null; command -v python3 >/dev/null; \
	  test "$$(find . -mindepth 1 -maxdepth 1 ! -name Makefile | wc -l | tr -d ' ')" = 0 || { echo 'Bootstrap directory must contain only Makefile.' >&2; exit 1; }; \
	  git clone --branch '$(BRANCH)' --single-branch '$(REPO)' .bootstrap-stage; \
	  cmp -s Makefile .bootstrap-stage/Makefile || { echo 'Bootstrap Makefile differs from saved branch.' >&2; exit 1; }; \
	  rsync -a --exclude=Makefile .bootstrap-stage/ ./; \
	  rm -rf .bootstrap-stage; \
	fi; \
	if ! command -v uv >/dev/null; then python3 -m venv .bootstrap-tools; .bootstrap-tools/bin/python -m pip install uv==0.13.6; export PATH="$$PWD/.bootstrap-tools/bin:$$PATH"; fi; \
	python3 recovery/recover.py setup
gradio-start:
	@bash scripts/gradio-mac.sh
restore:
	@test -f recovery/recover.py || { echo "Run make setup first." >&2; exit 1; }
	@python3 recovery/recover.py restore
start:
	@test -f comfyui/local/run.sh || { echo "Run make setup first." >&2; exit 1; }
	@bash comfyui/local/run.sh --lowvram --use-split-cross-attention
verify:
	@test -f recovery/recover.py || { echo "Run make setup first." >&2; exit 1; }
	@python3 recovery/recover.py verify
status:
	@if [[ -f recovery/recover.py ]]; then python3 recovery/recover.py status; else echo "Source, dependencies, custom nodes, and models: missing (run make setup)"; fi
clean:
	@if [[ -f recovery/recover.py ]]; then python3 recovery/recover.py clean; else echo "Only Makefile remains; nothing to clean."; fi
