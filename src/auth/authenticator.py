"""Playwright-based authentication for Hallmark Connect with session persistence."""

import re
import logging
from pathlib import Path
from typing import Dict, Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError
import requests

from .mfa_handler import MFAHandler


logger = logging.getLogger(__name__)


class HallmarkAuthenticator:
    """Handles authentication to Hallmark Connect using Playwright with session persistence."""

    # Selectors for landing page
    RETAILER_LOGIN_BUTTON = "a:has-text('Retailer Login'), button:has-text('Retailer Login'), a[href*='login'], .login-button"

    # Selectors for PingOne login form elements
    USERNAME_FIELD = "input[name='username'], input[id='username'], input[type='email'], input[name='identifier']"
    PASSWORD_FIELD = "input[name='password'], input[id='password'], input[type='password']"
    LOGIN_BUTTON = "button[type='submit'], input[type='submit'], button:has-text('Sign On'), button:has-text('Sign In'), button:has-text('Log In')"
    MFA_FIELD = "input[name='code'], input[name='verificationCode'], input[type='text'][placeholder*='code' i], input[name='otp']"
    MFA_SUBMIT = "button[type='submit'], button:has-text('Verify'), button:has-text('Submit')"

    # Token extraction patterns
    TOKEN_PATTERN = r'"aura\.token":"([^"]+)"'
    FWUID_PATTERN = r'"fwuid":"([^"]+)"'

    def __init__(
        self,
        username: str,
        password: str,
        mfa_handler: MFAHandler,
        base_url: str = "https://services.hallmarkconnect.com",
        headless: bool = False,
        session_file: Optional[str] = None,
    ):
        """Initialize authenticator.

        Args:
            username: Hallmark Connect username
            password: Hallmark Connect password
            mfa_handler: MFA code handler instance
            base_url: Base URL for Hallmark Connect (default: production URL)
            headless: Run browser in headless mode (default: False for debugging)
            session_file: Path to save/load browser session state (default: hallmark_session.json)
        """
        self.username = username
        self.password = password
        self.mfa_handler = mfa_handler
        self.base_url = base_url
        self.headless = headless
        self.session_file = Path(session_file) if session_file else Path("hallmark_session.json")

        self._tokens: Optional[Dict[str, str]] = None
        self._session: Optional[requests.Session] = None

    def authenticate_with_saved_session(self) -> bool:
        """Try to authenticate using saved browser session (skips login/MFA).

        Returns:
            bool: True if authentication successful, False if saved session invalid

        Raises:
            Exception: If session loading fails
        """
        if not self.session_file.exists():
            logger.info(f"No saved session found at {self.session_file}")
            return False

        logger.info(f"Loading saved session from {self.session_file}")

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                try:
                    # Create context with saved state
                    context = browser.new_context(storage_state=str(self.session_file))
                    page = context.new_page()

                    # Navigate to a protected page to verify session is valid
                    test_url = f"{self.base_url}/s/"
                    logger.debug(f"Testing saved session by navigating to {test_url}")
                    page.goto(test_url, wait_until="networkidle", timeout=30000)

                    # Check if we're still logged in (not redirected to login page)
                    if "/login" in page.url.lower():
                        logger.warning("Saved session expired or invalid (redirected to login)")
                        return False

                    # Extract tokens
                    logger.info("Extracting session tokens from saved session")
                    self._tokens = self._extract_tokens(page)

                    if not self._tokens:
                        logger.warning("Failed to extract tokens from saved session")
                        return False

                    # Create requests session with cookies
                    self._session = self._create_session(page)

                    logger.info("✓ Successfully authenticated using saved session (no MFA needed!)")
                    return True

                finally:
                    browser.close()

        except Exception as e:
            logger.warning(f"Failed to load saved session: {e}")
            return False

    def authenticate(self, save_session: bool = True) -> bool:
        """Perform full authentication flow with login and MFA.

        Args:
            save_session: Whether to save browser session for future use (default: True)

        Returns:
            bool: True if authentication successful

        Raises:
            Exception: If authentication fails
        """
        logger.info("Starting full authentication flow (login + MFA)")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            try:
                context = browser.new_context()
                page = context.new_page()

                # Step 1: Navigate to landing page
                logger.info(f"Navigating to landing page: {self.base_url}")
                page.goto(self.base_url, wait_until="networkidle", timeout=30000)
                logger.debug(f"Current URL after landing page load: {page.url}")

                # Step 2: Click "Retailer Login" button
                logger.info("Looking for Retailer Login button...")
                try:
                    # Wait for the button to be visible and click it
                    page.wait_for_selector(self.RETAILER_LOGIN_BUTTON, timeout=15000)
                    page.click(self.RETAILER_LOGIN_BUTTON)
                    logger.info("Clicked Retailer Login button")
                except PlaywrightTimeoutError:
                    logger.warning("Retailer Login button not found, may already be on login page")

                # Step 3: Wait for redirect to PingOne login page
                logger.info("Waiting for redirect to PingOne login page...")
                try:
                    # Wait for either PingOne URL or username field to appear
                    page.wait_for_function(
                        """() => {
                            return window.location.href.includes('pingone.com') ||
                                   document.querySelector('input[name="username"]') ||
                                   document.querySelector('input[id="username"]') ||
                                   document.querySelector('input[type="email"]');
                        }""",
                        timeout=30000
                    )
                    logger.info(f"Redirected to: {page.url}")
                except PlaywrightTimeoutError:
                    logger.warning(f"Timeout waiting for PingOne redirect. Current URL: {page.url}")

                # Wait for page to stabilize
                page.wait_for_load_state("networkidle", timeout=15000)

                # Step 4: Wait for and fill username field
                logger.info("Waiting for username field...")
                page.wait_for_selector(self.USERNAME_FIELD, timeout=15000)
                logger.debug("Entering credentials")
                page.fill(self.USERNAME_FIELD, self.username)

                # Check if password field is on the same page or separate
                password_visible = page.locator(self.PASSWORD_FIELD).is_visible()
                if password_visible:
                    # Both fields on same page
                    page.fill(self.PASSWORD_FIELD, self.password)
                    page.click(self.LOGIN_BUTTON)
                else:
                    # Username-first flow: submit username, then enter password
                    logger.debug("Username-first flow detected, submitting username")
                    page.click(self.LOGIN_BUTTON)
                    page.wait_for_selector(self.PASSWORD_FIELD, timeout=15000)
                    page.fill(self.PASSWORD_FIELD, self.password)
                    page.click(self.LOGIN_BUTTON)

                logger.info("Credentials submitted")

                # Wait for MFA field or successful redirect
                logger.info("Waiting for MFA prompt or redirect...")
                try:
                    page.wait_for_selector(self.MFA_FIELD, timeout=15000)
                    logger.info("MFA required")

                    # Get MFA code from handler
                    mfa_code = self.mfa_handler.get_mfa_code()
                    logger.debug("Received MFA code")

                    # Enter MFA code
                    page.fill(self.MFA_FIELD, mfa_code)
                    page.click(self.MFA_SUBMIT)

                except PlaywrightTimeoutError:
                    logger.info("No MFA prompt detected, continuing")

                # Wait for navigation to complete - back to Hallmark Connect
                logger.info("Waiting for authentication to complete and redirect back...")
                try:
                    page.wait_for_function(
                        f"""() => window.location.href.includes('{self.base_url.replace('https://', '')}')""",
                        timeout=30000
                    )
                except PlaywrightTimeoutError:
                    logger.warning(f"Timeout waiting for redirect back. Current URL: {page.url}")

                page.wait_for_load_state("networkidle", timeout=30000)
                logger.debug(f"Final URL: {page.url}")

                # Extract tokens
                logger.info("Extracting session tokens")
                self._tokens = self._extract_tokens(page)

                if not self._tokens:
                    raise Exception("Failed to extract authentication tokens")

                logger.info("Token extraction successful")

                # Create requests session with cookies
                self._session = self._create_session(page)

                # Save browser session for future use
                if save_session:
                    self._save_browser_state(context)

                logger.info("Authentication completed successfully")
                return True

            finally:
                browser.close()

    def _save_browser_state(self, context: BrowserContext) -> None:
        """Save browser context state to file for session persistence.

        Args:
            context: Playwright browser context to save
        """
        try:
            context.storage_state(path=str(self.session_file))
            logger.info(f"✓ Session saved to {self.session_file}")
            logger.info("  Next run will skip login/MFA!")
        except Exception as e:
            logger.warning(f"Failed to save session state: {e}")

    def _extract_tokens(self, page: Page) -> Optional[Dict[str, str]]:
        """Extract Aura framework tokens from page.

        Args:
            page: Playwright page object

        Returns:
            Dict with token, context, and fwuid, or None if extraction fails
        """
        # Try JavaScript extraction first
        tokens = self._extract_tokens_js(page)
        if tokens:
            return tokens

        # Fallback to regex extraction from page source
        logger.warning("JavaScript extraction failed, trying regex fallback")
        return self._extract_tokens_regex(page)

    def _extract_tokens_js(self, page: Page) -> Optional[Dict[str, str]]:
        """Extract tokens using JavaScript execution.

        Args:
            page: Playwright page object

        Returns:
            Dict with token, context, and fwuid, or None if extraction fails
        """
        try:
            result = page.evaluate("""
                () => {
                    if (window.$A && window.$A.getToken) {
                        return {
                            token: window.$A.getToken(),
                            context: window.$A.getContext() ?
                                window.$A.getContext().encodeForServer() : null,
                            fwuid: window.$A.getContext() ?
                                window.$A.getContext().fwuid : null
                        };
                    }
                    return null;
                }
            """)

            if result and result.get("token"):
                logger.debug("Successfully extracted tokens via JavaScript")
                return {
                    "token": result["token"],
                    "context": result.get("context", ""),
                    "fwuid": result.get("fwuid", "")
                }

        except Exception as e:
            logger.warning(f"JavaScript token extraction failed: {e}")

        return None

    def _extract_tokens_regex(self, page: Page) -> Optional[Dict[str, str]]:
        """Extract tokens using regex patterns from page content.

        Args:
            page: Playwright page object

        Returns:
            Dict with token, context, and fwuid, or None if extraction fails
        """
        try:
            content = page.content()

            token_match = re.search(self.TOKEN_PATTERN, content)
            fwuid_match = re.search(self.FWUID_PATTERN, content)

            if token_match:
                logger.debug("Successfully extracted tokens via regex")
                return {
                    "token": token_match.group(1),
                    "context": "",  # Context harder to extract via regex
                    "fwuid": fwuid_match.group(1) if fwuid_match else ""
                }

        except Exception as e:
            logger.error(f"Regex token extraction failed: {e}")

        return None

    def _create_session(self, page: Page) -> requests.Session:
        """Create requests.Session with cookies from Playwright.

        Args:
            page: Playwright page object

        Returns:
            requests.Session configured with browser cookies
        """
        session = requests.Session()

        # Transfer cookies from Playwright to requests
        cookies = page.context.cookies()
        for cookie in cookies:
            session.cookies.set(
                name=cookie["name"],
                value=cookie["value"],
                domain=cookie.get("domain", ""),
                path=cookie.get("path", "/")
            )

        logger.debug(f"Transferred {len(cookies)} cookies to session")
        return session

    def get_session(self) -> requests.Session:
        """Get authenticated requests session.

        Returns:
            requests.Session: Session with authentication cookies

        Raises:
            RuntimeError: If not authenticated yet
        """
        if not self._session:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        return self._session

    def get_tokens(self) -> Dict[str, str]:
        """Get extracted authentication tokens.

        Returns:
            Dict with token, context, and fwuid

        Raises:
            RuntimeError: If not authenticated yet
        """
        if not self._tokens:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        return self._tokens

    def is_authenticated(self) -> bool:
        """Check if authentication was successful.

        Returns:
            bool: True if authenticated and tokens available
        """
        return self._tokens is not None and self._session is not None

    def clear_saved_session(self) -> None:
        """Delete saved session file."""
        if self.session_file.exists():
            self.session_file.unlink()
            logger.info(f"Deleted saved session: {self.session_file}")
