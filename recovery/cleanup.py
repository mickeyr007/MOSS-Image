"""Fail-closed, per-file audit for the standalone cleanup command."""

import getpass
import base64
import csv
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def command(*args, cwd=None, input=None, capture=True):
    return subprocess.run(args, cwd=cwd, input=input, text=True, check=True,
                          capture_output=capture)


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git(repo, *args):
    return command("git", *args, cwd=repo).stdout


def inventory(root):
    """Include symlinks, never traversing them or leaving root."""
    result = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        base = Path(base)
        for name in list(dirs):
            path = base / name
            if path.is_symlink():
                dirs.remove(name)
                result[path.relative_to(root).as_posix()] = path
        for name in files:
            path = base / name
            result[path.relative_to(root).as_posix()] = path
    return result


def approved_entries(root, approval, commit):
    approved = json.loads(approval.read_text())
    current = {p.name: p for p in root.iterdir() if p.name != "Makefile"}
    names = {item["name"] for item in approved.get("delete", [])}
    if (approved.get("directory") != str(root.resolve()) or
            approved.get("remote_commit") != commit or
            not set(current).issubset(names) or
            any(name in ("", ".", "..", "Makefile") or "/" in name for name in names)):
        raise SystemExit("Cleanup approval differs from directory, commit, or current entry names")
    return current


def repositories(root, nodes):
    repos = [(root, git(root, "rev-parse", "HEAD").strip())]
    for path, _, expected in nodes.values():
        if not (path / ".git").is_dir() or git(path, "rev-parse", "HEAD").strip() != expected:
            raise SystemExit(f"Nested checkout is not at its pinned commit: {path}")
        repos.append((path, expected))
    return repos


def changes(repo):
    tracked = set(git(repo, "diff", "HEAD", "--name-only", "-z").split("\0")) - {""}
    untracked = set(git(repo, "ls-files", "--others", "--exclude-standard", "-z").split("\0")) - {""}
    return tracked, untracked


def snapshot(root):
    result = {}
    for rel, path in inventory(root).items():
        stat = path.lstat()
        result[rel] = (stat.st_mode, stat.st_size, stat.st_mtime_ns,
                       os.readlink(path) if path.is_symlink() else None)
    return result


def installed_venv_files(venv):
    """Accept installed files recorded by wheels, plus uv's venv scaffolding."""
    allowed = set()
    for record in venv.glob("lib/python*/site-packages/*.dist-info/RECORD"):
        with record.open(newline="") as stream:
            for name, signature, _ in csv.reader(stream):
                path = (record.parent.parent / name).resolve()
                if not path.is_relative_to(venv.resolve()) or not path.is_file():
                    continue
                if signature.startswith("sha256="):
                    expected = signature.partition("=")[2].rstrip("=")
                    got = base64.urlsafe_b64encode(bytes.fromhex(sha(path))).decode().rstrip("=")
                    if got != expected:
                        continue
                allowed.add(path.relative_to(venv.resolve()).as_posix())
    scaffolding = {"pyvenv.cfg", "CACHEDIR.TAG", ".lock", ".gitignore"}
    scaffolding.update(f"bin/{name}" for name in (
        "python", "python3", "python3.12", "activate", "activate.csh", "activate.fish",
        "activate.nu", "activate.ps1", "Activate.ps1", "activate_this.py", "deactivate.bat",
        "activate.bat", "activate.xsh", "pydoc.bat"))
    return allowed, scaffolding


