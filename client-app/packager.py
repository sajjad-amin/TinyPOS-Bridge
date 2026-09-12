#!/usr/bin/env python3
"""
TinyPOS Standalone Packager
Converts standalone build artifacts (macOS .app, Windows .exe, Linux binary)
into ready-to-distribute installers and packages according to the platform:
  - macOS:   .dmg drag-and-drop installer
  - Linux:   .deb (Debian/Ubuntu package) & .tar.gz (portable bundle with installer)
  - Windows: Inno Setup script (.iss / .inn) & compiled Setup.exe installer
"""

from __future__ import annotations

import argparse
import io
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from typing import Optional

CLIENT_DIR = Path(__file__).resolve().parent
DIST_DIR = CLIENT_DIR / "dist"
INSTALLER_DIR = DIST_DIR / "installer"
ICON_DIR = CLIENT_DIR / "icon"

APP_NAME = "TinyPOS"
DEFAULT_VERSION = "1.0.0"
APP_DESCRIPTION = "TinyPOS Cloud Bridge & Portable Thermal Receipt Printer Driver"
APP_HOMEPAGE = "https://sajjadamin.com"
MAINTAINER = "Sajjad Amin <https://sajjadamin.com>"


def print_step(title: str):
    print(f"\n\033[1;36m==>\033[0m \033[1m{title}\033[0m")


def print_success(msg: str):
    print(f"\033[1;32m✔\033[0m {msg}")


def print_warning(msg: str):
    print(f"\033[1;33m⚠\033[0m {msg}")


def print_error(msg: str):
    print(f"\033[1;31m✖\033[0m {msg}", file=sys.stderr)


def prompt_version(cli_version: Optional[str] = None) -> str:
    """Prompt the user for a version number (default: 1.0.0)."""
    if cli_version and cli_version.strip():
        return cli_version.strip()

    if sys.stdin.isatty():
        try:
            val = input(f"Enter version number [default: {DEFAULT_VERSION}]: ").strip()
            if val:
                return val
        except (EOFError, KeyboardInterrupt):
            print()

    return DEFAULT_VERSION


def ensure_dist_exists():
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    INSTALLER_DIR.mkdir(parents=True, exist_ok=True)


def ensure_built(target_os: str, version: str = DEFAULT_VERSION, keep_cache: bool = False):
    """Verify that the required binary exists in dist/; invoke build.py if missing."""
    app_target = None
    extra_build_flags = []
    if target_os == "Darwin":
        app_target = DIST_DIR / f"{APP_NAME}.app"
    elif target_os == "Windows":
        onedir_target = DIST_DIR / APP_NAME
        exe_target = DIST_DIR / f"{APP_NAME}.exe"
        if onedir_target.is_dir() and (onedir_target / f"{APP_NAME}.exe").is_file():
            app_target = onedir_target
        elif exe_target.is_file():
            app_target = exe_target
        else:
            # Build onedir by default on Windows so Inno Setup can shrink installer to 30-45 MB
            extra_build_flags.append("--onedir")
    else:
        app_target = DIST_DIR / APP_NAME

    if not app_target or not app_target.exists():
        print_step(f"Pre-compiled binary for '{target_os}' not found. Invoking build.py...")
        build_script = CLIENT_DIR / "build.py"
        cmd = [sys.executable, str(build_script), "--version", version] + extra_build_flags
        if keep_cache:
            cmd.append("--keep-cache")
        res = subprocess.run(cmd, cwd=str(CLIENT_DIR))
        if res.returncode != 0:
            print_error("Compilation with build.py failed.")
            sys.exit(res.returncode)

    # Re-check after build
    if target_os == "Windows":
        onedir_target = DIST_DIR / APP_NAME
        exe_target = DIST_DIR / f"{APP_NAME}.exe"
        if onedir_target.is_dir() and (onedir_target / f"{APP_NAME}.exe").is_file():
            app_target = onedir_target
        elif exe_target.is_file():
            app_target = exe_target

    if app_target and app_target.exists():
        print_success(f"Verified standalone target: {app_target.name}")
    else:
        print_warning(f"Target binary '{app_target}' was not generated.")


# ==============================================================================
# 1. macOS: DMG Installer Package
# ==============================================================================

