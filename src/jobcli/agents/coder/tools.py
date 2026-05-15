import ast
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

def list_dir(path: str, recursive: bool = False, max_depth: int = 2) -> str:
    """Lists files and directories."""
    base_path = Path(path).resolve()
    if not base_path.exists():
        return f"Error: Path {path} does not exist."
    if not base_path.is_dir():
        return f"Error: Path {path} is not a directory."

    output = []
    
    def _scan(current_path: Path, current_depth: int):
        if current_depth > max_depth:
            return
        try:
            entries = sorted(current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
            for entry in entries:
                # Basic ignore list
                if entry.name in {".git", "__pycache__", "node_modules", ".venv", "venv"}:
                    continue
                    
                rel_path = entry.relative_to(base_path)
                indent = "  " * (current_depth - 1)
                marker = "[D] " if entry.is_dir() else "[F] "
                output.append(f"{indent}{marker}{rel_path}")
                
                if recursive and entry.is_dir():
                    _scan(entry, current_depth + 1)
        except PermissionError:
            output.append(f"{'  ' * (current_depth - 1)}[Permission Denied] {current_path.name}")
            
    _scan(base_path, 1)
    return "\n".join(output) if output else "Directory is empty."


def search_code(query: str, directory: str, top_k: int = 5) -> str:
    """Searches for relevant code snippets."""
    base_path = Path(directory).resolve()
    if not base_path.exists() or not base_path.is_dir():
        return f"Error: Directory {directory} does not exist."

    results = []
    
    try:
        # We'll use ripgrep if available, otherwise fallback to simple python search
        # To keep it robust across OS, we'll implement a simple recursive python search
        # that respects common ignores.
        ignore_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv"}
        
        matches_found = 0
        for root, dirs, files in os.walk(base_path):
            # prune ignored dirs
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            
            for file in files:
                if matches_found >= top_k:
                    break
                    
                file_path = Path(root) / file
                # Skip likely binary files
                if file.endswith(('.pyc', '.pdf', '.png', '.jpg', '.zip', '.sqlite3', '.db')):
                    continue
                    
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        
                    for i, line in enumerate(lines):
                        if query.lower() in line.lower():
                            rel_path = file_path.relative_to(base_path)
                            snippet = "".join(lines[max(0, i-1):min(len(lines), i+2)])
                            results.append(f"--- File: {rel_path} (Line {i+1}) ---\n{snippet.strip()}")
                            matches_found += 1
                            if matches_found >= top_k:
                                break
                except UnicodeDecodeError:
                    pass # Skip non-text files
                    
        if not results:
            return f"No results found for '{query}'"
        return "\n\n".join(results)
    except Exception as e:
        return f"Error searching code: {e}"


def read_file(path: str, start_line: int = 1, end_line: Optional[int] = None) -> str:
    """Reads a portion of a file."""
    file_path = Path(path).resolve()
    if not file_path.exists() or not file_path.is_file():
        return f"Error: File {path} does not exist."

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        start_idx = max(0, start_line - 1)
        end_idx = len(lines) if end_line is None else min(len(lines), end_line)
        
        if start_idx >= len(lines):
            return f"Error: start_line {start_line} is beyond file length ({len(lines)} lines)."
            
        output = []
        for i in range(start_idx, end_idx):
            line_content = lines[i].rstrip('\n')
            output.append(f"{i+1:4d} | {line_content}")
            
        return "\n".join(output)
    except Exception as e:
        return f"Error reading file: {e}"


def read_file_summary(path: str) -> str:
    """Provides a high-level summary of a file (e.g., classes and functions)."""
    file_path = Path(path).resolve()
    if not file_path.exists() or not file_path.is_file():
        return f"Error: File {path} does not exist."

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        if file_path.suffix == ".py":
            # Use AST for python files
            tree = ast.parse(content)
            summary = []
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    summary.append(f"class {node.name}:")
                    for sub in node.body:
                        if isinstance(sub, ast.FunctionDef):
                            summary.append(f"    def {sub.name}(...)")
                elif isinstance(node, ast.FunctionDef):
                    summary.append(f"def {node.name}(...)")
            
            if not summary:
                return "File contains no top-level classes or functions."
            return "\n".join(summary)
        else:
            # For non-python, just return the first 20 lines
            lines = content.splitlines()
            return "File summary (first 20 lines):\n" + "\n".join(lines[:20])
    except Exception as e:
        return f"Error parsing summary: {e}"


def replace_in_file(path: str, target_text: str, replacement_text: str, occurrence: str = "all") -> str:
    """Replaces specific content in a file."""
    file_path = Path(path).resolve()
    if not file_path.exists() or not file_path.is_file():
        return f"Error: File {path} does not exist."

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        if target_text not in content:
            return "Error: target_text not found in file."
            
        if occurrence == "all":
            new_content = content.replace(target_text, replacement_text)
            count = content.count(target_text)
        else:
            try:
                count = 1
                occ_idx = int(occurrence)
                # Split and replace only the Nth occurrence
                parts = content.split(target_text)
                if occ_idx < 1 or occ_idx >= len(parts):
                    return f"Error: Occurrence {occ_idx} out of bounds."
                
                new_content = target_text.join(parts[:occ_idx]) + replacement_text + target_text.join(parts[occ_idx:])
            except ValueError:
                return "Error: occurrence must be 'all' or an integer."

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
            
        return f"Successfully replaced {count} occurrence(s)."
    except Exception as e:
        return f"Error replacing text: {e}"


def run_command(command: str, timeout_sec: int = 10, kill_on_timeout: bool = True) -> str:
    """Executes a shell command with timeout protection."""
    try:
        # Use shell=True for windows compatibility and ease of use, but limit scope
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        try:
            stdout, _ = process.communicate(timeout=timeout_sec)
            return stdout or "Command completed with no output."
        except subprocess.TimeoutExpired:
            if kill_on_timeout:
                process.kill()
                process.communicate() # flush
            return f"Error: Command timed out after {timeout_sec} seconds."
            
    except Exception as e:
        return f"Error running command: {e}"