def audit(root, nodes, model_entries, archive_files, backup_files):
    """Return unknown paths. Each file/symlink is visited, including ignored files."""
    repos = repositories(root, nodes)
    repo_data = []
    for repo, _ in repos:
        tracked = set(git(repo, "ls-files", "-z").split("\0")) - {""}
        changed, untracked = changes(repo)
        repo_data.append((repo, tracked, changed, untracked))
    model_paths = {e["path"] for e in model_entries
                   if e.get("source") or e["path"] in archive_files}
    venvs = {}
    for rel in (".venv", "local/ComfyUI/.venv"):
        path = root / rel
        if path.is_dir():
            venvs[rel] = installed_venv_files(path)
    unknown = []
    for rel, path in inventory(root).items():
        if rel == "Makefile":
            continue
        # A nested checkout owns its files, even though the parent ignores it.
        owner = next((data for data in reversed(repo_data)
                      if path == data[0] or data[0] in path.parents), None)
        if owner is None:
            unknown.append(rel)
            continue
        repo, tracked, changed, untracked = owner
        sub = path.relative_to(repo).as_posix()
        if sub == ".git" or sub.startswith(".git/"):
            # Every Git administrative file is copied into the encrypted image.
            continue
        if rel == "local/.restore-manifest.json":
            # Recreated by make restore; its contents were checked against the archive.
            continue
        if sub in tracked:
            if sub not in changed or rel in backup_files:
                continue
            unknown.append(rel)
            continue
        if sub in untracked and rel in backup_files:
            continue
        if rel in archive_files or rel in model_paths:
            continue
        venv = next((name for name in venvs if rel.startswith(name + "/")), None)
        if venv:
            subvenv = rel[len(venv) + 1:]
            allowed, scaffolding = venvs[venv]
            if subvenv in allowed or subvenv in scaffolding:
                continue
        if rel == "local/ComfyUI/custom_nodes/moss-image" and path.is_symlink():
            if path.resolve() == root / "comfyui/moss-image":
                continue
        if (path.name == ".DS_Store" or path.suffix in (".pyc", ".pyo", ".log") or
                "__pycache__" in path.parts or ".pytest_cache" in path.parts or
                ".ruff_cache" in path.parts or "moss_image.egg-info" in path.parts):
            continue
        unknown.append(rel)
    return unknown


def mount_image(image, password, mount):
    result = subprocess.run(("hdiutil", "attach", "-nobrowse", "-mountpoint", str(mount),
                             "-stdinpass", str(image)), input=password + "\n", text=True,
                            capture_output=True)
    if result.returncode:
        raise SystemExit(f"Cannot mount encrypted backup: {result.stderr.strip()}")


def check_private_archive(archive, receipt, marker, password):
    if not archive.is_file() or sha(archive) != receipt["archive_sha256"]:
        raise SystemExit("Private archive checksum differs from receipt")
    with tempfile.TemporaryDirectory(prefix="moss-check-mount-") as directory:
        mount = Path(directory)
        mount_image(archive, password, mount)
        try:
            manifest = json.loads((mount / "private-manifest.json").read_text())
            files = {item["path"]: item["sha256"] for item in manifest["files"]}
            if files != {item["path"]: item["sha256"] for item in marker["files"]}:
                raise SystemExit("Private archive inventory differs from restore marker")
            for rel, expected in files.items():
                relative = Path(rel)
                if relative.is_absolute() or ".." in relative.parts:
                    raise SystemExit(f"Invalid private archive path: {rel}")
                path = mount / rel
                if path.is_symlink() or not path.is_file() or sha(path) != expected:
                    raise SystemExit(f"Private archive file failed verification: {rel}")
            return files
        finally:
            command("hdiutil", "detach", "-quiet", str(mount))


