"""Configuration management for Hallmark Connect scraper."""

import os
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv


# Banner's Hallmark 39 store customer IDs
BANNER_HALLMARK_CUSTOMER_IDS: List[str] = [
    "1000055874", "1000004735", "1000041880", "1000030843",
    "1000114306", "1000115859", "1000115805", "1000116758", "1000116745",
    "1000118750", "1000055291", "1000002154", "1000011835",
    "1000000626", "1000012828", "1000006859", "1000002240", "1000110655",
    "1000019277", "1000019864", "1000008399", "1000054183", "1000003575",
    "1000055311", "1000009732", "1000054184", "1000010181", "1000002149",
    "1000112560", "1000009191", "1000011545", "1000041844", "1000054160",
    "1000018832", "1000002234", "1000116853", "1000116772", "1000013175",
    "1000020145"
]

# Default maximum consecutive failures before stopping extraction
DEFAULT_MAX_CONSECUTIVE_FAILURES: int = 3


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
    def log_file(self) -> Optional[Path]:
        """Path to log file (optional)."""
        path_str = os.getenv("LOG_FILE")
        if not path_str:
            return None
        path = Path(path_str)
        # Create parent directory if it doesn't exist
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    # Timeout settings
    @property
    def request_timeout_seconds(self) -> float:
        """Timeout for regular detail requests."""
        return float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))

    @property
    def search_timeout_seconds(self) -> float:
        """Timeout for search requests (which take longer)."""
        return float(os.getenv("SEARCH_TIMEOUT_SECONDS", "120"))

    # Rate limiting settings
    @property
    def rate_limit_seconds(self) -> float:
        """Seconds to wait between API requests (deprecated, use rate_limit_detail_seconds)."""
        return float(os.getenv("RATE_LIMIT_SECONDS", "2.5"))

    @property
    def rate_limit_detail_seconds(self) -> float:
        """Seconds to wait between detail requests."""
        return float(os.getenv("RATE_LIMIT_DETAIL_SECONDS", os.getenv("RATE_LIMIT_SECONDS", "2.5")))

    @property
    def rate_limit_search_seconds(self) -> float:
        """Seconds to wait between search requests."""
        return float(os.getenv("RATE_LIMIT_SEARCH_SECONDS", "5.0"))

    @property
    def rate_limit_jitter_seconds(self) -> float:
        """Random jitter to add to rate limits (makes timing look more human)."""
        return float(os.getenv("RATE_LIMIT_JITTER_SECONDS", "0.5"))

    @property
    def max_retries(self) -> int:
        """Maximum number of retry attempts for failed requests."""
        return int(os.getenv("MAX_RETRIES", "3"))

    # Break settings (periodic pauses)
    @property
    def break_after_requests(self) -> int:
        """Number of requests before taking a break."""
        return int(os.getenv("BREAK_AFTER_REQUESTS", "25"))

    @property
    def break_after_jitter(self) -> int:
        """Random jitter for break interval (requests ± jitter)."""
        return int(os.getenv("BREAK_AFTER_JITTER", "5"))

    @property
    def break_duration_seconds(self) -> float:
        """Base duration of breaks in seconds."""
        return float(os.getenv("BREAK_DURATION_SECONDS", "60"))

    @property
    def break_jitter_seconds(self) -> float:
        """Random jitter for break duration (duration ± jitter)."""
        return float(os.getenv("BREAK_JITTER_SECONDS", "15"))

    # Conservative mode
    @property
    def conservative_mode(self) -> bool:
        """Enable conservative mode (doubles delays, halves requests between breaks)."""
        value = os.getenv("CONSERVATIVE_MODE", "false").lower()
        return value in ("true", "1", "yes")

    @property
    def headless_mode(self) -> bool:
        """Run browser in headless mode (default: True)."""
        value = os.getenv("HEADLESS_MODE", "true").lower()
        return value in ("true", "1", "yes")

    @property
    def session_file(self) -> Path:
        """Path to session file for Playwright state persistence."""
        path_str = os.getenv("SESSION_FILE", "./hallmark_session.json")
        return Path(path_str)

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
