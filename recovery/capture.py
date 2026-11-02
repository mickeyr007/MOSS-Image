"""Capture the current local model inventory. Run only when intentionally updating it."""
import hashlib
import json
from pathlib import Path
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
API = HfApi()
REPOS = {
    "sft": ("model", "OpenMOSS-Team/MOSS-Image-SFT"),
    "comfy": ("model", "Comfy-Org/MOSS-Image"),
    "edit": ("model", "chinoll/Moss-Image-Edit"),
    "reactor": ("dataset", "Gourieff/ReActor"),
    "nsfw": ("model", "AdamCodd/vit-base-nsfw-detector"),
}
INFO = {}
for key, (kind, repo) in REPOS.items():
    info = API.dataset_info(repo, files_metadata=True) if kind == "dataset" else API.model_info(repo, files_metadata=True)
    INFO[key] = (kind, repo, info.sha, {s.rfilename: s for s in info.siblings})

def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def source_for(path):
    rel = path.relative_to(ROOT).as_posix()
    if rel.startswith("models/MOSS-Image-SFT/"):
        return "sft", rel.removeprefix("models/MOSS-Image-SFT/")
    prefix = "local/ComfyUI/models/"
    sub = rel.removeprefix(prefix)
    if sub in {
        "diffusion_models/moss_image_sft_int8_convrot.safetensors",
        "text_encoders/qwen3.5_9b_int8_convrot.safetensors",
        "vae/flux2-vae_small.safetensors",
    }:
        return "comfy", sub
    if sub == "model_patches/adapter_model.safetensors":
        return "edit", "adapter_model.safetensors"
    if sub.startswith("nsfw_detector/vit-base-nsfw-detector/"):
        return "nsfw", sub.rsplit("/", 1)[-1]
    if sub == "insightface/inswapper_128.onnx":
        return "reactor", "models/inswapper_128.onnx"
    if sub.startswith("facerestore_models/"):
        return "reactor", "models/" + sub
    return None

entries = []
for base in (ROOT / "models/MOSS-Image-SFT", ROOT / "local/ComfyUI/models"):
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.name.startswith("put_") or path.name == ".DS_Store":
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("local/ComfyUI/models/configs/"):
            continue  # These templates are tracked in the pinned ComfyUI checkout.
        entry = {"path": rel, "size": path.stat().st_size, "sha256": sha256(path)}
        source = source_for(path)
        if source:
            kind, repo, revision, siblings = INFO[source[0]]
            sibling = siblings.get(source[1])
            remote_sha = (sibling.lfs or {}).get("sha256") if sibling else None
            if sibling and (remote_sha is None or remote_sha == entry["sha256"]):
                entry["source"] = {"kind": kind, "repo": repo, "revision": revision, "file": source[1], "url": f"https://huggingface.co/{'datasets/' if kind == 'dataset' else ''}{repo}/resolve/{revision}/{source[1]}"}
                if remote_sha:
                    entry["source_sha256"] = remote_sha
            else:
                entry["external_backup_required"] = True
                entry["source_mismatch"] = f"{repo}/{source[1]}"
        else:
            entry["external_backup_required"] = True
        entries.append(entry)
        print(rel, "download" if "source" in entry else "BACKUP", flush=True)

manifest = {"schema": 1, "models": entries}
(ROOT / "recovery/model-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print("Entries:", len(entries), "external backup:", sum("external_backup_required" in e for e in entries))
