"""Grep tool - Search file contents using regex."""

import os
import re
from typing import Optional
from kagent.core.tool import tool


@tool(
    param_descriptions={
        "pattern": "Regex pattern to search for",
        "path": "Directory to search in (optional)",
        "include": "File pattern filter (e.g., '*.py', '*.{ts,tsx}')",
    }
)
async def grep(
    pattern: str, path: Optional[str] = None, include: Optional[str] = None
) -> str:
    """Search file contents using regex."""
    try:
        search_path = path if path else os.getcwd()
        search_path = os.path.abspath(search_path)

        if not os.path.exists(search_path):
            return f"Error: Directory not found: {search_path}"

        if not os.path.isdir(search_path):
            return f"Error: Path is not a directory: {search_path}"

        try:
            regex = re.compile(pattern, re.MULTILINE)
        except re.error as e:
            return f"Error: Invalid regex pattern: {e}"

        include_pattern = None
        if include:
            include_regex = (
                include.replace(".", r"\.").replace("*", ".*").replace("?", ".")
            )
            include_pattern = re.compile(include_regex)

        matches = []

        for root, dirs, files in os.walk(search_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]

            for filename in files:
                if include_pattern and not include_pattern.match(filename):
                    continue

                filepath = os.path.join(root, filename)

                try:
                    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()

                    for match in regex.finditer(content):
                        line_start = content.rfind("\n", 0, match.start()) + 1
                        line_num = content[:line_start].count("\n") + 1

                        line_end = content.find("\n", match.start())
                        if line_end == -1:
                            line_end = len(content)
                        line_content = content[line_start:line_end].strip()

                        matches.append((filepath, line_num, line_content))

                except (PermissionError, IsADirectoryError):
                    continue
                except Exception:
                    continue

        if not matches:
            return f"No matches found for pattern '{pattern}'"

        matches.sort(key=lambda x: (x[0], x[1]))

        lines = [f"Found {len(matches)} match(es) for '{pattern}':"]
        current_file = None

        for filepath, line_num, line_content in matches:
            if filepath != current_file:
                lines.append(f"\n{filepath}")
                current_file = filepath
            display = (
                line_content[:100] + "..." if len(line_content) > 100 else line_content
            )
            lines.append(f"  {line_num}: {display}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error searching content: {str(e)}"
