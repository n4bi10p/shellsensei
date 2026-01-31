"""
system_profiler.py
Scans the entire Linux system and saves a detailed profile to ~/.shellsensei/
This profile is fed to Gemini on every query so it KNOWS the user's system.
"""

import os
import json
import platform
import subprocess
import shutil
from pathlib import Path
from datetime import datetime

import distro
import psutil


PROFILE_DIR = Path.home() / ".shellsensei"
PROFILE_MD = PROFILE_DIR / "system_profile.md"
PROFILE_JSON = PROFILE_DIR / "system_profile.json"


def detect_package_manager() -> str:
    managers = ["apt", "pacman", "dnf", "zypper", "emerge", "apk", "yum", "brew"]
    for pm in managers:
        if shutil.which(pm):
            return pm
    return "unknown"


def detect_shell() -> dict:
    shell_path = os.environ.get("SHELL", "/bin/bash")
    shell_name = Path(shell_path).name
    try:
        r = subprocess.run(
            [shell_path, "--version"],
            capture_output=True, text=True, timeout=2
        )
        version = r.stdout.strip().split("\n")[0]
    except Exception:
        version = "unknown"
    return {"name": shell_name, "path": shell_path, "version": version}


def detect_de_wm() -> str:
    de = os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION")
    if de:
        return de

    wms = ["i3", "sway", "hyprland", "bspwm", "awesome", "dwm", "openbox", "qtile", "herbstluftwm"]
    for wm in wms:
        try:
            subprocess.run(["pgrep", "-x", wm], check=True, capture_output=True, timeout=2)
            return wm
        except Exception:
            continue
    return "unknown"


def get_tool_versions() -> dict:
    tools = [
        "python3", "node", "npm", "git", "docker",
        "gcc", "g++", "make", "nvim", "vim",
        "go", "rustc", "cargo", "java", "javac",
        "kubectl", "terraform", "aws", "code"
    ]
    versions = {}
    for tool in tools:
        if shutil.which(tool):
            try:
                r = subprocess.run(
                    [tool, "--version"],
                    capture_output=True, text=True, timeout=2
                )
                line = (r.stdout or r.stderr).strip().split("\n")[0]
                versions[tool] = line
            except Exception:
                versions[tool] = "installed"
    return versions


def get_installed_packages() -> list:
    pm = detect_package_manager()
    commands = {
        "apt":     "dpkg -l 2>/dev/null | awk 'NR>5 {print $2, $3}'",
        "pacman":  "pacman -Q 2>/dev/null",
        "dnf":     "rpm -qa --queryformat '%{NAME} %{VERSION}\n' 2>/dev/null",
        "yum":     "rpm -qa --queryformat '%{NAME} %{VERSION}\n' 2>/dev/null",
        "zypper":  "rpm -qa --queryformat '%{NAME} %{VERSION}\n' 2>/dev/null",
        "apk":     "apk list --installed 2>/dev/null",
    }
    cmd = commands.get(pm)
    if not cmd:
        return []
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return [line.strip() for line in r.stdout.strip().split("\n") if line.strip()]
    except Exception:
        return []


def get_user_groups() -> list:
    try:
        r = subprocess.run(["id", "-Gn"], capture_output=True, text=True, timeout=2)
        return r.stdout.strip().split()
    except Exception:
        return []


def get_hardware() -> dict:
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cpu_cores": psutil.cpu_count(logical=False),
        "cpu_threads": psutil.cpu_count(logical=True),
        "arch": platform.machine(),
        "ram_total_gb": round(mem.total / (1024 ** 3), 1),
        "ram_available_gb": round(mem.available / (1024 ** 3), 1),
        "disk_total_gb": round(disk.total / (1024 ** 3), 1),
        "disk_free_gb": round(disk.free / (1024 ** 3), 1),
    }


def generate_profile() -> dict:
    shell_info = detect_shell()
    profile = {
        "generated_at": datetime.now().isoformat(),
        "distro": distro.name(pretty=True),
        "distro_id": distro.id(),
        "distro_version": distro.version(),
        "distro_codename": distro.codename(),
        "kernel": platform.release(),
        "package_manager": detect_package_manager(),
        "shell": shell_info,
        "de_wm": detect_de_wm(),
        "user": os.environ.get("USER", "unknown"),
        "home": os.environ.get("HOME", ""),
        "groups": get_user_groups(),
        "hardware": get_hardware(),
        "tool_versions": get_tool_versions(),
        "packages": get_installed_packages(),
    }
    return profile


def save_profile(profile: dict):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    # --- Save JSON (for programmatic use) ---
    with open(PROFILE_JSON, "w") as f:
        json.dump(profile, f, indent=2)

    # --- Save Markdown (fed to Gemini as context) ---
    hw = profile["hardware"]
    shell = profile["shell"]

    md_lines = [
        "# shellsensei — System Profile",
        f"**Generated:** {profile['generated_at']}",
        "",
        "## Operating System",
        f"- **Distribution:** {profile['distro']}",
        f"- **Distro ID:** {profile['distro_id']}",
        f"- **Version:** {profile['distro_version']}",
        f"- **Codename:** {profile['distro_codename']}",
        f"- **Kernel:** {profile['kernel']}",
        "",
        "## Package Manager",
        f"- **Package Manager:** {profile['package_manager']}",
        "",
        "## Shell",
        f"- **Shell:** {shell['name']}",
        f"- **Version:** {shell['version']}",
        f"- **Path:** {shell['path']}",
        "",
        "## Desktop Environment / Window Manager",
        f"- **DE/WM:** {profile['de_wm']}",
        "",
        "## User",
        f"- **Username:** {profile['user']}",
        f"- **Home:** {profile['home']}",
        f"- **Groups:** {', '.join(profile['groups'])}",
        "",
        "## Hardware",
        f"- **CPU:** {hw['cpu_cores']} cores / {hw['cpu_threads']} threads ({hw['arch']})",
        f"- **RAM:** {hw['ram_total_gb']} GB total, {hw['ram_available_gb']} GB available",
        f"- **Disk (/):** {hw['disk_total_gb']} GB total, {hw['disk_free_gb']} GB free",
        "",
        "## Installed Developer Tools",
    ]

    for tool, ver in profile["tool_versions"].items():
        md_lines.append(f"- **{tool}:** {ver}")

    pkg_count = len(profile["packages"])
    md_lines += [
        "",
        f"## Installed Packages ({pkg_count} total)",
        "```",
    ]
    # Include first 300 packages (enough context, not too bloated)
    for pkg in profile["packages"][:300]:
        md_lines.append(pkg)
    if pkg_count > 300:
        md_lines.append(f"... and {pkg_count - 300} more packages")
    md_lines.append("```")

    PROFILE_MD.write_text("\n".join(md_lines))


def load_profile_md() -> str:
    if PROFILE_MD.exists():
        return PROFILE_MD.read_text()
    return ""


def load_profile_json() -> dict:
    if PROFILE_JSON.exists():
        with open(PROFILE_JSON) as f:
            return json.load(f)
    return {}
