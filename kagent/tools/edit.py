"""Edit tool - Edit files with specific replacements."""

from typing import Optional
from kagent.core.tool import tool


@tool(
    param_descriptions={
        "filePath": "Absolute path to the file",
        "oldString": "Text to replace",
        "newString": "Text to replace with",
        "replaceAll": "Replace all occurrences (default: false)",
    }
)
async def edit(
    filePath: str, oldString: str, newString: str, replaceAll: Optional[bool] = False
) -> str:
    """Edit a file by replacing specific text."""
    try:
        with open(filePath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        if replaceAll:
            count = content.count(oldString)
            if count == 0:
                return "Error: oldString not found in file"
            new_content = content.replace(oldString, newString)
            message = f"Successfully replaced {count} occurrence(s)"
        else:
            if oldString not in content:
                return "Error: oldString not found in file"
            if content.count(oldString) > 1:
                return "Error: oldString found multiple times. Use replaceAll=true or provide more context"
            new_content = content.replace(oldString, newString, 1)
            message = "Successfully replaced 1 occurrence"

        with open(filePath, "w", encoding="utf-8") as f:
            f.write(new_content)

        return f"{message} in {filePath}"

    except FileNotFoundError:
        return f"Error: File not found: {filePath}"
    except PermissionError:
        return f"Error: Permission denied: {filePath}"
    except IsADirectoryError:
        return f"Error: Path is a directory: {filePath}"
    except Exception as e:
        return f"Error editing file: {str(e)}"
