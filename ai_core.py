"""
ai_core.py
All Gemini API interactions live here.
Every call includes the full system profile so responses are system-specific.
"""

import os
import re
import json
import warnings

# Suppress the deprecation warning for google.generativeai
warnings.filterwarnings('ignore', message='.*google.generativeai.*')

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# --- Setup ---
API_KEY = os.environ.get("GEMINI_API_KEY", "")
genai.configure(api_key=API_KEY)

MODEL_NAME = "gemini-2.5-flash"

SYSTEM_PROMPT = """You are ShellSensei — a system-aware AI terminal assistant for Linux beginners.

You have been given the user's FULL system profile below. You MUST use this context in every response.
Always use their specific package manager, distro commands, and installed tools.
Never hallucinate software that isn't installed. Never suggest generic commands that won't work on their system.

RULES:
1. Commands must work on THEIR exact system.
2. Explain everything in simple, beginner-friendly language.
3. NEVER auto-execute commands — always let the user confirm first.
4. Always warn about anything involving sudo or destructive operations.
5. Suggest logical next steps based on what they just asked.
6. Be concise. Don't over-explain.

RESPONSE FORMAT — return ONLY valid JSON, nothing else, no markdown, no code blocks:
{
  "command": "the exact bash command to run (empty string if not applicable)",
  "explanation": "clear beginner-friendly explanation of what this command does and why",
  "safety": "safe | caution | dangerous",
  "warning": "warning message if safety is caution or dangerous, empty string otherwise",
  "next_steps": [
    {"cmd": "suggested next command", "why": "short reason why they might want this"},
    {"cmd": "another suggestion", "why": "reason"}
  ]
}
"""

ERROR_FIX_PROMPT = """You are ShellSensei. The user ran a command and got an error.
Diagnose and fix it based on their SPECIFIC system.

RESPONSE FORMAT — return ONLY valid JSON, nothing else:
{
  "diagnosis": "what went wrong and why it happened on this specific system",
  "fix_command": "the exact command to fix it (empty string if no fix possible)",
  "explanation": "beginner-friendly explanation of the error and the fix"
}
"""


def _parse_json(text: str) -> dict:
    """Safely parse JSON from Gemini response, stripping markdown if present."""
    text = text.strip()
    # Strip ```json ... ``` wrapper if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    return json.loads(text)


def get_ai_response(user_query: str, system_profile_md: str, context: dict) -> dict:
    """
    Main query handler. Sends user question + full system context to Gemini.

    Args:
        user_query: What the user typed in plain English
        system_profile_md: Full markdown system profile
        context: Current state (cwd, files, history, last_error)

    Returns:
        Parsed dict with command, explanation, safety, next_steps
    """
    prompt = f"""=== USER'S SYSTEM PROFILE ===
{system_profile_md}

=== CURRENT CONTEXT ===
Working Directory: {context.get('cwd', '/')}
Files in Current Directory: {context.get('files', [])}
Last 5 Commands Run: {context.get('history', [])}
Last Error (if any): {context.get('last_error', 'None')}

=== USER'S QUESTION ===
{user_query}
"""

    try:
        model = genai.GenerativeModel(
            MODEL_NAME,
            system_instruction=SYSTEM_PROMPT,
            generation_config={
                "temperature": 0.3,
                "max_output_tokens": 1024,
                "response_mime_type": "application/json",
            },
        )
        response = model.generate_content(prompt)
        return _parse_json(response.text)

    except json.JSONDecodeError:
        # If JSON parsing fails, return the raw text as explanation
        return {
            "command": "",
            "explanation": response.text if 'response' in dir() else "Something went wrong parsing the response.",
            "safety": "safe",
            "warning": "",
            "next_steps": [],
        }
    except Exception as e:
        return {
            "command": "",
            "explanation": f"API error: {str(e)}. Check your GEMINI_API_KEY.",
            "safety": "safe",
            "warning": "",
            "next_steps": [],
        }


def get_error_fix(error_output: str, failed_command: str, system_profile_md: str) -> dict:
    """
    Auto error fixer. Called when a command fails.
    Analyzes the error in context of the user's system and suggests a fix.

    Args:
        error_output: The stderr / error message
        failed_command: The command that failed
        system_profile_md: Full system profile

    Returns:
        Parsed dict with diagnosis, fix_command, explanation
    """
    prompt = f"""=== USER'S SYSTEM PROFILE ===
{system_profile_md}

=== FAILED COMMAND ===
{failed_command}

=== ERROR OUTPUT ===
{error_output}

Diagnose and fix this error for this specific system.
"""

    try:
        model = genai.GenerativeModel(
            MODEL_NAME,
            system_instruction=ERROR_FIX_PROMPT,
            generation_config={
                "temperature": 0.2,
                "max_output_tokens": 512,
                "response_mime_type": "application/json",
            },
        )
        response = model.generate_content(prompt)
        return _parse_json(response.text)

    except json.JSONDecodeError:
        return {
            "diagnosis": "Could not parse the error automatically.",
            "fix_command": "",
            "explanation": response.text if 'response' in dir() else "Failed to analyze error.",
        }
    except Exception as e:
        return {
            "diagnosis": f"API error: {str(e)}",
            "fix_command": "",
            "explanation": "Could not reach the AI. Check your API key and connection.",
        }
