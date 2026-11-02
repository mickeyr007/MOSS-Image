# Apple Silicon recovery

The saved public source is `mickeyr007/MOSS-Image`, branch
`feature/macos-apple-silicon-support`. Keep its tracked `Makefile` when cleaning
the local checkout. On an Apple Silicon Mac with Git, Make, and Python 3:

```sh
cd MOSS-Image
make setup
make restore
make verify
make start
```

`make setup` can run when `Makefile` is the only file in the directory. It clones
the saved branch, installs pinned Python 3.12.8 environments with `uv`, checks
out the pinned ComfyUI and custom-node commits, and downloads models from exact
Hugging Face revisions. Each download is checked against the SHA-256 in
`recovery/model-manifest.json`. Installation needs enough free space for about
43 GiB of models plus Python environments and temporary download space.

The manifest records the exact path, byte size, SHA-256, repository, revision,
and repository file for all 56 local model files. Seven model files (the two
face detection weights and five extracted `buffalo_l` files) require the
encrypted iCloud archive. The archive also contains original private
workflows, reference images, outputs, ComfyUI settings, and Git bundles for
the three nested checkouts. No model weights or private assets are committed.

The private archive lives at `~/Library/Mobile Documents/com~apple~CloudDocs/
MOSS-Image-Recovery/moss-private.dmg`. Its password must be retained separately.
`make restore` prompts for that password and checks every archived file's
SHA-256 before copying it. It refuses to overwrite a different existing file.
The adjacent `recovery-receipt.json` records the saved GitHub commit and archive
checksum. Check the receipt against a freshly downloaded iCloud copy before
any cleanup. Git bundles are kept as insurance if upstream node repositories
become unavailable; restoration normally checks out their pinned commits.

`make status` shows missing components. `make verify` checks the installed
commits, model checksums, environment presence, and workflow JSON. `make
gradio-start` launches the original Gradio UI; `make start` launches ComfyUI.

`make clean` is intentionally locked. A separate, reviewed deletion manifest
and explicit approval are required before the local installation can be
reduced to `Makefile`. Never remove shared model stores, shared caches, or
files outside the MOSS-Image directory.
