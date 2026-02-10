"""Bash tool - Execute shell commands."""

import asyncio
import os
from typing import Optional
from kagent.core.tool import tool


@tool(
    param_descriptions={
        "command": "The command to execute",
        "workdir": "Working directory to run command in (optional)",
        "timeout": "Timeout in milliseconds (optional, default 120000)",
    }
)
async def bash(
    command: str, workdir: Optional[str] = None, timeout: Optional[int] = 120000
) -> str:
    """Execute a shell command in a persistent shell session."""
    cwd = workdir if workdir else os.getcwd()
    timeout_sec = timeout / 1000 if timeout else 120

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout_sec
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return f"Error: Command timed out after {timeout_sec} seconds"

        stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

        result_parts = []
        if stdout_str:
            result_parts.append(stdout_str)
        if stderr_str:
            result_parts.append(f"[stderr]\n{stderr_str}")

        if process.returncode != 0:
            result_parts.append(f"[exit code: {process.returncode}]")

        return "\n".join(result_parts) if result_parts else "(no output)"

    except Exception as e:
        return f"Error executing command: {str(e)}"
