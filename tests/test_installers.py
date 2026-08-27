from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


class InstallerTests(unittest.TestCase):
    def test_public_scripts_are_small_posix_stable_installers(self) -> None:
        for name in ("install.sh", "install-server.sh"):
            result = subprocess.run(["sh", "-n", str(ROOT / name)], check=False)
            self.assertEqual(result.returncode, 0)
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("release-manifest.json", source)
            self.assertNotIn("--channel", source)
            self.assertNotIn("--version", source)
            self.assertNotIn("eval ", source)

    def test_desktop_stable_downloads_verified_deb(self) -> None:
        fixture = self._fixture("desktop", b"desktop-fixture")
        result = subprocess.run(
            ["sh", str(ROOT / "install.sh"), "--download-only", str(fixture["downloads"])],
            capture_output=True,
            text=True,
            env=fixture["env"],
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (fixture["downloads"] / "aeloon-lite-1.2.3-x86_64.deb").read_bytes(),
            b"desktop-fixture",
        )

    def test_runtime_stable_downloads_verified_archive(self) -> None:
        fixture = self._fixture("runtime", b"runtime-fixture")
        result = subprocess.run(
            ["sh", str(ROOT / "install-server.sh"), "--download-only", str(fixture["downloads"])],
            capture_output=True,
            text=True,
            env=fixture["env"],
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (fixture["downloads"] / "aeloon-runtime-linux-x86_64.tar.gz").read_bytes(),
            b"runtime-fixture",
        )

    def test_desktop_rpm_selection(self) -> None:
        fixture = self._fixture("desktop", b"rpm-fixture", desktop_format="rpm", os_release="ID=fedora\n")
        result = subprocess.run(
            ["sh", str(ROOT / "install.sh"), "--download-only", str(fixture["downloads"])],
            capture_output=True,
            text=True,
            env=fixture["env"],
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (fixture["downloads"] / "aeloon-lite-1.2.3-x86_64.rpm").read_bytes(),
            b"rpm-fixture",
        )

    def test_removed_release_selection_flags_are_rejected(self) -> None:
        result = subprocess.run(
            ["sh", str(ROOT / "install.sh"), "--version", "1.2.3"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Unknown argument", result.stderr)

    def test_malformed_or_duplicate_metadata_is_rejected(self) -> None:
        fixture = self._fixture("desktop", b"fixture")
        channel = fixture["channel"]
        assert isinstance(channel, Path)
        channel.write_text(channel.read_text() + channel.read_text().splitlines()[-1] + "\n")
        result = subprocess.run(
            ["sh", str(ROOT / "install.sh"), "--download-only", str(fixture["downloads"])],
            capture_output=True,
            text=True,
            env=fixture["env"],
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("exactly one checksum", result.stderr)

    def test_digest_mismatch_fails_closed(self) -> None:
        fixture = self._fixture("desktop", b"fixture", wrong_digest=True)
        result = subprocess.run(
            ["sh", str(ROOT / "install.sh"), "--download-only", str(fixture["downloads"])],
            capture_output=True,
            text=True,
            env=fixture["env"],
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("SHA-256 mismatch", result.stderr)
        self.assertFalse(Path(fixture["downloads"]).exists())

    def test_network_failure_leaves_no_download(self) -> None:
        fixture = self._fixture("desktop", b"fixture")
        tools = fixture["tools"]
        assert isinstance(tools, Path)
        write_executable(tools / "curl", "#!/bin/sh\nexit 22\n")
        result = subprocess.run(
            ["sh", str(ROOT / "install.sh"), "--download-only", str(fixture["downloads"])],
            capture_output=True,
            text=True,
            env=fixture["env"],
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(Path(fixture["downloads"]).exists())

    def test_runtime_rejects_unsafe_archive_paths(self) -> None:
        fixture = self._fixture("runtime", b"runtime-fixture")
        tools = fixture["tools"]
        assert isinstance(tools, Path)
        write_executable(tools / "tar", "#!/bin/sh\necho ../escape\n")
        result = subprocess.run(
            ["sh", str(ROOT / "install-server.sh"), "--download-only", str(fixture["downloads"])],
            capture_output=True,
            text=True,
            env=fixture["env"],
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("unsafe path", result.stderr)

    def test_committed_stable_files_have_the_fixed_contract(self) -> None:
        for product, (repository, asset_count) in {
            "desktop": ("AetherHeart-AI/aeloon-lite-ui", 5),
            "runtime": ("AetherHeart-AI/aeloon-lite-runtime", 5),
        }.items():
            lines = (ROOT / "channels" / product / "stable").read_text().splitlines()
            self.assertEqual(lines[0], "# aeloon-release-v1")
            self.assertEqual(lines[1], f"# product={product}")
            self.assertRegex(lines[2], r"^# version=\d+\.\d+\.\d+$")
            self.assertRegex(lines[3], rf"^# source={re.escape(repository)}@[0-9a-f]{{40}}$")
            entries = [line.split("  ", 1) for line in lines[4:]]
            self.assertEqual(len(entries), asset_count)
            self.assertEqual([entry[1] for entry in entries], sorted(entry[1] for entry in entries))
            self.assertEqual(len({entry[1] for entry in entries}), asset_count)
            for digest, name in entries:
                self.assertRegex(digest, r"^[0-9a-f]{64}$")
                self.assertNotIn("/", name)

    def test_publisher_has_no_promotion_or_manifest_layer(self) -> None:
        script = (ROOT / "tools" / "publish_release.sh").read_text()
        self.assertNotIn("repository_dispatch", script)
        self.assertNotIn("release-manifest", script)
        self.assertNotIn("prerelease", script)
        self.assertNotIn("gh release create", script)
        self.assertIn('gh api --method POST "repos/$DISTRIBUTION_REPOSITORY/releases"', script)
        self.assertIn("SHA256SUMS", script)
        self.assertIn("contents/$channel_path", script)
        self.assertIn("git/ref/heads/$branch", script)
        self.assertIn('gh pr create --repo "$DISTRIBUTION_REPOSITORY"', script)
        self.assertIn('gh pr merge "$pr" --repo "$DISTRIBUTION_REPOSITORY" --auto --squash', script)
        self.assertIn("Timed out waiting for stable channel PR", script)

    def test_publish_workflow_receives_and_verifies_source_releases(self) -> None:
        workflow = (ROOT / ".github/workflows/publish.yml").read_text()
        self.assertIn("repository_dispatch", workflow)
        self.assertIn("publish-runtime", workflow)
        self.assertIn("publish-desktop", workflow)
        self.assertIn("workflow_dispatch", workflow)
        self.assertIn("inputs.product", workflow)
        self.assertIn("inputs.version", workflow)
        self.assertIn("gh release download", workflow)
        self.assertIn("source_commit", workflow)
        self.assertIn("sha256sum -c SHA256SUMS", workflow)
        self.assertIn("tools/publish_release.sh", workflow)
        self.assertIn("GH_TOKEN: ${{ secrets.AELOON_RELEASE_TOKEN }}", workflow)
        self.assertIn("event_type=runtime-release", workflow)
        self.assertIn("AELOON_RELEASE_TOKEN", workflow)

    def _fixture(
        self,
        product: str,
        payload: bytes,
        *,
        desktop_format: str = "deb",
        os_release: str = "ID=ubuntu\n",
        wrong_digest: bool = False,
    ) -> dict[str, object]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        tools = root / "bin"
        tools.mkdir()
        downloads = root / "downloads"
        channel = root / "stable"
        artifact = root / "artifact"
        artifact.write_bytes(payload)
        digest = "0" * 64 if wrong_digest else hashlib.sha256(payload).hexdigest()
        version = "1.2.3"
        if product == "desktop":
            repository = "AetherHeart-AI/aeloon-lite-ui"
            name = f"aeloon-lite-{version}-x86_64.{desktop_format}"
        else:
            repository = "AetherHeart-AI/aeloon-lite-runtime"
            name = "aeloon-runtime-linux-x86_64.tar.gz"
        channel.write_text(
            "\n".join(
                [
                    "# aeloon-release-v1",
                    f"# product={product}",
                    f"# version={version}",
                    f"# source={repository}@{'ab' * 20}",
                    f"{digest}  {name}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        write_executable(tools / "uname", '#!/bin/sh\n[ "${1:-}" = "-s" ] && echo Linux || echo x86_64\n')
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
    --header|--proto|--retry) shift 2 ;;
    --fail|--location|--tlsv1.2) shift ;;
    *) url=$1; shift ;;
  esac
done
case "$url" in
  *raw.githubusercontent.com*) cp "$FIXTURE_CHANNEL" "$output" ;;
  *) cp "$FIXTURE_ARTIFACT" "$output" ;;
esac
""",
        )
        os_release_path = root / "os-release"
        os_release_path.write_text(os_release, encoding="utf-8")
        env = {
            **os.environ,
            "PATH": f"{tools}:{os.environ.get('PATH', '')}",
            "AELOON_CHANNEL_FILE": str(channel),
            "AELOON_UI_OS_RELEASE_FILE": str(os_release_path),
            "FIXTURE_CHANNEL": str(channel),
            "FIXTURE_ARTIFACT": str(artifact),
        }
        return {"downloads": downloads, "env": env, "channel": channel, "tools": tools}


if __name__ == "__main__":
    unittest.main()
