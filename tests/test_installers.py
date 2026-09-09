from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


# A ``tar`` that lists and extracts a minimal Runtime archive.
FAKE_RUNTIME_TAR = """#!/bin/sh
case " $* " in
  *" -tzf "*)
    printf 'aeloon-runtime/bin/aeloon-runtime\\naeloon-runtime/bin/aeloon-runtime-server\\n'
    ;;
  *)
    destination=""
    while [ "$#" -gt 0 ]; do
      if [ "$1" = "-C" ]; then destination=$2; break; fi
      shift
    done
    mkdir -p "$destination/aeloon-runtime/bin"
    for name in aeloon-runtime aeloon-runtime-server; do
      printf '#!/bin/sh\\nexit 0\\n' > "$destination/aeloon-runtime/bin/$name"
      chmod 0755 "$destination/aeloon-runtime/bin/$name"
    done
    ;;
esac
"""


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


class InstallerTests(unittest.TestCase):
    def test_public_scripts_are_small_posix_stable_installers(self) -> None:
        for name in ("install.sh", "install-server.sh", "uninstall.sh", "uninstall-server.sh"):
            self.assertTrue(os.access(ROOT / name, os.X_OK), f"{name} must be executable")
            result = subprocess.run(["sh", "-n", str(ROOT / name)], check=False)
            self.assertEqual(result.returncode, 0)
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("release-manifest.json", source)
            self.assertNotIn("--channel", source)
            self.assertNotIn("eval ", source)
            if name.startswith("install"):
                self.assertNotIn("--version", source)
                self.assertNotIn("SHA-256", source)
                self.assertNotIn("sha256sum", source)
                self.assertNotIn("shasum", source)

    def test_windows_scripts_keep_the_same_contract(self) -> None:
        for name in ("install.ps1", "uninstall.ps1"):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("release-manifest.json", source)
            self.assertNotIn("--channel", source)
            self.assertNotIn("--version", source)
            self.assertNotIn("sha256", source)
            # `irm ... | iex` runs in the caller's session, where `exit` would
            # close the user's whole PowerShell window.
            self.assertIsNone(re.search(r"^\s*exit\b", source, re.MULTILINE))
            if shutil.which("pwsh"):
                self._assert_powershell_parses(ROOT / name)

        install = (ROOT / "install.ps1").read_text(encoding="utf-8")
        for token in (
            "-UseBasicParsing",
            "Tls12",
            "AELOON_CHANNEL_FILE",
            "channels/desktop/stable",
            "-x64.exe",
        ):
            self.assertIn(token, install)
        uninstall = (ROOT / "uninstall.ps1").read_text(encoding="utf-8")
        self.assertIn("PurgeData", uninstall)
        self.assertIn("dev.aeloon.desktop", uninstall)

    def _assert_powershell_parses(self, script: Path) -> None:
        result = subprocess.run(
            [
                "pwsh",
                "-NoProfile",
                "-Command",
                "$errors = $null; "
                "[System.Management.Automation.Language.Parser]::ParseFile("
                f"'{script}', [ref]$null, [ref]$errors) > $null; "
                "if ($errors) { $errors | ForEach-Object { $_.ToString() }; exit 1 }",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, f"{script.name}: {result.stdout}{result.stderr}")

    def test_desktop_stable_downloads_deb_from_unified_release(self) -> None:
        fixture = self._fixture("desktop", b"desktop-fixture")
        result = subprocess.run(
            ["sh", str(ROOT / "install.sh"), "--download-only", str(fixture["downloads"])],
            capture_output=True,
            text=True,
            env=fixture["env"],
            check=False,
        )
        self.assertEqual(result.returncode, 0, f"{result.stderr}\n{result.stdout}")
        self.assertEqual(
            (fixture["downloads"] / "aeloon-lite-1.2.3-x86_64.deb").read_bytes(),
            b"desktop-fixture",
        )

    def test_runtime_stable_downloads_archive_from_unified_release(self) -> None:
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

    def test_desktop_installed_action_can_skip_without_downloading_artifact(self) -> None:
        fixture = self._fixture("desktop", b"desktop-fixture")
        tools = fixture["tools"]
        assert isinstance(tools, Path)
        write_executable(
            tools / "dpkg-query",
            "#!/bin/sh\nprintf 'install ok installed|1.2.3\\n'\n",
        )
        result = subprocess.run(
            ["sh", str(ROOT / "install.sh"), "--if-installed", "skip"],
            capture_output=True,
            text=True,
            env=fixture["env"],
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Keeping the installed aeloon-lite 1.2.3", result.stdout)
        self.assertFalse(Path(fixture["curl_log"]).exists())

    def test_desktop_update_skips_same_or_newer_installed_version(self) -> None:
        fixture = self._fixture("desktop", b"desktop-fixture")
        tools = fixture["tools"]
        assert isinstance(tools, Path)
        write_executable(
            tools / "dpkg-query",
            "#!/bin/sh\nprintf 'install ok installed|1.2.4-1\\n'\n",
        )
        result = subprocess.run(
            ["sh", str(ROOT / "install.sh"), "--if-installed", "update"],
            capture_output=True,
            text=True,
            env=fixture["env"],
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("already at or newer than stable 1.2.3", result.stdout)
        self.assertFalse(Path(fixture["curl_log"]).exists())

    def test_desktop_overwrite_forces_deb_reinstall(self) -> None:
        fixture = self._fixture("desktop", b"desktop-fixture")
        tools = fixture["tools"]
        assert isinstance(tools, Path)
        write_executable(
            tools / "dpkg-query",
            "#!/bin/sh\nprintf 'install ok installed|1.2.3\\n'\n",
        )
        write_executable(tools / "id", "#!/bin/sh\nprintf '0\\n'\n")
        result = subprocess.run(
            ["sh", str(ROOT / "install.sh"), "--if-installed", "overwrite"],
            capture_output=True,
            text=True,
            env=fixture["env"],
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        install_log = Path(fixture["install_log"]).read_text(encoding="utf-8")
        self.assertIn("install -y --reinstall --allow-downgrades", install_log)

    def test_desktop_update_installs_a_newer_stable_version(self) -> None:
        fixture = self._fixture("desktop", b"desktop-fixture")
        tools = fixture["tools"]
        assert isinstance(tools, Path)
        write_executable(
            tools / "dpkg-query",
            "#!/bin/sh\nprintf 'install ok installed|1.2.2\\n'\n",
        )
        write_executable(tools / "id", "#!/bin/sh\nprintf '0\\n'\n")
        result = subprocess.run(
            ["sh", str(ROOT / "install.sh"), "--if-installed", "update"],
            capture_output=True,
            text=True,
            env=fixture["env"],
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Updating aeloon-lite 1.2.2 to 1.2.3", result.stdout)
        install_log = Path(fixture["install_log"]).read_text(encoding="utf-8")
        self.assertIn("install -y ", f"{install_log} ")
        self.assertNotIn("--reinstall", install_log)

    def test_runtime_install_lays_out_a_user_prefix_and_prints_how_to_run_it(self) -> None:
        fixture = self._fixture("runtime", b"runtime-fixture")
        tools = fixture["tools"]
        assert isinstance(tools, Path)
        home = tools.parent / "home"
        home.mkdir()
        write_executable(tools / "tar", FAKE_RUNTIME_TAR)
        env = {**fixture["env"], "HOME": str(home), "PATH": f"{tools}:/usr/bin:/bin"}
        result = subprocess.run(
            ["sh", str(ROOT / "install-server.sh")],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, f"{result.stderr}\n{result.stdout}")
        prefix = home / ".local/share/aeloon-runtime"
        release = prefix / "releases/1.2.3"
        self.assertTrue((release / "bin/aeloon-runtime-server").is_file())
        self.assertEqual((prefix / "current").readlink(), release)
        for name in ("aeloon-runtime", "aeloon-runtime-server"):
            self.assertEqual((home / ".local/bin" / name).readlink(), prefix / "current/bin" / name)
        self.assertIn("Installed Aeloon Runtime 1.2.3", result.stdout)
        self.assertIn(f"Add {home}/.local/bin to your PATH", result.stdout)
        self.assertIn(f"{home}/.local/bin/aeloon-runtime-server run --host", result.stdout)
        self.assertIn("systemd user service", result.stdout)
        self.assertIn(
            f"ExecStart={prefix}/current/bin/aeloon-runtime-server run --host", result.stdout
        )
        self.assertIn("systemctl --user enable --now aeloon-runtime", result.stdout)
        self.assertIn("loginctl enable-linger", result.stdout)
        self.assertNotIn("sudo", result.stdout)
        # Nothing was started and nothing was written outside the two directories.
        self.assertEqual(sorted(path.name for path in home.iterdir()), [".local"])

        # Re-running with the same stable version downloads nothing.
        Path(fixture["curl_log"]).unlink()
        again = subprocess.run(
            ["sh", str(ROOT / "install-server.sh")],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("1.2.3 is already installed", again.stdout)
        self.assertIn("run --host", again.stdout)
        self.assertFalse(Path(fixture["curl_log"]).exists())

        # A newer stable version lands beside the old one and takes over the links.
        channel = Path(fixture["channel"])
        channel.write_text(channel.read_text().replace("version=1.2.3", "version=1.3.0"))
        upgraded = subprocess.run(
            ["sh", str(ROOT / "install-server.sh")],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(upgraded.returncode, 0, f"{upgraded.stderr}\n{upgraded.stdout}")
        self.assertIn("Upgraded Aeloon Runtime 1.2.3 to 1.3.0", upgraded.stdout)
        self.assertIn("Restart the Runtime", upgraded.stdout)
        self.assertEqual((prefix / "current").readlink(), prefix / "releases/1.3.0")
        self.assertTrue((release / "bin/aeloon-runtime-server").is_file())

    def test_runtime_install_refuses_to_replace_a_real_file_with_a_link(self) -> None:
        fixture = self._fixture("runtime", b"runtime-fixture")
        tools = fixture["tools"]
        assert isinstance(tools, Path)
        home = tools.parent / "home"
        (home / ".local/bin").mkdir(parents=True)
        (home / ".local/bin/aeloon-runtime").write_text("#!/bin/sh\n", encoding="utf-8")
        write_executable(tools / "tar", FAKE_RUNTIME_TAR)
        result = subprocess.run(
            ["sh", str(ROOT / "install-server.sh")],
            capture_output=True,
            text=True,
            env={**fixture["env"], "HOME": str(home)},
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("is not a symlink", result.stderr)

    def test_runtime_uninstall_removes_prefix_links_and_unit_but_keeps_data(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        home = Path(temporary.name) / "home"
        tools = Path(temporary.name) / "bin"
        tools.mkdir()
        systemctl_log = Path(temporary.name) / "systemctl.log"
        write_executable(tools / "uname", "#!/bin/sh\necho Linux\n")
        write_executable(
            tools / "systemctl", f'#!/bin/sh\nprintf \'%s\\n\' "$*" >> "{systemctl_log}"\n'
        )
        prefix = home / ".local/share/aeloon-runtime"
        (prefix / "releases/1.2.3/bin").mkdir(parents=True)
        (prefix / "current").symlink_to(prefix / "releases/1.2.3")
        (home / ".local/bin").mkdir(parents=True)
        (home / ".local/bin/aeloon-runtime-server").symlink_to(
            prefix / "current/bin/aeloon-runtime-server"
        )
        (home / ".local/bin/unrelated").write_text("keep", encoding="utf-8")
        unit = home / ".config/systemd/user/aeloon-runtime.service"
        unit.parent.mkdir(parents=True)
        unit.write_text("[Unit]\n", encoding="utf-8")
        data = home / ".aeloon-lite"
        data.mkdir()
        (data / "runtime.sqlite").write_text("data", encoding="utf-8")
        env = {
            **os.environ,
            "HOME": str(home),
            "PATH": f"{tools}:{os.environ.get('PATH', '')}",
        }
        env.pop("XDG_CONFIG_HOME", None)
        result = subprocess.run(
            ["sh", str(ROOT / "uninstall-server.sh"), "--yes"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(prefix.exists())
        self.assertFalse((home / ".local/bin/aeloon-runtime-server").is_symlink())
        self.assertTrue((home / ".local/bin/unrelated").exists())
        self.assertFalse(unit.exists())
        self.assertIn("--user disable --now aeloon-runtime.service", systemctl_log.read_text())
        self.assertTrue((data / "runtime.sqlite").exists())
        self.assertIn(f"Preserved Runtime data: {data}", result.stdout)

        purged = subprocess.run(
            ["sh", str(ROOT / "uninstall-server.sh"), "--yes", "--purge-data"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(purged.returncode, 0, purged.stderr)
        self.assertFalse(data.exists())

    def test_uninstall_help_documents_safe_data_defaults(self) -> None:
        for name in ("uninstall.sh", "uninstall-server.sh"):
            result = subprocess.run(
                ["sh", str(ROOT / name), "--help"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--purge-data", result.stdout)
            self.assertIn("preserved", result.stdout)

    def test_desktop_uninstall_purge_removes_only_private_temp_data(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        tools = root / "bin"
        tools.mkdir()
        write_executable(tools / "uname", "#!/bin/sh\nprintf 'Linux\\n'\n")
        write_executable(tools / "dpkg-query", "#!/bin/sh\nexit 1\n")
        write_executable(tools / "rpm", "#!/bin/sh\nexit 1\n")
        user_home = root / "home"
        private_config = user_home / ".config" / "dev.aeloon.desktop"
        private_cache = user_home / ".cache" / "dev.aeloon.desktop"
        external_project = user_home / "project"
        private_config.mkdir(parents=True)
        private_cache.mkdir(parents=True)
        external_project.mkdir(parents=True)
        (private_config / "credentials.json").write_text("fixture", encoding="utf-8")
        (external_project / "keep.txt").write_text("keep", encoding="utf-8")
        result = subprocess.run(
            ["sh", str(ROOT / "uninstall.sh"), "--purge-data", "--yes"],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "HOME": str(user_home),
                "XDG_CONFIG_HOME": str(user_home / ".config"),
                "XDG_CACHE_HOME": str(user_home / ".cache"),
                "PATH": f"{tools}:{os.environ.get('PATH', '')}",
            },
            check=False,
        )
        self.assertEqual(result.returncode, 0, f"{result.stderr}\n{result.stdout}")
        self.assertFalse(private_config.exists())
        self.assertFalse(private_cache.exists())
        self.assertEqual((external_project / "keep.txt").read_text(encoding="utf-8"), "keep")

    def test_desktop_uninstall_preserves_private_data_by_default(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        tools = root / "bin"
        tools.mkdir()
        package_log = root / "package.log"
        write_executable(tools / "uname", "#!/bin/sh\nprintf 'Linux\\n'\n")
        write_executable(
            tools / "dpkg-query",
            "#!/bin/sh\nprintf 'install ok installed\\n'\n",
        )
        write_executable(tools / "id", "#!/bin/sh\nprintf '0\\n'\n")
        write_executable(
            tools / "apt-get",
            '#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$PACKAGE_LOG"\n',
        )
        user_home = root / "home"
        private_config = user_home / ".config" / "dev.aeloon.desktop"
        private_config.mkdir(parents=True)
        (private_config / "settings.json").write_text("keep", encoding="utf-8")
        result = subprocess.run(
            ["sh", str(ROOT / "uninstall.sh"), "--yes"],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "HOME": str(user_home),
                "XDG_CONFIG_HOME": str(user_home / ".config"),
                "XDG_CACHE_HOME": str(user_home / ".cache"),
                "PATH": f"{tools}:{os.environ.get('PATH', '')}",
                "PACKAGE_LOG": str(package_log),
            },
            check=False,
        )
        self.assertEqual(result.returncode, 0, f"{result.stderr}\n{result.stdout}")
        self.assertEqual((private_config / "settings.json").read_text(encoding="utf-8"), "keep")
        self.assertIn("remove -y aeloon-lite", package_log.read_text(encoding="utf-8"))

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

    def test_duplicate_metadata_is_rejected(self) -> None:
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
        self.assertIn("Invalid desktop release metadata", result.stderr)

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
        for product, repository in {
            "desktop": "AetherHeart-AI/aeloon-lite-ui",
            "runtime": "AetherHeart-AI/aeloon-lite-runtime",
        }.items():
            lines = (ROOT / "channels" / product / "stable").read_text().splitlines()
            self.assertEqual(lines[0], "# aeloon-release-v2")
            self.assertEqual(lines[1], f"# product={product}")
            self.assertRegex(lines[2], r"^# version=\d+\.\d+\.\d+$")
            self.assertRegex(lines[3], r"^# release=v\d+\.\d+\.\d+$")
            self.assertRegex(lines[4], rf"^# source={re.escape(repository)}@[0-9a-f]{{40}}$")
            self.assertEqual(len(lines), 5)

    def test_publisher_keeps_the_official_release_contract_small(self) -> None:
        script = (ROOT / "tools" / "publish_release.sh").read_text()
        self.assertNotIn("repository_dispatch", script)
        self.assertNotIn("release-manifest", script)
        self.assertNotIn("prerelease", script)
        self.assertNotIn("gh release create", script)
        self.assertIn('gh api --method POST "repos/$DISTRIBUTION_REPOSITORY/releases"', script)
        self.assertNotIn("SHA256SUMS", script)
        self.assertNotIn("sha256sum", script)
        self.assertIn("channels/desktop/stable", script)
        self.assertIn("channels/runtime/stable", script)
        self.assertIn("git/ref/heads/$branch", script)
        self.assertIn('gh pr create --repo "$DISTRIBUTION_REPOSITORY"', script)
        self.assertIn(
            'gh pr merge "$pr" --repo "$DISTRIBUTION_REPOSITORY" '
            '--auto --squash --delete-branch',
            script,
        )
        self.assertIn("Timed out waiting for stable channel PR", script)
        self.assertIn("--summary-zh", script)
        self.assertIn("--summary-en", script)
        self.assertIn("printf '%s\\n' \"$summary_zh\"", script)
        self.assertIn("printf '%s\\n' \"$summary_en\"", script)
        self.assertNotIn("collect_pull_requests", script)
        self.assertIn("tools/issue_flow.py collect", script)
        self.assertIn("tools/issue_flow.py annotate-release", script)
        self.assertIn("### 已完成的公开 Issue", script)
        self.assertIn("### Resolved public Issues", script)
        self.assertNotIn("Pull requests since", script)
        self.assertNotIn("### 安装", script)
        self.assertNotIn("### Installation", script)
        self.assertNotIn("发布负责人需在发布后", script)
        self.assertNotIn("After publication, the release owner", script)

    def test_candidate_workflow_is_downloadable_but_cannot_publish(self) -> None:
        workflow = (ROOT / ".github/workflows/candidate.yml").read_text()
        self.assertIn("types: [publish-desktop]", workflow)
        self.assertIn(
            "options: [all, macos-arm64, linux-arm64, linux-x86_64, windows-x64]", workflow
        )
        self.assertIn('case "$platform" in', workflow)
        self.assertIn('macos-arm64) selected=("aeloon-lite-$version-arm64.dmg")', workflow)
        self.assertIn('windows-x64) selected=("aeloon-lite-$version-x64.exe")', workflow)
        self.assertIn("candidate-${{ steps.candidate.outputs.platform }}", workflow)
        self.assertIn("actions/upload-artifact", workflow)
        self.assertIn("retention-days: 7", workflow)
        self.assertIn("candidate.json", workflow)
        self.assertIn("sha256sum", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("gh release upload", workflow)
        self.assertNotIn("gh release edit", workflow)
        self.assertNotIn("channels/desktop/stable", workflow)

    def test_official_publish_promotes_a_tested_candidate_and_verifies_sources(self) -> None:
        workflow = (ROOT / ".github/workflows/publish.yml").read_text()
        self.assertIn("repository_dispatch", workflow)
        self.assertIn("publish-runtime", workflow)
        self.assertNotIn("types: [publish-runtime, publish-desktop]", workflow)
        self.assertIn("workflow_dispatch", workflow)
        self.assertIn("inputs.product", workflow)
        self.assertIn("inputs.version", workflow)
        self.assertIn("inputs.candidate_run_id", workflow)
        self.assertIn("inputs.summary_zh", workflow)
        self.assertIn("inputs.summary_en", workflow)
        self.assertIn("gh run download", workflow)
        self.assertIn("candidate-all", workflow)
        self.assertIn('test "$(jq -r .platform "$candidate_manifest")" = all', workflow)
        self.assertIn("candidate.json", workflow)
        self.assertIn("gh release download", workflow)
        self.assertIn("source_commit", workflow)
        self.assertNotIn("SHA256SUMS", workflow)
        self.assertIn("sha256sum", workflow)
        self.assertIn("runtime-bundle.lock.json", workflow)
        self.assertIn("tools/publish_release.sh", workflow)
        self.assertIn("Publish public Runtime assets for SSH deployment", workflow)
        self.assertIn("--repo AetherHeart-AI/aeloon-lite --draft=false --latest=false", workflow)
        self.assertIn("GH_TOKEN: ${{ secrets.AELOON_RELEASE_TOKEN }}", workflow)
        self.assertIn("actions/create-github-app-token@", workflow)
        self.assertIn("AELOON_ISSUE_APP_ID", workflow)
        self.assertIn("AELOON_ISSUE_APP_PRIVATE_KEY", workflow)
        self.assertIn("tools/issue_flow.py collect", workflow)
        self.assertIn("tools/issue_flow.py annotate-release", workflow)
        self.assertNotIn("Public Runtime assets for SSH deployment from", workflow)
        self.assertIn("event_type=runtime-release", workflow)
        self.assertIn("AELOON_RELEASE_TOKEN", workflow)

    def test_windows_assets_travel_through_the_whole_release_contract(self) -> None:
        candidate = (ROOT / ".github/workflows/candidate.yml").read_text()
        publish_workflow = (ROOT / ".github/workflows/publish.yml").read_text()
        publish_script = (ROOT / "tools/publish_release.sh").read_text()

        # One Windows Desktop installer and one Windows Runtime archive join the
        # fixed asset set every stage re-verifies.
        self.assertIn('"aeloon-lite-$version-x64.exe"', candidate)
        self.assertIn('"aeloon-lite-$version-x64.exe"', publish_workflow)
        self.assertIn('"aeloon-lite-$DESKTOP_VERSION-x64.exe"', publish_workflow)
        self.assertIn('"aeloon-lite-$desktop_version-x64.exe"', publish_script)
        self.assertEqual(
            publish_workflow.count("aeloon-runtime-windows-x86_64.tar.zst"), 3
        )
        self.assertIn('"aeloon-runtime-windows-x86_64.tar.zst"', publish_script)

    def test_public_issue_forms_and_reconcile_workflow_are_present(self) -> None:
        bug = (ROOT / ".github/ISSUE_TEMPLATE/bug.yml").read_text()
        feature = (ROOT / ".github/ISSUE_TEMPLATE/feature.yml").read_text()
        config = (ROOT / ".github/ISSUE_TEMPLATE/config.yml").read_text()
        reconcile_workflow = (ROOT / ".github/workflows/reconcile-public-issues.yml").read_text()
        for form in (bug, feature):
            self.assertIn("status:needs-triage", form)
            self.assertIn("version", form)
            self.assertIn("environment", form)
            self.assertRegex(form, r"(?i)(password|密码).*(token|Token)")
        self.assertIn("blank_issues_enabled: false", config)
        self.assertIn('cron: "7,22,37,52 * * * *"', reconcile_workflow)
        self.assertIn("tools/issue_flow.py reconcile", reconcile_workflow)
        self.assertNotIn("github.event.issue.title", reconcile_workflow)

    def _fixture(
        self,
        product: str,
        payload: bytes,
        *,
        desktop_format: str = "deb",
        os_release: str = "ID=ubuntu\n",
    ) -> dict[str, object]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        tools = root / "bin"
        tools.mkdir()
        downloads = root / "downloads"
        curl_log = root / "curl.log"
        install_log = root / "install.log"
        channel = root / "stable"
        artifact = root / "artifact"
        artifact.write_bytes(payload)
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
                    "# aeloon-release-v2",
                    f"# product={product}",
                    f"# version={version}",
                    "# release=v9.9.9",
                    f"# source={repository}@{'ab' * 20}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        write_executable(tools / "uname", '#!/bin/sh\n[ "${1:-}" = "-s" ] && echo Linux || echo x86_64\n')
        write_executable(
            tools / "apt-get",
            '#!/bin/sh\n[ -z "${FIXTURE_INSTALL_LOG:-}" ] || printf \'%s\\n\' "$*" >> "$FIXTURE_INSTALL_LOG"\nexit 0\n',
        )
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
  */install-server.sh)
    [ -z "${FIXTURE_FAIL_INSTALLER_FETCH:-}" ] || exit 22
    cp "$FIXTURE_INSTALLER" "$output"
    ;;
  *raw.githubusercontent.com*) cp "$FIXTURE_CHANNEL" "$output" ;;
  *)
    [ -z "${FIXTURE_CURL_LOG:-}" ] || printf '%s\n' "$url" >> "$FIXTURE_CURL_LOG"
    cp "$FIXTURE_ARTIFACT" "$output"
    ;;
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
            "FIXTURE_CURL_LOG": str(curl_log),
            "FIXTURE_INSTALL_LOG": str(install_log),
            "FIXTURE_INSTALLER": str(ROOT / "install-server.sh"),
        }
        return {
            "downloads": downloads,
            "env": env,
            "channel": channel,
            "tools": tools,
            "curl_log": curl_log,
            "install_log": install_log,
        }


if __name__ == "__main__":
    unittest.main()
