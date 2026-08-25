#!/usr/bin/env python3
"""Build and validate immutable Aeloon release manifests and channel pointers."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY = "AetherHeart-AI/aeloon-lite"
SEMVER = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def artifact_contract(product: str, version: str) -> dict[str, tuple[str, str, str, str]]:
    if product == "desktop":
        prefix = f"aeloon-lite-{version}"
        return {
            "darwin-arm64-dmg": ("darwin", "arm64", "dmg", f"{prefix}-arm64.dmg"),
            "linux-arm64-deb": ("linux", "arm64", "deb", f"{prefix}-arm64.deb"),
            "linux-arm64-rpm": ("linux", "arm64", "rpm", f"{prefix}-arm64.rpm"),
            "linux-x86_64-deb": ("linux", "x86_64", "deb", f"{prefix}-x86_64.deb"),
            "linux-x86_64-rpm": ("linux", "x86_64", "rpm", f"{prefix}-x86_64.rpm"),
        }
    if product == "runtime":
        return {
            "darwin-aarch64-tar.zst": (
                "darwin", "aarch64", "tar.zst", "aeloon-runtime-darwin-aarch64.tar.zst"
            ),
            "linux-aarch64-tar.zst": (
                "linux", "aarch64", "tar.zst", "aeloon-runtime-linux-aarch64.tar.zst"
            ),
            "linux-x86_64-tar.zst": (
                "linux", "x86_64", "tar.zst", "aeloon-runtime-linux-x86_64.tar.zst"
            ),
            "linux-aarch64-tar.gz": (
                "linux", "aarch64", "tar.gz", "aeloon-runtime-linux-aarch64.tar.gz"
            ),
            "linux-x86_64-tar.gz": (
                "linux", "x86_64", "tar.gz", "aeloon-runtime-linux-x86_64.tar.gz"
            ),
        }
    raise ValueError(f"unsupported product: {product}")


def release_tag(product: str, version: str) -> str:
    return ("v" if product == "desktop" else "runtime-v") + version


def source_repository(product: str) -> str:
    return {
        "desktop": "AetherHeart-AI/aeloon-lite-ui",
        "runtime": "AetherHeart-AI/aeloon-lite-runtime",
    }[product]


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON field: {key}")
        value[key] = item
    return value


def loads_json(source: str | bytes) -> Any:
    return json.loads(source, object_pairs_hook=_strict_object)


def read_json(path: Path) -> dict[str, Any]:
    value = loads_json(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_release(value: dict[str, Any]) -> None:
    required = {"schemaVersion", "product", "version", "tag", "source", "publishedAt", "artifacts"}
    if set(value) != required:
        raise ValueError(f"release manifest fields must be exactly {sorted(required)}")
    if value["schemaVersion"] != 1:
        raise ValueError("unsupported release manifest schemaVersion")
    product = value["product"]
    version = value["version"]
    if product not in {"desktop", "runtime"}:
        raise ValueError("product must be desktop or runtime")
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        raise ValueError("version must be semantic version syntax")
    tag = release_tag(product, version)
    if value["tag"] != tag:
        raise ValueError(f"tag must be {tag}")
    source = value["source"]
    if not isinstance(source, dict) or set(source) != {"repository", "commit"}:
        raise ValueError("source must contain exactly repository and commit")
    if source["repository"] != source_repository(product):
        raise ValueError("source repository does not match product")
    if not isinstance(source["commit"], str) or not COMMIT.fullmatch(source["commit"]):
        raise ValueError("source commit must be a full lowercase Git SHA")
    try:
        timestamp = datetime.fromisoformat(str(value["publishedAt"]).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("publishedAt must be ISO-8601") from error
    if timestamp.tzinfo is None:
        raise ValueError("publishedAt must include a timezone")

    expected = artifact_contract(product, version)
    artifacts = value["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != len(expected):
        raise ValueError(f"{product} release must contain {len(expected)} artifacts")
    seen: set[str] = set()
    for artifact in artifacts:
        fields = {"key", "os", "arch", "format", "name", "url", "sha256", "size"}
        if not isinstance(artifact, dict) or set(artifact) != fields:
            raise ValueError(f"artifact fields must be exactly {sorted(fields)}")
        key = artifact["key"]
        if key in seen or key not in expected:
            raise ValueError(f"duplicate or unknown artifact key: {key}")
        seen.add(key)
        os_name, arch, package_format, name = expected[key]
        if (artifact["os"], artifact["arch"], artifact["format"], artifact["name"]) != (
            os_name, arch, package_format, name
        ):
            raise ValueError(f"artifact contract mismatch for {key}")
        expected_url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}"
        if artifact["url"] != expected_url:
            raise ValueError(f"artifact URL must be {expected_url}")
        if not isinstance(artifact["sha256"], str) or not SHA256.fullmatch(artifact["sha256"]):
            raise ValueError(f"artifact {key} has an invalid SHA-256")
        if not isinstance(artifact["size"], int) or artifact["size"] <= 0:
            raise ValueError(f"artifact {key} has an invalid size")
    if seen != set(expected):
        raise ValueError("release manifest is missing required artifacts")


def pointer_identity(value: dict[str, Any]) -> tuple[str, str, str]:
    match = re.fullmatch(
        rf"https://github\.com/{re.escape(REPOSITORY)}/releases/download/"
        r"(v|runtime-v)([^/]+)/release-manifest\.json",
        str(value.get("manifestUrl", "")),
    )
    if not match or not SEMVER.fullmatch(match.group(2)):
        raise ValueError("manifestUrl must select a canonical immutable Aeloon release")
    product = "desktop" if match.group(1) == "v" else "runtime"
    version = match.group(2)
    return product, version, release_tag(product, version)


def validate_pointer(value: dict[str, Any]) -> None:
    required = {"manifestUrl", "manifestSha256"}
    if set(value) != required:
        raise ValueError(f"release pointer fields must be exactly {sorted(required)}")
    pointer_identity(value)
    if not isinstance(value["manifestSha256"], str) or not SHA256.fullmatch(value["manifestSha256"]):
        raise ValueError("manifestSha256 must be lowercase SHA-256")


def build_manifest(args: argparse.Namespace) -> None:
    product = args.product
    version = args.version
    if not SEMVER.fullmatch(version):
        raise ValueError("--version must be semantic version syntax")
    if args.source_repository != source_repository(product):
        raise ValueError(f"--source-repository must be {source_repository(product)}")
    if not COMMIT.fullmatch(args.source_commit):
        raise ValueError("--source-commit must be a full lowercase Git SHA")
    tag = release_tag(product, version)
    artifacts: list[dict[str, Any]] = []
    for key, (os_name, arch, package_format, name) in artifact_contract(product, version).items():
        path = args.asset_dir / name
        if not path.is_file():
            raise ValueError(f"missing release artifact: {path}")
        artifacts.append(
            {
                "key": key,
                "os": os_name,
                "arch": arch,
                "format": package_format,
                "name": name,
                "url": f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}",
                "sha256": sha256(path),
                "size": path.stat().st_size,
            }
        )
    published_at = args.published_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    value = {
        "schemaVersion": 1,
        "product": product,
        "version": version,
        "tag": tag,
        "source": {"repository": args.source_repository, "commit": args.source_commit},
        "publishedAt": published_at,
        "artifacts": artifacts,
    }
    validate_release(value)
    write_json(args.output, value)


def build_pointer(args: argparse.Namespace) -> None:
    manifest = read_json(args.manifest)
    validate_release(manifest)
    version = manifest["version"]
    if args.channel == "stable" and "-" in version:
        raise ValueError("a prerelease cannot be promoted to stable")
    if args.channel == "prerelease" and "-" not in version:
        raise ValueError("a stable version cannot be promoted to prerelease")
    value = {
        "manifestUrl": (
            f"https://github.com/{REPOSITORY}/releases/download/{manifest['tag']}/release-manifest.json"
        ),
        "manifestSha256": sha256(args.manifest),
    }
    validate_pointer(value)
    write_json(args.output, value)


def version_key(version: str) -> tuple[int, int, int, str]:
    match = SEMVER.fullmatch(version)
    if not match:
        raise ValueError("version must be semantic version syntax")
    core, separator, suffix = version.partition("-")
    major, minor, patch = (int(part) for part in core.split("."))
    return major, minor, patch, suffix if separator else "~"


def check_promotion(args: argparse.Namespace) -> None:
    candidate = read_json(args.manifest)
    validate_release(candidate)
    if args.channel == "stable" and "-" in candidate["version"]:
        raise ValueError("a prerelease cannot be promoted to stable")
    if args.channel == "prerelease" and "-" not in candidate["version"]:
        raise ValueError("a stable version cannot be promoted to prerelease")
    if not args.current.exists():
        return
    current = read_json(args.current)
    validate_pointer(current)
    current_product, current_version, current_tag = pointer_identity(current)
    if current_product != candidate["product"]:
        raise ValueError("current pointer identifies another product")
    if current_tag == candidate["tag"]:
        if current["manifestSha256"] == sha256(args.manifest):
            return
        raise ValueError("current pointer selects the same tag with a different manifest")
    if version_key(candidate["version"]) <= version_key(current_version):
        raise ValueError(
            f"promotion must advance {args.channel} beyond {current_version}; "
            "use the rollback workflow to move stable backwards"
        )


def compare_release(args: argparse.Namespace) -> None:
    left = read_json(args.left)
    right = read_json(args.right)
    validate_release(left)
    validate_release(right)
    left.pop("publishedAt")
    right.pop("publishedAt")
    if left != right:
        raise ValueError("release manifests describe different source or artifact bytes")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    validate_release_parser = commands.add_parser("validate-release")
    validate_release_parser.add_argument("path", type=Path)
    validate_pointer_parser = commands.add_parser("validate-pointer")
    validate_pointer_parser.add_argument("path", type=Path)
    validate_pointer_parser.add_argument("--manifest", type=Path)
    validate_pointer_parser.add_argument("--product", choices=("desktop", "runtime"))
    validate_pointer_parser.add_argument("--channel", choices=("stable", "prerelease"))
    build = commands.add_parser("build")
    build.add_argument("--product", choices=("desktop", "runtime"), required=True)
    build.add_argument("--version", required=True)
    build.add_argument("--source-repository", required=True)
    build.add_argument("--source-commit", required=True)
    build.add_argument("--published-at")
    build.add_argument("--asset-dir", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    pointer = commands.add_parser("pointer")
    pointer.add_argument("--manifest", type=Path, required=True)
    pointer.add_argument("--channel", choices=("stable", "prerelease"), required=True)
    pointer.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("check-promotion")
    check.add_argument("--manifest", type=Path, required=True)
    check.add_argument("--channel", choices=("stable", "prerelease"), required=True)
    check.add_argument("--current", type=Path, required=True)
    compare = commands.add_parser("compare-release")
    compare.add_argument("left", type=Path)
    compare.add_argument("right", type=Path)
    return root


def main() -> int:
    args = parser().parse_args()
    if args.command == "validate-release":
        validate_release(read_json(args.path))
    elif args.command == "validate-pointer":
        pointer = read_json(args.path)
        validate_pointer(pointer)
        product, version, tag = pointer_identity(pointer)
        if args.product and product != args.product:
            raise ValueError("pointer URL identifies another product")
        if args.channel == "stable" and "-" in version:
            raise ValueError("stable pointers cannot select prerelease versions")
        if args.channel == "prerelease" and "-" not in version:
            raise ValueError("prerelease pointers must select prerelease versions")
        if args.manifest:
            manifest = read_json(args.manifest)
            validate_release(manifest)
            if product != manifest["product"] or tag != manifest["tag"]:
                raise ValueError("pointer and release manifest identify different releases")
            if pointer["manifestSha256"] != sha256(args.manifest):
                raise ValueError("pointer manifestSha256 does not match the release manifest")
    elif args.command == "build":
        build_manifest(args)
    elif args.command == "pointer":
        build_pointer(args)
    elif args.command == "check-promotion":
        check_promotion(args)
    elif args.command == "compare-release":
        compare_release(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
