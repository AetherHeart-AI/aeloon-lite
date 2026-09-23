#!/usr/bin/env python3
"""Publish a verified native installer set and update the fixed CDN page."""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

from oss_mirror import Oss, mirror_channels, sha256


ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = {
    "windows-x64": "aeloon-installer-windows-x64.zip",
    "macos-arm64": "aeloon-installer-macos-arm64.tar.gz",
    "linux-x86_64": "aeloon-installer-linux-x86_64.tar.gz",
    "linux-arm64": "aeloon-installer-linux-arm64.tar.gz",
}


def publish(directory: Path, commit: str, oss: Oss) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid installer build commit")
    expected = set(PLATFORMS.values())
    if {path.name for path in directory.iterdir() if path.is_file()} != expected:
        raise ValueError("Installer archives do not match the four-platform contract")

    # A superseded main build may upload its immutable binaries but must not roll the page back.
    latest = subprocess.run(
        ["gh", "api", "repos/AetherHeart-AI/aeloon-lite/commits/main", "--jq", ".sha"],
        text=True, capture_output=True, check=True,
    ).stdout.strip()
    if latest != commit:
        print(f"Skipping superseded installer build {commit}")
        return

    urls = {}
    for platform, name in PLATFORMS.items():
        path = directory / name
        if path.stat().st_size == 0:
            raise ValueError(f"Empty installer package: {name}")
        key = f"installer/{commit}/{platform}/{name}"
        oss.upload_immutable(path, key)
        urls[platform] = f"https://downloads.aeloon-lite.aetherheart.com/{key}"
        print(f"{name}: {sha256(path)}")

    # A download page must never become visible before stable metadata is usable.
    mirror_channels(ROOT / "channels", oss)

    template = (ROOT / "assets/download.html.template").read_text(encoding="utf-8")
    replacements = {
        "__WINDOWS_URL__": urls["windows-x64"],
        "__MACOS_URL__": urls["macos-arm64"],
        "__LINUX_X64_URL__": urls["linux-x86_64"],
        "__LINUX_ARM64_URL__": urls["linux-arm64"],
        "__COMMIT__": commit,
    }
    for marker, value in replacements.items():
        template = template.replace(marker, value)
    if re.search(r"__[A-Z0-9_]+__", template):
        raise ValueError("Download page has unresolved placeholders")
    with tempfile.TemporaryDirectory(prefix="aeloon-download-page-") as temporary:
        page = Path(temporary) / "download.html"
        page.write_text(template, encoding="utf-8")
        for name in ("install.sh", "install.ps1", "install-server.sh"):
            oss.upload_mutable(ROOT / name, name)
        oss.upload_mutable(page, "download.html")
    print("Published https://downloads.aeloon-lite.aetherheart.com/download.html")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    arguments = parser.parse_args()
    publish(arguments.directory, arguments.commit, Oss())


if __name__ == "__main__":
    main()
