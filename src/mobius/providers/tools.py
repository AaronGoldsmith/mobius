"""Shared tool definitions and execution for all providers.

Each provider has its own format for declaring tools, but the underlying
execution is identical: run a shell command, return the output.
"""

from __future__ import annotations

import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def run_command(command: str, timeout: int = 30, working_dir: str | None = None) -> str:
    """Execute a shell command and return output."""
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=working_dir or os.getcwd(),
            encoding="utf-8", errors="replace",
        )
        output = result.stdout
        if result.returncode != 0 and result.stderr:
            output += f"\n[stderr]: {result.stderr}"
        return output[:10000]
    except subprocess.TimeoutExpired:
        return "[Command timed out]"
    except Exception as e:
        return f"[Error]: {e}"


# --- Anthropic format ---

ANTHROPIC_BASH_TOOL = {
    "name": "bash",
    "description": "Run a shell command and return its output.",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The bash command to execute"}
        },
        "required": ["command"],
    },
}

# --- OpenAI format (function calling) ---

OPENAI_BASH_TOOL = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Run a shell command and return its output.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The bash command to execute"}
            },
            "required": ["command"],
        },
    },
}

# --- Google format (function declarations) ---

GOOGLE_BASH_DECLARATION = {
    "name": "bash",
    "description": "Run a shell command and return its output.",
    "parameters": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The bash command to execute"}
        },
        "required": ["command"],
    },
}
