param(
    [switch]$NoDesktopShortcut
)

$ErrorActionPreference = "Stop"

$AppName = "Qualitrol FAT Summary"
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceApp = Join-Path $PackageRoot "QualitrolFATSummary"
$InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\Qualitrol FAT Summary"
$ExePath = Join-Path $InstallRoot "QualitrolFATSummary.exe"
$StartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Qualitrol"
$StartMenuShortcut = Join-Path $StartMenuDir "$AppName.lnk"
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "$AppName.lnk"

if (!(Test-Path -LiteralPath $SourceApp)) {
    throw "Cannot find bundled application folder: $SourceApp"
}

if (Test-Path -LiteralPath $InstallRoot) {
    Remove-Item -LiteralPath $InstallRoot -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
Copy-Item -Path (Join-Path $SourceApp "*") -Destination $InstallRoot -Recurse -Force

New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($StartMenuShortcut)
$Shortcut.TargetPath = $ExePath
$Shortcut.WorkingDirectory = $InstallRoot
$Shortcut.IconLocation = "$ExePath,0"
$Shortcut.Description = "Generate Qualitrol FAT visual summary PDFs"
$Shortcut.Save()

if (!$NoDesktopShortcut) {
    $Desktop = $Shell.CreateShortcut($DesktopShortcut)
    $Desktop.TargetPath = $ExePath
    $Desktop.WorkingDirectory = $InstallRoot
    $Desktop.IconLocation = "$ExePath,0"
    $Desktop.Description = "Generate Qualitrol FAT visual summary PDFs"
    $Desktop.Save()
}

$UninstallScript = @"
`$ErrorActionPreference = "Stop"
`$InstallRoot = "$InstallRoot"
`$StartMenuShortcut = "$StartMenuShortcut"
`$DesktopShortcut = "$DesktopShortcut"
if (Test-Path -LiteralPath `$StartMenuShortcut) { Remove-Item -LiteralPath `$StartMenuShortcut -Force }
if (Test-Path -LiteralPath `$DesktopShortcut) { Remove-Item -LiteralPath `$DesktopShortcut -Force }
if (Test-Path -LiteralPath `$InstallRoot) { Remove-Item -LiteralPath `$InstallRoot -Recurse -Force }
Write-Host "Qualitrol FAT Summary uninstalled."
"@

$UninstallPath = Join-Path $InstallRoot "Uninstall.ps1"
$UninstallScript | Set-Content -LiteralPath $UninstallPath -Encoding UTF8

Write-Host ""
Write-Host "$AppName installed successfully."
Write-Host "Installed to: $InstallRoot"
Write-Host "Start Menu shortcut: $StartMenuShortcut"
if (!$NoDesktopShortcut) { Write-Host "Desktop shortcut: $DesktopShortcut" }
Write-Host ""
