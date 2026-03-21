"""Shared tool definitions and execution for all providers.

Each provider has its own format for declaring tools, but the underlying
execution is identical: run a shell command, return the output.

When sandbox mode is enabled, commands run inside a disposable Docker
container instead of on the host.
"""

from __future__ import annotations

import logging
import os
import subprocess
import uuid

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sandbox container lifecycle
# ---------------------------------------------------------------------------

_active_containers: dict[str, str] = {}  # name -> container id
_current_sandbox: str | None = None  # set by orchestrator for current competition


def create_sandbox(
    image: str = "python:3.12-slim",
    memory_limit: str = "512m",
    network: bool = False,
    working_dir: str | None = None,
) -> str:
    """Create and start a warm sandbox container. Returns container name."""
    name = f"mobius-sandbox-{uuid.uuid4().hex[:8]}"
    cmd = [
        "docker", "create",
        "--name", name,
        "--memory", memory_limit,
        "--cpus", "1",
        "--workdir", "/workspace",
    ]
    if working_dir:
        cmd += ["-v", f"{working_dir}:/workspace"]
    if not network:
        cmd += ["--network", "none"]
    cmd += [image, "sleep", "infinity"]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create sandbox: {result.stderr.strip()}")

    start_result = subprocess.run(
        ["docker", "start", name],
        capture_output=True, text=True, timeout=10,
    )
    if start_result.returncode != 0:
        # Cleanup the created-but-not-started container
        subprocess.run(
            ["docker", "rm", "-f", name],
            capture_output=True, text=True, timeout=10,
        )
        raise RuntimeError(f"Failed to start sandbox: {start_result.stderr.strip()}")

    _active_containers[name] = result.stdout.strip()
    logger.info("Sandbox created: %s (image=%s, network=%s)", name, image, network)
    return name


def destroy_sandbox(name: str) -> None:
    """Stop and remove a sandbox container."""
    try:
        subprocess.run(
            ["docker", "rm", "-f", name],
            capture_output=True, text=True, timeout=15,
        )
        _active_containers.pop(name, None)
        logger.info("Sandbox destroyed: %s", name)
    except Exception as e:
        logger.warning("Failed to destroy sandbox %s: %s", name, e)


def destroy_all_sandboxes() -> None:
    """Clean up all active sandbox containers."""
    for name in list(_active_containers):
        destroy_sandbox(name)


def set_sandbox(name: str | None) -> None:
    """Set the active sandbox for all subsequent run_command calls."""
    global _current_sandbox
    _current_sandbox = name


def get_current_sandbox() -> str | None:
    """Return the name of the currently active sandbox, or None."""
    return _current_sandbox


# ---------------------------------------------------------------------------
# Command execution
# ---------------------------------------------------------------------------

def run_command(
    command: str,
    timeout: int = 30,
    working_dir: str | None = None,
    sandbox: str | None = None,
) -> str:
    """Execute a shell command and return output.

    Args:
        command: The shell command to run.
        timeout: Max seconds before killing the command.
        working_dir: Working directory (host mode only).
        sandbox: Container name to exec into. If None, uses current sandbox.
    """
    sandbox = sandbox or _current_sandbox
    try:
        if sandbox:
            if sandbox not in _active_containers:
                raise RuntimeError(
                    f"Sandbox '{sandbox}' is not in active containers. "
                    "Refusing to fall back to host execution."
                )
            result = subprocess.run(
                ["docker", "exec", sandbox, "sh", "-lc", command],
                capture_output=True, text=True, timeout=timeout,
                encoding="utf-8", errors="replace",
            )
        else:
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