def package_macos_dmg(version: str) -> Optional[Path]:
    """Create a drag-and-drop .dmg disk image on macOS."""
    print_step(f"Packaging macOS Disk Image (.dmg) for {APP_NAME} v{version}...")

    app_path = DIST_DIR / f"{APP_NAME}.app"
    if not app_path.exists():
        print_error(f"Application bundle not found: {app_path}")
        return None

    if platform.system() != "Darwin":
        print_warning("Creating macOS DMG files requires macOS (hdiutil is not available on other OS).")
        return None

    hdiutil_path = shutil.which("hdiutil")
    if not hdiutil_path:
        print_error("hdiutil utility not found in PATH.")
        return None

    dmg_out = INSTALLER_DIR / f"{APP_NAME}-{version}.dmg"
    staging_dir = DIST_DIR / "dmg_staging"

    # Clean previous staging and output
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)
    if dmg_out.exists():
        dmg_out.unlink(missing_ok=True)

    staging_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Copy .app into staging
        staged_app = staging_dir / f"{APP_NAME}.app"
        print("  Copying application bundle to staging area...")
        shutil.copytree(app_path, staged_app, symlinks=True)

        # 2. Add /Applications symlink for drag-and-drop installation
        app_symlink = staging_dir / "Applications"
        os.symlink("/Applications", app_symlink)

        # 3. Create DMG using hdiutil
        print("  Compressing disk image with UDZO format...")
        cmd = [
            hdiutil_path,
            "create",
            "-volname", f"{APP_NAME} Installer",
            "-srcfolder", str(staging_dir),
            "-ov",
            "-format", "UDZO",
            str(dmg_out),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print_error(f"hdiutil failed to create DMG: {res.stderr.strip()}")
            return None

        # 4. Report results
        size_mb = dmg_out.stat().st_size / (1024 * 1024)
        print_success(f"macOS DMG created: \033[1m{dmg_out}\033[0m ({size_mb:.1f} MB)")
        return dmg_out

    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)


# ==============================================================================
# 2. Linux: Debian Package (.deb)
# ==============================================================================

def _build_deb_pure_python(staging_dir: Path, deb_path: Path):
    """Build a standard Debian binary package (.deb) using pure Python ar and tar archives."""
    def make_tar_bytes(source_dir: Path) -> bytes:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for root, _, files in os.walk(source_dir):
                for f in files:
                    full = Path(root) / f
                    rel = full.relative_to(source_dir)
                    ti = tar.gettarinfo(str(full), arcname=f"./{rel.as_posix()}")
                    ti.uid = 0
                    ti.gid = 0
                    ti.uname = "root"
                    ti.gname = "root"
                    if str(rel).startswith("usr/bin"):
                        ti.mode = 0o755
                    with open(full, "rb") as fp:
                        tar.addfile(ti, fp)
        return buf.getvalue()

    # 1. Create control.tar.gz
    control_bytes = make_tar_bytes(staging_dir / "DEBIAN")

    # 2. Create data.tar.gz
    data_dir = staging_dir / "data"
    data_bytes = make_tar_bytes(data_dir)

    # 3. Write ar archive: !<arch>\n + entries
    with open(deb_path, "wb") as deb:
        deb.write(b"!<arch>\n")

        def write_ar_entry(name: str, content: bytes):
            # name (16), mtime (12), uid (6), gid (6), mode (8), size (10), magic (2)
            hdr = f"{name:<16}{int(time.time()):<12}0     0     100644  {len(content):<10}`\n".encode("ascii")
            deb.write(hdr)
            deb.write(content)
            if len(content) % 2 != 0:
                deb.write(b"\n")

        write_ar_entry("debian-binary", b"2.0\n")
        write_ar_entry("control.tar.gz", control_bytes)
        write_ar_entry("data.tar.gz", data_bytes)