def save_changes(root, repos, cloud):
    """Create a separate encrypted image; no plaintext staging files."""
    selections = []
    for repo, commit in repos:
        modified, untracked = changes(repo)
        selections.append((repo, commit, modified, untracked))
    password = getpass.getpass("New local-changes archive password: ")
    if len(password) < 12 or password != getpass.getpass("Repeat password: "):
        raise SystemExit("New archive password mismatch or shorter than 12 characters")
    size = sum((repo / name).lstat().st_size for repo, _, _, names in selections for name in names)
    size += sum(sum(p.lstat().st_size for p in inventory(repo / ".git").values())
                for repo, _ in repos)
    image = cloud / f"moss-local-changes-{os.getpid()}.sparseimage"
    if image.exists():
        raise SystemExit(f"Refusing to overwrite: {image}")
    command("hdiutil", "create", "-quiet", "-size", f"{max(512, size // (1024 * 1024) + 512)}m",
            "-fs", "APFS", "-volname", "MOSS-Local-Changes", "-type", "SPARSE",
            "-encryption", "AES-256", "-stdinpass", str(image), input=password + "\n")
    files = set()
    manifest = []
    try:
        with tempfile.TemporaryDirectory(prefix="moss-changes-mount-") as directory:
            mount = Path(directory)
            mount_image(image, password, mount)
            try:
                for idx, (repo, commit, modified, untracked) in enumerate(selections):
                    dest = mount / f"repo-{idx}"
                    dest.mkdir()
                    shutil.copytree(repo / ".git", dest / "git-metadata", symlinks=True)
                    patch = dest / "tracked.patch"
                    with patch.open("wb") as stream:
                        subprocess.run(("git", "diff", "--binary", "HEAD"), cwd=repo,
                                       stdout=stream, check=True)
                    for rel in sorted(untracked):
                        src = repo / rel
                        target = dest / "untracked" / rel
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if src.is_symlink():
                            target.symlink_to(os.readlink(src))
                        elif src.is_file():
                            shutil.copy2(src, target)
                        else:
                            raise SystemExit(f"Unsupported untracked entry: {src}")
                    for rel in modified | untracked:
                        files.add((repo / rel).relative_to(root).as_posix())
                    manifest.append({"index": idx, "repo": repo.relative_to(root).as_posix(),
                                     "commit": commit, "modified": sorted(modified),
                                     "untracked": sorted(untracked)})
                (mount / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            finally:
                command("hdiutil", "detach", "-quiet", str(mount))
        # Read it back after remount; test each patch against a clean Git index.
        with tempfile.TemporaryDirectory(prefix="moss-check-mount-") as directory:
            mount = Path(directory)
            mount_image(image, password, mount)
            try:
                if json.loads((mount / "manifest.json").read_text()) != manifest:
                    raise SystemExit("Local changes manifest did not round trip")
                for item in manifest:
                    repo = root / item["repo"]
                    dest = mount / f"repo-{item['index']}"
                    original_git = inventory(repo / ".git")
                    saved_git = inventory(dest / "git-metadata")
                    if original_git.keys() != saved_git.keys():
                        raise SystemExit(f"Git metadata backup inventory differs: {repo}")
                    for rel, src in original_git.items():
                        dst = saved_git[rel]
                        if src.is_symlink():
                            if not dst.is_symlink() or os.readlink(src) != os.readlink(dst):
                                raise SystemExit(f"Git metadata symlink mismatch: {src}")
                        elif sha(src) != sha(dst):
                            raise SystemExit(f"Git metadata backup mismatch: {src}")
                    patch = dest / "tracked.patch"
                    if item["modified"]:
                        current_patch = subprocess.run(("git", "diff", "--binary", "HEAD"),
                                                       cwd=repo, stdout=subprocess.PIPE,
                                                       check=True).stdout
                        if patch.read_bytes() != current_patch:
                            raise SystemExit(f"Tracked edits changed during backup: {repo}")
                        env = dict(os.environ, GIT_INDEX_FILE=str(mount / f"index-{item['index']}"))
                        subprocess.run(("git", "read-tree", item["commit"]), cwd=repo, env=env, check=True)
                        subprocess.run(("git", "apply", "--cached", "--check", str(patch)),
                                       cwd=repo, env=env, check=True)
                    for rel in item["untracked"]:
                        src, dst = repo / rel, dest / "untracked" / rel
                        if src.is_symlink():
                            if not dst.is_symlink() or os.readlink(src) != os.readlink(dst):
                                raise SystemExit(f"Untracked symlink backup mismatch: {src}")
                        elif not dst.is_file() or sha(src) != sha(dst):
                            raise SystemExit(f"Untracked backup mismatch: {src}")
            finally:
                command("hdiutil", "detach", "-quiet", str(mount))
    except BaseException:
        # Keep a failed image for diagnosis; never proceed to deletion.
        raise
    print("Verified encrypted local changes image:", image)
    return files, image
