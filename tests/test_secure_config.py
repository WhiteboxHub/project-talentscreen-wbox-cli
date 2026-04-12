"""Tests for secure configuration."""

import os
import pytest
from pathlib import Path

from jobcli.core.secure_config import (
    SecureConfig,
    EncryptionManager,
    load_secure_config,
    validate_api_keys,
)


def test_config_loads_from_env():
    """Test that config loads from environment variables."""
    os.environ["OPENAI_API_KEY"] = "sk-test123"
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test456"

    config = load_secure_config()

    assert config.openai_api_key == "sk-test123"
    assert config.anthropic_api_key == "sk-ant-test456"

    # Cleanup
    del os.environ["OPENAI_API_KEY"]
    del os.environ["ANTHROPIC_API_KEY"]


def test_encryption_roundtrip(tmp_path):
    """Test that encryption/decryption works."""
    key_path = tmp_path / "test_key"
    manager = EncryptionManager(key_path)

    plaintext = "sk-secret-api-key-12345"
    encrypted = manager.encrypt(plaintext)

    assert encrypted != plaintext
    assert len(encrypted) > len(plaintext)

    decrypted = manager.decrypt(encrypted)
    assert decrypted == plaintext


def test_encryption_key_persists(tmp_path):
    """Test that encryption key is saved and reused."""
    key_path = tmp_path / "test_key"

    manager1 = EncryptionManager(key_path)
    encrypted = manager1.encrypt("test")

    manager2 = EncryptionManager(key_path)
    decrypted = manager2.decrypt(encrypted)

    assert decrypted == "test"


def test_encryption_key_permissions(tmp_path):
    """Test that encryption key has correct permissions."""
    key_path = tmp_path / "test_key"
    manager = EncryptionManager(key_path)

    # Check file permissions (Unix only)
    if os.name != "nt":  # Not Windows
        stat = key_path.stat()
        permissions = oct(stat.st_mode)[-3:]
        assert permissions == "600"  # Owner read/write only


def test_api_key_validation():
    """Test API key format validation."""
    config = SecureConfig(
        openai_api_key="sk-valid123",
        anthropic_api_key="sk-ant-valid456",
        gemini_api_key="validkey789",
    )

    validation = validate_api_keys(config)

    assert validation["openai"] is True
    assert validation["anthropic"] is True
    assert validation["gemini"] is True


def test_api_key_validation_invalid():
    """Test API key validation catches invalid formats."""
    config = SecureConfig(
        openai_api_key="invalid",  # Should start with sk-
        anthropic_api_key="also-invalid",  # Should start with sk-ant-
    )

    validation = validate_api_keys(config)

    assert validation.get("openai") is False
    assert validation.get("anthropic") is False


def test_config_defaults():
    """Test that config has sensible defaults."""
    config = SecureConfig()

    assert config.headless is True
    assert config.max_retries == 3
    assert config.screenshot_on_error is True
    assert config.log_directory == "logs"


def test_no_plaintext_api_keys_in_repr():
    """Test that API keys are not exposed in repr/str."""
    config = SecureConfig(openai_api_key="sk-secret123")

    config_str = str(config)
    config_repr = repr(config)

    # API key should not appear in full
    assert "sk-secret123" not in config_str
    assert "sk-secret123" not in config_repr


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