def is_elf_binary(path: Path) -> bool:
    """Verify that the binary begins with the Linux ELF magic bytes."""
    try:
        if not path.is_file():
            return False
        with open(path, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except Exception:
        return False


def get_linux_target_binary() -> tuple[Optional[Path], bool]:
    """
    Locates the Linux binary in dist/.
    Returns (path, is_directory) or (None, False).
    """
    candidates = [DIST_DIR / APP_NAME, DIST_DIR / "tinypos"]
    for cand in candidates:
        if not cand.exists():
            continue
        if cand.is_file():
            if platform.system() != "Linux" and not is_elf_binary(cand):
                continue
            return cand, False
        elif cand.is_dir():
            inner = cand / APP_NAME
            if not inner.is_file():
                inner = cand / "tinypos"
            if inner.is_file():
                if platform.system() != "Linux" and not is_elf_binary(inner):
                    continue
                return cand, True
    return None, False


def package_linux_deb(version: str) -> Optional[Path]:
    """Create a Debian package (.deb) for Linux distributions."""
    print_step(f"Packaging Linux Debian Package (.deb) for {APP_NAME} v{version}...")

    bin_path, is_dir = get_linux_target_binary()
    if not bin_path:
        print_warning(
            f"No Linux ELF executable found in {DIST_DIR}.\n"
            f"  (Current OS is {platform.system()}. Linux Debian packages must be compiled on Linux or with an ELF binary.)"
        )
        return None

    # Determine target architecture
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "amd64"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    elif "arm" in machine:
        arch = "armhf"
    else:
        arch = "all"

    deb_name = f"tinypos_{version}_{arch}.deb"
    deb_out = INSTALLER_DIR / deb_name
    staging = DIST_DIR / "deb_staging"

    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)

    try:
        # Build hierarchy
        deb_control_dir = staging / "DEBIAN"
        deb_control_dir.mkdir(parents=True, exist_ok=True)

        data_root = staging if shutil.which("dpkg-deb") else (staging / "data")
        bin_target_dir = data_root / "usr" / "bin"
        apps_dir = data_root / "usr" / "share" / "applications"
        icons_dir = data_root / "usr" / "share" / "icons" / "hicolor" / "512x512" / "apps"

        bin_target_dir.mkdir(parents=True, exist_ok=True)
        apps_dir.mkdir(parents=True, exist_ok=True)
        icons_dir.mkdir(parents=True, exist_ok=True)

        # 1. Binary / Application Files
        dest_bin = bin_target_dir / "tinypos"
        if is_dir:
            lib_dir = data_root / "usr" / "lib" / "tinypos"
            lib_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(bin_path, lib_dir, dirs_exist_ok=True, symlinks=True)
            launcher_sh = """#!/bin/sh
exec /usr/lib/tinypos/TinyPOS "$@"
"""
            dest_bin.write_text(launcher_sh, encoding="utf-8")
            dest_bin.chmod(0o755)
        else:
            shutil.copy2(bin_path, dest_bin)
            dest_bin.chmod(0o755)

        # 2. Desktop file
        desktop_content = f"""[Desktop Entry]
Name={APP_NAME}
GenericName=Thermal Receipt Printer Driver
Comment={APP_DESCRIPTION}
Exec=/usr/bin/tinypos
Icon=tinypos
Terminal=false
Type=Application
Categories=Utility;Office;HardwareSettings;
StartupNotify=false
Keywords=printer;thermal;pos;bluetooth;receipt;
"""
        (apps_dir / "tinypos.desktop").write_text(desktop_content, encoding="utf-8")

        # 3. Application icon
        src_icon = ICON_DIR / "icon.png"
        if src_icon.exists():
            shutil.copy2(src_icon, icons_dir / "tinypos.png")

        # 4. Control file
        if is_dir:
            total_size = sum(f.stat().st_size for f in bin_path.rglob("*") if f.is_file())
            installed_size = total_size // 1024
        else:
            installed_size = bin_path.stat().st_size // 1024

        control_content = f"""Package: tinypos
Version: {version}
Section: utils
Priority: optional
Architecture: {arch}
Installed-Size: {installed_size}
Maintainer: {MAINTAINER}
Homepage: {APP_HOMEPAGE}
Description: {APP_NAME} Cloud Bridge
 {APP_DESCRIPTION}
 Allows seamless printing to Bluetooth ESC/POS and portable thermal receipt
 printers from TinyPOS web console.
"""
        (deb_control_dir / "control").write_text(control_content, encoding="utf-8")

        # 5. Build .deb
        dpkg_deb = shutil.which("dpkg-deb")
        if dpkg_deb:
            print(f"  Building with native {dpkg_deb}...")
            res = subprocess.run([dpkg_deb, "--build", str(staging), str(deb_out)], capture_output=True, text=True)
            if res.returncode != 0:
                print_warning(f"dpkg-deb returned error: {res.stderr.strip()}; falling back to pure Python packager...")
                _build_deb_pure_python(staging, deb_out)
        else:
            print("  Building Debian archive with pure Python packager...")
            _build_deb_pure_python(staging, deb_out)

        size_mb = deb_out.stat().st_size / (1024 * 1024)
        print_success(f"Linux Debian package created: \033[1m{deb_out}\033[0m ({size_mb:.1f} MB)")
        print(f"  Install command: sudo apt install \"./{deb_out.name}\"")
        return deb_out

    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


