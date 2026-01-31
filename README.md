# ShellSensei 🐧

> **A system-aware AI terminal assistant for Linux beginners.**  
> Powered by Google Gemini — gives commands that actually work on YOUR system.

---

## The Problem

Every AI terminal tool (Warp, Copilot CLI, shell-gpt) is **context-blind**. They don't know if you're on Ubuntu or Arch. They suggest `apt install` when you need `pacman`. Commands fail because the AI is guessing.

Beginners copy-paste commands from Stack Overflow that break on their system. They get errors they can't understand. They're stuck.

## The Solution

ShellSensei **scans your entire system** on first run and saves a detailed profile:

- Distro, kernel, package manager
- Shell, desktop environment / window manager
- All installed packages and versions
- Developer tools, user groups, hardware

**Every single AI response reads this profile.** So when you ask "install docker", it doesn't guess — it knows you're on Arch and gives you `pacman -S docker`. It knows you're not in the docker group yet and tells you to fix that too.

Zero hallucination. Maximum accuracy.

## Features

| Feature | What it does |
|---|---|
| 🔍 **System Profiling** | Scans your full system on first run, saves to `~/.ShellSensei/` |
| 🤖 **System-Aware AI** | Every Gemini response is tailored to your exact setup |
| 🔧 **Auto Error Fix** | When a command fails, instantly diagnoses and suggests a fix |
| 💡 **Smart Suggestions** | Shows logical next steps after every command |
| 🏆 **Learning Tracker** | Tracks your progress across categories, awards achievements |
| 🛡️ **Safety Checks** | Blocks dangerous commands, warns before running sudo |

## Install

```bash
git clone https://github.com/n4bi10p/shellsensei.git
cd shellsensei
pip install -r requirements.txt
```

## Setup

Get a **free** Gemini API key (no credit card needed):  
👉 https://aistudio.google.com/apikey

```bash
echo "GEMINI_API_KEY=your_key_here" > .env
```

## Run

```bash
python tui_app.py
```

## How to Use

```
💬  Ask anything in plain English:

    > list files in this folder
    > install docker
    > how do I check disk space
    > why is my disk full
    > set up a python virtual environment

📋  Special commands:

    run <cmd>      Run a shell command directly
    1 / 2 / 3     Pick a suggested next step
    profile        Show your system profile
    progress       Show learning progress + achievements
    help           Show help
    exit           Quit

⌨️   Keyboard shortcuts:

    Ctrl+L         Clear screen
    Ctrl+H         Help
    Ctrl+P         Profile
```

## How It Works

```
You type plain English
        ↓
ShellSensei loads your system profile
        ↓
Sends query + full system context to Gemini
        ↓
Gemini returns a command tailored to YOUR system
        ↓
ShellSensei explains it, checks safety, runs it
        ↓
If it fails → auto-diagnoses and suggests a fix
        ↓
Tracks what you learned
```

## Tech Stack

| Tool | Role |
|---|---|
| Python 3.11+ | Core language |
| Google Gemini API | AI brain (gemini-2.0-flash) |
| Textual | Terminal UI framework |
| Rich | Terminal formatting |
| psutil | System metrics |
| distro | Linux distro detection |

## Project Structure

```
ShellSensei/
├── tui_app.py            ← Entry point + full TUI
├── system_profiler.py    ← Scans system, generates profile
├── ai_core.py            ← All Gemini API calls
├── executor.py           ← Command execution + safety layer
├── learning.py           ← Progress tracking + achievements
├── requirements.txt      ← Python dependencies
└── .env                  ← API key (gitignored)
```

## Built At

**Hack Days Pune** — MLH × Linux Club  
January 2026

---

*ShellSensei is open source. Contributions welcome.*
