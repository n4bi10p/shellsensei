"""
ai_core.py
All Gemini API interactions live here.
Every call includes the full system profile so responses are system-specific.
"""

import os
import re
import json
import warnings
import hashlib
import pickle
import time
import asyncio
import hmac
from pathlib import Path

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# --- Setup ---
API_KEY = os.environ.get("GEMINI_API_KEY", "")
client = genai.Client(api_key=API_KEY)

MODEL_NAME = "gemini-2.5-flash"

# --- Cache Setup ---
CACHE_DIR = Path.home() / ".shellsensei" / "cache"
CACHE_DIR.mkdir(exist_ok=True, parents=True)
CACHE_TTL = 86400  # 24 hours

# Security: Per-session HMAC secret for cache integrity
CACHE_SECRET = os.urandom(32)

SYSTEM_PROMPT = """You are ShellSensei — a system-aware AI terminal assistant for Linux beginners.

You have been given the user's FULL system profile below. You MUST use this context in every response.
Always use their specific package manager, distro commands, and installed tools.
Never hallucinate software that isn't installed. Never suggest generic commands that won't work on their system.

RULES:
1. Commands must work on THEIR exact system.
2. ALWAYS check the "Installed Packages" section before suggesting commands. If a package is NOT installed, suggest installation first.
3. For interactive programs (htop, vim, nano, top, etc), explain they need a real terminal and can't run in this TUI.
4. Explain everything in simple, beginner-friendly language.
5. NEVER auto-execute commands — always let the user confirm first.
6. Always warn about anything involving sudo or destructive operations.
7. Suggest logical next steps based on what they just asked.
8. Be concise. Don't over-explain.

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


def _get_cache_key(query: str, profile: str) -> str:
    """Generate cache key from query + profile hash."""
    content = f"{query}|{profile}"
    return hashlib.md5(content.encode()).hexdigest()


def _sign_cache(data: bytes) -> bytes:
    """Sign cache data with HMAC for integrity verification."""
    signature = hmac.new(CACHE_SECRET, data, hashlib.sha256).digest()
    return signature + data


def _verify_cache(signed_data: bytes) -> bytes | None:
    """Verify HMAC signature and return original data if valid."""
    if len(signed_data) < 32:
        return None
    signature = signed_data[:32]
    data = signed_data[32:]
    expected_signature = hmac.new(CACHE_SECRET, data, hashlib.sha256).digest()
    if hmac.compare_digest(signature, expected_signature):
        return data
    return None


def _get_cached_response(query: str, profile: str) -> dict | None:
    """Check if response is cached (24h TTL) and verify integrity."""
    cache_file = CACHE_DIR / f"{_get_cache_key(query, profile)}.pkl"
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < CACHE_TTL:
            try:
                with open(cache_file, 'rb') as f:
                    signed_data = f.read()
                # Verify HMAC signature
                data = _verify_cache(signed_data)
                if data is None:
                    # Corrupted or tampered cache - delete it
                    cache_file.unlink()
                    return None
                return pickle.loads(data)
            except Exception:
                # Corrupted cache, delete it
                cache_file.unlink()
    return None


def _cache_response(query: str, profile: str, response: dict) -> None:
    """Save response to cache with HMAC signature and secure permissions."""
    try:
        cache_file = CACHE_DIR / f"{_get_cache_key(query, profile)}.pkl"
        # Pickle the data
        data = pickle.dumps(response)
        # Sign it with HMAC
        signed_data = _sign_cache(data)
        # Write to file
        with open(cache_file, 'wb') as f:
            f.write(signed_data)
        # Set restrictive permissions (0600)
        cache_file.chmod(0o600)
    except Exception:
        # Silently fail if caching doesn't work
        pass


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
    # Check cache first
    cached = _get_cached_response(user_query, system_profile_md)
    if cached:
        return cached
    
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
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.3,
                max_output_tokens=1024,
                response_mime_type="application/json",
            ),
        )
        parsed = _parse_json(response.text)
        
        # Cache the response
        _cache_response(user_query, system_profile_md, parsed)
        
        return parsed

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


async def get_ai_response_async(user_query: str, system_profile_md: str, context: dict) -> dict:
    """Async wrapper for AI response - doesn't block TUI."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        get_ai_response,
        user_query,
        system_profile_md,
        context
    )


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
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=ERROR_FIX_PROMPT,
                temperature=0.2,
                max_output_tokens=512,
                response_mime_type="application/json",
            ),
        )
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
