"""Glob tool - Find files by pattern matching."""

import os
import fnmatch
from pathlib import Path
from typing import Optional
from kagent.core.tool import tool


@tool(
    param_descriptions={
        "pattern": "Glob pattern (e.g., '**/*.py', 'src/**/*.ts')",
        "path": "Directory to search in (optional, defaults to current directory)",
    }
)
async def glob(pattern: str, path: Optional[str] = None) -> str:
    """Find files matching a glob pattern."""
    try:
        search_path = path if path else os.getcwd()
        search_path = os.path.abspath(search_path)

        if not os.path.exists(search_path):
            return f"Error: Directory not found: {search_path}"

        if not os.path.isdir(search_path):
            return f"Error: Path is not a directory: {search_path}"

        base_path = Path(search_path)
        results = []

        if pattern.startswith("**/") or pattern == "**":
            remainder = pattern[3:] if pattern.startswith("**/") else ""

            for root, dirs, files in os.walk(search_path):
                if remainder:
                    for file in files:
                        if fnmatch.fnmatch(file, remainder):
                            full_path = os.path.join(root, file)
                            results.append(full_path)
                        elif fnmatch.fnmatch(file, pattern):
                            full_path = os.path.join(root, file)
                            results.append(full_path)
                else:
                    for file in files:
                        full_path = os.path.join(root, file)
                        results.append(full_path)

            results.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        else:
            matches = list(base_path.glob(pattern))
            file_matches = [str(m) for m in matches if m.is_file()]
            file_matches.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            results = file_matches

        if not results:
            return f"No files found matching '{pattern}' in {search_path}"

        lines = [f"Found {len(results)} file(s) matching '{pattern}':"]
        for filepath in results:
            lines.append(f"  {filepath}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error searching files: {str(e)}"
