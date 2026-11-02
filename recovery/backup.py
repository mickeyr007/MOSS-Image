"""Create an encrypted private iCloud backup without changing source assets."""
import getpass
import os
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLOUD = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/MOSS-Image-Recovery"
MODEL_MANIFEST = json.loads((ROOT / "recovery/model-manifest.json").read_text())

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def files():
    for name in ("local/ComfyUI/input", "local/ComfyUI/output", "local/ComfyUI/user", "local/ComfyUI/local/api", "outputs"):
        base = ROOT / name
        if base.exists():
            yield from (p for p in base.rglob("*") if p.is_file() and p.name != ".DS_Store")
    for entry in MODEL_MANIFEST["models"]:
        if entry.get("external_backup_required"):
            yield ROOT / entry["path"]

def main():
    if not CLOUD.parent.is_dir():
        raise SystemExit("iCloud Drive is unavailable")
    CLOUD.mkdir(exist_ok=True)
    archive = CLOUD / "moss-private.dmg"
    if archive.exists():
        raise SystemExit(f"Refusing to overwrite existing archive: {archive}")
    with tempfile.TemporaryDirectory(prefix="moss-backup-stage-", dir=ROOT) as temp:
        stage = Path(temp)
        for src in files():
            dst = stage / src.relative_to(ROOT)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        for name, checkout in {
            "ComfyUI": ROOT / "local/ComfyUI",
            "ComfyUI-ReActor": ROOT / "local/ComfyUI/custom_nodes/ComfyUI-ReActor",
            "ComfyUI-Moss-Image-Edit": ROOT / "local/ComfyUI/custom_nodes/ComfyUI-Moss-Image-Edit",
        }.items():
            dst = stage / "private/git-bundles" / f"{name}.bundle"
            dst.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "bundle", "create", str(dst), "--all", "HEAD"], cwd=checkout, check=True)
        inventory = [{"path": p.relative_to(stage).as_posix(), "size": p.stat().st_size, "sha256": sha(p)} for p in sorted(stage.rglob("*")) if p.is_file()]
        (stage / "private-manifest.json").write_text(json.dumps({"schema": 1, "files": inventory}, indent=2) + "\n")
        password_file = os.environ.get("MOSS_BACKUP_PASSWORD_FILE")
        password = Path(password_file).read_text().strip() if password_file else getpass.getpass("New archive password: ")
        if len(password) < 12 or (not password_file and password != getpass.getpass("Repeat archive password: ")):
            raise SystemExit("Passwords differ or are shorter than 12 characters")
        subprocess.run(["hdiutil", "create", "-quiet", "-srcfolder", str(stage), "-volname", "MOSS-Image-Recovery", "-format", "UDZO", "-encryption", "AES-256", "-stdinpass", str(archive)], input=password + "\n", text=True, check=True)
    receipt = {"repo": "mickeyr007/MOSS-Image", "branch": "feature/macos-apple-silicon-support", "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "archive": archive.name, "archive_size": archive.stat().st_size, "archive_sha256": sha(archive), "files": len(inventory)}
    (CLOUD / "recovery-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))

if __name__ == "__main__":
    main()
