# quoka-agent: Build Plan

A minimal CLI coding agent powered by Claude. This document contains everything needed to build and run the agent from scratch on a clean machine. Follow the steps in order. Copy each code block into the specified file.

## Prerequisites

- Python 3.10 or higher
- An Anthropic API key
- pip

## Step 1: Create the project directory structure

```bash
mkdir -p quoka-agent/src
mkdir -p quoka-agent/tests
cd quoka-agent
```

## Step 2: Create `pyproject.toml`

This is the project configuration file. It defines dependencies and the CLI entry point.

Create file: `pyproject.toml`

```toml
[project]
name = "quoka-agent"
version = "0.1.0"
description = "A minimal CLI coding agent powered by Claude"
requires-python = ">=3.10"
dependencies = [
    "anthropic>=0.39.0",
    "rich>=13.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
]

[project.scripts]
quoka = "src.cli:main"
```

## Step 3: Create `src/__init__.py`

Create file: `src/__init__.py`

```python
"""quoka-agent: a minimal CLI coding agent powered by Claude."""
```

## Step 4: Create `src/tools.py`

This file defines the six tools the agent can use (read files, write files, edit files, run commands, list directories, search files) and their implementations. All file operations are sandboxed to the working directory.

Create file: `src/tools.py`

```python
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
```

## Step 5: Create `src/agent.py`

This is the core agentic loop. It sends messages to Claude with tool definitions, executes tool calls locally, feeds results back, and repeats until Claude stops calling tools.

Create file: `src/agent.py`

```python
"""Core agent loop: sends messages to Claude, handles tool calls, iterates."""

import anthropic
from .tools import TOOL_SCHEMAS, execute_tool

DEFAULT_MODEL = "claude-sonnet-4-20250514"
MAX_ITERATIONS = 25  # safety limit per user message


SYSTEM_PROMPT = """You are a coding agent running in a CLI environment. You help the user by reading, writing, and editing files, running commands, and solving programming tasks.

Your working directory is the user's current directory. You have access to these tools:
- read_file: read file contents
- write_file: create or overwrite files
- edit_file: find-and-replace within a file (old_str must be unique)
- run_command: execute shell commands (tests, git, installs, etc.)
- list_directory: list files in a directory
- search_files: grep for patterns across files

Guidelines:
- Read existing files before editing them
- Run tests after making changes when tests exist
- Keep explanations brief. Show your work through tool use, not narration
- If something fails, read the error, diagnose, and fix it
- Ask the user for clarification if the task is ambiguous
"""


class Agent:
    """The agentic loop: user message -> Claude -> tool calls -> repeat."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self.client = anthropic.Anthropic()
        self.model = model
        self.messages: list[dict] = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def send(self, user_message: str) -> list[dict]:
        """Send a user message and run the agentic loop until done.

        Returns a list of events for the UI to render:
        [
            {"type": "text", "content": "..."},
            {"type": "tool_use", "name": "...", "input": {...}},
            {"type": "tool_result", "name": "...", "output": "..."},
        ]
        """
        self.messages.append({"role": "user", "content": user_message})
        events = []

        for _ in range(MAX_ITERATIONS):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOL_SCHEMAS,
                messages=self.messages,
            )

            self.total_input_tokens += response.usage.input_tokens
            self.total_output_tokens += response.usage.output_tokens

            # Process response content blocks
            assistant_content = response.content
            self.messages.append({"role": "assistant", "content": assistant_content})

            # Collect text blocks and tool use blocks
            tool_uses = []
            for block in assistant_content:
                if block.type == "text" and block.text.strip():
                    events.append({"type": "text", "content": block.text})
                elif block.type == "tool_use":
                    events.append({
                        "type": "tool_use",
                        "name": block.name,
                        "input": block.input,
                    })
                    tool_uses.append(block)

            # If no tool calls, we're done
            if response.stop_reason == "end_turn" or not tool_uses:
                break

            # Execute tools and build tool results
            tool_results = []
            for tool_use in tool_uses:
                output = execute_tool(tool_use.name, tool_use.input)
                events.append({
                    "type": "tool_result",
                    "name": tool_use.name,
                    "output": output,
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": output,
                })

            # Add tool results as user message and continue loop
            self.messages.append({"role": "user", "content": tool_results})

        return events

    @property
    def token_usage(self) -> dict:
        return {
            "input": self.total_input_tokens,
            "output": self.total_output_tokens,
            "total": self.total_input_tokens + self.total_output_tokens,
        }

    def reset(self):
        """Clear conversation history."""
        self.messages = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0
```

