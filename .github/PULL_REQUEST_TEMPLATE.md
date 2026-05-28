## Summary

<!-- 1-3 sentences explaining what changes and why. -->

## Type of change

- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change (any user-facing API, CLI flag, or storage format)
- [ ] Documentation / chore / refactor

## Related issues

<!-- Closes #123, Refs #456 -->

## Test plan

<!-- How did you verify this works? Commands you ran, ATS sites you tested
     against, screenshots, etc. -->

```bash
# example
PYTHONPATH=src python -m jobcli.cli.main apply --dry-run
```

## Checklist

- [ ] I ran `black src tests` and `ruff check src tests`
- [ ] I added or updated tests where appropriate
- [ ] I updated `CHANGELOG.md` under `[Unreleased]`
- [ ] I updated README / docs for any user-facing change
- [ ] No secrets, API keys, or personal data are in the diff
- [ ] My PR targets `dev` (not `main`), unless it's a hotfix
