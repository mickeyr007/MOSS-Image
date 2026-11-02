import argparse
import logging
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def link(root, name):
    source = ROOT / name
    target = root / "custom_nodes" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if target.resolve() != source.resolve():
            raise FileExistsError(f"Another node installation exists: {target}")
        return
    target.symlink_to(os.path.relpath(source, target.parent), target_is_directory=True)


def install(root):
    if not (root / "main.py").is_file():
        raise FileNotFoundError(f"Not a ComfyUI checkout: {root}")
    link(root, "moss-image")
    workflows = root / "user/default/workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    for name in ("moss-image.json", "moss-image-native-sft.json"):
        source = ROOT / "moss-image/example_workflows" / name
        target = workflows / name
        if not target.exists():
            shutil.copy2(source, target)
    logging.info("Installed MOSS-Image custom nodes into %s", root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-root", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    install(args.comfy_root.resolve())


if __name__ == "__main__":
    main()