## Step 6: Create `src/cli.py`

The terminal interface. Uses Rich for coloured output. Supports slash commands.

Create file: `src/cli.py`

```python
"""CLI interface for the coding agent."""

import sys
import os
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme

from .agent import Agent

custom_theme = Theme({
    "tool": "cyan",
    "tool_output": "dim",
    "error": "red bold",
    "info": "dim cyan",
    "prompt": "green bold",
})

console = Console(theme=custom_theme)

BANNER = """[dim cyan]┌──────────────────────────────────┐
│  quoka-agent v0.1.0              │
│  CLI coding agent powered by     │
│  Claude                          │
│                                  │
│  Commands:                       │
│    /quit     exit                 │
│    /reset    clear history        │
│    /tokens   show token usage     │
│    /model    show current model   │
│    /help     show this help       │
└──────────────────────────────────┘[/dim cyan]"""


def render_events(events: list[dict]):
    """Render agent events to the terminal."""
    for event in events:
        match event["type"]:
            case "text":
                console.print()
                console.print(Markdown(event["content"]))

            case "tool_use":
                name = event["name"]
                inp = event["input"]

                # Compact display for each tool
                match name:
                    case "read_file":
                        detail = inp.get("path", "")
                    case "write_file":
                        detail = inp.get("path", "")
                        size = len(inp.get("content", ""))
                        detail = f"{detail} ({size} bytes)"
                    case "edit_file":
                        detail = inp.get("path", "")
                    case "run_command":
                        detail = inp.get("command", "")
                    case "list_directory":
                        detail = inp.get("path", ".")
                    case "search_files":
                        detail = f"/{inp.get('pattern', '')}/ in {inp.get('path', '.')}"
                    case _:
                        detail = str(inp)

                console.print(f"  [tool]⚡ {name}[/tool] [dim]{detail}[/dim]")

            case "tool_result":
                output = event["output"]
                # Truncate long output for display
                lines = output.split("\n")
                if len(lines) > 20:
                    display = "\n".join(lines[:15]) + f"\n  ... ({len(lines)} lines total)"
                else:
                    display = output
                console.print(f"  [tool_output]{display}[/tool_output]")


def handle_command(cmd: str, agent: Agent) -> bool:
    """Handle slash commands. Returns True if the REPL should continue."""
    cmd = cmd.strip().lower()

    match cmd:
        case "/quit" | "/exit" | "/q":
            console.print("[info]Bye.[/info]")
            return False
        case "/reset":
            agent.reset()
            console.print("[info]Conversation reset.[/info]")
        case "/tokens":
            usage = agent.token_usage
            console.print(f"[info]Tokens: {usage['input']:,} in / {usage['output']:,} out / {usage['total']:,} total[/info]")
        case "/model":
            console.print(f"[info]Model: {agent.model}[/info]")
        case "/help":
            console.print(BANNER)
        case _:
            console.print(f"[error]Unknown command: {cmd}[/error]")

    return True


def main():
    """Entry point for the CLI agent."""
    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[error]ANTHROPIC_API_KEY not set. Export it and try again.[/error]")
        sys.exit(1)

    # Allow model override via env var
    model = os.environ.get("QUOKA_MODEL", "claude-sonnet-4-20250514")

    console.print(BANNER)
    console.print(f"[info]Working directory: {os.getcwd()}[/info]")
    console.print(f"[info]Model: {model}[/info]")
    console.print()

    agent = Agent(model=model)

    while True:
        try:
            user_input = console.input("[prompt]> [/prompt]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[info]Bye.[/info]")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            if not handle_command(user_input, agent):
                break
            continue

        try:
            events = agent.send(user_input)
            render_events(events)
            console.print()
        except Exception as e:
            console.print(f"[error]Error: {e}[/error]")
            console.print()


if __name__ == "__main__":
    main()
```

