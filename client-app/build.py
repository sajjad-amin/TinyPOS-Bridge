#!/usr/bin/env python3
"""
TinyPOS Standalone Cross-Platform Build Script
Builds native standalone applications for macOS (.app), Windows (.exe), and Linux.
Automatically selects platform icons, packages dependencies with PyInstaller,
and cleans up build cache/temporary files upon completion.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Paths
CLIENT_DIR = Path(__file__).resolve().parent
ICON_DIR = CLIENT_DIR / "icon"
DIST_DIR = CLIENT_DIR / "dist"
BUILD_DIR = CLIENT_DIR / "build"
SPEC_FILE = CLIENT_DIR / "TinyPOS.spec"

APP_NAME = "TinyPOS"
BUNDLE_ID = "top.sayem.tinypos.client"
APP_VERSION = "1.0.0"


def print_step(title: str):
    print(f"\n\033[1;36m==>\033[0m \033[1m{title}\033[0m")


def print_success(msg: str):
    print(f"\033[1;32m✔\033[0m {msg}")


def print_warning(msg: str):
    print(f"\033[1;33m⚠\033[0m {msg}")


def print_error(msg: str):
    print(f"\033[1;31m✖\033[0m {msg}", file=sys.stderr)


def clean_cache():
    """Remove build directory, spec files, and python bytecode caches."""
    print_step("Cleaning build cache and temporary artifacts...")
    cleaned_items = []

    # 1. Remove PyInstaller build directory
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
        cleaned_items.append("build/")

    # 2. Remove .spec file
    if SPEC_FILE.exists():
        SPEC_FILE.unlink(missing_ok=True)
        cleaned_items.append(SPEC_FILE.name)

    # 3. Also check for any *.spec in CLIENT_DIR
    for f in CLIENT_DIR.glob("*.spec"):
        f.unlink(missing_ok=True)
        cleaned_items.append(f.name)

    # 4. Remove __pycache__ directories
    for pycache in CLIENT_DIR.rglob("__pycache__"):
        shutil.rmtree(pycache, ignore_errors=True)
        cleaned_items.append(f"{pycache.relative_to(CLIENT_DIR)}")

    # 5. Remove .pyc files
    for pyc in CLIENT_DIR.rglob("*.pyc"):
        pyc.unlink(missing_ok=True)

    if cleaned_items:
        print_success(f"Cache cleared: {', '.join(set(cleaned_items))}")
    else:
        print_success("No temporary cache files found.")


def ensure_pyinstaller():
    """Ensure PyInstaller is available in current Python environment."""
    try:
        import PyInstaller
        return
    except ImportError:
        print_step("PyInstaller not detected. Installing in current environment...")
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"]
        res = subprocess.run(cmd)
        if res.returncode != 0:
            print_error("Failed to install PyInstaller automatically. Please install it with: pip install pyinstaller")
            sys.exit(1)
        print_success("PyInstaller installed successfully.")


def get_platform_config():
    """Determine OS-specific icon, flags, and hidden imports."""
    os_name = platform.system()
    data_sep = ";" if os_name == "Windows" else ":"

    # Base hidden imports common to all platforms
    hidden_imports = [
        "bleak",
        "websockets",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "core",
        "core.config",
        "core.ble_driver",
        "core.relay_worker",
    ]

    collect_all = [
        "bleak",
        "websockets",
        "PIL",
    ]

    extra_args = []
    icon_path = None

    if os_name == "Darwin":
        # macOS Configuration (100% native Cocoa)
        icon_path = ICON_DIR / "icon.icns"
        hidden_imports.extend([
            "AppKit",
            "objc",
            "PyObjCTools",
            "PyObjCTools.AppHelper",
            "ui",
            "ui.mac_tray",
            "ui.mac_settings",
        ])
        extra_args = [
            "--windowed",
            f"--osx-bundle-identifier={BUNDLE_ID}",
        ]

    elif os_name == "Windows":
        # Windows Configuration
        icon_path = ICON_DIR / "icon.ico"
        import importlib.util
        if importlib.util.find_spec("PyQt6") is not None:
            collect_all.append("PyQt6")
        if importlib.util.find_spec("tkinter") is not None:
            collect_all.append("tkinter")
        if importlib.util.find_spec("pystray") is not None:
            collect_all.append("pystray")

        hidden_imports.extend([
            "ui",
            "ui.theme",
            "ui.styles",
            "ui.qt_settings",
            "ui.tk_settings",
            "ui.crossplatform_tray",
            "ctypes",
            "ctypes.wintypes",
        ])
        extra_args = [
            "--windowed",
            "--onefile",
        ]

    else:
        # Linux Configuration
        icon_path = ICON_DIR / "icon.png"
        import importlib.util
        if importlib.util.find_spec("PyQt6") is not None:
            collect_all.append("PyQt6")
        if importlib.util.find_spec("tkinter") is not None:
            collect_all.append("tkinter")
        if importlib.util.find_spec("pystray") is not None:
            collect_all.append("pystray")

        hidden_imports.extend([
            "ui",
            "ui.theme",
            "ui.styles",
            "ui.qt_settings",
            "ui.tk_settings",
            "ui.crossplatform_tray",
        ])
        extra_args = [
            "--windowed",
            "--onefile",
        ]

    return {
        "os_name": os_name,
        "icon_path": icon_path,
        "hidden_imports": hidden_imports,
        "collect_all": collect_all,
        "extra_args": extra_args,
        "data_sep": data_sep,
    }


def build_app(keep_cache: bool = False):
    """Execute the PyInstaller build process."""
    ensure_pyinstaller()
    cfg = get_platform_config()

    print_step(f"Starting TinyPOS standalone build for {cfg['os_name']} ({platform.machine()})...")

    # Construct PyInstaller command
    entry_script = CLIENT_DIR / "main.py"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name", APP_NAME,
        "--noconfirm",
        "--clean",
    ]

    # Add platform specific arguments
    cmd.extend(cfg["extra_args"])

    # Add icon if found
    if cfg["icon_path"] and cfg["icon_path"].exists():
        cmd.extend(["--icon", str(cfg["icon_path"])])
        print_success(f"Attached platform icon: {cfg['icon_path'].name}")
    else:
        print_warning(f"Icon file not found at {cfg['icon_path']}; proceeding with default icon.")

    # Add data directories
    if ICON_DIR.exists():
        cmd.extend(["--add-data", f"{ICON_DIR}{cfg['data_sep']}icon"])

    # Add collect-all packages (ensures all dynamic backends like winrt/bluezdbus/pystray are packaged)
    for pkg in cfg.get("collect_all", []):
        cmd.extend(["--collect-all", pkg])

    # Add hidden imports
    for imp in cfg["hidden_imports"]:
        cmd.extend(["--hidden-import", imp])

    # Entry point
    cmd.append(str(entry_script))

    print(f"Build command: {' '.join(cmd)}\n")

    # Run PyInstaller
    res = subprocess.run(cmd, cwd=str(CLIENT_DIR))

    if res.returncode != 0:
        print_error(f"PyInstaller build failed with exit code {res.returncode}")
        if not keep_cache:
            clean_cache()
        sys.exit(res.returncode)

    # Success: Report output location
    print_step("Build completed successfully!")

    if cfg["os_name"] == "Darwin":
        out_target = DIST_DIR / f"{APP_NAME}.app"
        if out_target.exists():
            # Inject macOS TCC Bluetooth privacy permissions & LSUIElement into Info.plist
            import plistlib
            plist_path = out_target / "Contents" / "Info.plist"
            if plist_path.exists():
                try:
                    with open(plist_path, "rb") as fp:
                        pl = plistlib.load(fp)
                    pl["NSBluetoothAlwaysUsageDescription"] = (
                        "TinyPOS requires Bluetooth access to discover, connect to, and send print jobs to your portable thermal receipt printer."
                    )
                    pl["NSBluetoothPeripheralUsageDescription"] = (
                        "TinyPOS requires Bluetooth access to connect to your portable thermal printer."
                    )
                    pl["CFBundleShortVersionString"] = APP_VERSION
                    pl["CFBundleVersion"] = APP_VERSION
                    pl["NSHighResolutionCapable"] = True
                    pl["LSUIElement"] = True  # Native Menu Bar agent app (runs as status item without Dock clutter)
                    with open(plist_path, "wb") as fp:
                        plistlib.dump(pl, fp)

                    # Re-sign ad-hoc so macOS TCC subsystem accepts the modified Info.plist
                    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(out_target)], capture_output=True)
                    print_success("Injected Bluetooth privacy permissions & signed macOS bundle.")
                except Exception as e:
                    print_warning(f"Failed to post-process Info.plist: {e}")

            print_success(f"Application Bundle: \033[1m{out_target}\033[0m")
            print(f"  To run: open \"{out_target}\"")
            print(f"  To install: cp -R \"{out_target}\" /Applications/")
    elif cfg["os_name"] == "Windows":
        out_target = DIST_DIR / f"{APP_NAME}.exe"
        if out_target.exists():
            size_mb = out_target.stat().st_size / (1024 * 1024)
            print_success(f"Executable: \033[1m{out_target}\033[0m ({size_mb:.1f} MB)")
    else:
        out_target = DIST_DIR / APP_NAME
        if out_target.exists():
            size_mb = out_target.stat().st_size / (1024 * 1024)
            print_success(f"Executable: \033[1m{out_target}\033[0m ({size_mb:.1f} MB)")

    # Clean build cache unless explicitly requested to keep
    if not keep_cache:
        clean_cache()


def main():
    parser = argparse.ArgumentParser(description="TinyPOS Desktop Client Standalone Builder")
    parser.add_argument("--clean-only", action="store_true", help="Remove build cache and artifacts without building")
    parser.add_argument("--keep-cache", action="store_true", help="Preserve intermediate build/ directory and spec file")
    args = parser.parse_args()

    if args.clean_only:
        clean_cache()
        return

    build_app(keep_cache=args.keep_cache)


if __name__ == "__main__":
    main()