# ==============================================================================
# 3. Linux: Portable Tarball (.tar.gz)
# ==============================================================================

def package_linux_tar(version: str) -> Optional[Path]:
    """Create a portable .tar.gz bundle for Linux with an automatic installer script."""
    print_step(f"Packaging Linux Portable Tarball (.tar.gz) for {APP_NAME} v{version}...")

    bin_path, is_dir = get_linux_target_binary()
    if not bin_path:
        print_warning(
            f"No Linux ELF executable found in {DIST_DIR}.\n"
            f"  (Current OS is {platform.system()}. Linux tarball bundles must be compiled on Linux or with an ELF binary.)"
        )
        return None

    machine = platform.machine() or "x86_64"
    tar_name = f"{APP_NAME}-{version}-linux-{machine}.tar.gz"
    tar_out = INSTALLER_DIR / tar_name
    staging = DIST_DIR / f"{APP_NAME}-{version}"

    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    try:
        # Copy binary / directory
        if is_dir:
            lib_dest = staging / "app"
            shutil.copytree(bin_path, lib_dest, dirs_exist_ok=True, symlinks=True)
            dest_bin = staging / "tinypos"
            dest_bin.write_text("""#!/bin/sh
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/app/TinyPOS" "$@"
""", encoding="utf-8")
            dest_bin.chmod(0o755)
        else:
            dest_bin = staging / "tinypos"
            shutil.copy2(bin_path, dest_bin)
            dest_bin.chmod(0o755)

        # Copy icon
        src_icon = ICON_DIR / "icon.png"
        if src_icon.exists():
            shutil.copy2(src_icon, staging / "tinypos.png")

        # Create desktop launcher file
        desktop_content = f"""[Desktop Entry]
Name={APP_NAME}
Comment={APP_DESCRIPTION}
Exec=tinypos
Icon=tinypos
Terminal=false
Type=Application
Categories=Utility;Office;
"""
        (staging / "tinypos.desktop").write_text(desktop_content, encoding="utf-8")

        # Create install.sh
        if is_dir:
            install_sh = f"""#!/bin/sh
set -e
echo "Installing {APP_NAME} to user local directory (~/.local)..."
mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.local/lib/{APP_NAME}"
mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.local/share/icons/hicolor/512x512/apps"

DIR="$(cd "$(dirname "$0")" && pwd)"

cp -R "$DIR/app/"* "$HOME/.local/lib/{APP_NAME}/"
cat << 'EOF' > "$HOME/.local/bin/tinypos"
#!/bin/sh
exec "$HOME/.local/lib/{APP_NAME}/TinyPOS" "$@"
EOF
chmod 755 "$HOME/.local/bin/tinypos"

if [ -f "$DIR/tinypos.png" ]; then
    cp "$DIR/tinypos.png" "$HOME/.local/share/icons/hicolor/512x512/apps/tinypos.png"
fi
if [ -f "$DIR/tinypos.desktop" ]; then
    cp "$DIR/tinypos.desktop" "$HOME/.local/share/applications/tinypos.desktop"
    sed -i "s|Exec=tinypos|Exec=$HOME/.local/bin/tinypos|g" "$HOME/.local/share/applications/tinypos.desktop"
fi

echo "✔ {APP_NAME} installed successfully! You can launch it with: tinypos"
"""
        else:
            install_sh = f"""#!/bin/sh
set -e
echo "Installing {APP_NAME} to user local directory (~/.local)..."
mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.local/share/icons/hicolor/512x512/apps"

DIR="$(cd "$(dirname "$0")" && pwd)"

install -m 755 "$DIR/tinypos" "$HOME/.local/bin/tinypos"
if [ -f "$DIR/tinypos.png" ]; then
    cp "$DIR/tinypos.png" "$HOME/.local/share/icons/hicolor/512x512/apps/tinypos.png"
fi
if [ -f "$DIR/tinypos.desktop" ]; then
    cp "$DIR/tinypos.desktop" "$HOME/.local/share/applications/tinypos.desktop"
    sed -i "s|Exec=tinypos|Exec=$HOME/.local/bin/tinypos|g" "$HOME/.local/share/applications/tinypos.desktop"
fi

echo "✔ {APP_NAME} installed successfully! You can launch it with: tinypos"
"""
        inst_file = staging / "install.sh"
        inst_file.write_text(install_sh, encoding="utf-8")
        inst_file.chmod(0o755)

        # Create README
        readme_content = f"""{APP_NAME} Portable Bundle v{version}
=============================
This archive contains the standalone {APP_NAME} desktop client for Linux ({machine}).

To run directly:
  ./tinypos

To install for current user:
  ./install.sh
"""
        (staging / "README.txt").write_text(readme_content, encoding="utf-8")

        # Compress into .tar.gz
        with tarfile.open(tar_out, "w:gz") as tar:
            tar.add(staging, arcname=f"{APP_NAME}-{version}")

        size_mb = tar_out.stat().st_size / (1024 * 1024)
        print_success(f"Linux tarball created: \033[1m{tar_out}\033[0m ({size_mb:.1f} MB)")
        return tar_out

    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


