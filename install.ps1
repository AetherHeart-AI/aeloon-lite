#Requires -Version 5.1
# Installs the current stable aeloon-lite desktop release on Windows.
# Historical version selection is intentionally unsupported.

[CmdletBinding()]
param(
  [string]$DownloadOnly,
  [ValidateSet("overwrite", "update", "skip")]
  [string]$IfInstalled,
  [switch]$Silent
)

$Repository = "AetherHeart-AI/aeloon-lite"
$RawRoot = "https://raw.githubusercontent.com/$Repository/main"

function Get-MetadataValue {
  param([string[]]$Lines, [string]$Key)

  $prefix = "# $Key="
  $matched = @($Lines | Where-Object { $_.StartsWith($prefix) })
  if ($matched.Count -ne 1) { throw "Invalid desktop release metadata." }
  return $matched[0].Substring($prefix.Length)
}

# electron-builder's NSIS package writes DisplayName from productName, and a
# per-user install lands in HKCU instead of HKLM.
function Get-InstalledDesktop {
  $roots = @(
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
  )
  foreach ($root in $roots) {
    foreach ($entry in @(Get-ItemProperty -Path $root -ErrorAction SilentlyContinue)) {
      if ($entry.DisplayName -eq "aeloon-lite") { return $entry }
    }
  }
  return $null
}

function Get-SemverCore {
  param([string]$Text)

  $found = [regex]::Match($Text, '\d+\.\d+\.\d+')
  if ($found.Success) { return [version]$found.Value }
  return $null
}

function Select-InstalledAction {
  param([string]$InstalledVersion, [string]$Version)

  if ($IfInstalled) { return $IfInstalled }

  Write-Host "aeloon-lite $InstalledVersion is already installed; stable is $Version."
  if (-not [Environment]::UserInteractive) {
    throw "No interactive terminal is available; rerun with -IfInstalled overwrite, update, or skip."
  }
  while ($true) {
    $reply = Read-Host "Choose [o]verwrite, [u]pdate, or [s]kip"
    switch -Regex ($reply) {
      '^(o|overwrite)$' { return "overwrite" }
      '^(u|update)$' { return "update" }
      '^(s|skip)$' { return "skip" }
      default { Write-Host "Please choose overwrite, update, or skip." }
    }
  }
}

function Install-AeloonDesktop {
  $ErrorActionPreference = "Stop"
  # Windows PowerShell 5.1 may still default to TLS 1.0.
  [Net.ServicePointManager]::SecurityProtocol =
    [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

  if ($env:OS -ne "Windows_NT") { throw "install.ps1 runs on Windows only." }
  if ([Environment]::OSVersion.Version.Major -lt 10) {
    throw "aeloon-lite requires Windows 10 or later."
  }
  $architecture = $env:PROCESSOR_ARCHITEW6432
  if (-not $architecture) { $architecture = $env:PROCESSOR_ARCHITECTURE }
  if ($architecture -ne "AMD64") {
    throw "aeloon-lite supports only x64 Windows; detected $architecture."
  }

  if ($env:AELOON_CHANNEL_FILE) {
    $channel = Get-Content -LiteralPath $env:AELOON_CHANNEL_FILE
  } else {
    $response = Invoke-WebRequest -Uri "$RawRoot/channels/desktop/stable" -UseBasicParsing `
      -Headers @{ "Cache-Control" = "no-cache" }
    $channel = [regex]::Split($response.Content, "\r?\n")
  }

  $schema = $channel[0]
  if ($schema -ne "# aeloon-release-v1" -and $schema -ne "# aeloon-release-v2") {
    throw "Unsupported desktop release metadata."
  }
  $product = Get-MetadataValue $channel "product"
  $version = Get-MetadataValue $channel "version"
  $source = Get-MetadataValue $channel "source"
  if ($product -ne "desktop") { throw "Release metadata is not for desktop." }
  if ($version -notmatch '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$') {
    throw "Stable desktop version is invalid."
  }
  if ($source -notmatch '^AetherHeart-AI/aeloon-lite-ui@[0-9a-f]{40}$') {
    throw "Desktop source identity is invalid."
  }
  $sourceCommit = $source.Split("@")[1]
  if ($schema -eq "# aeloon-release-v2") {
    $tag = Get-MetadataValue $channel "release"
    if ($tag -notmatch '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$') {
      throw "Unified release tag is invalid."
    }
  } else {
    $tag = "v$version"
  }

  if (-not $DownloadOnly) {
    $installed = Get-InstalledDesktop
    if ($installed) {
      $installedVersion = $installed.DisplayVersion
      if (-not $installedVersion) { $installedVersion = "unknown" }
      switch (Select-InstalledAction $installedVersion $version) {
        "skip" {
          Write-Host "Keeping the installed aeloon-lite $installedVersion."
          return
        }
        "update" {
          $installedCore = Get-SemverCore $installedVersion
          if ($installedCore -and $installedCore -ge [version]$version) {
            Write-Host ("Installed aeloon-lite $installedVersion is already at or newer than " +
              "stable $version; nothing to update.")
            return
          }
          Write-Host "Updating aeloon-lite $installedVersion to $version."
        }
        "overwrite" {
          Write-Host "Overwriting aeloon-lite $installedVersion with stable $version."
        }
      }
    }
  }

  $asset = "aeloon-lite-$version-x64.exe"
  $assetUrl = "https://github.com/$Repository/releases/download/$tag/$asset"
  $temporary = Join-Path ([IO.Path]::GetTempPath()) ("aeloon-lite-" + [guid]::NewGuid().ToString("n"))

  Write-Host "Downloading aeloon-lite $version from GitHub..."
  try {
    Invoke-WebRequest -Uri $assetUrl -OutFile $temporary -UseBasicParsing
    if ($DownloadOnly) {
      $destination = $DownloadOnly
    } elseif ($env:USERPROFILE -and (Test-Path -LiteralPath "$env:USERPROFILE\Downloads")) {
      $destination = "$env:USERPROFILE\Downloads"
    } else {
      $destination = $PWD.Path
    }
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    $installer = Join-Path $destination $asset
    Move-Item -LiteralPath $temporary -Destination $installer -Force
  } finally {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
  }
  Write-Host "Downloaded installer: $installer"
  if ($DownloadOnly) { return }

  Unblock-File -LiteralPath $installer
  Write-Host ("This internal build is not signed; Windows SmartScreen may warn. " +
    "Choose 'More info' > 'Run anyway'.")
  if ($Silent) {
    $process = Start-Process -FilePath $installer -ArgumentList "/S" -PassThru
  } else {
    $process = Start-Process -FilePath $installer -PassThru
  }
  # -Wait would also wait on the app the installer launches when it finishes.
  $process.WaitForExit()
  if ($process.ExitCode -ne 0) {
    throw "The aeloon-lite installer failed with code $($process.ExitCode)."
  }
  Write-Host "Installed aeloon-lite $version (source commit $sourceCommit)."
}

Install-AeloonDesktop
