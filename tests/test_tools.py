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
        import platform
        if platform.system() == "Windows":
            cmd = "ping -n 10 127.0.0.1"
        else:
            cmd = "sleep 10"
        result = execute_tool("run_command", {"command": cmd, "timeout": 1})
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
        assert "def hello" in result or "hello" in result

    def test_search_no_matches(self, tmp_workspace):
        (tmp_workspace / "test.py").write_text("nothing here")
        result = execute_tool("search_files", {
            "pattern": "nonexistent_pattern_xyz",
            "path": str(tmp_workspace),
        })
        assert "no matches" in result.lower() or "not found" in result.lower() or "no match" in result.lower()


class TestUnknownTool:
    def test_unknown_tool_name(self):
        result = execute_tool("nonexistent", {})
        assert "unknown tool" in result.lower()
