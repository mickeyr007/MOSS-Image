"""Pinned Apple Silicon installation and recovery checks."""
import getpass
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMFY = ROOT / "local/ComfyUI"
ARCHIVE = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/MOSS-Image-Recovery/moss-private.dmg"
NODES = {
    "ComfyUI": (COMFY, "https://github.com/Comfy-Org/ComfyUI.git", "edb3db00fd88f059e748c8a400391b5eab76266b"),
    "ReActor": (COMFY / "custom_nodes/ComfyUI-ReActor", "https://github.com/Gourieff/ComfyUI-ReActor.git", "0763f707e3f791323f2e7450d100a25860df546c"),
    "Moss-Image-Edit": (COMFY / "custom_nodes/ComfyUI-Moss-Image-Edit", "https://github.com/Chenkin-x/ComfyUI-Moss-Image-Edit.git", "b3377be990c0fa296459a20a4503dda40c045b4b"),
}

def run(*args, cwd=None, input=None):
    return subprocess.run(args, cwd=cwd, input=input, text=True, check=True)

def output(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()

def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def models():
    return json.loads((ROOT / "recovery/model-manifest.json").read_text())["models"]

def check_platform():
    if sys.platform != "darwin" or output("uname", "-m") != "arm64":
        raise SystemExit("Native Apple Silicon macOS is required")

def checkout(path, url, commit):
    if not (path / ".git").exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        bundle = ROOT / "private/git-bundles" / (path.name + ".bundle")
        run("git", "clone", str(bundle) if bundle.is_file() else url, str(path))
        if bundle.is_file():
            run("git", "remote", "set-url", "origin", url, cwd=path)
    if output("git", "rev-parse", "HEAD", cwd=path) != commit:
        if output("git", "status", "--porcelain", cwd=path):
            raise SystemExit(f"Refusing to change modified checkout: {path}")
        bundle = ROOT / "private/git-bundles" / (path.name + ".bundle")
        run("git", "fetch", str(bundle) if bundle.is_file() else "origin", commit, cwd=path)
        run("git", "checkout", "--detach", commit, cwd=path)

def setup():
    check_platform()
    if not shutil.which("uv"):
        raise SystemExit("Install public tooling first: brew install uv")
    if (ROOT / ".git").exists():
        remotes = output("git", "remote", cwd=ROOT).splitlines()
        if "upstream" not in remotes:
            run("git", "remote", "add", "upstream", "https://github.com/OpenMOSS/MOSS-Image.git", cwd=ROOT)
        run("git", "remote", "set-url", "--push", "upstream", "DISABLED", cwd=ROOT)
    run("uv", "python", "install", "3.12.8")
    for path, url, commit in NODES.values():
        checkout(path, url, commit)
    for venv, requirements in ((ROOT / ".venv", "moss"), (COMFY / ".venv", "comfy")):
        run("uv", "venv", "--python", "3.12.8", "--allow-existing", str(venv))
        run("uv", "pip", "install", "--python", str(venv / "bin/python"), "-r", str(ROOT / f"recovery/{requirements}-requirements.txt"))
    run("uv", "pip", "install", "--python", str(ROOT / ".venv/bin/python"), "--no-deps", "-e", str(ROOT))
    run(str(COMFY / ".venv/bin/python"), str(ROOT / "comfyui/install.py"), "--comfy-root", str(COMFY))
    run(str(COMFY / ".venv/bin/python"), str(COMFY / "custom_nodes/ComfyUI-Moss-Image-Edit/install.py"), "--comfyui", str(COMFY))
    if os.environ.get("MOSS_SKIP_MODELS") != "1":
        run(str(ROOT / ".venv/bin/python"), str(ROOT / "recovery/recover.py"), "download")
    status()

def download_models():
    from huggingface_hub import hf_hub_download
    for entry in models():
        target = ROOT / entry["path"]
        if target.is_file() and digest(target) == entry["sha256"]:
            continue
        source = entry.get("source")
        if not source:
            print("Needs private archive:", entry["path"])
            continue
        (ROOT / "local").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="moss-download-", dir=ROOT / "local") as tmp:
            downloaded = hf_hub_download(source["repo"], filename=source["file"], revision=source["revision"], repo_type=source["kind"], local_dir=tmp)
            if digest(downloaded) != entry["sha256"]:
                raise SystemExit(f"Downloaded checksum mismatch: {entry['path']}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(downloaded, target)

def status():
    for name, (path, _, commit) in NODES.items():
        got = output("git", "rev-parse", "HEAD", cwd=path) if (path / ".git").exists() else "missing"
        print(f"{name}: {'OK' if got == commit else got}")
    for name, path in (("MOSS Python", ROOT / ".venv/bin/python"), ("Comfy Python", COMFY / ".venv/bin/python")):
        print(f"{name}: {'OK' if path.exists() else 'missing'}")
    missing = [e["path"] for e in models() if not (ROOT / e["path"]).is_file()]
    print(f"Models: {len(models())-len(missing)}/{len(models())} present")
    for item in missing:
        print("  missing:", item)
    print("Private archive:", ARCHIVE if ARCHIVE.exists() else "missing")

def verify():
    check_platform()
    errors = []
    for name, (path, _, commit) in NODES.items():
        if not (path / ".git").exists() or output("git", "rev-parse", "HEAD", cwd=path) != commit:
            errors.append(f"{name} revision")
    for entry in models():
        target = ROOT / entry["path"]
        if not target.is_file() or digest(target) != entry["sha256"]:
            errors.append(entry["path"])
    for name, path in (("MOSS", ROOT / ".venv/bin/python"), ("Comfy", COMFY / ".venv/bin/python")):
        if not path.exists():
            errors.append(name + " Python")
    if shutil.which("uv"):
        for name, venv in (("moss", ROOT / ".venv"), ("comfy", COMFY / ".venv")):
            if (venv / "bin/python").exists():
                expected = set((ROOT / f"recovery/{name}-requirements.txt").read_text().splitlines())
                installed = set(line for line in output("uv", "pip", "freeze", "--python", str(venv / "bin/python")).splitlines() if not line.startswith("-e "))
                if not expected.issubset(installed):
                    errors.append(f"{name} package versions: {sorted(expected - installed)}")
    else:
        errors.append("uv unavailable for package verification")
    for base in (ROOT / "comfyui/moss-image/example_workflows", COMFY / "user/default/workflows"):
        for path in base.glob("*.json"):
            json.loads(path.read_text())
    if errors:
        raise SystemExit("Verification failed: " + ", ".join(errors))
    print("Source revisions, models, environments, and workflow JSON: OK")

def restore():
    if not ARCHIVE.is_file():
        raise SystemExit(f"Missing iCloud archive: {ARCHIVE}")
    receipt = json.loads((ARCHIVE.parent / "recovery-receipt.json").read_text())
    if output("git", "rev-parse", "HEAD", cwd=ROOT) != receipt["commit"] or digest(ARCHIVE) != receipt["archive_sha256"]:
        raise SystemExit("Git commit or encrypted archive differs from recovery receipt")
    password = getpass.getpass("Encrypted iCloud archive password: ")
    with tempfile.TemporaryDirectory(prefix="moss-mounted-") as mount:
        run("hdiutil", "attach", "-quiet", "-nobrowse", "-mountpoint", mount, "-stdinpass", str(ARCHIVE), input=password + "\n")
        try:
            source = Path(mount)
            inventory = json.loads((source / "private-manifest.json").read_text())
            planned = []
            for item in inventory["files"]:
                rel = Path(item["path"])
                if rel.is_absolute() or ".." in rel.parts:
                    raise SystemExit("Invalid archive path")
                src = source / rel
                if digest(src) != item["sha256"]:
                    raise SystemExit(f"Archive checksum mismatch: {rel}")
                dst = ROOT / rel
                if dst.exists() and digest(dst) != item["sha256"]:
                    seed = ROOT / "comfyui/moss-image/example_workflows" / rel.name
                    seeded_workflow = rel.parts[:4] == ("local", "ComfyUI", "user", "default") and rel.parent.name == "workflows" and seed.is_file() and digest(dst) == digest(seed)
                    if not seeded_workflow:
                        raise SystemExit(f"Refusing to overwrite: {dst}")
                planned.append((src, dst))
            for src, dst in planned:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            print(f"Restored {len(inventory['files'])} private files")
        finally:
            run("hdiutil", "detach", "-quiet", mount)

def clean():
    approval = ROOT / "recovery/approved-cleanup.json"
    entries = sorted(p.name for p in ROOT.iterdir() if p.name != "Makefile")
    print("Proposed deletion within", ROOT.resolve())
    for name in entries:
        print("  ", name)
    if not approval.is_file():
        raise SystemExit("Cleanup locked: explicit approval of this manifest has not been recorded.")
    approved = json.loads(approval.read_text())
    if approved.get("directory") != str(ROOT.resolve()) or approved.get("entries") != entries:
        raise SystemExit("Cleanup manifest changed; refusing deletion")
    receipt = ARCHIVE.parent / "recovery-receipt.json"
    if not receipt.is_file() or digest(ARCHIVE) != json.loads(receipt.read_text())["archive_sha256"]:
        raise SystemExit("Private archive verification failed; refusing deletion")
    if input("Type DELETE MOSS-IMAGE to remove these entries: ").strip() != "DELETE MOSS-IMAGE":
        raise SystemExit("Cleanup cancelled")
    for name in entries:
        path = ROOT / name
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
    print("Only Makefile remains")

if __name__ == "__main__":
    {"setup": setup, "download": download_models, "restore": restore, "verify": verify, "status": status, "clean": clean}[sys.argv[1]]()
