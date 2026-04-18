"""Secure configuration management with encryption support."""

import os
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables from .env file
load_dotenv()


class SecureConfig(BaseModel):
    """Secure configuration using environment variables and encryption.

    Priority order:
    1. Environment variables (highest)
    2. .env file
    3. Database (encrypted)
    4. Defaults

    API keys should NEVER be stored in plaintext.
    """

    # Job board credentials (prefer env vars)
    job_board_username: Optional[str] = Field(
        default_factory=lambda: os.getenv("JOBCLI_USERNAME"),
        repr=False,
    )
    job_board_password: Optional[str] = Field(
        default_factory=lambda: os.getenv("JOBCLI_PASSWORD"),
        repr=False,
    )

    # LLM API keys (prefer env vars)
    openai_api_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY"),
        repr=False,
    )
    anthropic_api_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"),
        repr=False,
    )
    gemini_api_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY"),
        repr=False,
    )

    # Application settings
    default_llm_provider: str = Field(default="openai")
    headless: bool = Field(default=True)
    max_retries: int = Field(default=3)
    screenshot_on_error: bool = Field(default=True)
    screenshot_on_success: bool = Field(default=False)
    random_delay_min: float = Field(default=1.0)
    random_delay_max: float = Field(default=3.0)
    user_agent: Optional[str] = None

    # Paths
    resume_pdf_path: Optional[str] = None
    resume_json_path: Optional[str] = None
    log_directory: str = Field(default="logs")
    database_path: str = Field(default="~/.jobcli/jobcli.db")

    class Config:
        """Pydantic config."""

        env_file = ".env"
        env_file_encoding = "utf-8"


class EncryptionManager:
    """Manage encryption for sensitive data."""

    def __init__(self, key_path: Optional[Path] = None) -> None:
        """Initialize encryption manager.

        Args:
            key_path: Path to encryption key. If None, uses ~/.jobcli/secret.key
        """
        self.key_path = key_path or Path.home() / ".jobcli" / "secret.key"
        self.key = self._load_or_create_key()
        self.cipher = Fernet(self.key)

    def _load_or_create_key(self) -> bytes:
        """Load existing key or create new one."""
        if self.key_path.exists():
            return self.key_path.read_bytes()

        # Create new key
        key = Fernet.generate_key()
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        self.key_path.write_bytes(key)
        self.key_path.chmod(0o600)  # Restrict permissions
        return key

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext to encrypted string."""
        encrypted_bytes = self.cipher.encrypt(plaintext.encode())
        return encrypted_bytes.decode()

    def decrypt(self, encrypted: str) -> str:
        """Decrypt encrypted string to plaintext."""
        decrypted_bytes = self.cipher.decrypt(encrypted.encode())
        return decrypted_bytes.decode()


def load_secure_config(
    use_encryption: bool = False,
    encryption_manager: Optional[EncryptionManager] = None,
) -> SecureConfig:
    """Load configuration securely.

    Recommended usage:
        # Use environment variables (most secure)
        export OPENAI_API_KEY=sk-...
        export ANTHROPIC_API_KEY=sk-...
        config = load_secure_config()

        # Or use .env file
        # .env file:
        # OPENAI_API_KEY=sk-...
        # ANTHROPIC_API_KEY=sk-...
        config = load_secure_config()

    Args:
        use_encryption: Whether to decrypt values from database
        encryption_manager: Optional encryption manager for database values

    Returns:
        SecureConfig instance
    """
    # Load from environment variables and .env file
    config = SecureConfig()

    # If using encryption, decrypt database values
    if use_encryption and encryption_manager:
        # This would load encrypted values from database
        # and decrypt them - implementation depends on storage
        pass

    return config


def create_env_template(output_path: Path = Path(".env.template")) -> None:
    """Create .env template file for users.

    Usage:
        create_env_template()
        # User copies .env.template to .env and fills in values
    """
    template = """# JobCLI Configuration
# Copy this file to .env and fill in your credentials
# NEVER commit .env to version control!

# Job Board Credentials
JOBCLI_USERNAME=your_username
JOBCLI_PASSWORD=your_password

# LLM API Keys (get from respective providers)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=...

# Application Settings (optional)
JOBCLI_DEFAULT_LLM=openai
JOBCLI_HEADLESS=true
JOBCLI_MAX_RETRIES=3
"""

    output_path.write_text(template)
    print(f"Created {output_path}")
    print("Copy to .env and fill in your credentials")


def validate_api_keys(config: SecureConfig) -> dict[str, bool]:
    """Validate that API keys are present and formatted correctly.

    Returns:
        Dictionary of provider -> is_valid
    """
    validation = {}

    if config.openai_api_key:
        validation["openai"] = config.openai_api_key.startswith("sk-")

    if config.anthropic_api_key:
        validation["anthropic"] = config.anthropic_api_key.startswith("sk-ant-")

    if config.gemini_api_key:
        validation["gemini"] = len(config.gemini_api_key) > 10

    return validation


# Best practices documentation
"""
SECURITY BEST PRACTICES:

1. **Use Environment Variables**
   - Most secure method
   - Not committed to version control
   - Easy to rotate

2. **Use .env File**
   - Add .env to .gitignore
   - Never commit
   - Restrict file permissions: chmod 600 .env

3. **Use System Keyring** (optional, advanced)
   - On macOS: Keychain
   - On Linux: Secret Service
   - On Windows: Credential Manager
   - Requires: pip install keyring

4. **Encrypt Database Storage** (optional)
   - Use EncryptionManager
   - Protect encryption key
   - Backup key securely

5. **Never:**
   - ❌ Hardcode API keys in code
   - ❌ Commit keys to git
   - ❌ Store keys in plaintext database
   - ❌ Log API keys
   - ❌ Include keys in screenshots

6. **Key Rotation:**
   - Rotate keys regularly
   - Use different keys per environment
   - Revoke compromised keys immediately

Example secure setup:

    # .env file (gitignored)
    OPENAI_API_KEY=sk-...
    ANTHROPIC_API_KEY=sk-ant-...

    # Load in code
    from jobcli.core.secure_config import load_secure_config
    config = load_secure_config()

    # API keys automatically loaded from environment
    engine = AsyncApplicationEngine(config, resume, db)
"""
