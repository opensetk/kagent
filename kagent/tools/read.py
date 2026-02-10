"""Read tool - Read file contents."""

from typing import Optional
from kagent.core.tool import tool


@tool(
    param_descriptions={
        "filePath": "Absolute path to the file",
        "offset": "Line number to start reading from (0-based, optional)",
        "limit": "Maximum number of lines to read (optional)",
    }
)
async def read(
    filePath: str, offset: Optional[int] = None, limit: Optional[int] = None
) -> str:
    """Read the contents of a file."""
    try:
        with open(filePath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        start = offset if offset is not None else 0
        if start < 0:
            start = 0
        if start >= len(lines):
            return "(file is empty or offset beyond file length)"

        if limit is not None:
            end = start + limit
            lines = lines[start:end]
        else:
            lines = lines[start:]

        numbered_lines = []
        for i, line in enumerate(lines, start=start + 1):
            numbered_lines.append(f"{i:4d}| {line.rstrip()}")

        return "\n".join(numbered_lines)

    except FileNotFoundError:
        return f"Error: File not found: {filePath}"
    except IsADirectoryError:
        return f"Error: Path is a directory: {filePath}"
    except PermissionError:
        return f"Error: Permission denied: {filePath}"
    except Exception as e:
        return f"Error reading file: {str(e)}"
