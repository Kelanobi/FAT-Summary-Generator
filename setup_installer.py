from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk


APP_NAME = "Qualitrol FAT Summary"
APP_FOLDER = "QualitrolFATSummary"


def package_root() -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            return Path(bundle_root)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent / "installer"


def install_root() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "Programs" / APP_NAME


def start_menu_shortcut() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Qualitrol" / f"{APP_NAME}.lnk"


def desktop_shortcut() -> Path:
    return Path.home() / "Desktop" / f"{APP_NAME}.lnk"


def create_shortcut(shortcut_path: Path, target: Path) -> None:
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    script = f"""
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut('{shortcut_path}')
$Shortcut.TargetPath = '{target}'
$Shortcut.WorkingDirectory = '{target.parent}'
$Shortcut.IconLocation = '{target},0'
$Shortcut.Description = 'Generate Qualitrol FAT visual summary PDFs'
$Shortcut.Save()
"""
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def stop_running_app() -> None:
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "Get-Process QualitrolFATSummary -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue",
        ],
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    time.sleep(0.7)


def remove_existing_install(target: Path) -> None:
    if not target.exists():
        return
    stop_running_app()
    last_error: Exception | None = None
    for attempt in range(1, 7):
        try:
            shutil.rmtree(target)
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.45 * attempt)
    raise RuntimeError(
        "Could not replace the existing installation. "
        "Close Qualitrol FAT Summary and run the installer again."
    ) from last_error


def copy_app_payload(source: Path, target: Path) -> None:
    remove_existing_install(target)
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        dest = target / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)


def write_uninstaller(target_dir: Path) -> None:
    script = f"""$ErrorActionPreference = "Stop"
$InstallRoot = "{target_dir}"
$StartMenuShortcut = "{start_menu_shortcut()}"
$DesktopShortcut = "{desktop_shortcut()}"
if (Test-Path -LiteralPath $StartMenuShortcut) {{ Remove-Item -LiteralPath $StartMenuShortcut -Force }}
if (Test-Path -LiteralPath $DesktopShortcut) {{ Remove-Item -LiteralPath $DesktopShortcut -Force }}
if (Test-Path -LiteralPath $InstallRoot) {{ Remove-Item -LiteralPath $InstallRoot -Recurse -Force }}
Write-Host "{APP_NAME} uninstalled."
"""
    (target_dir / "Uninstall.ps1").write_text(script, encoding="utf-8")


class SetupApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} Setup")
        self.geometry("560x320")
        self.resizable(False, False)
        self.create_desktop_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Ready to install.")
        self._build_ui()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self, padding=22)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text=APP_NAME, font=("Arial", 20, "bold")).pack(anchor=tk.W)
        ttk.Label(
            frame,
            text="Install the local FAT report visual summary generator.",
            foreground="#5f6970",
        ).pack(anchor=tk.W, pady=(4, 18))

        destination = install_root()
        ttk.Label(frame, text="Install location", font=("Arial", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(frame, text=str(destination), foreground="#5f6970", wraplength=500).pack(anchor=tk.W, pady=(2, 12))

        ttk.Checkbutton(frame, text="Create desktop shortcut", variable=self.create_desktop_var).pack(anchor=tk.W)

        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill=tk.X, pady=(22, 8))
        ttk.Label(frame, textvariable=self.status_var, foreground="#5f6970").pack(anchor=tk.W)

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, side=tk.BOTTOM, pady=(18, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)
        self.install_button = ttk.Button(buttons, text="Install", command=self.install)
        self.install_button.pack(side=tk.RIGHT, padx=(0, 8))

    def install(self) -> None:
        self.install_button.configure(state=tk.DISABLED)
        self.progress.start(8)
        self.status_var.set("Installing...")
        self.after(50, self._install_now)

    def _install_now(self) -> None:
        try:
            root = package_root()
            source = root / APP_FOLDER
            if not source.exists():
                raise FileNotFoundError(f"Missing application folder: {source}")

            target = install_root()
            copy_app_payload(source, target)

            exe = target / "QualitrolFATSummary.exe"
            create_shortcut(start_menu_shortcut(), exe)
            if self.create_desktop_var.get():
                create_shortcut(desktop_shortcut(), exe)
            write_uninstaller(target)
        except Exception as exc:
            self.progress.stop()
            self.install_button.configure(state=tk.NORMAL)
            self.status_var.set("Installation failed.")
            messagebox.showerror("Installation failed", str(exc))
            return

        self.progress.stop()
        self.status_var.set("Installation complete.")
        if messagebox.askyesno("Installation complete", f"{APP_NAME} installed successfully.\n\nLaunch now?"):
            os.startfile(install_root() / "QualitrolFATSummary.exe")  # type: ignore[attr-defined]
        self.destroy()


def main() -> None:
    if "--smoke-test" in sys.argv:
        source = package_root() / APP_FOLDER
        if not source.exists():
            raise SystemExit(f"Missing application folder: {source}")
        raise SystemExit(0)
    if "--silent" in sys.argv:
        root = package_root()
        source = root / APP_FOLDER
        if not source.exists():
            raise SystemExit(f"Missing application folder: {source}")
        target = install_root()
        copy_app_payload(source, target)
        exe = target / "QualitrolFATSummary.exe"
        create_shortcut(start_menu_shortcut(), exe)
        if "--no-desktop" not in sys.argv:
            create_shortcut(desktop_shortcut(), exe)
        write_uninstaller(target)
        raise SystemExit(0)
    SetupApp().mainloop()


if __name__ == "__main__":
    main()
