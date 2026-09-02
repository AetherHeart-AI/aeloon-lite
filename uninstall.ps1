#Requires -Version 5.1
# Removes the aeloon-lite desktop application on Windows. User settings and
# Runtime data are preserved unless -PurgeData is specified. External projects
# are never removed.

[CmdletBinding()]
param(
  [switch]$PurgeData,
  [switch]$Yes
)

# An assisted electron-builder installer writes "<productName> <version>" as
# the DisplayName, a one-click one writes the bare product name, and a
# per-user install lands in HKCU instead of HKLM.
function Get-InstalledDesktop {
  $roots = @(
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
  )
  foreach ($root in $roots) {
    foreach ($entry in @(Get-ItemProperty -Path $root -ErrorAction SilentlyContinue)) {
      $name = $entry.DisplayName
      if ($name -eq "aeloon-lite" -or $name -eq "aeloon-lite $($entry.DisplayVersion)") {
        return $entry
      }
    }
  }
  return $null
}

function Uninstall-AeloonDesktop {
  $ErrorActionPreference = "Stop"

  if ($env:OS -ne "Windows_NT") { throw "uninstall.ps1 runs on Windows only." }

  $installed = Get-InstalledDesktop
  if (-not $installed -and -not $PurgeData) {
    Write-Host "aeloon-lite is not installed."
    return
  }

  if (-not $Yes) {
    $detail = ""
    if ($PurgeData) { $detail = " and delete its private user data" }
    if (-not [Environment]::UserInteractive) {
      throw "No interactive terminal is available; rerun with -Yes."
    }
    $reply = Read-Host "Uninstall aeloon-lite$detail? [y/N]"
    if ($reply -notmatch '^(y|yes)$') {
      Write-Host "Uninstall cancelled."
      return
    }
  }

  if ($installed) {
    $command = $installed.UninstallString
    if (-not $command) { throw "The installed aeloon-lite has no uninstall command." }
    # A per-user install records `"<path>" /currentuser`; keep that argument.
    $arguments = @("/S")
    if ($command -match '^\s*"([^"]+)"\s*(.*)$') {
      $uninstaller = $Matches[1]
      if ($Matches[2].Trim()) { $arguments += $Matches[2].Trim() }
    } else {
      $uninstaller = $command.Trim()
    }
    $process = Start-Process -FilePath $uninstaller -ArgumentList $arguments -PassThru
    $process.WaitForExit()
    # The NSIS uninstaller copies itself into TEMP and re-executes, so the
    # process we waited on exits before the registry entry disappears.
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-InstalledDesktop) -and (Get-Date) -lt $deadline) {
      Start-Sleep -Seconds 1
    }
    if (Get-InstalledDesktop) { throw "The aeloon-lite uninstaller did not finish." }
  }

  if ($PurgeData) {
    if (-not $env:APPDATA -or -not $env:LOCALAPPDATA) {
      throw "APPDATA and LOCALAPPDATA are required for -PurgeData."
    }
    Remove-Item -LiteralPath (Join-Path $env:APPDATA "dev.aeloon.desktop") `
      -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $env:LOCALAPPDATA "dev.aeloon.desktop") `
      -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Removed aeloon-lite private settings, credentials, cache, and Runtime data."
  }

  Write-Host "Uninstalled aeloon-lite."
}

Uninstall-AeloonDesktop
