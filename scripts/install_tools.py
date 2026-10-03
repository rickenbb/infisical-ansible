#!/usr/bin/env python3
"""Install pinned, checksum-verified release binaries only inside this repo."""

import hashlib
import io
from pathlib import Path
import platform
import tarfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def install(repo, version, archive, checksums, binary):
    base = f"https://github.com/{repo}/releases/download/v{version}"
    with urlopen(f"{base}/{checksums}", timeout=60) as response:
        manifest = response.read().decode()
    expected = next((line.split()[0] for line in manifest.splitlines()
                     if len(line.split()) == 2 and line.split()[1].lstrip("*") == archive), None)
    if not expected:
        raise RuntimeError(f"No published checksum for {archive}")
    with urlopen(f"{base}/{archive}", timeout=60) as response:
        payload = response.read()
    if hashlib.sha256(payload).hexdigest() != expected:
        raise RuntimeError(f"Checksum mismatch: {archive}")
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as bundle:
        matches = [m for m in bundle.getmembers() if m.isfile() and Path(m.name).name == binary]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one {binary} executable in {archive}")
        content = bundle.extractfile(matches[0]).read()
    destination = ROOT / ".tools/bin" / binary
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    destination.chmod(0o755)
    print(f"Installed {binary} {version} in .tools/bin")


def main():
    system = platform.system()
    arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64"}.get(platform.machine())
    if system not in ("Darwin", "Linux") or not arch:
        raise SystemExit("Supported controllers: macOS/Linux, arm64/amd64")
    install("Infisical/cli", "0.43.132", f"cli_0.43.132_{system.lower()}_{arch}.tar.gz",
            "checksums-darwin.txt" if system == "Darwin" else "checksums.txt", "infisical")
    act_arch = "arm64" if arch == "arm64" else "x86_64"
    install("nektos/act", "0.2.89", f"act_{system}_{act_arch}.tar.gz", "checksums.txt", "act")


if __name__ == "__main__":
    main()

