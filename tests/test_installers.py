from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


class InstallerTests(unittest.TestCase):
    def test_scripts_are_posix_shell_and_do_not_execute_manifest(self) -> None:
        for name in ("install.sh", "install-server.sh"):
            result = subprocess.run(["sh", "-n", str(ROOT / name)], check=False)
            self.assertEqual(result.returncode, 0)
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("eval ", source)
            self.assertNotIn("releases/latest", source)
            self.assertIn("--channel stable|prerelease", source)
            self.assertIn("--version VERSION", source)

    def test_desktop_exact_version_downloads_verified_fixture(self) -> None:
        fixture = self._fixture("desktop", "1.2.3", b"desktop-fixture")
        result = subprocess.run(
            ["sh", str(ROOT / "install.sh"), "--version", "1.2.3", "--download-only", str(fixture["downloads"])],
            capture_output=True,
            text=True,
            env=fixture["env"],
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((fixture["downloads"] / "aeloon-lite-1.2.3-x86_64.deb").read_bytes(), b"desktop-fixture")

    def test_runtime_stable_downloads_verified_fixture(self) -> None:
        fixture = self._fixture("runtime", "1.2.3", b"runtime-fixture")
        result = subprocess.run(
            ["sh", str(ROOT / "install-server.sh"), "--download-only", str(fixture["downloads"])],
            capture_output=True,
            text=True,
            env=fixture["env"],
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((fixture["downloads"] / "aeloon-runtime-linux-x86_64.tar.gz").read_bytes(), b"runtime-fixture")

    def test_prerelease_channel_and_rpm_selection(self) -> None:
        fixture = self._fixture(
            "desktop",
            "1.2.3-rc.1",
            b"rpm-fixture",
            desktop_format="rpm",
            os_release_content="ID=fedora\n",
        )
        result = subprocess.run(
            [
                "sh",
                str(ROOT / "install.sh"),
                "--channel",
                "prerelease",
                "--download-only",
                str(fixture["downloads"]),
            ],
            capture_output=True,
            text=True,
            env=fixture["env"],
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (fixture["downloads"] / "aeloon-lite-1.2.3-rc.1-x86_64.rpm").read_bytes(),
            b"rpm-fixture",
        )

    def test_channel_and_version_are_mutually_exclusive(self) -> None:
        result = subprocess.run(
            ["sh", str(ROOT / "install.sh"), "--channel", "stable", "--version", "1.2.3"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("mutually exclusive", result.stderr)

    def test_redirected_manifest_url_fails_before_artifact_download(self) -> None:
        fixture = self._fixture("desktop", "1.2.3", b"fixture", redirected=True)
        result = subprocess.run(
            ["sh", str(ROOT / "install.sh"), "--version", "1.2.3", "--download-only", str(fixture["downloads"])],
            capture_output=True,
            text=True,
            env=fixture["env"],
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("redirects outside", result.stderr)

    def test_duplicate_pointer_field_is_rejected(self) -> None:
        fixture = self._fixture("desktop", "1.2.3", b"fixture")
        pointer = fixture["pointer"]
        assert isinstance(pointer, Path)
        source = pointer.read_text(encoding="utf-8")
        pointer.write_text(
            source.replace(
                '  "manifestUrl":',
                '  "manifestUrl": "https://github.com/duplicate.invalid/release-manifest.json",\n  "manifestUrl":',
            )
        )
        result = subprocess.run(
            ["sh", str(ROOT / "install.sh"), "--version", "1.2.3", "--download-only", str(fixture["downloads"])],
            capture_output=True,
            text=True,
            env=fixture["env"],
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("strict generated JSON", result.stderr)

    def test_manifest_digest_mismatch_fails_closed(self) -> None:
        fixture = self._fixture("runtime", "1.2.3", b"fixture")
        manifest = fixture["manifest"]
        assert isinstance(manifest, Path)
        manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        result = subprocess.run(
            ["sh", str(ROOT / "install-server.sh"), "--download-only", str(fixture["downloads"])],
            capture_output=True,
            text=True,
            env=fixture["env"],
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("manifest SHA-256 mismatch", result.stderr)

    def test_network_failure_does_not_leave_an_unverified_download(self) -> None:
        fixture = self._fixture("desktop", "1.2.3", b"fixture")
        tools = fixture["tools"]
        assert isinstance(tools, Path)
        write_executable(tools / "curl", "#!/bin/sh\nexit 22\n")
        result = subprocess.run(
            ["sh", str(ROOT / "install.sh"), "--version", "1.2.3", "--download-only", str(fixture["downloads"])],
            capture_output=True,
            text=True,
            env=fixture["env"],
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertFalse(Path(fixture["downloads"]).exists())

    def _fixture(
        self,
        product: str,
        version: str,
        payload: bytes,
        redirected: bool = False,
        desktop_format: str = "deb",
        os_release_content: str = "ID=ubuntu\n",
    ) -> dict[str, object]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        tools = root / "bin"
        tools.mkdir()
        downloads = root / "downloads"
        pointer = root / "pointer.json"
        manifest = root / "release-manifest.json"
        artifact = root / "artifact"
        artifact.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        tag = ("v" if product == "desktop" else "runtime-v") + version
        if product == "desktop":
            package_format = desktop_format
            key, arch, name = (
                f"linux-x86_64-{package_format}",
                "x86_64",
                f"aeloon-lite-{version}-x86_64.{package_format}",
            )
            source_repository = "AetherHeart-AI/aeloon-lite-ui"
        else:
            key, arch, package_format, name = "linux-x86_64-tar.gz", "x86_64", "tar.gz", "aeloon-runtime-linux-x86_64.tar.gz"
            source_repository = "AetherHeart-AI/aeloon-lite-runtime"
        artifact_url = f"https://github.com/AetherHeart-AI/aeloon-lite/releases/download/{tag}/{name}"
        manifest_value = {
            "schemaVersion": 1,
            "product": product,
            "version": version,
            "tag": tag,
            "source": {"repository": source_repository, "commit": "ab" * 20},
            "publishedAt": "2026-08-26T00:00:00Z",
            "artifacts": [{
                "key": key, "os": "linux", "arch": arch, "format": package_format,
                "name": name, "url": artifact_url, "sha256": digest, "size": len(payload),
            }],
        }
        manifest.write_text(json.dumps(manifest_value, indent=2) + "\n", encoding="utf-8")
        manifest_url = f"https://github.com/AetherHeart-AI/aeloon-lite/releases/download/{tag}/release-manifest.json"
        pointer_value = {
            "manifestUrl": "https://example.com/evil.json" if redirected else manifest_url,
            "manifestSha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        }
        pointer.write_text(json.dumps(pointer_value, indent=2) + "\n", encoding="utf-8")
        write_executable(tools / "uname", '#!/bin/sh\n[ "$1" = "-s" ] && echo Linux || echo x86_64\n')
        write_executable(tools / "apt-get", "#!/bin/sh\nexit 0\n")
        write_executable(tools / "dnf", "#!/bin/sh\nexit 0\n")
        write_executable(tools / "tar", "#!/bin/sh\necho aeloon-runtime/bin/aeloon-runtime\n")
        write_executable(
            tools / "curl",
            """#!/bin/sh
url=""
output=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output) output=$2; shift 2 ;;
    --header|--proto) shift 2 ;;
    --retry) shift 2 ;;
    --fail|--location|--tlsv1.2) shift ;;
    *) url=$1; shift ;;
  esac
done
case "$url" in
  *raw.githubusercontent.com*) cp "$FIXTURE_POINTER" "$output" ;;
  */release-manifest.json) cp "$FIXTURE_MANIFEST" "$output" ;;
  *) cp "$FIXTURE_ARTIFACT" "$output" ;;
esac
""",
        )
        os_release_path = root / "os-release"
        os_release_path.write_text(os_release_content, encoding="utf-8")
        env = {
            **os.environ,
            "PATH": f"{tools}:{os.environ.get('PATH', '')}",
            "AELOON_UI_OS_RELEASE_FILE": str(os_release_path),
            "FIXTURE_POINTER": str(pointer),
            "FIXTURE_MANIFEST": str(manifest),
            "FIXTURE_ARTIFACT": str(artifact),
        }
        return {
            "downloads": downloads,
            "env": env,
            "pointer": pointer,
            "manifest": manifest,
            "tools": tools,
        }


if __name__ == "__main__":
    unittest.main()
