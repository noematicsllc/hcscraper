"""MFA code retrieval handlers for Hallmark Connect authentication."""

from abc import ABC, abstractmethod
import requests
import time
from typing import Optional


class MFAHandler(ABC):
    """Abstract base class for MFA code retrieval."""

    @abstractmethod
    def get_mfa_code(self) -> str:
        """Retrieve MFA code from configured source.

        Returns:
            str: The MFA code

        Raises:
            Exception: If MFA code cannot be retrieved
        """
        pass


class ConsoleMFAHandler(MFAHandler):
    """Manual console input for MFA codes."""

    def get_mfa_code(self) -> str:
        """Prompt user for MFA code via console input.

        Returns:
            str: The MFA code entered by user
        """
        code = input("Enter MFA code: ").strip()
        if not code:
            raise ValueError("MFA code cannot be empty")
        return code


class WebhookMFAHandler(MFAHandler):
    """Retrieve MFA code from n8n webhook endpoint."""

    def __init__(self, webhook_url: str, timeout: int = 60, poll_interval: int = 2):
        """Initialize webhook MFA handler.

        Args:
            webhook_url: The n8n webhook URL to poll for MFA codes
            timeout: Maximum seconds to wait for MFA code (default: 60)
            poll_interval: Seconds between polling attempts (default: 2)
        """
        self.webhook_url = webhook_url
        self.timeout = timeout
        self.poll_interval = poll_interval

    def get_mfa_code(self) -> str:
        """Poll webhook endpoint for MFA code.

        Returns:
            str: The MFA code from webhook

        Raises:
            TimeoutError: If MFA code not received within timeout period
            requests.RequestException: If webhook request fails
        """
        start_time = time.time()

        while time.time() - start_time < self.timeout:
            try:
                response = requests.get(self.webhook_url, timeout=5)
                response.raise_for_status()

                data = response.json()

                # Expecting webhook to return {"code": "123456"} or similar
                if "code" in data and data["code"]:
                    return str(data["code"]).strip()

            except requests.RequestException as e:
                # Log but continue polling
                print(f"Webhook poll failed: {e}")

            time.sleep(self.poll_interval)

        raise TimeoutError(f"MFA code not received within {self.timeout} seconds")
