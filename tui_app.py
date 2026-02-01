"""
tui_app.py — ShellSensei Main Application

Run with: python tui_app.py

This is the entry point. It builds the full Textual TUI and wires together:
  - system_profiler  → scans + saves system info
  - ai_core          → sends queries to Gemini with system context
  - executor         → runs commands safely
  - learning         → tracks progress + achievements
"""

import os
import sys
import json
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, TextArea, RichLog, Static
from textual.containers import Vertical
from textual.reactive import reactive
from textual.message import Message
from rich.text import Text

from system_profiler import (
    generate_profile,
    save_profile,
    load_profile_md,
    load_profile_json,
    PROFILE_MD,
)
from ai_core import get_ai_response, get_ai_response_async, get_error_fix
from executor import execute, check_safety, read_shell_history
from learning import track_command, get_progress_lines


# ---------------------------------------------------------------------------
# Custom TextArea that submits on Enter
# ---------------------------------------------------------------------------
class SubmitTextArea(TextArea):
    """TextArea that submits on Enter, new line on Ctrl+J."""
    
    class Submitted(Message):
        """Message sent when Enter is pressed."""
        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()
    
    def on_key(self, event) -> None:
        """Handle key events: Enter submits, Ctrl+J creates new line."""
        if event.key == "enter":
            # Enter = Submit query
            self.post_message(self.Submitted(self.text))
            self.load_text("")
            event.prevent_default()
            event.stop()
        elif event.key == "ctrl+j":
            # Ctrl+J = Insert new line (Line Feed)
            self.insert("\n")
            event.prevent_default()
            event.stop()
        # All other keys handled by TextArea normally


# ---------------------------------------------------------------------------
# CSS — all styling lives here
# ---------------------------------------------------------------------------
APP_CSS = """
Screen {
    background: #0d1117;
    color: #c9d1d9;
}

Header {
    background: #161b22;
    color: #ff6b6b;
    dock: top;
    height: 1;
}

#title-bar {
    background: #1a0505;
    color: #ff8888;
    text-align: center;
    height: 1;
    content-align: center middle;
}

Footer {
    background: #161b22;
    color: #8b949e;
    dock: bottom;
}

#sysbar {
    background: #1a0505;
    color: #ffa07a;
    height: 1;
    padding: 0 2;
    margin-bottom: 1;
}

#main-area {
    height: 1fr;
    padding: 0 1;
    min-height: 20;
}

#log {
    height: 1fr;
    border: round #ff4444;
    background: #0d1117;
    padding: 1;
    overflow-x: hidden;
    overflow-y: auto;
}

#suggestions-bar {
    display: none;
}

#input-row {
    height: 8;
    margin-top: 1;
    padding: 0 1;
}

#user-input {
    border: heavy #ff4444;
    background: #000000;
    color: #00ff00;
    height: 8;
    padding: 0 1;
}

#user-input:focus {
    border: heavy #ff6666;
    background: #000000;
    color: #00ff00;
}

TextArea {
    background: #000000;
    color: #00ff00;
}

TextArea:focus {
    border: heavy #ff6666;
}
"""


