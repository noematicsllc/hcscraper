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
    MFA_FIELD = "input[name='code'], input[name='verificationCode'], input[type='text'][placeholder*='code' i], input[name='otp'], input[id='otp-code'], input[id*='otp'], input[id*='code'], input[autocomplete='one-time-code']"
    # Expanded MFA submit selectors for PingOne and other auth providers
    MFA_SUBMIT_SELECTORS = [
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Verify')",
        "button:has-text('Continue')",
        "button:has-text('Submit')",
        "button:has-text('Sign On')",
        "button:has-text('Sign In')",
        "button:has-text('Confirm')",
        "button:has-text('Next')",
        "button[data-id='submit-button']",
        "button.btn-primary",
        "button.primary",
        "form button",
        "[role='button']:has-text('Verify')",
        "[role='button']:has-text('Continue')",
    ]

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

                # Step 1: Navigate to the base URL
                logger.info(f"Step 1: Navigating to {self.base_url}")
                page.goto(self.base_url, wait_until="domcontentloaded", timeout=30000)
                logger.info(f"  Initial URL: {page.url}")

                # Step 2: Wait for any automatic redirects to complete and page to stabilize
                logger.info("Step 2: Waiting for page to stabilize (automatic redirects)...")
                try:
                    # Give page time to process any automatic redirects
                    page.wait_for_load_state("networkidle", timeout=15000)
                except PlaywrightTimeoutError:
                    logger.warning("  Network idle timeout - continuing anyway")

                current_url = page.url
                logger.info(f"  URL after stabilization: {current_url}")

                # Step 3: Determine which page we're on and take appropriate action
                logger.info("Step 3: Checking current page state...")

                is_on_pingone = "pingone.com" in current_url.lower()
                is_on_hallmark = "hallmarkconnect.com" in current_url.lower() or "hallmark" in current_url.lower()
                has_login_field = page.locator(self.USERNAME_FIELD).count() > 0

                logger.info(f"  On PingOne: {is_on_pingone}")
                logger.info(f"  On Hallmark: {is_on_hallmark}")
                logger.info(f"  Login field visible: {has_login_field}")

                if is_on_pingone or has_login_field:
                    # Already redirected to login page - skip button click
                    logger.info("  → Already on login page, skipping Retailer Login button")
                elif is_on_hallmark:
                    # On landing page - need to click Retailer Login button
                    logger.info("  → On landing page, looking for Retailer Login button...")

                    # Try to find the button with aria-label first (more specific)
                    retailer_button = page.locator('[aria-label="Retailer Login"]')
                    if retailer_button.count() > 0:
                        logger.info("  Found button with aria-label='Retailer Login'")
                        retailer_button.click()
                        logger.info("  Clicked Retailer Login button")
                    else:
                        # Fall back to text-based selectors
                        try:
                            page.wait_for_selector(self.RETAILER_LOGIN_BUTTON, timeout=10000)
                            page.click(self.RETAILER_LOGIN_BUTTON)
                            logger.info("  Clicked Retailer Login button (fallback selector)")
                        except PlaywrightTimeoutError:
                            logger.warning("  Retailer Login button not found - checking for redirects...")
                else:
                    logger.warning(f"  Unknown page state. URL: {current_url}")

                # Step 4: Wait for PingOne login page
                logger.info("Step 4: Waiting for PingOne login page...")
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
                    logger.info(f"  Now on login page: {page.url}")
                except PlaywrightTimeoutError:
                    logger.warning(f"  Timeout waiting for login page. Current URL: {page.url}")

                # Wait for page to stabilize before entering credentials
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except PlaywrightTimeoutError:
                    logger.warning("  Network idle timeout - continuing anyway")

                # Step 5: Wait for and fill username field
                logger.info("Step 5: Entering credentials...")
                logger.info(f"  Current URL: {page.url}")
                page.wait_for_selector(self.USERNAME_FIELD, timeout=15000)
                logger.info("  Found username field, entering username")
                page.fill(self.USERNAME_FIELD, self.username)

                # Check if password field is on the same page or separate
                password_visible = page.locator(self.PASSWORD_FIELD).is_visible()
                if password_visible:
                    # Both fields on same page
                    logger.info("  Password field visible, entering password")
                    page.fill(self.PASSWORD_FIELD, self.password)
                    page.click(self.LOGIN_BUTTON)
                    logger.info("  Clicked login button")
                else:
                    # Username-first flow: submit username, then enter password
                    logger.info("  Username-first flow detected, submitting username first")
                    page.click(self.LOGIN_BUTTON)
                    logger.info("  Waiting for password field...")
                    page.wait_for_selector(self.PASSWORD_FIELD, timeout=15000)
                    logger.info("  Found password field, entering password")
                    page.fill(self.PASSWORD_FIELD, self.password)
                    page.click(self.LOGIN_BUTTON)
                    logger.info("  Clicked login button")

                logger.info("  Credentials submitted successfully")

                # Step 6: Handle MFA if required
                logger.info("Step 6: Checking for MFA prompt...")
                logger.info(f"  Current URL: {page.url}")
                try:
                    page.wait_for_selector(self.MFA_FIELD, timeout=15000)
                    logger.info("  MFA field detected - MFA required")

                    # Log what MFA-related elements are visible on the page
                    self._log_mfa_page_elements(page)

                    # Get MFA code from handler
                    mfa_code = self.mfa_handler.get_mfa_code()
                    logger.info(f"  Received MFA code ({len(mfa_code)} characters), entering...")

                    # Enter MFA code
                    mfa_input = page.locator(self.MFA_FIELD).first
                    mfa_input.fill(mfa_code)
                    logger.info("  MFA code entered into field")

                    # Small delay to ensure code is registered
                    page.wait_for_timeout(500)

                    # Find and click the MFA submit button
                    submit_clicked = self._click_mfa_submit_button(page)
                    if not submit_clicked:
                        logger.warning("  Could not find MFA submit button - trying Enter key")
                        mfa_input.press("Enter")
                        logger.info("  Pressed Enter key to submit MFA form")

                    # Wait for the MFA form to process and redirect
                    logger.info("  Waiting for MFA verification and redirect...")
                    try:
                        # Wait for URL to change away from current (PingOne) URL
                        current_url = page.url
                        page.wait_for_function(
                            f"""() => window.location.href !== '{current_url}'""",
                            timeout=30000
                        )
                        logger.info(f"  MFA verified! Redirected to: {page.url}")
                    except PlaywrightTimeoutError:
                        logger.warning(f"  Timeout waiting for post-MFA redirect. Current URL: {page.url}")
                        # Log page state for debugging
                        self._log_mfa_page_elements(page)

                except PlaywrightTimeoutError:
                    logger.info("  No MFA prompt detected, continuing...")

                # Step 7: Wait for redirect back to Hallmark Connect
                logger.info("Step 7: Waiting for redirect back to Hallmark Connect...")
                try:
                    page.wait_for_function(
                        f"""() => window.location.href.includes('{self.base_url.replace('https://', '')}')""",
                        timeout=30000
                    )
                    logger.info(f"  Redirected back to: {page.url}")
                except PlaywrightTimeoutError:
                    logger.warning(f"  Timeout waiting for redirect. Current URL: {page.url}")

                try:
                    page.wait_for_load_state("networkidle", timeout=30000)
                except PlaywrightTimeoutError:
                    logger.warning("  Network idle timeout - continuing anyway")
                logger.info(f"  Final URL: {page.url}")

                # Step 8: Extract tokens
                logger.info("Step 8: Extracting session tokens...")
                self._tokens = self._extract_tokens(page)

                if not self._tokens:
                    raise Exception("Failed to extract authentication tokens")

                logger.info("  Token extraction successful")

                # Step 9: Create requests session with cookies
                logger.info("Step 9: Creating requests session with cookies...")
                self._session = self._create_session(page)

                # Save browser session for future use
                if save_session:
                    self._save_browser_state(context)

                logger.info("✓ Authentication completed successfully")
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

    def _log_mfa_page_elements(self, page: Page) -> None:
        """Log MFA-related elements visible on the page for debugging.

        Args:
            page: Playwright page object
        """
        logger.info("  === MFA Page Element Analysis ===")

        # Log all buttons on the page
        try:
            buttons = page.locator("button").all()
            logger.info(f"  Found {len(buttons)} button elements:")
            for i, btn in enumerate(buttons[:10]):  # Limit to first 10
                try:
                    text = btn.inner_text().strip()[:50] if btn.is_visible() else "(hidden)"
                    btn_type = btn.get_attribute("type") or "no-type"
                    btn_class = btn.get_attribute("class") or "no-class"
                    logger.info(f"    [{i}] text='{text}' type='{btn_type}' class='{btn_class[:50]}'")
                except Exception:
                    logger.info(f"    [{i}] (could not read button)")
        except Exception as e:
            logger.warning(f"  Error reading buttons: {e}")

        # Log all input[type=submit] elements
        try:
            submits = page.locator("input[type='submit']").all()
            logger.info(f"  Found {len(submits)} input[type=submit] elements:")
            for i, sub in enumerate(submits[:5]):
                try:
                    value = sub.get_attribute("value") or "no-value"
                    logger.info(f"    [{i}] value='{value}'")
                except Exception:
                    logger.info(f"    [{i}] (could not read submit input)")
        except Exception as e:
            logger.warning(f"  Error reading submit inputs: {e}")

        # Log forms on the page
        try:
            forms = page.locator("form").all()
            logger.info(f"  Found {len(forms)} form elements:")
            for i, form in enumerate(forms[:5]):
                try:
                    action = form.get_attribute("action") or "no-action"
                    method = form.get_attribute("method") or "no-method"
                    logger.info(f"    [{i}] action='{action[:50]}' method='{method}'")
                except Exception:
                    logger.info(f"    [{i}] (could not read form)")
        except Exception as e:
            logger.warning(f"  Error reading forms: {e}")

        # Log MFA input field details
        try:
            mfa_inputs = page.locator(self.MFA_FIELD).all()
            logger.info(f"  Found {len(mfa_inputs)} MFA input field(s):")
            for i, inp in enumerate(mfa_inputs[:3]):
                try:
                    name = inp.get_attribute("name") or "no-name"
                    inp_id = inp.get_attribute("id") or "no-id"
                    inp_type = inp.get_attribute("type") or "no-type"
                    placeholder = inp.get_attribute("placeholder") or "no-placeholder"
                    logger.info(f"    [{i}] name='{name}' id='{inp_id}' type='{inp_type}' placeholder='{placeholder}'")
                except Exception:
                    logger.info(f"    [{i}] (could not read input)")
        except Exception as e:
            logger.warning(f"  Error reading MFA inputs: {e}")

        logger.info("  === End MFA Page Analysis ===")

    def _click_mfa_submit_button(self, page: Page) -> bool:
        """Find and click the MFA submit button.

        Args:
            page: Playwright page object

        Returns:
            bool: True if a button was found and clicked, False otherwise
        """
        logger.info("  Searching for MFA submit button...")

        for selector in self.MFA_SUBMIT_SELECTORS:
            try:
                locator = page.locator(selector)
                count = locator.count()
                if count > 0:
                    # Find the first visible button matching this selector
                    for i in range(count):
                        btn = locator.nth(i)
                        if btn.is_visible():
                            text = ""
                            try:
                                text = btn.inner_text().strip()[:30]
                            except Exception:
                                pass
                            logger.info(f"    Found visible button with selector '{selector}': '{text}'")
                            btn.click()
                            logger.info(f"  ✓ Clicked MFA submit button: '{text}' (selector: {selector})")
                            return True
            except Exception as e:
                logger.debug(f"    Selector '{selector}' failed: {e}")
                continue

        logger.warning("  No MFA submit button found with any selector")
        return False
