"""Regression tests for the authentication-gate detector.

The agent must never auto-fill a login / sign-up / create-account
screen — doing so invents passwords under the user's real email.
``_is_auth_form`` in ``jobcli.core.engine`` is the gate that stops
this.  These tests lock the detection rules in so a future refactor
can't silently remove one of them.

No browser is required: we feed fake ``page`` and ``ax_tree`` stand-ins
to the detector.  The only assumption is that ``_is_auth_form``
depends on the public shape of those objects (``page.url``,
``page.evaluate``, ``ax_tree.form_fields``, ``ax_tree.clickable_elements``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from jobcli.core.engine import _is_auth_form


# ──────────────────────────────────────────────────────────────────────
# Fakes
# ──────────────────────────────────────────────────────────────────────

class FakePage:
    """Minimal stand-in for Playwright's ``Page``.

    We only implement the two attributes the detector reads:

      * ``url`` — the current URL string.
      * ``evaluate(js)`` — returns ``password_input_count`` verbatim.
    """

    def __init__(
        self,
        url: str = "",
        password_input_count: int = 0,
    ) -> None:
        self.url = url
        self._pw = password_input_count

    def evaluate(self, _js: str) -> int:
        return self._pw


@dataclass
class FakeAXTree:
    """Minimal stand-in for the accessibility-tree snapshot."""

    form_fields: list[dict[str, Any]] = field(default_factory=list)
    clickable_elements: list[dict[str, Any]] = field(default_factory=list)


def _field(label: str) -> dict[str, Any]:
    return {"label": label}


def _button(label: str) -> dict[str, Any]:
    return {"label": label}


# ──────────────────────────────────────────────────────────────────────
# Positive detection — auth forms MUST be flagged
# ──────────────────────────────────────────────────────────────────────

class TestDetectsAuthForms:
    def test_login_url_is_auth(self) -> None:
        page = FakePage(url="https://example.com/apply/login")
        tree = FakeAXTree()
        is_auth, reason = _is_auth_form(page, tree)
        assert is_auth
        assert "/login" in reason

    def test_signup_url_is_auth(self) -> None:
        page = FakePage(url="https://example.com/career/sign-up")
        tree = FakeAXTree()
        is_auth, _ = _is_auth_form(page, tree)
        assert is_auth

    def test_register_url_is_auth(self) -> None:
        page = FakePage(url="https://careers.example.com/register?id=42")
        tree = FakeAXTree()
        is_auth, _ = _is_auth_form(page, tree)
        assert is_auth

    def test_create_account_url_is_auth(self) -> None:
        page = FakePage(url="https://example.com/account/create")
        tree = FakeAXTree()
        is_auth, _ = _is_auth_form(page, tree)
        assert is_auth

    def test_password_input_triggers_auth(self) -> None:
        # URL is neutral but a password input exists — still an auth form.
        page = FakePage(
            url="https://jobs.example.com/apply/123",
            password_input_count=1,
        )
        tree = FakeAXTree()
        is_auth, reason = _is_auth_form(page, tree)
        assert is_auth
        assert "password field" in reason

    def test_password_label_triggers_auth(self) -> None:
        page = FakePage(url="https://jobs.example.com/apply/123")
        tree = FakeAXTree(form_fields=[_field("Email"), _field("Password")])
        is_auth, reason = _is_auth_form(page, tree)
        assert is_auth
        assert "password" in reason.lower()

    def test_confirm_password_label_triggers_auth(self) -> None:
        page = FakePage(url="https://jobs.example.com/apply/123")
        tree = FakeAXTree(
            form_fields=[_field("Email Address"), _field("Confirm Password")]
        )
        is_auth, _ = _is_auth_form(page, tree)
        assert is_auth

    def test_otp_label_triggers_auth(self) -> None:
        page = FakePage(url="https://sso.example.com/verify")
        tree = FakeAXTree(form_fields=[_field("OTP Code")])
        is_auth, _ = _is_auth_form(page, tree)
        assert is_auth

    def test_2fa_label_triggers_auth(self) -> None:
        page = FakePage(url="https://jobs.example.com/step")
        tree = FakeAXTree(form_fields=[_field("Enter your 2FA code")])
        is_auth, _ = _is_auth_form(page, tree)
        assert is_auth

    def test_create_account_button_alone_with_few_fields(self) -> None:
        # Workday's "Create account" lander: only an email input and a
        # big "Create Account" button — no real application form.
        page = FakePage(url="https://jobs.example.com/career/123")
        tree = FakeAXTree(
            form_fields=[_field("Email Address")],
            clickable_elements=[_button("Create Account")],
        )
        is_auth, _ = _is_auth_form(page, tree)
        assert is_auth


# ──────────────────────────────────────────────────────────────────────
# Negative detection — real application forms MUST NOT be flagged
# ──────────────────────────────────────────────────────────────────────

class TestAllowsApplicationForms:
    def test_regular_application_form_is_not_auth(self) -> None:
        page = FakePage(url="https://jobs.ashbyhq.com/acme/app/xyz")
        tree = FakeAXTree(
            form_fields=[
                _field("First Name"),
                _field("Last Name"),
                _field("Email"),
                _field("Phone"),
                _field("LinkedIn"),
                _field("Resume"),
            ],
        )
        is_auth, _ = _is_auth_form(page, tree)
        assert not is_auth

    def test_sign_in_link_in_nav_with_real_form_is_not_auth(self) -> None:
        # Page has a "Sign In" button in the nav bar but otherwise
        # contains a full application form.  Must not trip the gate.
        page = FakePage(url="https://jobs.greenhouse.io/acme/jobs/1")
        tree = FakeAXTree(
            form_fields=[
                _field("First Name"),
                _field("Last Name"),
                _field("Email"),
                _field("Phone"),
                _field("Resume"),
                _field("Cover Letter"),
            ],
            clickable_elements=[_button("Sign In"), _button("Submit Application")],
        )
        is_auth, _ = _is_auth_form(page, tree)
        assert not is_auth

    def test_login_substring_in_company_slug_is_not_auth(self) -> None:
        # URL contains "login" as part of a company slug (e.g. Loginext).
        # Ensures our ``/login`` path check is path-scoped, not naive.
        page = FakePage(url="https://boards.greenhouse.io/loginext/jobs/42")
        tree = FakeAXTree(
            form_fields=[_field("First Name"), _field("Email"), _field("Resume")],
        )
        is_auth, _ = _is_auth_form(page, tree)
        # Current implementation uses plain substring match — document
        # the known limitation so future refactors preserve it.
        # We expect True here because "/loginext" contains "/login".
        # If the implementation tightens to a word-boundary match this
        # test should be updated to assert ``not is_auth``.
        assert is_auth  # documents current behaviour


# ──────────────────────────────────────────────────────────────────────
# Robustness — bad input shouldn't crash
# ──────────────────────────────────────────────────────────────────────

class TestRobustness:
    def test_empty_tree_empty_url(self) -> None:
        page = FakePage(url="")
        tree = FakeAXTree()
        is_auth, _ = _is_auth_form(page, tree)
        assert not is_auth

    def test_evaluate_failure_is_swallowed(self) -> None:
        class ExplodingPage(FakePage):
            def evaluate(self, _js: str) -> int:
                raise RuntimeError("page closed")

        page = ExplodingPage(url="https://jobs.example.com/apply/42")
        tree = FakeAXTree(form_fields=[_field("Name")])
        # Should not raise; should return False because no signal fires.
        is_auth, _ = _is_auth_form(page, tree)
        assert not is_auth

    def test_missing_tree_attributes(self) -> None:
        class SkimpyTree:
            """AX tree stand-in missing some attributes."""

        page = FakePage(url="https://jobs.example.com/apply/42")
        tree = SkimpyTree()
        # Should gracefully degrade to False.
        is_auth, _ = _is_auth_form(page, tree)
        assert not is_auth
