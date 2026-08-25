from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("release_manifest", ROOT / "tools" / "release_manifest.py")
assert SPEC and SPEC.loader
release_manifest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_manifest)


class ReleaseManifestTests(unittest.TestCase):
    def test_seed_manifests_and_pointers_are_valid(self) -> None:
        pairs = (
            ("desktop", "v0.0.18", ROOT / "manifests" / "desktop-v0.0.18.json"),
            ("runtime", "runtime-v0.1.2", ROOT / "manifests" / "runtime-v0.1.2.json"),
        )
        for product, tag, manifest_path in pairs:
            manifest = release_manifest.read_json(manifest_path)
            release_manifest.validate_release(manifest)
            pointer_path = ROOT / "releases" / product / f"{tag}.json"
            pointer = release_manifest.read_json(pointer_path)
            release_manifest.validate_pointer(pointer)
            self.assertEqual(pointer["manifestSha256"], release_manifest.sha256(manifest_path))
            self.assertEqual(pointer, release_manifest.read_json(ROOT / "channels" / product / "stable.json"))

    def test_rejects_redirected_artifact_and_duplicate_key(self) -> None:
        manifest = release_manifest.read_json(ROOT / "manifests" / "desktop-v0.0.18.json")
        redirected = copy.deepcopy(manifest)
        redirected["artifacts"][0]["url"] = "https://example.com/installer.dmg"
        with self.assertRaisesRegex(ValueError, "artifact URL"):
            release_manifest.validate_release(redirected)
        duplicate = copy.deepcopy(manifest)
        duplicate["artifacts"][1]["key"] = duplicate["artifacts"][0]["key"]
        with self.assertRaisesRegex(ValueError, "duplicate or unknown"):
            release_manifest.validate_release(duplicate)

    def test_channel_and_semver_must_agree(self) -> None:
        args = type(
            "Args",
            (),
            {
                "manifest": ROOT / "manifests" / "desktop-v0.0.18.json",
                "channel": "prerelease",
                "output": ROOT / "unused.json",
            },
        )()
        with self.assertRaisesRegex(ValueError, "stable version cannot"):
            release_manifest.build_pointer(args)

    def test_json_loader_rejects_duplicate_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"product":"desktop","product":"runtime"}\n')
            with self.assertRaisesRegex(ValueError, "duplicate JSON field: product"):
                release_manifest.read_json(path)

    def test_repeating_the_same_promotion_is_idempotent(self) -> None:
        manifest = ROOT / "manifests" / "desktop-v0.0.18.json"
        args = type(
            "Args",
            (),
            {
                "manifest": manifest,
                "channel": "stable",
                "current": ROOT / "channels" / "desktop" / "stable.json",
            },
        )()
        release_manifest.check_promotion(args)

    def test_build_computes_digest_and_size_from_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            version = "1.2.3"
            for _, (_, _, _, name) in release_manifest.artifact_contract("desktop", version).items():
                (root / name).write_bytes(name.encode())
            output = root / "release-manifest.json"
            args = type(
                "Args",
                (),
                {
                    "product": "desktop",
                    "version": version,
                    "source_repository": "AetherHeart-AI/aeloon-lite-ui",
                    "source_commit": "ab" * 20,
                    "published_at": "2026-08-26T00:00:00Z",
                    "asset_dir": root,
                    "output": output,
                },
            )()
            release_manifest.build_manifest(args)
            value = json.loads(output.read_text())
            release_manifest.validate_release(value)
            for artifact in value["artifacts"]:
                path = root / artifact["name"]
                self.assertEqual(artifact["size"], path.stat().st_size)
                self.assertEqual(artifact["sha256"], release_manifest.sha256(path))


if __name__ == "__main__":
    unittest.main()
