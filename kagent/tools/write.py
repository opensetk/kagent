"""Write tool - Write file content."""

import os
from kagent.core.tool import tool


@tool(
    param_descriptions={
        "filePath": "Absolute path to the file",
        "content": "Content to write",
    }
)
async def write(filePath: str, content: str) -> str:
    """Write content to a file (creates or overwrites)."""
    try:
        parent_dir = os.path.dirname(filePath)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        with open(filePath, "w", encoding="utf-8") as f:
            f.write(content)

        return f"Successfully wrote {len(content)} characters to {filePath}"

    except PermissionError:
        return f"Error: Permission denied: {filePath}"
    except IsADirectoryError:
        return f"Error: Path is a directory: {filePath}"
    except Exception as e:
        return f"Error writing file: {str(e)}"
