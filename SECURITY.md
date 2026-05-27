# Security Policy

## Supported versions

Only the latest minor release on `main` receives security fixes.

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a vulnerability

**Please do not file a public GitHub issue for security problems.**

Email `security@whitebox-learning.com` with:

- A description of the issue and the impact.
- Steps to reproduce, ideally with a minimal proof-of-concept.
- Your assessment of the severity.
- Whether you'd like to be credited in the release notes.

You will receive an acknowledgement within **3 business days**. We aim to
ship a fix or mitigation within **30 days** for high-severity issues.

## Scope

In scope:

- The CLI itself (`src/jobcli/`)
- The install / uninstall scripts (`scripts/`)
- The TalentScreen browser extension when installed via WboxCLI
- Anything that exposes user credentials, LLM API keys, or session tokens

Out of scope:

- Third-party ATS sites that WboxCLI automates (report to those sites directly)
- Issues that require physical access to the user's machine
- DoS attacks that require an unreasonable amount of traffic

## Handling secrets

WboxCLI stores credentials and API keys in `~/.jobcli/jobcli.db` (SQLite,
encrypted via `cryptography.fernet`). The CLI does **not** read `.env` files
in production. Do not paste secrets into bug reports — redact them.
