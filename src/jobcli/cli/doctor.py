"""Environment and dependency checks (career-ops-style `doctor`)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console


def run_doctor(console: "Console", wbox_smoke: bool = False) -> int:
    """Run health checks. Returns 0 if all critical checks pass."""
    issues = 0
    ok = "[green]OK[/green]"
    bad = "[red]FAIL[/red]"
    warn = "[yellow]WARN[/yellow]"

    console.print("[bold cyan]jobcli doctor[/bold cyan]\n")

    # Python
    py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    console.print(f"Python {py}: {ok}")

    # Playwright / Chromium
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        console.print(f"Playwright Chromium launch: {ok}")
    except Exception as e:
        console.print(f"Playwright Chromium launch: {bad} ({e})")
        issues += 1

    # Database (default path; mirrors jobcli.cli.main)
    try:
        from sqlalchemy import text

        from jobcli.storage.models import Database

        _cfg_dir = Path.home() / ".jobcli"
        _db_file = _cfg_dir / "jobcli.db"
        _cfg_dir.mkdir(parents=True, exist_ok=True)
        db = Database(f"sqlite:///{_db_file}")
        db.create_tables()
        s = db.get_session()
        try:
            s.execute(text("SELECT 1"))
            s.commit()
        finally:
            s.close()
        console.print(f"SQLite database ({_db_file}): {ok}")
    except Exception as e:
        console.print(f"SQLite database: {bad} ({e})")
        issues += 1

    # Config / API keys (masked)
    try:
        from jobcli.cli.main import get_config

        cfg = get_config()
        has_llm = bool(cfg.openai_api_key or cfg.anthropic_api_key or cfg.gemini_api_key)
        has_board = bool(cfg.job_board_username and cfg.job_board_password)
        if has_llm:
            console.print(f"LLM API key configured ({cfg.default_llm_provider}): {ok}")
        else:
            console.print(f"LLM API key: {warn} (automation will be limited)")
        if has_board:
            console.print("Job board (Whitebox) credentials: [green]set[/green]")
        else:
            console.print(f"Job board credentials: {warn} (discover/login flows need `jobcli login`)")
    except Exception as e:
        console.print(f"Config load: {bad} ({e})")
        issues += 1

    # Resume JSON
    resume_path = os.environ.get("JOBCLI_RESUME_JSON")
    if not resume_path:
        try:
            from jobcli.cli.main import get_config

            cfg = get_config()
            if cfg.resume_json_path:
                resume_path = str(Path(cfg.resume_json_path).expanduser())
        except Exception:
            pass
    if not resume_path:
        here = Path(__file__).resolve().parents[2]
        candidate = here / "example_resume.json"
        if candidate.is_file():
            resume_path = str(candidate)

    if resume_path and Path(resume_path).is_file():
        try:
            from jobcli.profile.schemas import ResumeData
            from jobcli.intelligence.synonym_resolver import ResumeAutoDetector

            raw = json.loads(Path(resume_path).read_text(encoding="utf-8"))
            converted = ResumeAutoDetector.detect_and_convert(raw)
            ResumeData.model_validate(converted)
            console.print(f"Resume JSON parse ({resume_path}): {ok}")
        except Exception as e:
            console.print(f"Resume JSON parse: {bad} ({e})")
            issues += 1
    else:
        console.print(f"Resume JSON sample: {warn} (set config resume_json_path or JOBCLI_RESUME_JSON)")

    if wbox_smoke:
        user = os.getenv("JOBCLI_USERNAME")
        pwd = os.getenv("JOBCLI_PASSWORD")
        if not user or not pwd:
            console.print(f"Wbox smoke (--wbox-smoke): {warn} (set JOBCLI_USERNAME and JOBCLI_PASSWORD)")
        else:
            try:
                from playwright.sync_api import sync_playwright

                login_url = os.getenv("WBOX_LOGIN_URL", "https://whitebox-learning.com/login")
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(login_url, timeout=25000, wait_until="domcontentloaded")
                    _ = page.content()
                    browser.close()
                console.print(f"Wbox login URL reachable ({login_url}): {ok}")
            except Exception as e:
                console.print(f"Wbox smoke: {bad} ({e})")
                issues += 1

    # Browser Extension (TalentScreen v2)
    try:
        from jobcli.cli.main import get_config
        from jobcli.extension.helpers import read_extension_manifest_version, resolve_extension_dir

        cfg = get_config()
        ext_path = resolve_extension_dir(cfg.extension_path)

        if ext_path:
            ext_ver = read_extension_manifest_version(ext_path)
            ver_label = f" v{ext_ver}" if ext_ver else ""
            console.print(f"TalentScreen extension{ver_label}: {ok}")
            console.print(f"  [dim]{ext_path}[/dim]")
        else:
            console.print(
                f"TalentScreen extension: {warn} (not found — run [cyan]jobcli setup[/cyan], "
                "set extension_path, or JOBCLI_EXTENSION_PATH)"
            )
    except Exception as e:
        console.print(f"TalentScreen extension: {warn} ({e})")

    console.print()
    if issues:
        console.print(f"[bold red]{issues} critical check(s) failed.[/bold red]")
        return 1
    console.print("[bold green]All critical checks passed.[/bold green]")
    return 0
