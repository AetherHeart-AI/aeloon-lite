"""Release mirror gates must reject incomplete or changed public bytes."""

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import oss_mirror
import oss_oidc


class RecordingOss:
    bucket = "aeloon-lite"

    def __init__(self):
        self.uploaded = []
        self.manifests = {}
        self.existing = set()

    def verified_existing_digest(self, key, size, digest, legacy_digest_key):
        return key in self.existing

    def upload_immutable(self, path, key, expected_digest=None, legacy_digest_key=None):
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
        self.assertEqual(keys[-2], "releases/v0.4.1/checksums.txt")
        self.assertEqual(len(keys), len(names) + 2)
        manifest = json.loads(self.oss.uploaded[-1][1])
        self.assertEqual({item["name"] for item in manifest["assets"]}, names)
        self.assertEqual(manifest["schema"], 1)
        index = self.oss.uploaded[-2][1].decode("ascii").splitlines()
        self.assertEqual(index[:2], ["# aeloon-checksums-v1", "# release=v0.4.1"])
        self.assertEqual(
            index[2:],
            [f"{asset['digest'][7:]} {asset['size']} {asset['name']}" for asset in manifest["assets"]],
        )

    def test_missing_or_changed_asset_stops_before_upload(self):
        names = oss_mirror.expected_names("v0.4.1", set())
        release = self.create_release(names)
        (self.assets / next(iter(names))).unlink()
        with patch.object(oss_mirror, "run", return_value=type("Result", (), {"stdout": json.dumps(release)})()):
            with self.assertRaises(RuntimeError):
                oss_mirror.mirror_release("v0.4.1", self.assets, True, self.oss)
        self.assertFalse(self.oss.uploaded)

    def test_replay_skips_all_large_github_downloads(self):
        names = oss_mirror.expected_names("v0.4.1", set())
        release = self.create_release(names)
        release["isDraft"] = False
        self.oss.existing = {f"releases/v0.4.1/{name}" for name in names}
        with patch.object(oss_mirror, "run", return_value=type("Result", (), {"stdout": json.dumps(release)})()) as command:
            oss_mirror.mirror_release("v0.4.1", None, False, self.oss)
        command.assert_called_once()
        self.assertEqual([key for key, _ in self.oss.uploaded], [
            "releases/v0.4.1/checksums.txt", "releases/v0.4.1/manifest.json",
        ])

    def test_replay_downloads_only_missing_github_assets(self):
        names = oss_mirror.expected_names("v0.4.1", set())
        release = self.create_release(names)
        release["isDraft"] = False
        missing = sorted(names)[0]
        self.oss.existing = {f"releases/v0.4.1/{name}" for name in names - {missing}}
        def fake_run(*args, **kwargs):
            if args[:3] == ("gh", "release", "view"):
                return type("Result", (), {"stdout": json.dumps(release)})()
            self.assertEqual(args[:3], ("gh", "release", "download"))
            self.assertEqual(args[-2:], ("--pattern", missing))
            Path(args[args.index("--dir") + 1], missing).write_bytes(missing.encode())
            return type("Result", (), {"stdout": ""})()
        with patch.object(oss_mirror, "run", side_effect=fake_run) as command:
            oss_mirror.mirror_release("v0.4.1", None, False, self.oss)
        self.assertEqual(command.call_count, 2)
        self.assertEqual([key for key, _ in self.oss.uploaded], [
            f"releases/v0.4.1/{missing}",
            "releases/v0.4.1/checksums.txt", "releases/v0.4.1/manifest.json",
        ])

    def test_existing_digest_attestation_skips_download(self):
        oss = oss_mirror.Oss()
        digest = "sha256:" + "a" * 64
        key = "releases/v0.4.1/archive"
        metadata = {"Content-Length": "7", "X-Oss-Hash-Crc64ecma": "123", "X-Oss-Meta-Sha256": "a" * 64}
        with patch.object(oss, "stat", return_value=metadata), patch.object(oss, "command") as command:
            self.assertTrue(oss.verified_existing_digest(key, 7, digest, key + ".sha256"))
        command.assert_not_called()

    def test_existing_digest_accepts_legacy_double_prefix(self):
        oss = oss_mirror.Oss()
        digest = "sha256:" + "a" * 64
        key = "releases/v0.4.1/archive"
        metadata = {"Content-Length": "7", "X-Oss-Hash-Crc64ecma": "123",
                    "X-Oss-Meta-X-Oss-Meta-Sha256": "a" * 64}
        with patch.object(oss, "stat", return_value=metadata), patch.object(oss, "command") as command:
            self.assertTrue(oss.verified_existing_digest(key, 7, digest, key + ".sha256"))
        command.assert_not_called()

    def test_existing_digest_attestation_rejects_changed_size(self):
        oss = oss_mirror.Oss()
        key = "releases/v0.4.1/archive"
        with patch.object(oss, "stat", return_value={"Content-Length": "8", "X-Oss-Hash-Crc64ecma": "123"}):
            with self.assertRaisesRegex(RuntimeError, "size differs"):
                oss.verified_existing_digest(key, 7, "sha256:" + "a" * 64, key + ".sha256")

    def test_replay_refuses_different_existing_object(self):
        path = self.assets / "archive"
        path.write_bytes(b"correct")
        oss = oss_mirror.Oss()
        with patch.object(oss, "stat", return_value={"Content-Length": "7", "X-Oss-Hash-Crc64ecma": "0"}), \
             patch.object(oss, "local_crc64", return_value="0"), \
             patch.object(oss, "command") as command:
            command.side_effect = lambda *args, **kwargs: Path(args[2]).write_bytes(b"changed")
            with self.assertRaisesRegex(RuntimeError, "Refusing to overwrite"):
                oss.upload_immutable(path, "releases/v0.4.1/archive")
        self.assertEqual(command.call_count, 1)
        self.assertIn(("--parallel", "10"), list(zip(command.call_args.args, command.call_args.args[1:])))

    def test_replay_uses_sha_metadata_without_downloading(self):
        path = self.assets / "archive"
        path.write_bytes(b"correct")
        digest = hashlib.sha256(b"correct").hexdigest()
        oss = oss_mirror.Oss()
        existing = {"Content-Length": "7", "X-Oss-Hash-Crc64ecma": "123", "X-Oss-Meta-Sha256": digest}
        with patch.object(oss, "stat", return_value=existing), \
             patch.object(oss, "local_crc64", return_value="123"), \
             patch.object(oss, "command") as command:
            oss.upload_immutable(path, "releases/v0.4.1/archive")
        command.assert_not_called()

    def test_replay_rejects_wrong_sha_metadata(self):
        path = self.assets / "archive"
        path.write_bytes(b"correct")
        oss = oss_mirror.Oss()
        existing = {"Content-Length": "7", "X-Oss-Hash-Crc64ecma": "123", "X-Oss-Meta-Sha256": "0" * 64}
        with patch.object(oss, "stat", return_value=existing), \
             patch.object(oss, "local_crc64", return_value="123"), \
             patch.object(oss, "command") as command:
            with self.assertRaisesRegex(RuntimeError, "Refusing to overwrite"):
                oss.upload_immutable(path, "releases/v0.4.1/archive")
        command.assert_not_called()

    def test_legacy_sidecar_avoids_large_download(self):
        path = self.assets / "archive"
        path.write_bytes(b"correct")
        digest = hashlib.sha256(b"correct").hexdigest()
        oss = oss_mirror.Oss()
        existing = {"Content-Length": "7", "X-Oss-Hash-Crc64ecma": "123"}
        with patch.object(oss, "stat", side_effect=[existing, {"Content-Length": "74"}]), \
             patch.object(oss, "local_crc64", return_value="123"), \
             patch.object(oss, "read_text", return_value=f"{digest}  archive\n"), \
             patch.object(oss, "command") as command:
            oss.upload_immutable(
                path, "releases/v0.4.1/archive",
                legacy_digest_key="releases/v0.4.1/archive.sha256",
            )
        command.assert_not_called()

    def test_new_immutable_upload_uses_parallel_parts(self):
        path = self.assets / "archive"
        path.write_bytes(b"correct")
        oss = oss_mirror.Oss()
        with patch.object(oss, "stat", return_value=None), \
             patch.object(oss, "command") as command, \
             patch.object(oss, "verify_object", return_value={"X-Oss-Meta-Sha256": hashlib.sha256(b"correct").hexdigest()}) as verify:
            oss.upload_immutable(path, "releases/v0.4.1/archive")
        self.assertIn(("--parallel", "10"), list(zip(command.call_args.args, command.call_args.args[1:])))
        self.assertIn(("--part-size", "16M"), list(zip(command.call_args.args, command.call_args.args[1:])))
        self.assertIn(("--bigfile-threshold", "16M"), list(zip(command.call_args.args, command.call_args.args[1:])))
        self.assertIn("--checkpoint-dir", command.call_args.args)
        self.assertIn(("--metadata", "sha256=" + hashlib.sha256(b"correct").hexdigest()),
                      list(zip(command.call_args.args, command.call_args.args[1:])))
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

    def test_fresh_oidc_and_sts_credentials_are_requested_without_logging_tokens(self):
        requests = []
        def fake_urlopen(request, timeout):
            requests.append(request)
            self.assertEqual(timeout, 30)
            if len(requests) == 1:
                return io.BytesIO(b'{"value":"private-oidc-token"}')
            return io.BytesIO(json.dumps({"Credentials": {
                "AccessKeyId": "STS.new", "AccessKeySecret": "private-secret",
                "SecurityToken": "private-sts-token", "Expiration": "2030-01-01T00:00:00Z",
            }}).encode())
        with patch.dict(os.environ, {
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://oidc.example/token?x=1",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "private-request-token",
        }), patch.object(oss_oidc.urllib.request, "urlopen", side_effect=fake_urlopen):
            credentials = oss_oidc.request_credentials("role-arn", "provider-arn")
        self.assertEqual(credentials.access_key_id, "STS.new")
        self.assertEqual(credentials.security_token, "private-sts-token")
        self.assertEqual(parse_qs(urlsplit(requests[0].full_url).query)["audience"], ["sts.aliyuncs.com"])
        self.assertEqual(requests[0].get_header("Authorization"), "bearer private-request-token")
        self.assertEqual(requests[1].full_url, "https://sts.aliyuncs.com/")
        form = parse_qs(requests[1].data.decode())
        self.assertEqual(form["OIDCToken"], ["private-oidc-token"])
        self.assertEqual(form["RoleArn"], ["role-arn"])
        self.assertEqual(form["OIDCProviderArn"], ["provider-arn"])

    def test_oss_renews_credentials_before_expiry(self):
        now = time.time()
        credentials = [
            oss_oidc.Credentials("STS.first", "secret-1", "token-1", now + 3600),
            oss_oidc.Credentials("STS.second", "secret-2", "token-2", now + 7200),
        ]
        with patch.dict(os.environ, {
            "AELOON_OSS_ROLE_ARN": "role-arn", "AELOON_OSS_OIDC_PROVIDER_ARN": "provider-arn",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "private-request-token",
        }), patch.object(oss_mirror, "request_credentials", side_effect=credentials) as request, \
             patch.object(oss_mirror, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as command, \
             patch.object(oss_mirror.time, "time", side_effect=[now, now + 3100]):
            oss = oss_mirror.Oss()
            oss.command("hash", "crc64", "first")
            oss.command("hash", "crc64", "second")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(command.call_args_list[0].kwargs["env"]["OSS_SESSION_TOKEN"], "token-1")
        self.assertEqual(command.call_args_list[1].kwargs["env"]["OSS_SESSION_TOKEN"], "token-2")
        self.assertNotIn("ACTIONS_ID_TOKEN_REQUEST_TOKEN", command.call_args.kwargs["env"])

    def test_expired_multipart_upload_resumes_with_same_checkpoint(self):
        path = self.assets / "archive"
        path.write_bytes(b"correct")
        now = time.time()
        credentials = [
            oss_oidc.Credentials("STS.first", "secret-1", "token-1", now + 3600),
            oss_oidc.Credentials("STS.second", "secret-2", "token-2", now + 3600),
        ]
        with patch.dict(os.environ, {
            "AELOON_OSS_ROLE_ARN": "role-arn", "AELOON_OSS_OIDC_PROVIDER_ARN": "provider-arn",
        }), patch.object(oss_mirror, "request_credentials", side_effect=credentials) as request, \
             patch.object(oss_mirror, "run", side_effect=[
                 RuntimeError("ossutil cp failed: SecurityTokenExpired"),
                 subprocess.CompletedProcess([], 0, "", ""),
             ]) as command:
            oss = oss_mirror.Oss()
            with patch.object(oss, "stat", return_value=None), \
                 patch.object(oss, "verify_object", return_value={
                     "X-Oss-Meta-Sha256": hashlib.sha256(b"correct").hexdigest(),
                 }):
                oss.upload_immutable(path, "releases/v0.4.1/archive")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(command.call_count, 2)
        checkpoints = [call.args[call.args.index("--checkpoint-dir") + 1] for call in command.call_args_list]
        self.assertEqual(checkpoints[0], checkpoints[1])
        self.assertEqual(command.call_args_list[0].kwargs["env"]["OSS_SESSION_TOKEN"], "token-1")
        self.assertEqual(command.call_args_list[1].kwargs["env"]["OSS_SESSION_TOKEN"], "token-2")

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