## Step 7: Create `tests/__init__.py`

Create file: `tests/__init__.py`

```python
```

(Empty file. Just needs to exist so pytest finds the test module.)

## Step 8: Create `tests/test_tools.py`

18 tests covering all tool implementations including edge cases.

Create file: `tests/test_tools.py`

```python
"""Tests for tool implementations."""

import os
import pytest
from pathlib import Path
from src.tools import execute_tool, _safe_path


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    """Set up a temporary working directory for tool tests."""
    import src.tools
    monkeypatch.setattr(src.tools, "WORKDIR", str(tmp_path))
    return tmp_path


class TestSafePath:
    def test_rejects_path_outside_workdir(self, tmp_workspace):
        with pytest.raises(PermissionError):
            _safe_path("/etc/passwd")

    def test_accepts_path_inside_workdir(self, tmp_workspace):
        result = _safe_path(str(tmp_workspace / "test.txt"))
        assert str(result).startswith(str(tmp_workspace))


class TestReadFile:
    def test_read_existing_file(self, tmp_workspace):
        f = tmp_workspace / "hello.txt"
        f.write_text("hello world")
        result = execute_tool("read_file", {"path": str(f)})
        assert result == "hello world"

    def test_read_missing_file(self, tmp_workspace):
        result = execute_tool("read_file", {"path": str(tmp_workspace / "nope.txt")})
        assert "not found" in result


class TestWriteFile:
    def test_write_new_file(self, tmp_workspace):
        path = str(tmp_workspace / "new.txt")
        result = execute_tool("write_file", {"path": path, "content": "test content"})
        assert "Wrote" in result
        assert Path(path).read_text() == "test content"

    def test_write_creates_directories(self, tmp_workspace):
        path = str(tmp_workspace / "sub" / "dir" / "file.txt")
        result = execute_tool("write_file", {"path": path, "content": "nested"})
        assert "Wrote" in result
        assert Path(path).read_text() == "nested"


class TestEditFile:
    def test_edit_unique_string(self, tmp_workspace):
        f = tmp_workspace / "edit.txt"
        f.write_text("hello world")
        result = execute_tool("edit_file", {
            "path": str(f),
            "old_str": "world",
            "new_str": "quoka",
        })
        assert "replaced 1" in result.lower()
        assert f.read_text() == "hello quoka"

    def test_edit_missing_string(self, tmp_workspace):
        f = tmp_workspace / "edit.txt"
        f.write_text("hello world")
        result = execute_tool("edit_file", {
            "path": str(f),
            "old_str": "missing",
            "new_str": "replacement",
        })
        assert "not found" in result.lower()

    def test_edit_duplicate_string(self, tmp_workspace):
        f = tmp_workspace / "edit.txt"
        f.write_text("aaa aaa")
        result = execute_tool("edit_file", {
            "path": str(f),
            "old_str": "aaa",
            "new_str": "bbb",
        })
        assert "2 times" in result


class TestRunCommand:
    def test_simple_command(self, tmp_workspace):
        result = execute_tool("run_command", {"command": "echo hello"})
        assert "hello" in result

    def test_command_failure(self, tmp_workspace):
        result = execute_tool("run_command", {"command": "false"})
        assert "exit code" in result

    def test_blocked_dangerous_command(self, tmp_workspace):
        result = execute_tool("run_command", {"command": "rm -rf /"})
        assert "blocked" in result.lower()

    def test_timeout(self, tmp_workspace):
        result = execute_tool("run_command", {"command": "sleep 10", "timeout": 1})
        assert "timed out" in result.lower()


class TestListDirectory:
    def test_list_files(self, tmp_workspace):
        (tmp_workspace / "a.txt").write_text("a")
        (tmp_workspace / "b.py").write_text("b")
        (tmp_workspace / "subdir").mkdir()
        result = execute_tool("list_directory", {"path": str(tmp_workspace)})
        assert "a.txt" in result
        assert "b.py" in result
        assert "subdir/" in result

    def test_empty_directory(self, tmp_workspace):
        empty = tmp_workspace / "empty"
        empty.mkdir()
        result = execute_tool("list_directory", {"path": str(empty)})
        assert "empty" in result.lower()


class TestSearchFiles:
    def test_search_finds_pattern(self, tmp_workspace):
        (tmp_workspace / "test.py").write_text("def hello():\n    pass\n")
        result = execute_tool("search_files", {
            "pattern": "def hello",
            "path": str(tmp_workspace),
        })
        assert "def hello" in result

    def test_search_no_matches(self, tmp_workspace):
        (tmp_workspace / "test.py").write_text("nothing here")
        result = execute_tool("search_files", {
            "pattern": "nonexistent_pattern_xyz",
            "path": str(tmp_workspace),
        })
        assert "no matches" in result.lower()


class TestUnknownTool:
    def test_unknown_tool_name(self):
        result = execute_tool("nonexistent", {})
        assert "unknown tool" in result.lower()
```

