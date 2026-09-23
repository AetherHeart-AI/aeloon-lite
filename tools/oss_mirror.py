#!/usr/bin/env python3
"""Mirror verified public distribution assets into the private CDN origin bucket."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


REPOSITORY = "AetherHeart-AI/aeloon-lite"
RUNTIME_ASSETS = {
    "aeloon-runtime-darwin-aarch64.tar.zst",
    "aeloon-runtime-linux-aarch64.tar.gz",
    "aeloon-runtime-linux-aarch64.tar.zst",
    "aeloon-runtime-linux-x86_64.tar.gz",
    "aeloon-runtime-linux-x86_64.tar.zst",
    "aeloon-runtime-windows-x86_64.tar.zst",
}
IMMUTABLE_CACHE = "public,max-age=2592000,immutable"
MUTABLE_CACHE = "public,max-age=60"


def run(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, text=True, capture_output=capture, check=False)
    if result.returncode:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"{' '.join(args[:2])} failed: {detail}")
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def expected_names(tag: str, actual: set[str]) -> set[str]:
    unified = re.fullmatch(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", tag)
    runtime = re.fullmatch(r"runtime-v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", tag)
    if not unified and not runtime:
        raise ValueError(f"Unsupported official tag: {tag}")
    if unified:
        version = tag[1:]
        return RUNTIME_ASSETS | {
            f"aeloon-lite-{version}-arm64.deb",
            f"aeloon-lite-{version}-arm64.dmg",
            f"aeloon-lite-{version}-arm64.rpm",
            f"aeloon-lite-{version}-x86_64.deb",
            f"aeloon-lite-{version}-x86_64.rpm",
            f"aeloon-lite-{version}-x64.exe",
            f"aeloon-client-{version}.tar.gz",
        }
    clients = {name for name in actual if re.fullmatch(r"aeloon-client-\d+\.\d+\.\d+\.tar\.gz", name)}
    if len(clients) > 1:
        raise ValueError("Runtime Release has multiple client archives")
    return RUNTIME_ASSETS | clients


def content_type(name: str) -> str:
    if name.endswith(".json"):
        return "application/json; charset=utf-8"
    if name.endswith(".html"):
        return "text/html; charset=utf-8"
    if name.endswith((".sh", ".ps1", ".sha256")) or name == "stable":
        return "text/plain; charset=utf-8"
    return "application/octet-stream"


class Oss:
    def __init__(self) -> None:
        self.bucket = os.environ.get("AELOON_OSS_BUCKET", "aeloon-lite")
        self.region = os.environ.get("AELOON_OSS_REGION", "cn-beijing")
        self.endpoint = os.environ.get(
            "AELOON_OSS_ENDPOINT", "https://oss-cn-beijing.aliyuncs.com"
        )

    def command(self, *args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
        return run("ossutil", *args, "--region", self.region, "--endpoint", self.endpoint, capture=capture)

    def url(self, key: str) -> str:
        if key.startswith("/") or ".." in key.split("/"):
            raise ValueError("Unsafe OSS key")
        return f"oss://{self.bucket}/{key}"

    def stat(self, key: str) -> dict[str, str] | None:
        result = subprocess.run(
            ["ossutil", "stat", self.url(key), "--region", self.region, "--endpoint", self.endpoint],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            output = result.stdout + result.stderr
            if re.search(r"NoSuchKey|404|ObjectNotExist", output, re.IGNORECASE):
                return None
            raise RuntimeError(f"OSS stat failed for {key}: {output.strip()}")
        return dict(re.findall(r"^\s*([\w-]+)\s*:\s*(\S+)\s*$", result.stdout, re.MULTILINE))

    def local_crc64(self, path: Path) -> str:
        output = self.command("hash", str(path), "--type=crc64", capture=True).stdout
        match = re.search(r"CRC64[-\w]*\s*:\s*(\d+)", output, re.IGNORECASE)
        if not match:
            raise RuntimeError(f"Could not read local CRC-64 for {path.name}")
        return match.group(1)

    def verify_object(self, path: Path, key: str) -> None:
        metadata = self.stat(key)
        if metadata is None:
            raise RuntimeError(f"OSS object is missing: {key}")
        if metadata.get("Content-Length") != str(path.stat().st_size):
            raise RuntimeError(f"OSS object size differs: {key}")
        if metadata.get("X-Oss-Hash-Crc64ecma") != self.local_crc64(path):
            raise RuntimeError(f"OSS object CRC-64 differs: {key}")

    def upload_immutable(self, path: Path, key: str) -> None:
        existing = self.stat(key)
        if existing is not None:
            with tempfile.TemporaryDirectory(prefix="aeloon-oss-compare-") as temporary:
                downloaded = Path(temporary) / path.name
                self.command("cp", self.url(key), str(downloaded), "--force", "--no-progress")
                if sha256(downloaded) != sha256(path):
                    raise RuntimeError(f"Refusing to overwrite different OSS object: {key}")
            self.verify_object(path, key)
            return
        self.command(
            "cp", str(path), self.url(key), "--ignore-existing", "--no-progress",
            "--acl", "private", "--cache-control", IMMUTABLE_CACHE,
            "--content-type", content_type(path.name),
        )
        self.verify_object(path, key)

    def upload_mutable(self, path: Path, key: str) -> None:
        self.command(
            "cp", str(path), self.url(key), "--force", "--no-progress", "--acl", "private",
            "--cache-control", MUTABLE_CACHE, "--content-type", content_type(path.name),
        )
        with tempfile.TemporaryDirectory(prefix="aeloon-oss-check-") as temporary:
            downloaded = Path(temporary) / path.name
            self.command("cp", self.url(key), str(downloaded), "--force", "--no-progress")
            if sha256(downloaded) != sha256(path):
                raise RuntimeError(f"OSS mutable object differs: {key}")

    def read_json(self, key: str) -> dict:
        with tempfile.TemporaryDirectory(prefix="aeloon-oss-read-") as temporary:
            path = Path(temporary) / "manifest.json"
            self.command("cp", self.url(key), str(path), "--force", "--no-progress")
            return json.loads(path.read_text(encoding="utf-8"))


def mirror_release(tag: str, asset_dir: Path | None, allow_draft: bool, oss: Oss) -> None:
    release = json.loads(
        run(
            "gh", "release", "view", tag, "--repo", REPOSITORY,
            "--json", "tagName,isDraft,isPrerelease,assets", capture=True,
        ).stdout
    )
    if release["tagName"] != tag or release["isPrerelease"] or (release["isDraft"] and not allow_draft):
        raise RuntimeError(f"Release {tag} is not an eligible official Release")
    listed = release["assets"]
    assets = {asset["name"]: asset for asset in listed}
    if len(assets) != len(listed) or set(assets) != expected_names(tag, set(assets)):
        raise RuntimeError(f"Release {tag} has an unexpected asset set")

    with tempfile.TemporaryDirectory(prefix="aeloon-release-mirror-") as temporary:
        local = asset_dir or Path(temporary) / "assets"
        if asset_dir is None:
            local.mkdir()
            run("gh", "release", "download", tag, "--repo", REPOSITORY, "--dir", str(local))
        if {path.name for path in local.iterdir() if path.is_file()} != set(assets):
            raise RuntimeError("Local assets do not match the official Release")
        manifest_assets = []
        for name in sorted(assets):
            path = local / name
            remote = assets[name]
            digest = remote.get("digest")
            size = remote.get("size")
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest or "") or size != path.stat().st_size:
                raise RuntimeError(f"Missing or mismatched GitHub asset metadata: {name}")
            if sha256(path) != digest:
                raise RuntimeError(f"GitHub asset digest differs: {name}")
            manifest_assets.append({"name": name, "size": size, "digest": digest})

        for name in sorted(assets):
            oss.upload_immutable(local / name, f"releases/{tag}/{name}")
            # POSIX desktop scripts can verify mirror downloads without jq.
            checksum = Path(temporary) / f"{name}.sha256"
            checksum.write_text(f"{assets[name]['digest'].removeprefix('sha256:')}  {name}\n", encoding="ascii")
            oss.upload_immutable(checksum, f"releases/{tag}/{name}.sha256")
            size = Path(temporary) / f"{name}.size"
            size.write_text(f"{assets[name]['size']}\n", encoding="ascii")
            oss.upload_immutable(size, f"releases/{tag}/{name}.size")
        manifest = Path(temporary) / "manifest.json"
        manifest.write_text(
            json.dumps({"schema": 1, "tag": tag, "assets": manifest_assets}, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        oss.upload_immutable(manifest, f"releases/{tag}/manifest.json")
        print(f"Mirrored official Release {tag} to oss://{oss.bucket}/releases/{tag}/")


def mirror_channels(directory: Path, oss: Oss) -> None:
    channels: dict[str, Path] = {}
    for product in ("desktop", "runtime"):
        path = directory / product / "stable"
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) != 5 or lines[0] != "# aeloon-release-v2" or lines[1] != f"# product={product}":
            raise RuntimeError(f"Invalid {product} stable channel")
        release = [line.removeprefix("# release=") for line in lines if line.startswith("# release=")]
        if len(release) != 1:
            raise RuntimeError(f"Missing {product} Release tag")
        tag = release[0]
        manifest = oss.read_json(f"releases/{tag}/manifest.json")
        if manifest.get("schema") != 1 or manifest.get("tag") != tag:
            raise RuntimeError(f"Invalid mirror manifest for {tag}")
        names = {asset["name"] for asset in manifest["assets"]}
        if names != expected_names(tag, names):
            raise RuntimeError(f"Incomplete mirror manifest for {tag}")
        if product == "runtime" and len([name for name in names if name.startswith("aeloon-client-")]) != 1:
            raise RuntimeError(f"Runtime stable {tag} has no matching client archive")
        channels[product] = path
    for product, path in channels.items():
        oss.upload_mutable(path, f"channels/{product}/stable")
    print("Mirrored both current stable channels")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    release = subparsers.add_parser("release")
    release.add_argument("--tag", required=True)
    release.add_argument("--asset-dir", type=Path)
    release.add_argument("--allow-draft", action="store_true")
    channels = subparsers.add_parser("channels")
    channels.add_argument("--directory", type=Path, required=True)
    arguments = parser.parse_args()
    oss = Oss()
    if arguments.command == "release":
        mirror_release(arguments.tag, arguments.asset_dir, arguments.allow_draft, oss)
    else:
        mirror_channels(arguments.directory, oss)


if __name__ == "__main__":
    main()
