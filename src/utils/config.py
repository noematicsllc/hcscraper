"""Configuration management for Hallmark Connect scraper."""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv


class Config:
    """Application configuration loaded from environment variables."""

    def __init__(self, env_file: Optional[str] = None):
        """Initialize configuration.

        Args:
            env_file: Path to .env file (default: .env in project root)
        """
        if env_file:
            load_dotenv(env_file)
        else:
            # Try to find .env in project root
            project_root = Path(__file__).parent.parent.parent
            env_path = project_root / ".env"
            if env_path.exists():
                load_dotenv(env_path)

    # Hallmark Connect credentials
    @property
    def username(self) -> str:
        """Hallmark Connect username."""
        value = os.getenv("HALLMARK_USERNAME", "")
        if not value:
            raise ValueError("HALLMARK_USERNAME not set in environment")
        return value

    @property
    def password(self) -> str:
        """Hallmark Connect password."""
        value = os.getenv("HALLMARK_PASSWORD", "")
        if not value:
            raise ValueError("HALLMARK_PASSWORD not set in environment")
        return value

    # MFA configuration
    @property
    def mfa_method(self) -> str:
        """MFA method: 'manual' or 'webhook'."""
        return os.getenv("MFA_METHOD", "manual").lower()

    @property
    def n8n_webhook_url(self) -> Optional[str]:
        """n8n webhook URL for MFA codes."""
        return os.getenv("N8N_WEBHOOK_URL")

    # Application settings
    @property
    def base_url(self) -> str:
        """Hallmark Connect base URL."""
        return os.getenv("BASE_URL", "https://services.hallmarkconnect.com")

    @property
    def output_directory(self) -> Path:
        """Output directory for data files."""
        path_str = os.getenv("OUTPUT_DIRECTORY", "./data")
        path = Path(path_str)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def log_level(self) -> str:
        """Logging level."""
        return os.getenv("LOG_LEVEL", "INFO").upper()

    @property
    def rate_limit_seconds(self) -> float:
        """Seconds to wait between API requests."""
        return float(os.getenv("RATE_LIMIT_SECONDS", "2.5"))

    @property
    def max_retries(self) -> int:
        """Maximum number of retry attempts for failed requests."""
        return int(os.getenv("MAX_RETRIES", "3"))

    @property
    def headless_mode(self) -> bool:
        """Run browser in headless mode."""
        value = os.getenv("HEADLESS_MODE", "false").lower()
        return value in ("true", "1", "yes")

    def validate(self) -> bool:
        """Validate that all required configuration is present.

        Returns:
            bool: True if configuration is valid

        Raises:
            ValueError: If required configuration is missing
        """
        # Check required fields
        _ = self.username
        _ = self.password

        # Validate MFA method
        if self.mfa_method not in ("manual", "webhook"):
            raise ValueError(f"Invalid MFA_METHOD: {self.mfa_method}. Must be 'manual' or 'webhook'")

        # If webhook method, ensure webhook URL is set
        if self.mfa_method == "webhook" and not self.n8n_webhook_url:
            raise ValueError("N8N_WEBHOOK_URL required when MFA_METHOD is 'webhook'")

        return True


# Global config instance
_config: Optional[Config] = None


def get_config(env_file: Optional[str] = None) -> Config:
    """Get global configuration instance.

    Args:
        env_file: Path to .env file (optional)

    Returns:
        Config: Global configuration instance
    """
    global _config
    if _config is None:
        _config = Config(env_file)
    return _config