## Step 9: Install dependencies

```bash
cd quoka-agent
pip install anthropic rich pytest
```

## Step 10: Run the tests

```bash
cd quoka-agent
python -m pytest tests/ -v
```

Expected output: 18 tests, all passing.

```
tests/test_tools.py::TestSafePath::test_rejects_path_outside_workdir PASSED
tests/test_tools.py::TestSafePath::test_accepts_path_inside_workdir PASSED
tests/test_tools.py::TestReadFile::test_read_existing_file PASSED
tests/test_tools.py::TestReadFile::test_read_missing_file PASSED
tests/test_tools.py::TestWriteFile::test_write_new_file PASSED
tests/test_tools.py::TestWriteFile::test_write_creates_directories PASSED
tests/test_tools.py::TestEditFile::test_edit_unique_string PASSED
tests/test_tools.py::TestEditFile::test_edit_missing_string PASSED
tests/test_tools.py::TestEditFile::test_edit_duplicate_string PASSED
tests/test_tools.py::TestRunCommand::test_simple_command PASSED
tests/test_tools.py::TestRunCommand::test_blocked_dangerous_command PASSED
tests/test_tools.py::TestRunCommand::test_command_failure PASSED
tests/test_tools.py::TestRunCommand::test_timeout PASSED
tests/test_tools.py::TestListDirectory::test_list_files PASSED
tests/test_tools.py::TestListDirectory::test_empty_directory PASSED
tests/test_tools.py::TestSearchFiles::test_search_finds_pattern PASSED
tests/test_tools.py::TestSearchFiles::test_search_no_matches PASSED
tests/test_tools.py::TestUnknownTool::test_unknown_tool_name PASSED

18 passed
```

## Step 11: Set your API key and run

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
cd quoka-agent
python -m src.cli
```

You should see the banner and a `>` prompt. Type a task and the agent will use its tools to complete it.

## Step 12: Verify it works

Try these at the prompt:

```
> list the files in this directory
> write a hello.py file that prints hello world, then run it
> read src/tools.py and count how many tools are defined
```

Type `/quit` to exit, `/tokens` to check API usage.

## File tree when complete

```
quoka-agent/
├── pyproject.toml
├── src/
│   ├── __init__.py
│   ├── agent.py
│   ├── cli.py
│   └── tools.py
└── tests/
    ├── __init__.py
    └── test_tools.py
```

## How it works

1. User types a message at the `>` prompt
2. The message is sent to Claude along with tool definitions
3. Claude responds with text and/or tool calls
4. Tool calls are executed locally on your machine
5. Results are sent back to Claude
6. Steps 3-5 repeat until Claude stops calling tools
7. Back to the `>` prompt

## Safety notes

- All file operations are restricted to the current working directory
- Dangerous shell commands (`rm -rf /`, `mkfs`, etc.) are blocked
- Shell commands time out after 30 seconds
- The agent loop is capped at 25 iterations per user message
- This is a development tool. Don't point it at production systems.

## Model override

Set `QUOKA_MODEL` to use a different Claude model:

```bash
QUOKA_MODEL=claude-sonnet-4-20250514 python -m src.cli
```
