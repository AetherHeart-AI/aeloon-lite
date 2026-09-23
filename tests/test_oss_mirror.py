"""Release mirror gates must reject incomplete or changed public bytes."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import oss_mirror


class RecordingOss:
    bucket = "aeloon-lite"

    def __init__(self):
        self.uploaded = []
        self.manifests = {}

    def upload_immutable(self, path, key):
        self.uploaded.append((key, path.read_bytes()))

    def upload_mutable(self, path, key):
        self.uploaded.append((key, path.read_bytes()))

    def read_json(self, key):
        return self.manifests[key]


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.assets = Path(self.temporary.name) / "assets"
        self.assets.mkdir()
        self.oss = RecordingOss()

    def create_release(self, names):
        assets = []
        for name in sorted(names):
            payload = name.encode()
            (self.assets / name).write_bytes(payload)
            assets.append({
                "name": name,
                "size": len(payload),
                "digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
            })
        return {"tagName": "v0.4.1", "isDraft": True, "isPrerelease": False, "assets": assets}

    def test_manifest_is_last_and_contains_all_verified_assets(self):
        names = oss_mirror.expected_names("v0.4.1", set())
        release = self.create_release(names)
        with patch.object(oss_mirror, "run", return_value=type("Result", (), {"stdout": json.dumps(release)})()):
            oss_mirror.mirror_release("v0.4.1", self.assets, True, self.oss)
        keys = [key for key, _ in self.oss.uploaded]
        self.assertEqual(keys[-1], "releases/v0.4.1/manifest.json")
        self.assertEqual(len(keys), len(names) * 3 + 1)
        manifest = json.loads(self.oss.uploaded[-1][1])
        self.assertEqual({item["name"] for item in manifest["assets"]}, names)
        self.assertEqual(manifest["schema"], 1)

    def test_missing_or_changed_asset_stops_before_upload(self):
        names = oss_mirror.expected_names("v0.4.1", set())
        release = self.create_release(names)
        (self.assets / next(iter(names))).unlink()
        with patch.object(oss_mirror, "run", return_value=type("Result", (), {"stdout": json.dumps(release)})()):
            with self.assertRaises(RuntimeError):
                oss_mirror.mirror_release("v0.4.1", self.assets, True, self.oss)
        self.assertFalse(self.oss.uploaded)

    def test_replay_refuses_different_existing_object(self):
        path = self.assets / "archive"
        path.write_bytes(b"correct")
        oss = oss_mirror.Oss()
        with patch.object(oss, "stat", return_value={"Content-Length": "7", "X-Oss-Hash-Crc64ecma": "0"}), \
             patch.object(oss, "command") as command:
            command.side_effect = lambda *args, **kwargs: Path(args[2]).write_bytes(b"changed")
            with self.assertRaisesRegex(RuntimeError, "Refusing to overwrite"):
                oss.upload_immutable(path, "releases/v0.4.1/archive")
        self.assertEqual(command.call_count, 1)

    def test_new_immutable_upload_uses_parallel_parts(self):
        path = self.assets / "archive"
        path.write_bytes(b"correct")
        oss = oss_mirror.Oss()
        with patch.object(oss, "stat", return_value=None), \
             patch.object(oss, "command") as command, \
             patch.object(oss, "verify_object") as verify:
            oss.upload_immutable(path, "releases/v0.4.1/archive")
        self.assertIn(("--parallel", "10"), list(zip(command.call_args.args, command.call_args.args[1:])))
        verify.assert_called_once_with(path, "releases/v0.4.1/archive")

    def test_crc64_uses_ossutil_v2_syntax(self):
        oss = oss_mirror.Oss()
        sample = self.assets / "sample"
        sample.write_bytes(b"sample")
        result = type("Result", (), {"stdout": f"295992936743767023  {sample}\n\n0.000530(s) elapsed\n"})()
        with patch.object(oss, "command", return_value=result) as command:
            self.assertEqual(oss.local_crc64(sample), "295992936743767023")
        command.assert_called_once_with("hash", "crc64", str(sample), capture=True)

    def test_oidc_temporary_credentials_reach_ossutil(self):
        issued = {
            "ALIBABA_CLOUD_ACCESS_KEY_ID": "STS.test-id",
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "temporary-secret",
            "ALIBABA_CLOUD_SECURITY_TOKEN": "temporary-token",
        }
        with patch.dict(os.environ, issued):
            oss = oss_mirror.Oss()
        with patch.object(oss_mirror.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as command:
            oss.command("hash", "crc64", "sample")
            oss.stat("releases/v0.4.1/sample")
        for call in command.call_args_list:
            env = call.kwargs["env"]
            self.assertEqual(env["OSS_ACCESS_KEY_ID"], issued["ALIBABA_CLOUD_ACCESS_KEY_ID"])
            self.assertEqual(env["OSS_ACCESS_KEY_SECRET"], issued["ALIBABA_CLOUD_ACCESS_KEY_SECRET"])
            self.assertEqual(env["OSS_SESSION_TOKEN"], issued["ALIBABA_CLOUD_SECURITY_TOKEN"])

    def test_channels_wait_for_both_complete_manifests(self):
        directory = Path(self.temporary.name) / "channels"
        for product in ("desktop", "runtime"):
            channel = directory / product / "stable"
            channel.parent.mkdir(parents=True)
            channel.write_text(f"# aeloon-release-v2\n# product={product}\n# version=0.4.1\n# release=v0.4.1\n# source=example\n")
        names = oss_mirror.expected_names("v0.4.1", set())
        self.oss.manifests["releases/v0.4.1/manifest.json"] = {
            "schema": 1, "tag": "v0.4.1", "assets": [{"name": name} for name in names]
        }
        oss_mirror.mirror_channels(directory, self.oss)
        self.assertEqual([key for key, _ in self.oss.uploaded], ["channels/desktop/stable", "channels/runtime/stable"])
        self.oss.uploaded.clear()
        self.oss.manifests["releases/v0.4.1/manifest.json"]["assets"].pop()
        with self.assertRaises(RuntimeError):
            oss_mirror.mirror_channels(directory, self.oss)
        self.assertFalse(self.oss.uploaded)


if __name__ == "__main__":
    unittest.main()
