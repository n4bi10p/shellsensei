"""
learning.py
Tracks the user's command usage and learning progress.
Awards achievements. All data stored in a single JSON file — no database.
"""

import json
import os
from pathlib import Path
from datetime import datetime


TRACKER_PATH = Path.home() / ".shellsensei" / "progress.json"

# Command → category mapping
CATEGORIES = {
    "file_ops": [
        "ls", "cd", "cp", "mv", "rm", "mkdir", "rmdir", "find",
        "locate", "touch", "cat", "less", "more", "head", "tail",
        "tree", "file", "stat", "du", "df",
    ],
    "packages": [
        "apt", "apt-get", "pacman", "dnf", "yum", "zypper",
        "pip", "pip3", "npm", "yarn", "cargo", "gem", "brew",
    ],
    "permissions": [
        "chmod", "chown", "sudo", "su", "groups", "id", "whoami", "usermod",
    ],
    "text_editing": [
        "vim", "nvim", "nano", "vi", "sed", "awk", "grep", "cut",
        "tr", "sort", "uniq", "wc",
    ],
    "networking": [
        "ping", "curl", "wget", "ssh", "scp", "rsync",
        "netstat", "ifconfig", "ip", "traceroute", "nslookup", "dig",
    ],
    "processes": [
        "ps", "kill", "top", "htop", "nice", "bg", "fg",
        "jobs", "killall", "pkill", "pgrep",
    ],
    "git": [
        "git",
    ],
    "docker": [
        "docker", "docker-compose",
    ],
    "system": [
        "uname", "uptime", "date", "cal", "history",
        "reboot", "shutdown", "systemctl", "journalctl",
    ],
}

# Achievement definitions
ACHIEVEMENTS = [
    {
        "id":   "first_cmd",
        "name": "First Steps",
        "icon": "🌱",
        "desc": "Ran your first command",
        "check": lambda cats, total: total >= 1,
    },
    {
        "id":   "ten_cmds",
        "name": "Getting Started",
        "icon": "🚶",
        "desc": "Ran 10 commands total",
        "check": lambda cats, total: total >= 10,
    },
    {
        "id":   "file_explorer",
        "name": "File Explorer",
        "icon": "📂",
        "desc": "Used 5 file operation commands",
        "check": lambda cats, total: cats.get("file_ops", 0) >= 5,
    },
    {
        "id":   "package_pro",
        "name": "Package Pro",
        "icon": "📦",
        "desc": "Installed or managed 3 packages",
        "check": lambda cats, total: cats.get("packages", 0) >= 3,
    },
    {
        "id":   "sudo_savvy",
        "name": "Sudo Savvy",
        "icon": "🛡️",
        "desc": "Used permission commands 3 times safely",
        "check": lambda cats, total: cats.get("permissions", 0) >= 3,
    },
    {
        "id":   "git_guru",
        "name": "Git Guru",
        "icon": "🔀",
        "desc": "Used git 5 times",
        "check": lambda cats, total: cats.get("git", 0) >= 5,
    },
    {
        "id":   "network_ninja",
        "name": "Network Ninja",
        "icon": "🌐",
        "desc": "Used 3 networking commands",
        "check": lambda cats, total: cats.get("networking", 0) >= 3,
    },
    {
        "id":   "text_master",
        "name": "Text Master",
        "icon": "✏️",
        "desc": "Used 4 text editing commands",
        "check": lambda cats, total: cats.get("text_editing", 0) >= 4,
    },
    {
        "id":   "docker_dev",
        "name": "Docker Dev",
        "icon": "🐳",
        "desc": "Used docker 3 times",
        "check": lambda cats, total: cats.get("docker", 0) >= 3,
    },
    {
        "id":   "fifty_cmds",
        "name": "Power User",
        "icon": "⚡",
        "desc": "Ran 50 commands total",
        "check": lambda cats, total: total >= 50,
    },
]


def _load() -> dict:
    """Load tracker from JSON file."""
    if TRACKER_PATH.exists():
        try:
            with open(TRACKER_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "categories": {cat: 0 for cat in CATEGORIES},
        "unlocked": [],
        "total": 0,
        "history": [],  # last 50 commands with timestamps
    }


def _save(tracker: dict):
    """Save tracker to JSON file."""
    TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKER_PATH, "w") as f:
        json.dump(tracker, f, indent=2)


def track_command(command: str) -> tuple:
    """
    Record that the user ran a command.
    Categorizes it and checks for new achievements.

    Returns:
        (tracker_dict, list_of_newly_unlocked_achievements)
    """
    tracker = _load()
    cmd_base = command.strip().split()[0] if command.strip() else ""

    # Find and increment category
    for category, commands in CATEGORIES.items():
        if cmd_base in commands:
            tracker["categories"][category] = tracker["categories"].get(category, 0) + 1
            break

    # Increment total
    tracker["total"] = tracker.get("total", 0) + 1

    # Log to history (keep last 50)
    tracker.setdefault("history", []).append({
        "cmd": command,
        "at": datetime.now().isoformat(),
    })
    tracker["history"] = tracker["history"][-50:]

    # Check achievements
    new_unlocks = []
    cats = tracker["categories"]
    total = tracker["total"]

    for ach in ACHIEVEMENTS:
        if ach["id"] not in tracker.get("unlocked", []):
            if ach["check"](cats, total):
                tracker.setdefault("unlocked", []).append(ach["id"])
                new_unlocks.append(ach)

    _save(tracker)
    return tracker, new_unlocks


def get_progress_lines() -> list:
    """
    Returns a list of strings representing the current learning progress.
    Used by the TUI to render the progress panel.
    """
    tracker = _load()
    cats = tracker.get("categories", {})
    total = tracker.get("total", 0)
    unlocked = tracker.get("unlocked", [])

    lines = []
    lines.append("📊  Learning Progress")
    lines.append("─" * 44)

    # Sort categories by count descending
    sorted_cats = sorted(cats.items(), key=lambda x: -x[1])

    for cat, count in sorted_cats:
        # Each category: 10 commands = 100%
        pct = min(count * 10, 100)
        bar_full = pct // 5   # 20 segments
        bar_empty = 20 - bar_full
        bar = "█" * bar_full + "░" * bar_empty
        label = cat.replace("_", " ").title()
        lines.append(f"  {label:<16} {bar} {pct:>3}%")

    lines.append("─" * 44)
    lines.append(f"  Total commands run: {total}")
    lines.append("")

    # Achievements
    lines.append(f"🏆  Achievements  ({len(unlocked)}/{len(ACHIEVEMENTS)})")
    lines.append("─" * 44)

    for ach in ACHIEVEMENTS:
        if ach["id"] in unlocked:
            lines.append(f"  ✅  {ach['icon']}  {ach['name']}  —  {ach['desc']}")
        else:
            lines.append(f"  🔒  {ach['icon']}  {ach['name']}  —  {ach['desc']}")

    return lines
