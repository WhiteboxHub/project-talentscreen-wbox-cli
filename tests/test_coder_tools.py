import os
import pytest
from pathlib import Path

from jobcli.coder.tools import (
    list_dir,
    search_code,
    read_file,
    read_file_summary,
    replace_in_file,
    run_command
)

@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace with some files for testing."""
    test_dir = tmp_path / "test_project"
    test_dir.mkdir()
    
    # Create some files
    file1 = test_dir / "app.py"
    file1.write_text("def hello():\n    print('hello world')\n\nclass Server:\n    def start(self):\n        pass\n")
    
    file2 = test_dir / "utils.py"
    file2.write_text("def add(a, b):\n    return a + b\n")
    
    # Subdir
    sub_dir = test_dir / "src"
    sub_dir.mkdir()
    file3 = sub_dir / "main.py"
    file3.write_text("import sys\n")
    
    return test_dir

def test_list_dir(temp_workspace):
    # Test flat listing
    out = list_dir(str(temp_workspace), recursive=False)
    assert "[F] app.py" in out
    assert "[F] utils.py" in out
    assert "[D] src" in out
    assert "main.py" not in out # Not recursive
    
    # Test recursive listing
    out = list_dir(str(temp_workspace), recursive=True)
    assert "main.py" in out

def test_search_code(temp_workspace):
    out = search_code("hello", str(temp_workspace))
    assert "File: app.py" in out
    assert "print('hello world')" in out
    
    # Not found
    out = search_code("nonexistent_string", str(temp_workspace))
    assert "No results found" in out

def test_read_file(temp_workspace):
    file_path = temp_workspace / "app.py"
    out = read_file(str(file_path), start_line=1, end_line=2)
    assert "1 | def hello():" in out
    assert "2 |     print('hello world')" in out
    assert "class Server" not in out
    
    # Full read
    out = read_file(str(file_path))
    assert "6 |         pass" in out

def test_read_file_summary(temp_workspace):
    file_path = temp_workspace / "app.py"
    out = read_file_summary(str(file_path))
    assert "def hello(...)" in out
    assert "class Server:" in out
    assert "def start(...)" in out

def test_replace_in_file(temp_workspace):
    file_path = temp_workspace / "utils.py"
    
    # Replace all
    out = replace_in_file(str(file_path), "a + b", "a * b", occurrence="all")
    assert "Successfully replaced" in out
    content = file_path.read_text()
    assert "return a * b" in content
    
def test_run_command():
    out = run_command("echo test_run_command_success")
    assert "test_run_command_success" in out
    
    # Test timeout
    # Use python to sleep for 2 seconds, but set timeout to 1
    out = run_command("python -c \"import time; time.sleep(2)\"", timeout_sec=1)
    assert "timed out" in out
