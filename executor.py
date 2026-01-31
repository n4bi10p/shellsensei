"""
executor.py
Handles command execution with a safety layer.
Blocks dangerous commands, warns on sudo, captures output and errors.
"""

import os
import re
import time
import subprocess


# Commands that are ALWAYS blocked — can destroy the system
BLOCKED_PATTERNS = [
    r"rm\s+-rf\s*/\s*$",
    r"rm\s+-rf\s*/\b",
    r"dd\s+.*of=/dev/sd",
    r"dd\s+.*of=/dev/hd",
    r"dd\s+.*of=/dev/nvme",
    r"mkfs\.",
    r":\(\)\{\s*:\|:\&\s*\};:",        # fork bomb
    r":\(\)\{\s*:\|:\s*&\s*\};:",      # fork bomb variant
    r"--no-preserve-root",
    r"chmod\s+777\s+/\s*$",
    r"chown\s+-R.*\s+/\s*$",
    r"rm\s+-rf\s+/home\s*$",
    r"rm\s+-rf\s+/etc",
    r"rm\s+-rf\s+/usr",
    r"rm\s+-rf\s+/var",
    r"rm\s+-rf\s+/bin",
    r"rm\s+-rf\s+/sbin",
    r"rm\s+-rf\s+/lib",
    r"rm\s+-rf\s+/boot",
]

# Commands that need explicit user confirmation
CAUTION_PATTERNS = [
    (r"\bsudo\b",             "This command requires administrator (sudo) privileges."),
    (r"\brm\s+-rf\b",         "This will permanently delete files/directories."),
    (r"\brm\s+-r\b",          "This will recursively delete a directory."),
    (r"\bcurl\b.*\|\s*(bash|sh)\b",  "This downloads a script from the internet and runs it directly."),
    (r"\bwget\b.*\|\s*(bash|sh)\b",  "This downloads a script from the internet and runs it directly."),
    (r"\bchmod\s+-R\b",       "This changes permissions recursively."),
    (r"\bdd\b",               "dd can be dangerous if used incorrectly."),
]


def check_safety(command: str) -> tuple:
    """
    Check if a command is safe to run.

    Returns:
        (level, warning_message)
        level: "safe" | "caution" | "dangerous"
    """
    # Check blocked first
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, command):
            return ("dangerous", "⛔ This command is BLOCKED — it can permanently destroy your system.")

    # Check caution
    warnings = []
    for pattern, msg in CAUTION_PATTERNS:
        if re.search(pattern, command):
            warnings.append(msg)

    if warnings:
        return ("caution", " | ".join(warnings))

    return ("safe", "")


def execute(command: str, timeout: int = 30) -> dict:
    """
    Execute a shell command and capture everything.

    Returns:
        {
            "success": bool,
            "output": str (stdout),
            "error": str (stderr),
            "exit_code": int,
            "duration_ms": int
        }
    """
    start = time.time()

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),
            cwd=os.getcwd(),
        )

        duration_ms = int((time.time() - start) * 1000)

        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr,
            "exit_code": result.returncode,
            "duration_ms": duration_ms,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "error": f"Command timed out after {timeout} seconds.",
            "exit_code": -1,
            "duration_ms": timeout * 1000,
        }

    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "exit_code": -1,
            "duration_ms": int((time.time() - start) * 1000),
        }


def read_shell_history(n: int = 20) -> list:
    """
    Read the user's actual shell history file.
    Handles bash, zsh, and fish history formats.
    """
    shell = os.environ.get("SHELL", "/bin/bash")
    shell_name = os.path.basename(shell)

    history_files = {
        "bash": ".bash_history",
        "zsh":  ".zsh_history",
        "fish": ".local/share/fish/fish_history",
    }

    hfile = os.path.join(os.environ.get("HOME", ""), history_files.get(shell_name, ".bash_history"))

    if not os.path.exists(hfile):
        return []

    try:
        with open(hfile, "r", errors="ignore") as f:
            lines = f.read().strip().split("\n")
    except Exception:
        return []

    # zsh history format: ": timestamp:0:command"
    if shell_name == "zsh":
        cleaned = []
        for line in lines:
            if line.startswith(": "):
                parts = line.split(":", 3)
                if len(parts) >= 4:
                    cleaned.append(parts[3].strip())
            else:
                cleaned.append(line.strip())
        lines = cleaned

    # fish history format: "- cmd: command"
    if shell_name == "fish":
        cleaned = []
        for line in lines:
            if line.startswith("- cmd: "):
                cleaned.append(line[7:].strip())
        lines = cleaned

    # Return last N non-empty lines
    return [l.strip() for l in lines if l.strip()][-n:]
