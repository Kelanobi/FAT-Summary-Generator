$ErrorActionPreference = "Stop"

$AppName = "Qualitrol FAT Summary"
$InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\Qualitrol FAT Summary"
$StartMenuShortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Qualitrol\$AppName.lnk"
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "$AppName.lnk"

if (Test-Path -LiteralPath $StartMenuShortcut) { Remove-Item -LiteralPath $StartMenuShortcut -Force }
if (Test-Path -LiteralPath $DesktopShortcut) { Remove-Item -LiteralPath $DesktopShortcut -Force }
if (Test-Path -LiteralPath $InstallRoot) { Remove-Item -LiteralPath $InstallRoot -Recurse -Force }

Write-Host "$AppName uninstalled."