# ==============================================================================
# 4. Windows: Inno Setup Script (.iss / .inn) & Compiler
# ==============================================================================

def generate_inno_script(version: str) -> Path:
    """Generate a production-grade Inno Setup script (.iss / .inn) for Windows."""
    print_step(f"Generating Inno Setup Script for {APP_NAME} v{version}...")

    # Detect whether we have a directory bundle (--onedir) or a single executable (--onefile)
    has_onedir = (DIST_DIR / APP_NAME).is_dir() and ((DIST_DIR / APP_NAME) / f"{APP_NAME}.exe").is_file()

    if has_onedir:
        files_section = f"""Source: "..\\{APP_NAME}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs"""
    else:
        files_section = f"""Source: "..\\{{#MyAppExeName}}"; DestDir: "{{app}}"; Flags: ignoreversion
Source: "..\\..\\icon\\*"; DestDir: "{{app}}\\icon"; Flags: ignoreversion recursesubdirs createallsubdirs"""

    iss_content = f"""; Inno Setup Installer Script for {APP_NAME}
; Automatically generated by packager.py

#define MyAppName "{APP_NAME}"
#define MyAppVersion "{version}"
#define MyAppPublisher "TinyPOS"
#define MyAppURL "{APP_HOMEPAGE}"
#define MyAppExeName "{APP_NAME}.exe"

[Setup]
AppId={{{{D8A4E391-7C21-4E8F-8F6B-3C9A1B2D4E5F}}}}
AppName={{#MyAppName}}
AppVersion={{#MyAppVersion}}
AppPublisher={{#MyAppPublisher}}
AppPublisherURL={{#MyAppURL}}
AppSupportURL={{#MyAppURL}}
AppUpdatesURL={{#MyAppURL}}
DefaultDirName={{autopf}}\\{{#MyAppName}}
DisableProgramGroupPage=yes
OutputBaseFilename={APP_NAME}-Setup-{{#MyAppVersion}}
OutputDir=.
SetupIconFile=..\\..\\icon\\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={{app}}\\{{#MyAppExeName}}
VersionInfoVersion={version}
VersionInfoCompany=TinyPOS
VersionInfoDescription={APP_DESCRIPTION}
VersionInfoTextVersion={version}
VersionInfoCopyright=Copyright (C) 2026 TinyPOS
VersionInfoProductName={APP_NAME}
VersionInfoProductVersion={version}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"; Flags: unchecked
Name: "startupicon"; Description: "Start {APP_NAME} automatically when logging in"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
{files_section}

[Icons]
Name: "{{autoprograms}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"
Name: "{{autodesktop}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; Tasks: desktopicon
Name: "{{userstartup}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; Tasks: startupicon

[Run]
Filename: "{{app}}\\{{#MyAppExeName}}"; Description: "{{cm:LaunchProgram,{{#StringChange(MyAppName, '&', '&&')}}}}"; Flags: nowait postinstall skipifsilent
"""
    iss_file = INSTALLER_DIR / f"{APP_NAME}.iss"
    inn_file = INSTALLER_DIR / f"{APP_NAME}.inn"

    iss_file.write_text(iss_content, encoding="utf-8")
    inn_file.write_text(iss_content, encoding="utf-8")

    print_success(f"Inno Setup script written: \033[1m{iss_file.name}\033[0m and \033[1m{inn_file.name}\033[0m in \033[1m{INSTALLER_DIR}\033[0m")
    return iss_file


