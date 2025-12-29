"""Playwright-based authentication for Hallmark Connect with session persistence."""

import re
import logging
from pathlib import Path
from typing import Dict, Optional, List, Any
from urllib.parse import urlparse, parse_qs, unquote
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

    # Salesforce session URL parameters to look for
    SF_URL_PARAMS = ['sid', 'oid', 'ssoStartPage', 'startURL', 'RelayState']

    # Salesforce session cookies to look for
    SF_SESSION_COOKIES = [
        'sid', 'sid_Client', 'oid', 'oinfo', 'inst', 'sfdc_lv2',
        'BrowserId', 'BrowserId_sec', 'clientSrc', 'force-stream'
    ]

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
                logger.debug("Launching Chromium browser for saved session...")
                browser = p.chromium.launch(headless=self.headless)
                try:
                    # Create context with saved state
                    logger.debug(f"Loading browser context from saved session: {self.session_file}")
                    context = browser.new_context(storage_state=str(self.session_file))
                    logger.debug("Creating new page...")
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

                except Exception as e:
                    logger.error(f"Error during saved session authentication: {e}", exc_info=True)
                    return False
                finally:
                    logger.debug("Closing browser...")
                    browser.close()

        except Exception as e:
            logger.error(f"Failed to load saved session: {e}", exc_info=True)
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
        logger.info(f"Browser mode: {'headless' if self.headless else 'headed'}")

        with sync_playwright() as p:
            logger.debug("Launching Chromium browser...")
            browser = p.chromium.launch(headless=self.headless)
            try:
                logger.debug("Creating browser context...")
                context = browser.new_context()
                logger.debug("Creating new page...")
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

                # Step 7.5: Save browser session NOW (before token extraction)
                # This allows us to reuse the authenticated session even if token extraction fails
                # The cookies are already authenticated after SAML redirect, so save them immediately
                if save_session:
                    logger.info("Step 7.5: Saving authenticated session (cookies from SAML redirect)...")
                    self._save_browser_state(context)
                    logger.info("  ✓ Session saved - can reuse without MFA if token extraction fails")

                # Step 7.6: Wait for frontdoor.jsp to redirect to /s/, or navigate manually
                # frontdoor.jsp is a redirect handler that should automatically redirect to /s/
                # We wait for this redirect to complete, but if it doesn't happen, we navigate manually
                logger.info("Step 7.6: Waiting for redirect to main app page (/s/)...")
                current_url = page.url
                
                # Check if we're on frontdoor.jsp - if so, wait for automatic redirect
                if "frontdoor.jsp" in current_url or "secur/frontdoor" in current_url:
                    logger.info("  On frontdoor.jsp - waiting for automatic redirect to /s/...")
                    try:
                        # Wait for URL to change away from frontdoor.jsp (should redirect to /s/)
                        page.wait_for_function(
                            """() => {
                                const url = window.location.href;
                                return !url.includes('frontdoor.jsp') && !url.includes('secur/frontdoor');
                            }""",
                            timeout=10000
                        )
                        logger.info(f"  Automatic redirect completed: {page.url}")
                    except PlaywrightTimeoutError:
                        logger.warning("  Automatic redirect timed out, navigating manually...")
                        # If automatic redirect didn't happen, navigate manually
                        app_url = f"{self.base_url}/s/"
                        page.goto(app_url, wait_until="networkidle", timeout=30000)
                        logger.info(f"  Manually navigated to: {page.url}")
                else:
                    # Already on /s/ or another page, just ensure we're on /s/
                    if "/s/" not in current_url:
                        logger.info("  Not on /s/, navigating to main app page...")
                        app_url = f"{self.base_url}/s/"
                        page.goto(app_url, wait_until="networkidle", timeout=30000)
                        logger.info(f"  Navigated to: {page.url}")
                    else:
                        logger.info(f"  Already on /s/: {page.url}")
                
                # Wait for network to settle and Aura to initialize
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except PlaywrightTimeoutError:
                    logger.warning("  Network idle timeout - continuing anyway")
                
                # Give Aura time to fully initialize after networkidle
                page.wait_for_timeout(2000)

                # Step 8: Extract tokens
                logger.info("Step 8: Extracting session tokens...")
                self._tokens = self._extract_tokens(page)

                if not self._tokens:
                    # Token extraction failed, but we have saved session - try using saved session
                    logger.warning("  Token extraction failed, but session is saved.")
                    logger.info("  Attempting to extract tokens using saved session...")
                    browser.close()  # Close current browser
                    
                    # Try using saved session to extract tokens
                    if self.authenticate_with_saved_session():
                        logger.info("  ✓ Successfully extracted tokens using saved session!")
                        return True
                    else:
                        raise Exception("Failed to extract authentication tokens (even with saved session)")

                logger.info("  Token extraction successful")

                # Step 9: Create requests session with cookies
                logger.info("Step 9: Creating requests session with cookies...")
                self._session = self._create_session(page)
                logger.info(f"✓ Created requests session with {len(page.context.cookies())} cookies")

                logger.info("✓ Authentication completed successfully")
                return True

            except Exception as e:
                logger.error(f"Authentication failed with exception: {e}", exc_info=True)
                raise
            finally:
                logger.debug("Closing browser...")
                browser.close()

    def _save_browser_state(self, context: BrowserContext) -> None:
        """Save browser context state to file for session persistence.

        Args:
            context: Playwright browser context to save
        """
        try:
            logger.debug(f"Saving browser state to {self.session_file}")
            context.storage_state(path=str(self.session_file))
            logger.info(f"✓ Session saved to {self.session_file}")
            logger.info("  Next run will skip login/MFA!")
        except Exception as e:
            logger.error(f"Failed to save session state: {e}", exc_info=True)

    def _extract_tokens(self, page: Page) -> Optional[Dict[str, str]]:
        """Extract Aura framework tokens from page using multiple methods.

        Args:
            page: Playwright page object

        Returns:
            Dict with token, context, and fwuid, or None if extraction fails
        """
        # Log comprehensive debug info about the current state
        self._log_extraction_debug_info(page)

        # Method 1: Extract from URL parameters (Salesforce session ID)
        url_tokens = self._extract_tokens_from_url(page)
        if url_tokens:
            logger.info("  ✓ Extracted tokens from URL parameters")
            # URL tokens give us the session ID, but we still need Aura tokens
            # Store the session ID and continue to get Aura tokens

        # Method 2: Try localStorage/sessionStorage (ONLY METHOD THAT WORKS)
        # Based on successful authentication logs, storage extraction is the ONLY reliable method.
        # All JavaScript methods fail in practice, and fallback methods (regex, page source) were
        # never reached in logs since storage extraction always succeeds. They have been removed.
        logger.info("Method 2: Attempting storage extraction (localStorage/sessionStorage)...")
        storage_tokens = self._extract_tokens_from_storage(page)
        if storage_tokens:
            logger.info("  ✓ Storage extraction succeeded")
            if url_tokens:
                storage_tokens['session_id'] = url_tokens.get('session_id', '')
                storage_tokens['org_id'] = url_tokens.get('org_id', '')
            return storage_tokens
        else:
            logger.warning("  ✗ Storage extraction failed - no tokens found in storage")

        # CRITICAL - Do NOT allow empty tokens
        # The Salesforce Aura API requires a valid aura.token field.
        # Empty tokens cause the API to return empty responses (status 200, empty body).
        # We must fail authentication if we cannot extract a token.
        session_id = url_tokens.get('session_id', '') if url_tokens else None
        fwuid = self._extract_fwuid_from_page(page)
        
        if session_id:
            logger.error(
                "  ✗ CRITICAL: Cannot extract Aura token but have session ID. "
                "The API requires a valid aura.token - empty tokens will cause API failures. "
                "Authentication cannot proceed without a valid token."
            )
            logger.error(
                "  Available: session_id={}, fwuid={}, but missing required aura.token".format(
                    session_id[:20] + "..." if session_id and len(session_id) > 20 else session_id,
                    fwuid[:20] + "..." if fwuid and len(fwuid) > 20 else fwuid
                )
            )
        else:
            logger.error("  ✗ CRITICAL: Cannot extract Aura token and no session ID available")

        logger.error("All token extraction methods failed - authentication cannot proceed without Aura token")
        return None

    def _extract_fwuid_from_page(self, page: Page) -> Optional[str]:
        """Extract just the fwuid from page content via regex.

        Args:
            page: Playwright page object

        Returns:
            fwuid string if found, None otherwise
        """
        try:
            content = page.content()

            fwuid_patterns = [
                (r'"fwuid"\s*:\s*"([^"]+)"', "fwuid JSON"),
                (r'fwuid\s*=\s*["\']([^"\']+)["\']', "fwuid assignment"),
                (r'"FWUID"\s*:\s*"([^"]+)"', "FWUID property"),
            ]

            for pattern, name in fwuid_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    fwuid = match.group(1)
                    logger.info(f"    Found fwuid via pattern '{name}': {fwuid}")
                    return fwuid

        except Exception as e:
            logger.debug(f"Error extracting fwuid: {e}")

        return None

    def _log_extraction_debug_info(self, page: Page) -> None:
        """Log comprehensive debug information about the page state for token extraction.

        Args:
            page: Playwright page object
        """
        logger.info("=== Token Extraction Debug Info ===")

        # Log current URL
        current_url = page.url
        logger.info(f"  Current URL: {current_url}")

        # Parse and log URL components
        parsed = urlparse(current_url)
        logger.info(f"  URL Host: {parsed.netloc}")
        logger.info(f"  URL Path: {parsed.path}")

        # Log URL query parameters
        if parsed.query:
            logger.info("  URL Query Parameters:")
            params = parse_qs(parsed.query)
            for key, values in params.items():
                for value in values:
                    # Truncate long values for readability
                    display_value = value[:80] + "..." if len(value) > 80 else value
                    # URL decode for clarity
                    decoded_value = unquote(display_value)
                    logger.info(f"    {key}: {decoded_value}")
                    # Highlight session-related params
                    if key.lower() in ['sid', 'oid', 'sessionid']:
                        logger.info(f"    ^^^ FOUND SESSION PARAMETER: {key} ^^^")
        else:
            logger.info("  URL Query Parameters: (none)")

        # Log all cookies
        try:
            cookies = page.context.cookies()
            logger.info(f"  Cookies ({len(cookies)} total):")
            for cookie in cookies:
                name = cookie.get('name', '')
                value = cookie.get('value', '')[:50]  # Truncate values
                domain = cookie.get('domain', '')
                # Highlight session-related cookies
                is_session = name.lower() in [c.lower() for c in self.SF_SESSION_COOKIES]
                marker = " *** SESSION COOKIE ***" if is_session else ""
                logger.info(f"    {name}: {value}... (domain: {domain}){marker}")
        except Exception as e:
            logger.warning(f"  Error reading cookies: {e}")

        # Check if Aura framework is available
        try:
            aura_available = page.evaluate("() => typeof window.$A !== 'undefined'")
            logger.info(f"  Aura framework available: {aura_available}")
            if aura_available:
                has_token = page.evaluate("() => typeof window.$A.getToken === 'function'")
                logger.info(f"  Aura getToken available: {has_token}")
        except Exception as e:
            logger.warning(f"  Error checking Aura availability: {e}")

        logger.info("=== End Debug Info ===")

    def _extract_tokens_from_url(self, page: Page) -> Optional[Dict[str, str]]:
        """Extract session tokens from URL query parameters.

        Args:
            page: Playwright page object

        Returns:
            Dict with session tokens from URL, or None if not found
        """
        try:
            current_url = page.url
            parsed = urlparse(current_url)
            params = parse_qs(parsed.query)

            tokens = {}

            # Look for session ID (sid)
            if 'sid' in params:
                raw_sid = params['sid'][0]
                decoded_sid = unquote(raw_sid)
                tokens['session_id'] = decoded_sid
                logger.info(f"  Found 'sid' in URL: {decoded_sid[:50]}...")

            # Look for org ID (oid)
            if 'oid' in params:
                raw_oid = params['oid'][0]
                decoded_oid = unquote(raw_oid)
                tokens['org_id'] = decoded_oid
                logger.info(f"  Found 'oid' in URL: {decoded_oid}")

            # Look for other useful params
            for param in self.SF_URL_PARAMS:
                if param in params and param not in ['sid', 'oid']:
                    raw_value = params[param][0]
                    decoded_value = unquote(raw_value)
                    tokens[param] = decoded_value
                    logger.debug(f"  Found '{param}' in URL: {decoded_value[:50]}...")

            if tokens:
                return tokens

        except Exception as e:
            logger.warning(f"Error extracting tokens from URL: {e}")

        return None

    def _extract_tokens_from_storage(self, page: Page) -> Optional[Dict[str, str]]:
        """Extract tokens from localStorage and sessionStorage.
        
        This is the PRIMARY and MOST RELIABLE extraction method based on successful
        authentication logs. The token is typically found in:
        - localStorage['$AuraClientService.token$siteforce:communityApp']
        
        Args:
            page: Playwright page object

        Returns:
            Dict with tokens, or None if not found
        """
        logger.info("  Trying storage extraction method: localStorage/sessionStorage")
        try:
            result = page.evaluate("""
                () => {
                    const tokens = {};
                    
                    // PRIMARY: Check for known working key pattern first (most reliable)
                    // Based on successful auth logs: $AuraClientService.token$siteforce:communityApp
                    const knownPatterns = [
                        '$AuraClientService.token$siteforce:communityApp',
                        '$AuraClientService.token',
                        'aura.token',
                        'auraToken',
                        'sfdc.auraToken'
                    ];
                    
                    // Check localStorage for known patterns first
                    for (const pattern of knownPatterns) {
                        const value = localStorage.getItem(pattern);
                        if (value && value.length > 10) {
                            tokens['localStorage_' + pattern] = value;
                            // Found primary token, can return early if we have it
                        }
                    }
                    
                    // Check sessionStorage for known patterns
                    for (const pattern of knownPatterns) {
                        const value = sessionStorage.getItem(pattern);
                        if (value && value.length > 10) {
                            tokens['sessionStorage_' + pattern] = value;
                        }
                    }
                    
                    // SECONDARY: Check for any key containing 'token' and 'aura' (broader search)
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        if (key && key.toLowerCase().includes('token') && 
                            (key.toLowerCase().includes('aura') || 
                             key.toLowerCase().includes('client'))) {
                            const value = localStorage.getItem(key);
                            if (value && value.length > 10) {
                                tokens['localStorage_' + key] = value;
                            }
                        }
                    }

                    for (let i = 0; i < sessionStorage.length; i++) {
                        const key = sessionStorage.key(i);
                        if (key && key.toLowerCase().includes('token') && 
                            (key.toLowerCase().includes('aura') || 
                             key.toLowerCase().includes('client'))) {
                            const value = sessionStorage.getItem(key);
                            if (value && value.length > 10) {
                                tokens['sessionStorage_' + key] = value;
                            }
                        }
                    }
                    
                    // TERTIARY: Look for fwuid and context
                    const contextKeys = ['fwuid', 'aura.context', 'auraContext'];
                    for (const key of contextKeys) {
                        const value = localStorage.getItem(key);
                        if (value) {
                            tokens['localStorage_' + key] = value;
                        }
                        const sessValue = sessionStorage.getItem(key);
                        if (sessValue) {
                            tokens['sessionStorage_' + key] = sessValue;
                        }
                    }

                    return Object.keys(tokens).length > 0 ? tokens : null;
                }
            """)

            if result:
                logger.info(f"  Found {len(result)} items in browser storage:")
                for key, value in result.items():
                    display_value = str(value)[:50] + "..." if len(str(value)) > 50 else value
                    logger.info(f"    {key}: {display_value}")

                # Try to extract the actual tokens we need
                token = None
                fwuid = None
                context = None

                for key, value in result.items():
                    if 'token' in key.lower() and 'aura' in key.lower():
                        token = value
                    elif 'fwuid' in key.lower():
                        fwuid = value
                    elif 'context' in key.lower() and 'aura' in key.lower():
                        context = value

                if token:
                    logger.info("  ✓ Successfully extracted tokens via: localStorage/sessionStorage")
                    return {
                        'token': token,
                        'context': context or '',
                        'fwuid': fwuid or ''
                    }
                else:
                    logger.warning("  ✗ Storage extraction found items but no valid token")
            else:
                logger.warning("  ✗ Storage extraction found no items in localStorage/sessionStorage")

        except Exception as e:
            logger.warning(f"  ✗ Storage extraction method failed with exception: {e}")

        return None

    def _create_session(self, page: Page) -> requests.Session:
        """Create requests.Session with cookies from Playwright.

        Args:
            page: Playwright page object

        Returns:
            requests.Session configured with browser cookies

        Raises:
            Exception: If cookie transfer fails
        """
        try:
            session = requests.Session()

            # Transfer cookies from Playwright to requests
            cookies = page.context.cookies()
            logger.debug(f"Transferring {len(cookies)} cookies from browser to requests session")
            
            transferred_count = 0
            for cookie in cookies:
                try:
                    session.cookies.set(
                        name=cookie["name"],
                        value=cookie["value"],
                        domain=cookie.get("domain", ""),
                        path=cookie.get("path", "/")
                    )
                    transferred_count += 1
                except Exception as e:
                    logger.warning(f"Failed to transfer cookie '{cookie.get('name', 'unknown')}': {e}")

            logger.info(f"Transferred {transferred_count}/{len(cookies)} cookies to requests session")
            
            # Log session cookie names for debugging
            session_cookie_names = [c.get('name', '') for c in cookies if c.get('name', '').lower() in [sc.lower() for sc in self.SF_SESSION_COOKIES]]
            if session_cookie_names:
                logger.debug(f"Session cookies transferred: {', '.join(session_cookie_names)}")
            
            if transferred_count == 0:
                logger.warning("No cookies transferred - session may not be authenticated")
            
            return session
        except Exception as e:
            logger.error(f"Failed to create requests session: {e}", exc_info=True)
            raise

    def get_session(self) -> requests.Session:
        """Get authenticated requests session.

        Returns:
            requests.Session: Session with authentication cookies

        Raises:
            RuntimeError: If not authenticated yet
        """
        if not self._session:
            logger.error("Attempted to get session but not authenticated")
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        logger.debug("Returning authenticated requests session")
        return self._session

    def get_tokens(self) -> Dict[str, str]:
        """Get extracted authentication tokens.

        Returns:
            Dict with token, context, and fwuid

        Raises:
            RuntimeError: If not authenticated yet
        """
        if not self._tokens:
            logger.error("Attempted to get tokens but not authenticated")
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        logger.debug("Returning authentication tokens")
        return self._tokens

    def is_authenticated(self) -> bool:
        """Check if authentication was successful.

        Returns:
            bool: True if authenticated and tokens available
        """
        authenticated = self._tokens is not None and self._session is not None
        logger.debug(f"Authentication status check: {authenticated}")
        return authenticated

    def clear_saved_session(self) -> None:
        """Delete saved session file."""
        if self.session_file.exists():
            self.session_file.unlink()
            logger.info(f"Deleted saved session: {self.session_file}")
        else:
            logger.debug(f"Saved session file does not exist: {self.session_file}")

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
