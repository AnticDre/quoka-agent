"""Tool definitions for the coding agent.

Each tool has a schema (for Claude) and an execute function (for the host).
"""

import os
import subprocess
from pathlib import Path

# Safety: restrict file operations to the working directory
WORKDIR = os.getcwd()


def _safe_path(path: str) -> Path:
    """Resolve path and ensure it's within the working directory."""
    resolved = Path(path).resolve()
    workdir = Path(WORKDIR).resolve()
    if not str(resolved).startswith(str(workdir)):
        raise PermissionError(f"Access denied: {path} is outside working directory")
    return resolved


# --- Tool schemas (sent to Claude) ---

TOOL_SCHEMAS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file. Returns the full text content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative or absolute path to the file to read",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file. Creates the file if it doesn't exist, overwrites if it does. Creates parent directories as needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to write the file to",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace a specific string in a file with new content. The old_str must appear exactly once in the file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to edit",
                },
                "old_str": {
                    "type": "string",
                    "description": "The exact string to find and replace (must be unique in the file)",
                },
                "new_str": {
                    "type": "string",
                    "description": "The string to replace it with",
                },
            },
            "required": ["path", "old_str", "new_str"],
        },
    },
    {
        "name": "run_command",
        "description": "Execute a shell command and return stdout/stderr. Use for running tests, installing packages, git operations, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 30)",
                    "default": 30,
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "list_directory",
        "description": "List files and directories at the given path. Returns names with / suffix for directories.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to list (default: current directory)",
                    "default": ".",
                }
            },
            "required": [],
        },
    },
    {
        "name": "search_files",
        "description": "Search for a pattern in files using grep. Returns matching lines with file paths and line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The regex pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file to search in (default: current directory)",
                    "default": ".",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter files, e.g. '*.py' (optional)",
                },
            },
            "required": ["pattern"],
        },
    },
]


# --- Tool implementations ---


def execute_tool(name: str, input: dict) -> str:
    """Dispatch and execute a tool call. Returns the result as a string."""
    try:
        match name:
            case "read_file":
                return _read_file(input["path"])
            case "write_file":
                return _write_file(input["path"], input["content"])
            case "edit_file":
                return _edit_file(input["path"], input["old_str"], input["new_str"])
            case "run_command":
                return _run_command(input["command"], input.get("timeout", 30))
            case "list_directory":
                return _list_directory(input.get("path", "."))
            case "search_files":
                return _search_files(
                    input["pattern"],
                    input.get("path", "."),
                    input.get("file_pattern"),
                )
            case _:
                return f"Error: unknown tool '{name}'"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


def _read_file(path: str) -> str:
    p = _safe_path(path)
    if not p.exists():
        return f"Error: file not found: {path}"
    if not p.is_file():
        return f"Error: not a file: {path}"
    content = p.read_text(encoding="utf-8", errors="replace")
    lines = content.split("\n")
    if len(lines) > 500:
        return f"[File has {len(lines)} lines, showing first 500]\n" + "\n".join(lines[:500])
    return content


def _write_file(path: str, content: str) -> str:
    p = _safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {path}"


def _edit_file(path: str, old_str: str, new_str: str) -> str:
    p = _safe_path(path)
    if not p.exists():
        return f"Error: file not found: {path}"
    content = p.read_text(encoding="utf-8")
    count = content.count(old_str)
    if count == 0:
        return f"Error: old_str not found in {path}"
    if count > 1:
        return f"Error: old_str appears {count} times in {path} (must be unique)"
    new_content = content.replace(old_str, new_str, 1)
    p.write_text(new_content, encoding="utf-8")
    return f"Edited {path}: replaced 1 occurrence"


def _run_command(command: str, timeout: int = 30) -> str:
    # Basic safety check
    dangerous = ["rm -rf /", "mkfs", "dd if=", "> /dev/"]
    for d in dangerous:
        if d in command:
            return f"Error: blocked potentially dangerous command"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=WORKDIR,
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += ("\n" if output else "") + f"[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"


def _list_directory(path: str) -> str:
    p = _safe_path(path)
    if not p.exists():
        return f"Error: directory not found: {path}"
    if not p.is_dir():
        return f"Error: not a directory: {path}"

    entries = sorted(p.iterdir())
    lines = []
    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            lines.append(f"{entry.name}/")
        else:
            size = entry.stat().st_size
            lines.append(f"{entry.name} ({size} bytes)")
    return "\n".join(lines) or "(empty directory)"


def _search_files(pattern: str, path: str = ".", file_pattern: str = None) -> str:
    import platform

    if platform.system() == "Windows":
        # Use findstr on Windows
        cmd = ["findstr", "/S", "/N", "/R"]
        if file_pattern:
            cmd.extend(["/M", pattern, os.path.join(path, file_pattern)])
        else:
            cmd.extend([pattern, os.path.join(path, "*")])
    else:
        cmd = ["grep", "-rn", "--color=never"]
        if file_pattern:
            cmd.extend(["--include", file_pattern])
        cmd.extend([pattern, path])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            cwd=WORKDIR,
        )
        if result.stdout:
            lines = result.stdout.strip().split("\n")
            if len(lines) > 50:
                return "\n".join(lines[:50]) + f"\n... ({len(lines)} total matches)"
            return result.stdout.strip()
        return "No matches found"
    except subprocess.TimeoutExpired:
        return "Error: search timed out"