def find_iscc_executable() -> Optional[Path]:
    """Find ISCC.exe compiler across PATH, registry, and Inno Setup 7 / 6 installation directories."""
    # 1. PATH check
    for bin_name in ("iscc", "ISCC.exe", "iscc.exe"):
        which_path = shutil.which(bin_name)
        if which_path and Path(which_path).exists():
            return Path(which_path)

    # 2. Windows Registry lookup (if on Windows)
    if platform.system() == "Windows":
        try:
            import winreg
            hives = [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]
            subkeys = [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
            ]
            for hive in hives:
                for subkey in subkeys:
                    try:
                        with winreg.OpenKey(hive, subkey) as root_key:
                            num_subkeys, _, _ = winreg.QueryInfoKey(root_key)
                            for i in range(num_subkeys):
                                try:
                                    child_name = winreg.EnumKey(root_key, i)
                                    if "inno setup" in child_name.lower():
                                        with winreg.OpenKey(root_key, child_name) as app_key:
                                            install_loc, _ = winreg.QueryValueEx(app_key, "InstallLocation")
                                            if install_loc:
                                                cand = Path(install_loc) / "ISCC.exe"
                                                if cand.exists():
                                                    return cand
                                except Exception:
                                    continue
                    except Exception:
                        continue
        except Exception:
            pass

    # 3. Comprehensive directory scan across Inno Setup 7, Inno Setup 6, etc.
    base_dirs = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("ProgramW6432", r"C:\Program Files"),
        os.environ.get("LOCALAPPDATA", ""),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
    ]

    for base in base_dirs:
        if not base or not os.path.isdir(base):
            continue
        base_path = Path(base)
        # Check modern Inno Setup 7 first, then 6, 5, etc.
        for folder_name in ("Inno Setup 7", "Inno Setup 6", "Inno Setup 5", "Inno Setup"):
            cand = base_path / folder_name / "ISCC.exe"
            if cand.exists():
                return cand
        # Glob fallback for any custom version numbering (e.g. Inno Setup 7.0)
        try:
            for cand in sorted(base_path.glob("Inno Setup*/ISCC.exe"), reverse=True):
                if cand.exists():
                    return cand
        except Exception:
            pass

    return None


def compile_inno_setup(iss_file: Path) -> Optional[Path]:
    """Search for ISCC.exe and compile installer executable on Windows."""
    iscc_bin = find_iscc_executable()

    if not iscc_bin:
        print_warning(
            "Inno Setup Compiler (ISCC.exe) not found.\n"
            "  Script was generated. To build the installer on Windows, install Inno Setup 7 or 6\n"
            "  from https://jrsoftware.org/isdl.php and compile TinyPOS.iss."
        )
        return None

    print(f"  Compiling installer with Inno Setup compiler: {iscc_bin}...")
    res = subprocess.run([str(iscc_bin), str(iss_file)], cwd=str(INSTALLER_DIR), capture_output=True, text=True)
    if res.returncode == 0:
        setup_exe = INSTALLER_DIR / f"{APP_NAME}-Setup.exe"
        # Find any matching installer in installer dir
        matches = list(INSTALLER_DIR.glob(f"{APP_NAME}-Setup*.exe"))
        if matches:
            setup_exe = matches[0]
            size_mb = setup_exe.stat().st_size / (1024 * 1024)
            print_success(f"Windows installer created: \033[1m{setup_exe}\033[0m ({size_mb:.1f} MB)")
            return setup_exe
    else:
        print_error(f"Inno Setup compilation failed with exit code {res.returncode}")
        if res.stdout and res.stdout.strip():
            print(f"\n\033[1;33m--- Inno Setup Compiler Output ---\033[0m\n{res.stdout.strip()}")
        if res.stderr and res.stderr.strip():
            print(f"\n\033[1;31m--- Inno Setup Compiler Errors ---\033[0m\n{res.stderr.strip()}", file=sys.stderr)
    return None


