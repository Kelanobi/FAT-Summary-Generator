param([switch] $Silent)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$appName = "Qualitrol FAT Summary"
$installDir = Join-Path $env:LOCALAPPDATA "Programs\Qualitrol FAT Summary"
$payloadZip = Join-Path $PSScriptRoot "Payload.zip"
$tempRoot = Join-Path $env:TEMP ("QualitrolFATSummaryInstall_" + [guid]::NewGuid().ToString("N"))

function New-Shortcut {
    param(
        [string] $ShortcutPath,
        [string] $TargetPath,
        [string] $WorkingDirectory
    )

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $TargetPath
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.IconLocation = $TargetPath
    $shortcut.Save()
}

function Remove-ExistingInstall {
    param([string] $Path)

    Get-Process QualitrolFATSummary -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            return
        }
        catch {
            if ($attempt -eq 5) {
                throw "Could not replace the existing installation. Close Qualitrol FAT Summary and run the installer again."
            }
            Start-Sleep -Milliseconds (400 * $attempt)
        }
    }
}

function Install-App {
    param([System.Windows.Forms.ProgressBar] $Progress, [System.Windows.Forms.Label] $Status)

    if (-not (Test-Path -LiteralPath $payloadZip)) {
        throw "Payload.zip was not found beside the installer bootstrap."
    }

    $Status.Text = "Preparing files..."
    $Progress.Value = 10
    [System.Windows.Forms.Application]::DoEvents()

    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    Expand-Archive -LiteralPath $payloadZip -DestinationPath $tempRoot -Force
    $sourceApp = Join-Path $tempRoot "QualitrolFATSummary"
    if (-not (Test-Path -LiteralPath (Join-Path $sourceApp "QualitrolFATSummary.exe"))) {
        throw "The installer payload is incomplete."
    }

    $Status.Text = "Installing application..."
    $Progress.Value = 40
    [System.Windows.Forms.Application]::DoEvents()

    Remove-ExistingInstall -Path $installDir
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
    Copy-Item -Path (Join-Path $sourceApp "*") -Destination $installDir -Recurse -Force

    $exePath = Join-Path $installDir "QualitrolFATSummary.exe"
    $uninstallPath = Join-Path $installDir "Uninstall.ps1"
    @'
$ErrorActionPreference = "Stop"
$installDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath("Desktop")
$startMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "Qualitrol"
Remove-Item -LiteralPath (Join-Path $desktop "Qualitrol FAT Summary.lnk") -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $startMenu "Qualitrol FAT Summary.lnk") -Force -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath $startMenu) {
    $remaining = Get-ChildItem -LiteralPath $startMenu -Force -ErrorAction SilentlyContinue
    if (-not $remaining) { Remove-Item -LiteralPath $startMenu -Force -ErrorAction SilentlyContinue }
}
Start-Sleep -Milliseconds 300
Remove-Item -LiteralPath $installDir -Recurse -Force
'@ | Set-Content -LiteralPath $uninstallPath -Encoding UTF8

    $Status.Text = "Creating shortcuts..."
    $Progress.Value = 75
    [System.Windows.Forms.Application]::DoEvents()

    $startMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) "Qualitrol"
    New-Item -ItemType Directory -Path $startMenuDir -Force | Out-Null
    New-Shortcut -ShortcutPath (Join-Path $startMenuDir "Qualitrol FAT Summary.lnk") -TargetPath $exePath -WorkingDirectory $installDir
    New-Shortcut -ShortcutPath (Join-Path ([Environment]::GetFolderPath("Desktop")) "Qualitrol FAT Summary.lnk") -TargetPath $exePath -WorkingDirectory $installDir

    $Progress.Value = 100
    $Status.Text = "Installation complete."
}

if ($Silent) {
    $progress = New-Object System.Windows.Forms.ProgressBar
    $status = New-Object System.Windows.Forms.Label
    Install-App -Progress $progress -Status $status
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    exit 0
}

$form = New-Object System.Windows.Forms.Form
$form.Text = $appName
$form.Width = 520
$form.Height = 330
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.BackColor = [System.Drawing.Color]::FromArgb(248, 250, 252)

$title = New-Object System.Windows.Forms.Label
$title.Text = "Qualitrol FAT Summary"
$title.Font = New-Object System.Drawing.Font("Segoe UI", 18, [System.Drawing.FontStyle]::Bold)
$title.ForeColor = [System.Drawing.Color]::FromArgb(51, 56, 59)
$title.AutoSize = $true
$title.Location = New-Object System.Drawing.Point(34, 30)
$form.Controls.Add($title)

$subtitle = New-Object System.Windows.Forms.Label
$subtitle.Text = "Install the PDM, GDM, and PDM/GDM FAT visual report generator."
$subtitle.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$subtitle.ForeColor = [System.Drawing.Color]::FromArgb(80, 88, 94)
$subtitle.AutoSize = $true
$subtitle.Location = New-Object System.Drawing.Point(38, 75)
$form.Controls.Add($subtitle)

$pathLabel = New-Object System.Windows.Forms.Label
$pathLabel.Text = "Install location:`r`n$installDir"
$pathLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$pathLabel.ForeColor = [System.Drawing.Color]::FromArgb(80, 88, 94)
$pathLabel.Size = New-Object System.Drawing.Size(440, 48)
$pathLabel.Location = New-Object System.Drawing.Point(38, 122)
$form.Controls.Add($pathLabel)

$status = New-Object System.Windows.Forms.Label
$status.Text = "Ready to install."
$status.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$status.ForeColor = [System.Drawing.Color]::FromArgb(51, 56, 59)
$status.Size = New-Object System.Drawing.Size(440, 22)
$status.Location = New-Object System.Drawing.Point(38, 182)
$form.Controls.Add($status)

$progress = New-Object System.Windows.Forms.ProgressBar
$progress.Size = New-Object System.Drawing.Size(440, 14)
$progress.Location = New-Object System.Drawing.Point(40, 210)
$progress.Style = "Continuous"
$form.Controls.Add($progress)

$installButton = New-Object System.Windows.Forms.Button
$installButton.Text = "Install"
$installButton.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$installButton.BackColor = [System.Drawing.Color]::FromArgb(214, 0, 28)
$installButton.ForeColor = [System.Drawing.Color]::White
$installButton.FlatStyle = "Flat"
$installButton.Size = New-Object System.Drawing.Size(120, 36)
$installButton.Location = New-Object System.Drawing.Point(232, 246)
$form.Controls.Add($installButton)

$cancelButton = New-Object System.Windows.Forms.Button
$cancelButton.Text = "Cancel"
$cancelButton.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$cancelButton.Size = New-Object System.Drawing.Size(120, 36)
$cancelButton.Location = New-Object System.Drawing.Point(360, 246)
$form.Controls.Add($cancelButton)

$cancelButton.Add_Click({ $form.Close() })
$installButton.Add_Click({
    try {
        $installButton.Enabled = $false
        $cancelButton.Enabled = $false
        Install-App -Progress $progress -Status $status
        [System.Windows.Forms.MessageBox]::Show("Qualitrol FAT Summary has been installed.", $appName, "OK", "Information") | Out-Null
        $form.Close()
    }
    catch {
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, "$appName Installer Error", "OK", "Error") | Out-Null
        $installButton.Enabled = $true
        $cancelButton.Enabled = $true
        $status.Text = "Installation failed."
    }
    finally {
        if (Test-Path -LiteralPath $tempRoot) {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
})

[void] $form.ShowDialog()
