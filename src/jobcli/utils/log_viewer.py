"""Per-job application log lines for CLI and web UI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _log_directory() -> Path:
    return Path(os.path.expanduser(os.getenv("JOBCLI_LOG_DIR", "~/.jobcli/logs")))


def _read_jsonl_tail(log_file: Path, tail: int) -> list[str]:
    if not log_file.is_file():
        return []
    lines: list[str] = []
    try:
        with log_file.open("r", encoding="utf-8") as fp:
            for line in fp:
                stripped = line.strip()
                if stripped:
                    lines.append(stripped)
    except OSError:
        return []
    if tail > 0 and len(lines) > tail:
        lines = lines[-tail:]
    return lines


def _format_jsonl_entry(raw: str) -> str:
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if not isinstance(obj, dict):
        return raw
    ts = obj.get("timestamp") or obj.get("ts") or ""
    phase = obj.get("phase") or ""
    action = obj.get("action") or obj.get("message") or ""
    success = obj.get("success")
    err = obj.get("error")
    parts = [p for p in (str(ts)[:19], str(phase), str(action)) if p]
    line = " | ".join(parts) if parts else raw
    if success is False and err:
        line += f" [ERR: {err}]"
    return line


def collect_log_lines(
    session: "Session",
    *,
    job_id: int,
    tail: int = 60,
) -> list[str]:
    """Collect human-readable log lines for one job (DB first, then application.jsonl)."""
    from jobcli.storage.repositories import ApplicationLogRepository

    tail = max(1, min(int(tail or 60), 500))
    lines: list[str] = []

    try:
        rows = ApplicationLogRepository(session).get_logs(job_id)
        for row in rows:
            ts = row.timestamp.isoformat() if row.timestamp else ""
            phase = getattr(row.phase, "value", str(row.phase or ""))
            action = row.action or ""
            ok = "ok" if row.success else "FAIL"
            err = f" — {row.error}" if row.error else ""
            lines.append(f"{ts[:19]} | {phase} | {action} [{ok}]{err}")
    except Exception:
        pass

    if not lines:
        log_file = _log_directory() / f"job_{job_id}" / "application.jsonl"
        for raw in _read_jsonl_tail(log_file, tail):
            lines.append(_format_jsonl_entry(raw))

    if tail > 0 and len(lines) > tail:
        lines = lines[-tail:]
    return lines


def format_log_lines_ansi(lines: list[str]) -> str:
    """Format lines for web terminal broadcast (ANSI)."""
    if not lines:
        return "\r\n\x1b[33m(no log lines for this job)\x1b[0m\r\n"
    out = ["\r\n\x1b[36m--- application log ---\x1b[0m\r\n"]
    for line in lines:
        if "FAIL" in line or "[ERR" in line:
            out.append(f"\x1b[31m{line}\x1b[0m\r\n")
        else:
            out.append(f"{line}\r\n")
    return "".join(out)