def package_windows(version: str) -> Optional[Path]:
    """Handle Windows packaging: generate Inno script and compile if ISCC is present."""
    iss_file = generate_inno_script(version)
    if platform.system() == "Windows":
        return compile_inno_setup(iss_file)
    else:
        print_warning("Cross-compiling Inno Setup requires Windows (or Wine with Inno Setup installed).")
        return iss_file


def clean_dist():
    """Remove the dist/ directory and intermediate build caches."""
    print_step(f"Cleaning distribution directory: {DIST_DIR}...")
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR, ignore_errors=True)
        print_success(f"Removed dist directory: {DIST_DIR}")
    else:
        print_success(f"Directory already clean: {DIST_DIR}")

    build_dir = CLIENT_DIR / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir, ignore_errors=True)
        print_success(f"Removed build cache: {build_dir}")


# ==============================================================================
# CLI Entrypoint
# ==============================================================================

def main():
    # Fast path for positional 'clean' command: python packager.py clean
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("clean", "distclean", "clean-dist"):
        clean_dist()
        return

    parser = argparse.ArgumentParser(
        description="TinyPOS Cross-Platform Standalone Packager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python packager.py                     Auto-detects platform and packages output
  python packager.py --clean             Clean and remove dist/ directory
  python packager.py clean               Clean and remove dist/ directory
  python packager.py --version 1.2.0     Specify version without interactive prompt
  python packager.py --target dmg        Build macOS DMG disk image
  python packager.py --target deb        Build Linux Debian (.deb) package
  python packager.py --target tar        Build Linux portable (.tar.gz) bundle
  python packager.py --target inno       Generate Windows Inno Setup script (.iss/.inn)
  python packager.py --target all        Generate all supported formats
""",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove dist/ and build cache directories and exit",
    )
    parser.add_argument(
        "--version", "-v",
        type=str,
        default=None,
        help=f"Application version (default: prompt user, or {DEFAULT_VERSION})",
    )
    parser.add_argument(
        "--target", "-t",
        choices=["auto", "dmg", "deb", "tar", "inno", "all", "clean"],
        default="auto",
        help="Packaging target format (default: auto detect from current OS)",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Skip build.py invocation if dist binary is already compiled",
    )
    parser.add_argument(
        "--keep-cache",
        action="store_true",
        help="Preserve intermediate build caches",
    )

    args = parser.parse_args()

    # If clean requested via flag or target
    if args.clean or args.target == "clean":
        clean_dist()
        return

    os_name = platform.system()

    print_step(f"TinyPOS Distribution Packager - Host: {os_name} ({platform.machine()})")

    # 1. Obtain Version Number
    version = prompt_version(args.version)
    print_success(f"Packaging version: \033[1m{version}\033[0m")

    ensure_dist_exists()

    # 2. Check or build binary if needed
    if not args.no_build:
        ensure_built(os_name, version=version, keep_cache=args.keep_cache)

    target = args.target

    # 3. Execute requested packaging targets
    if target == "auto":
        if os_name == "Darwin":
            package_macos_dmg(version)
        elif os_name == "Windows":
            package_windows(version)
        else:
            package_linux_deb(version)
            package_linux_tar(version)

    elif target == "dmg":
        package_macos_dmg(version)

    elif target == "deb":
        package_linux_deb(version)

    elif target == "tar":
        package_linux_tar(version)

    elif target == "inno":
        package_windows(version)

    elif target == "all":
        print_step("Generating all package formats...")
        generate_inno_script(version)
        if os_name == "Darwin":
            package_macos_dmg(version)
        if (DIST_DIR / APP_NAME).exists():
            package_linux_deb(version)
            package_linux_tar(version)
        if os_name == "Windows":
            compile_inno_setup(INSTALLER_DIR / f"{APP_NAME}.iss")

    print_step("Packaging process completed.")


if __name__ == "__main__":
    main()