class ShellSenseiApp(App):
    """Main TUI application."""

    CSS = APP_CSS

    BINDINGS = [
        ("ctrl+l", "clear_log",   "Clear"),
        ("ctrl+h", "show_help",   "Help"),
        ("ctrl+p", "show_profile","Profile"),
    ]

    # ---------------------------------------------------------------------------
    # State
    # ---------------------------------------------------------------------------
    profile_md:   str  = ""
    profile_data: dict = {}
    history:      list = []       # running list of commands (session + shell history)
    last_error:   dict = {}       # {"cmd": ..., "error": ...} or empty
    suggestions:  list = []       # current next_steps list
    _pending_cmd: str  = ""       # command waiting for y/n confirmation
    _pending_alias: str = ""      # alias waiting for confirmation
    aliases:      dict = {}       # user-defined command aliases

    # ---------------------------------------------------------------------------
    # Layout
    # ---------------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("🔥 ShellSensei — System-Aware AI Terminal Assistant", id="title-bar")
        yield Static(id="sysbar")
        with Vertical(id="main-area"):
            yield RichLog(id="log", highlight=True, markup=True, wrap=True, max_lines=1000)
            yield Static(id="suggestions-bar")
            with Vertical(id="input-row"):
                yield SubmitTextArea(
                    id="user-input",
                )
        yield Footer()

    # ---------------------------------------------------------------------------
    # Startup
    # ---------------------------------------------------------------------------
    def on_mount(self) -> None:
        # 1. Ensure system profile exists
        if not PROFILE_MD.exists():
            self._log("🔍  First run detected — scanning your system…", "dim")
            profile = generate_profile()
            save_profile(profile)
            self._log("✅  System profile created and saved.", "green")

        self.profile_md   = load_profile_md()
        self.profile_data = load_profile_json()

        # 2. Load aliases
        self._load_aliases()

        # 3. Read shell history for context
        self.history = read_shell_history(30)

        # 4. Populate system info bar
        p = self.profile_data
        self.query_one("#sysbar", Static).update(
            f"🖥️  {p.get('distro','?')}  │  "
            f"📦 {p.get('package_manager','?')}  │  "
            f"🐚 {p.get('shell',{}).get('name','?')}  │  "
            f"🪟 {p.get('de_wm','?')}  │  "
            f"📁 {os.getcwd()}"
        )

        # 4. Welcome message with compact ASCII logo
        self._log("", "dim")
        self._log("[bold #ff4444]   ███████╗██╗  ██╗███████╗██╗     ██╗     ███████╗███████╗███╗   ██╗███████╗███████╗██╗[/]", "white")
        self._log("[bold #ff5555]   ██╔════╝██║  ██║██╔════╝██║     ██║     ██╔════╝██╔════╝████╗  ██║██╔════╝██╔════╝██║[/]", "white")
        self._log("[bold #ff6666]   ███████╗███████║█████╗  ██║     ██║     ███████╗█████╗  ██╔██╗ ██║███████╗█████╗  ██║[/]", "white")
        self._log("[bold #ff8888]   ╚════██║██╔══██║██╔══╝  ██║     ██║     ╚════██║██╔══╝  ██║╚██╗██║╚════██║██╔══╝  ██║[/]", "white")
        self._log("[bold #ffaaaa]   ███████║██║  ██║███████╗███████╗███████╗███████║███████╗██║ ╚████║███████║███████╗██║[/]", "white")
        self._log("[bold #ffcccc]   ╚══════╝╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝╚══════╝╚══════╝╚═╝  ╚═══╝╚══════╝╚══════╝╚═╝[/]", "white")
        self._log("", "dim")
        self._log("[bold #ff6666]" + "━" * 60 + "[/]", "white")
        self._log("", "dim")
        self._log(
            f"[#58a6ff]•[/] System detected: [bold]{p.get('distro','Linux')}[/bold] with [bold]{p.get('package_manager','unknown')}[/bold]",
            "white",
        )
        self._log(
            f"[#58a6ff]•[/] Every command suggestion is [bold #7ee787]tailored to your setup[/]",
            "white",
        )
        self._log("", "dim")
        self._log("[bold #ffa07a]Quick Start:[/]", "white")
        self._log("  [#7ee787]→[/] Type questions in plain English: [dim]\"install docker\"[/]", "white")
        self._log("  [#7ee787]→[/] Press [bold cyan]Enter[/] to submit (Ctrl+J for new line)", "white")
        self._log("  [#7ee787]→[/] Type [bold cyan]help[/] for all commands", "white")
        self._log("  [#7ee787]→[/] Type [bold cyan]profile[/] to see your full system scan", "white")
        self._log("", "dim")
        self._log("[bold #ff6666]" + "━" * 72 + "[/]", "white")
        self._separator()

        # 5. Auto-focus input field and force styling
        input_widget = self.query_one("#user-input", SubmitTextArea)
        input_widget.load_text("")
        input_widget.focus()
        # Force refresh to apply styles
        input_widget.refresh()

    # ---------------------------------------------------------------------------
    # Logging helpers
    # ---------------------------------------------------------------------------
    def _log(self, msg: str, style: str = "white") -> None:
        log_widget = self.query_one("#log", RichLog)
        log_widget.write(
            Text.from_markup(f"[{style}]{msg}[/]")
        )
        # Auto-scroll to bottom to show latest content
        log_widget.scroll_end(animate=False)

    def _separator(self) -> None:
        self.query_one("#log", RichLog).write(
            Text("─" * 60, style="dim")
        )

    # ---------------------------------------------------------------------------
    # Suggestions display (inline)
    # ---------------------------------------------------------------------------
    def _show_suggestions(self, steps: list) -> None:
        """Show suggestions inline in the conversation."""
        self.suggestions = steps
        if not steps:
            return
        
        self._log("", "dim")
        self._log("💡 [bold #ffa07a]Suggested next steps:[/]", "white")
        for i, step in enumerate(steps[:3], 1):
            cmd = step.get("cmd", "")
            why = step.get("why", "")
            self._log(f"  [bold #7ee787][{i}][/] [cyan]{cmd}[/]", "white")
            self._log(f"      [dim]{why}[/]", "white")
        
        if len(steps) > 0:
            self._log("", "dim")
            self._log("[dim]Type 1, 2, or 3 to run a suggestion[/]", "white")

    # ---------------------------------------------------------------------------
    # Input handler — the main event loop
    # ---------------------------------------------------------------------------
    def on_submit_text_area_submitted(self, event: SubmitTextArea.Submitted) -> None:
        """Handle submission from custom TextArea."""
        raw = event.text.strip()
        if raw:
            self.call_later(self._handle_input, raw)
    
    async def _handle_input(self, raw: str) -> None:
        """Process user input."""

        if not raw:
            return

        # --- Alias confirmation flow (y/n for pending alias) ---
        if (raw.lower() == "y" or raw.lower() == "yes") and self._pending_alias:
            expanded = self.aliases[self._pending_alias]
            self._separator()
            self._log(f"🔖  Alias expanded: /{self._pending_alias} → {expanded}", "#7ee787")
            self._pending_alias = ""
            raw = expanded
            # Continue processing the expanded command
        elif (raw.lower() == "n" or raw.lower() == "no") and self._pending_alias:
            self._log("❌ Alias cancelled", "yellow")
            self._pending_alias = ""
            return

        # --- Check for alias invocation (e.g., /update) ---
        if raw.startswith("/"):
            alias_name = raw[1:]
            if alias_name in self.aliases:
                # Show alias and ask for confirmation
                expanded = self.aliases[alias_name]
                self._separator()
                self._log(f"🔖  Alias: /{alias_name}", "#7ee787")
                self._log(f"   Will execute: {expanded}", "#c9d1d9")
                self._log("\n🔒 Confirm execution? (y/n)", "#ffa07a")
                self._pending_alias = alias_name
                return
            else:
                self._log(f"❌ Unknown alias: /{alias_name}", "red")
                self._log(f"💡 Available aliases: {', '.join('/' + k for k in self.aliases.keys()) or 'none'}", "dim")
                return

        # --- Special commands ---
        if raw.lower() in ("exit", "quit", "q"):
            self.exit()
            return

        if raw.lower() == "help":
            self._show_help()
            return

        if raw.lower() == "profile":
            self._show_profile()
            return

        if raw.lower() == "progress":
            self._show_progress()
            return

        # --- Confirmation flow (y/n for pending command) ---
        if (raw.lower() == "y" or raw.lower() == "yes") and self._pending_cmd:
            cmd = self._pending_cmd
            self._pending_cmd = ""
            self._reset_placeholder()
            self._separator()
            await self._run_command(cmd)
            return

        if (raw.lower() == "n" or raw.lower() == "no") and self._pending_cmd:
            self._pending_cmd = ""
            self._reset_placeholder()
            self._separator()
            self._log("❌ Command cancelled.", "#f85149")
            return

        # --- Pick a suggestion by number ---
        if raw in ("1", "2", "3") and self.suggestions:
            idx = int(raw) - 1
            if idx < len(self.suggestions):
                picked = self.suggestions[idx].get("cmd", "")
                if picked:
                    self._separator()
                    self._log(f"💬  You picked suggestion [{raw}]: {picked}", "#58a6ff")
                    await self._run_command(picked)
                    return

        # --- Raw command execution: "run <cmd>" ---
        if raw.lower().startswith("run "):
            cmd = raw[4:].strip()
            if cmd:
                self._separator()
                self._log(f"💬  Running raw command: {cmd}", "#58a6ff")
                await self._run_command(cmd)
                return

        # --- Normal AI query ---
        self._separator()
        self._log(f"💬  You: {raw}", "#58a6ff")
        self._log("🤖  Thinking…", "dim")

        context = self._build_context()

        # Call Gemini async - TUI stays responsive
        try:
            response = await get_ai_response_async(raw, self.profile_md, context)
        except Exception as e:
            self._log(f"❌ Error: {str(e)}", "red")
            return

        # If no command came back, just show the explanation
        if not response.get("command"):
            self._log(response.get("explanation", "Hmm, I couldn't understand that. Try rephrasing."), "dim")
            self._show_suggestions(response.get("next_steps", []))
            return

        # --- Display the AI response ---
        self._log("", "dim")
        self._log(f"📋  Command:  {response['command']}", "green bold")
        self._log(f"📝  {response['explanation']}", "#e3b341")

        if response.get("warning"):
            self._log(f"⚠️   {response['warning']}", "#f85149")

        # Show suggestions
        self._show_suggestions(response.get("next_steps", []))

        # Check if command is interactive
        from executor import is_interactive_command
        if is_interactive_command(response['command']):
            self._log("", "dim")
            self._log("💡  This is an [bold yellow]interactive program[/] that needs a real terminal.", "#e3b341")
            self._log("   Open a new terminal and run it there, or type [bold cyan]'run <command>'[/] to try anyway.", "dim")
            return

        # --- Ask for permission before running ANY command ---
        self._log("", "dim")
        self._log("[bold #ffa07a]Run this command?[/] Type [bold green]y[/] (yes) or [bold red]n[/] (no)", "white")

        # Check if this looks like an explanation request (command without args that needs stdin)
        cmd = response["command"].strip()
        stdin_cmds = ["cat", "grep", "sed", "awk", "sort", "uniq", "wc"]
        if cmd in stdin_cmds:
            self._log("", "dim")
            self._log("💡 This command needs a file or input. Check the suggestions above!", "#58a6ff")
            self._log("   Type '1' to run the first suggestion, or ask me to run a specific example.", "dim")
            return

        # --- Safety check (still block dangerous commands) ---
        safety, warning = check_safety(response["command"])

        if safety == "dangerous":
            self._log("", "dim")
            self._log("⛔  BLOCKED  —  This command is too dangerous to run.", "red bold")
            return

        # --- Always require confirmation (no auto-execution) ---
        self._pending_cmd = response["command"]
        # TextArea doesn't have placeholder, so we'll show instruction in log

    # ---------------------------------------------------------------------------
    # Command execution
    # ---------------------------------------------------------------------------
    async def _run_command(self, cmd: str) -> None:
        """Execute a command, show output, handle errors, track learning."""
        self._log(f"\n▶  Running:  {cmd}", "dim")

        result = execute(cmd)
        self.history.append(cmd)

        # Track in learning system
        _, new_achievements = track_command(cmd)

        # --- Success ---
        if result["success"]:
            output = result["output"].strip()
            self._log(f"✅  Done  ({result['duration_ms']} ms)", "green bold")

            if output:
                # Show up to 25 lines of output
                for line in output.split("\n")[:25]:
                    self._log(f"   {line}", "#8b949e")
                total_lines = len(output.split("\n"))
                if total_lines > 25:
                    self._log(f"   … ({total_lines - 25} more lines)", "dim")

            self.last_error = {}

        # --- Failure ---
        else:
            error_text = result["error"].strip() or "Unknown error"
            self._log(f"❌  Error  (exit code {result['exit_code']})", "red bold")
            for line in error_text.split("\n")[:10]:
                self._log(f"   {line}", "#f85149")

            self.last_error = {"cmd": cmd, "error": error_text}

            # --- Auto error fix ---
            self._log("", "dim")
            self._log("🔄  Analyzing error…", "dim")

            fix = get_error_fix(error_text, cmd, self.profile_md)

            self._log(f"🔍  Diagnosis:  {fix.get('diagnosis','')}", "#e3b341")

            if fix.get("fix_command"):
                self._log(f"🔧  Fix:  {fix['fix_command']}", "yellow bold")
                self._log(f"📝  {fix.get('explanation','')}", "dim")
                self._pending_cmd = fix["fix_command"]
                self.query_one("#user-input", Input).placeholder = "🔧  Type 'y' to apply the fix or 'n' to skip"
            else:
                self._log(fix.get("explanation", "No automatic fix available."), "dim")

        # --- Show new achievements ---
        for ach in new_achievements:
            self._log("", "dim")
            self._log(f"🏆  Achievement Unlocked:  {ach['icon']}  {ach['name']}  —  {ach['desc']}", "yellow bold")

        self._log("", "dim")

    # ---------------------------------------------------------------------------
    # Context builder
    # ---------------------------------------------------------------------------
    def _build_context(self) -> dict:
        cwd = os.getcwd()
        try:
            files = os.listdir(cwd)
        except PermissionError:
            files = ["(permission denied)"]

        return {
            "cwd":        cwd,
            "files":      files[:40],
            "history":    self.history[-5:],
            "last_error": (
                f"{self.last_error['cmd']} → {self.last_error['error']}"
                if self.last_error else "None"
            ),
        }

    # ---------------------------------------------------------------------------
    # Special command handlers
    # ---------------------------------------------------------------------------
    def _show_help(self) -> None:
        self._separator()
        self._log("📖  ShellSensei — How to use", "cyan bold")
        self._log("", "dim")
        self._log("  Ask anything in plain English:", "#8b949e")
        self._log("      \"list files\"", "#7ee787")
        self._log("      \"install docker\"", "#7ee787")
        self._log("      \"how do I check my disk space\"", "#7ee787")
        self._log("", "dim")
        self._log("  Special commands:", "#8b949e")
        self._log("      run <cmd>     →  Run any shell command directly", "#8b949e")
        self._log("      1 / 2 / 3     →  Pick a suggestion from the list", "#8b949e")
        self._log("      /<alias>      →  Use saved alias (e.g., /update, /ports)", "#8b949e")
        self._log("      profile       →  Show your system profile", "#8b949e")
        self._log("      progress      →  Show learning progress & achievements", "#8b949e")
        self._log("      help          →  Show this help", "#8b949e")
        self._log("      exit          →  Quit", "#8b949e")
        self._log("", "dim")
        self._log("  Keyboard shortcuts:", "#8b949e")
        self._log("      Ctrl+L        →  Clear the screen", "#8b949e")
        self._log("      Ctrl+H        →  Show help", "#8b949e")
        self._log("      Ctrl+P        →  Show profile", "#8b949e")
        self._separator()

    def _show_profile(self) -> None:
        self._separator()
        self._log("🖥️   System Profile", "cyan bold")
        self._log("", "dim")
        p = self.profile_data
        hw = p.get("hardware", {})
        shell = p.get("shell", {})

        self._log(f"  Distro          {p.get('distro','?')}", "#8b949e")
        self._log(f"  Kernel          {p.get('kernel','?')}", "#8b949e")
        self._log(f"  Package Manager {p.get('package_manager','?')}", "#8b949e")
        self._log(f"  Shell           {shell.get('name','?')}  ({shell.get('version','')})", "#8b949e")
        self._log(f"  DE / WM         {p.get('de_wm','?')}", "#8b949e")
        self._log(f"  User            {p.get('user','?')}", "#8b949e")
        self._log(f"  Groups          {', '.join(p.get('groups',[]))}", "#8b949e")
        self._log(f"  CPU             {hw.get('cpu_cores','?')} cores / {hw.get('cpu_threads','?')} threads", "#8b949e")
        self._log(f"  RAM             {hw.get('ram_total_gb','?')} GB total", "#8b949e")
        self._log(f"  Disk Free       {hw.get('disk_free_gb','?')} GB", "#8b949e")
        self._log(f"  Packages        {len(p.get('packages',[]))} installed", "#8b949e")

        tools = p.get("tool_versions", {})
        if tools:
            self._log("", "dim")
            self._log("  Developer Tools:", "#58a6ff")
            for t, v in tools.items():
                self._log(f"    {t:<12} {v}", "#7ee787")

        self._separator()

    def _show_progress(self) -> None:
        self._separator()
        for line in get_progress_lines():
            self._log(line, "#8b949e")
        self._separator()

    # ---------------------------------------------------------------------------
    # Keyboard actions
    # ---------------------------------------------------------------------------
    def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()
        self._log("Screen cleared.", "dim")

    def action_show_help(self) -> None:
        self._show_help()

    def action_show_profile(self) -> None:
        self._show_profile()

    # ---------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------
    def _reset_placeholder(self) -> None:
        # TextArea doesn't use placeholders - info shown in footer
        pass
    
    def _load_aliases(self) -> None:
        """Load user-defined command aliases from JSON file with security validation."""
        from system_profiler import PROFILE_DIR
        import re
        aliases_file = PROFILE_DIR / "aliases.json"
        
        # Dangerous patterns to block
        dangerous_patterns = [
            r'curl\s+http',  # remote code execution
            r'wget\s+http',  # remote code execution
            r'\$\(',         # command substitution
            r'`',            # backtick substitution
            r';\s*rm\s+-rf', # destructive commands
            r'\|\s*sh',      # piped shell execution
            r'\|\s*bash',    # piped bash execution
        ]
        
        def is_safe_alias(command: str) -> bool:
            """Check if alias command contains dangerous patterns."""
            for pattern in dangerous_patterns:
                if re.search(pattern, command, re.IGNORECASE):
                    return False
            return True
        
        # Create default aliases if file doesn't exist
        if not aliases_file.exists():
            default_aliases = {
                "update": "sudo apt update && sudo apt upgrade -y",
                "ports": "sudo netstat -tulpn",
                "myip": "curl -s ifconfig.me",
                "clean": "sudo apt autoremove -y && sudo apt clean",
            }
            try:
                with open(aliases_file, 'w') as f:
                    json.dump(default_aliases, f, indent=2)
                self.aliases = default_aliases
            except Exception:
                self.aliases = {}
        else:
            # Load existing aliases and validate them
            try:
                with open(aliases_file, 'r') as f:
                    loaded_aliases = json.load(f)
                # Filter out dangerous aliases
                self.aliases = {
                    name: cmd for name, cmd in loaded_aliases.items()
                    if is_safe_alias(cmd)
                }
                # Warn if any were filtered
                if len(self.aliases) < len(loaded_aliases):
                    filtered = len(loaded_aliases) - len(self.aliases)
                    self.log.write(f"⚠️  Filtered {filtered} potentially dangerous alias(es)")
            except Exception:
                self.aliases = {}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    # Quick sanity check — API key must exist
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_api_key_here":
        print("❌  GEMINI_API_KEY is not set!")
        print()
        print("  1. Go to https://aistudio.google.com/apikey")
        print("  2. Create a free API key")
        print("  3. Create a .env file in this directory with:")
        print("       GEMINI_API_KEY=your_actual_key_here")
        print()
        sys.exit(1)

    app = ShellSenseiApp()
    app.run()


if __name__ == "__main__":
    main()
