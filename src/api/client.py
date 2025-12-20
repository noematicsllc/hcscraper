"""Hallmark Connect API client with retry logic and rate limiting."""

import time
import random
import logging
from typing import Dict, Any, Optional, List, Union, Callable
import requests

from .request_builder import AuraRequestBuilder


logger = logging.getLogger(__name__)


class RequestType:
    """Constants for request types."""
    DETAIL = "detail"
    SEARCH = "search"


class HallmarkAPIClient:
    """API client for Hallmark Connect with Aura framework support."""

    # HTTP status codes that should trigger retry
    RETRY_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        session: requests.Session,
        aura_token: str,
        aura_context: str,
        fwuid: str,
        base_url: str = "https://services.hallmarkconnect.com",
        rate_limit_seconds: float = 2.5,
        max_retries: int = 3,
        # Timeout settings
        request_timeout_seconds: float = 30,
        search_timeout_seconds: float = 120,
        # Rate limiting settings
        rate_limit_detail_seconds: Optional[float] = None,
        rate_limit_search_seconds: float = 5.0,
        rate_limit_jitter_seconds: float = 0.5,
        # Break settings
        break_after_requests: int = 25,
        break_after_jitter: int = 5,
        break_duration_seconds: float = 60,
        break_jitter_seconds: float = 15,
        # Conservative mode
        conservative_mode: bool = False,
        # Callbacks
        on_break_callback: Optional[Callable[[int, float], None]] = None
    ):
        """Initialize API client.

        Args:
            session: Authenticated requests session (with sid cookie for auth)
            aura_token: Aura authentication token (can be empty if using session auth)
            aura_context: Aura context (encoded, can be empty)
            fwuid: Framework unique identifier (can be empty)
            base_url: Base URL for Hallmark Connect
            rate_limit_seconds: Legacy - seconds to wait between requests (default: 2.5)
            max_retries: Maximum retry attempts (default: 3)
            request_timeout_seconds: Timeout for detail requests (default: 30)
            search_timeout_seconds: Timeout for search requests (default: 120)
            rate_limit_detail_seconds: Delay between detail requests (default: rate_limit_seconds)
            rate_limit_search_seconds: Delay between search requests (default: 5.0)
            rate_limit_jitter_seconds: Random jitter for rate limits (default: 0.5)
            break_after_requests: Number of requests before taking a break (default: 25)
            break_after_jitter: Randomize break interval (default: 5)
            break_duration_seconds: Base break duration (default: 60)
            break_jitter_seconds: Randomize break duration (default: 15)
            conservative_mode: Double delays and halve requests between breaks (default: False)
            on_break_callback: Called when taking a break (request_count, break_duration)
        """
        self.session = session
        self.base_url = base_url
        self.max_retries = max_retries
        self.last_request_time: Optional[float] = None
        self.on_break_callback = on_break_callback

        # Apply conservative mode multipliers
        conservative_multiplier = 2.0 if conservative_mode else 1.0
        break_request_divisor = 2 if conservative_mode else 1

        # Timeout settings
        self.request_timeout = request_timeout_seconds
        self.search_timeout = search_timeout_seconds

        # Rate limiting settings (with conservative mode applied)
        self.rate_limit_detail = (rate_limit_detail_seconds or rate_limit_seconds) * conservative_multiplier
        self.rate_limit_search = rate_limit_search_seconds * conservative_multiplier
        self.rate_limit_jitter = rate_limit_jitter_seconds * conservative_multiplier

        # Break settings (with conservative mode applied)
        self.break_after_requests = max(1, break_after_requests // break_request_divisor)
        self.break_after_jitter = max(0, break_after_jitter // break_request_divisor)
        self.break_duration = break_duration_seconds * conservative_multiplier
        self.break_jitter = break_jitter_seconds * conservative_multiplier

        # Request tracking for breaks
        self.request_count = 0
        self.next_break_at = self._calculate_next_break()

        # Log configuration
        if conservative_mode:
            logger.info("Conservative mode ACTIVE - delays doubled, breaks more frequent")
        logger.debug(
            f"Rate limiting: detail={self.rate_limit_detail:.1f}s, search={self.rate_limit_search:.1f}s, "
            f"jitter=±{self.rate_limit_jitter:.1f}s"
        )
        logger.debug(
            f"Breaks: every ~{self.break_after_requests}±{self.break_after_jitter} requests, "
            f"duration ~{self.break_duration:.0f}±{self.break_jitter:.0f}s"
        )

        # Log authentication mode
        if aura_token:
            logger.debug("API client initialized with Aura token authentication")
        else:
            logger.info("API client using session-based authentication (no Aura token)")

        # Create request builder (handles empty tokens gracefully)
        self.request_builder = AuraRequestBuilder(
            base_url=base_url,
            aura_token=aura_token or '',
            aura_context=aura_context or '',
            fwuid=fwuid or ''
        )

    def _calculate_next_break(self) -> int:
        """Calculate the request count at which to take the next break."""
        jitter = random.randint(-self.break_after_jitter, self.break_after_jitter)
        return self.request_count + self.break_after_requests + jitter

    def _check_and_take_break(self) -> None:
        """Check if it's time for a break and take one if needed."""
        if self.request_count >= self.next_break_at:
            # Calculate break duration with jitter
            jitter = random.uniform(-self.break_jitter, self.break_jitter)
            break_duration = max(1, self.break_duration + jitter)

            logger.info(f"Taking a break ({break_duration:.0f}s)... processed {self.request_count} requests so far")

            # Call the callback if provided
            if self.on_break_callback:
                self.on_break_callback(self.request_count, break_duration)

            time.sleep(break_duration)

            # Reset for next break
            self.next_break_at = self._calculate_next_break()
            logger.debug(f"Break complete. Next break at ~{self.next_break_at} requests")

    def get_order_detail(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve order detail from Hallmark Connect.

        Args:
            order_id: The order ID to retrieve

        Returns:
            Dict containing order data, or None if request fails

        Raises:
            requests.RequestException: If all retry attempts fail
        """
        logger.info(f"Retrieving order detail for order {order_id}")

        # Build request
        request_spec = self.request_builder.build_order_detail_request(order_id)

        # Execute with retry logic
        response_data = self._execute_request(
            url=request_spec['url'],
            headers=request_spec['headers'],
            data=request_spec['data']
        )

        if response_data is None:
            logger.error(f"Failed to retrieve order {order_id}")
            return None

        # Parse Aura response
        return self._parse_aura_response(response_data, order_id)

    def get_billing_document_detail(self, billing_document_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve billing document detail from Hallmark Connect.

        Args:
            billing_document_id: The billing document ID to retrieve

        Returns:
            Dict containing billing document data, or None if request fails

        Raises:
            requests.RequestException: If all retry attempts fail
        """
        logger.info(f"Retrieving billing document detail for {billing_document_id}")

        # Build request
        request_spec = self.request_builder.build_billing_document_detail_request(billing_document_id)

        # Execute with retry logic
        response_data = self._execute_request(
            url=request_spec['url'],
            headers=request_spec['headers'],
            data=request_spec['data']
        )

        if response_data is None:
            logger.error(f"Failed to retrieve billing document {billing_document_id}")
            return None

        # Parse Aura response
        return self._parse_aura_response(response_data, billing_document_id)

    def get_delivery_detail(self, delivery_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve delivery detail from Hallmark Connect.

        Args:
            delivery_id: The delivery ID to retrieve

        Returns:
            Dict containing delivery data, or None if request fails

        Raises:
            requests.RequestException: If all retry attempts fail
        """
        logger.info(f"Retrieving delivery detail for {delivery_id}")

        # Build request
        request_spec = self.request_builder.build_delivery_detail_request(delivery_id)

        # Execute with retry logic
        response_data = self._execute_request(
            url=request_spec['url'],
            headers=request_spec['headers'],
            data=request_spec['data']
        )

        if response_data is None:
            logger.error(f"Failed to retrieve delivery {delivery_id}")
            return None

        # Parse Aura response
        return self._parse_aura_response(response_data, delivery_id)

    def search_orders(
        self,
        customer_ids: Union[List[str], str],
        start_date: str,
        end_date: str,
        page_size: int = 50,
        page_number: int = 1
    ) -> Optional[Dict[str, Any]]:
        """Search for orders matching criteria.

        Args:
            customer_ids: List of customer IDs or comma-separated string
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            page_size: Number of results per page (default: 50)
            page_number: Page number to retrieve (default: 1)

        Returns:
            Dict containing search results, or None if request fails
        """
        logger.info(f"Searching orders from {start_date} to {end_date}, page {page_number}")

        # Build request
        request_spec = self.request_builder.build_order_search_request(
            customer_ids=customer_ids,
            start_date=start_date,
            end_date=end_date,
            page_size=page_size,
            page_number=page_number
        )

        # Execute with retry logic (search requests use longer timeout)
        response_data = self._execute_request(
            url=request_spec['url'],
            headers=request_spec['headers'],
            data=request_spec['data'],
            request_type=RequestType.SEARCH
        )

        if response_data is None:
            logger.error(f"Failed to search orders for page {page_number}")
            return None

        # Parse Aura response
        return self._parse_aura_response(response_data, f"search_page_{page_number}")

    def construct_search_filter_request(
        self,
        customer_ids: Union[List[str], str],
        start_date: str,
        end_date: str
    ) -> Optional[Dict[str, Any]]:
        """Construct search filter request for download.

        Args:
            customer_ids: List of customer IDs or comma-separated string
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            Dict containing filter request data, or None if request fails
        """
        logger.info(f"Constructing search filter request for {start_date} to {end_date}")

        # Build request
        request_spec = self.request_builder.build_search_filter_request(
            customer_ids=customer_ids,
            start_date=start_date,
            end_date=end_date
        )

        # Execute with retry logic (search requests use longer timeout)
        response_data = self._execute_request(
            url=request_spec['url'],
            headers=request_spec['headers'],
            data=request_spec['data'],
            request_type=RequestType.SEARCH
        )

        if response_data is None:
            logger.error("Failed to construct search filter request")
            return None

        # Parse Aura response
        return self._parse_aura_response(response_data, "search_filter_request")

    def _execute_request(
        self,
        url: str,
        headers: Dict[str, str],
        data: Dict[str, str],
        request_type: str = RequestType.DETAIL
    ) -> Optional[Dict[str, Any]]:
        """Execute HTTP request with retry logic and rate limiting.

        Args:
            url: Request URL
            headers: Request headers
            data: Form data
            request_type: Type of request (RequestType.DETAIL or RequestType.SEARCH)

        Returns:
            Response JSON data, or None if request fails
        """
        # Check if we need a break before this request
        self._check_and_take_break()

        # Apply rate limiting with appropriate delay for request type
        self._apply_rate_limit(request_type)

        # Select timeout based on request type
        timeout = self.search_timeout if request_type == RequestType.SEARCH else self.request_timeout

        # Retry loop
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Request attempt {attempt + 1}/{self.max_retries}: POST {url}")

                response = self.session.post(
                    url=url,
                    headers=headers,
                    data=data,
                    timeout=timeout
                )

                # Update last request time and increment count
                self.last_request_time = time.time()
                self.request_count += 1

                # Check for HTTP errors
                if response.status_code == 200:
                    logger.debug(f"Request successful (200 OK)")
                    return response.json()

                elif response.status_code in self.RETRY_STATUS_CODES:
                    # Retryable error
                    logger.warning(
                        f"Request failed with status {response.status_code}, "
                        f"attempt {attempt + 1}/{self.max_retries}"
                    )

                    # Special handling for rate limiting (429)
                    if response.status_code == 429:
                        retry_after = response.headers.get('Retry-After', 60)
                        try:
                            wait_time = int(retry_after)
                        except (ValueError, TypeError):
                            wait_time = 60

                        logger.warning(f"Rate limited. Waiting {wait_time} seconds")
                        time.sleep(wait_time)
                        continue

                    # Exponential backoff for other errors
                    if attempt < self.max_retries - 1:
                        backoff_time = 2 ** attempt  # 1, 2, 4 seconds
                        logger.debug(f"Backing off for {backoff_time} seconds")
                        time.sleep(backoff_time)
                        continue

                else:
                    # Non-retryable error
                    logger.error(f"Request failed with status {response.status_code}: {response.text[:200]}")
                    response.raise_for_status()

            except requests.Timeout:
                logger.warning(f"Request timeout ({timeout}s), attempt {attempt + 1}/{self.max_retries}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                else:
                    logger.error("Request timed out after all retries")
                    return None

            except requests.RequestException as e:
                logger.error(f"Request failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                else:
                    raise

        logger.error("All retry attempts exhausted")
        return None

    def _parse_aura_response(
        self,
        response_data: Dict[str, Any],
        order_id: str
    ) -> Optional[Dict[str, Any]]:
        """Parse Aura framework API response.

        Args:
            response_data: Raw response JSON
            order_id: Order ID (for logging)

        Returns:
            Extracted return value, or None if response indicates error
        """
        if not isinstance(response_data, dict):
            logger.error(f"Invalid response format for order {order_id}")
            return None

        # Aura responses have an 'actions' array
        actions = response_data.get('actions', [])
        if not actions:
            logger.error(f"No actions in response for order {order_id}")
            return None

        # Get first action (should only be one for our requests)
        action = actions[0]
        state = action.get('state')

        if state == 'SUCCESS':
            logger.debug(f"Action successful for order {order_id}")
            return action.get('returnValue')

        elif state == 'ERROR':
            errors = action.get('error', [])
            error_messages = [err.get('message', 'Unknown error') for err in errors]
            logger.error(f"Action failed for order {order_id}: {', '.join(error_messages)}")
            return None

        else:
            logger.error(f"Unknown action state '{state}' for order {order_id}")
            return None

    def _apply_rate_limit(self, request_type: str = RequestType.DETAIL) -> None:
        """Apply rate limiting by waiting if necessary.

        Ensures minimum delay between requests with random jitter to look more human.

        Args:
            request_type: Type of request to determine appropriate delay
        """
        if self.last_request_time is None:
            return

        # Select base delay based on request type
        base_delay = self.rate_limit_search if request_type == RequestType.SEARCH else self.rate_limit_detail

        # Add random jitter to make timing look more human
        jitter = random.uniform(0, self.rate_limit_jitter)
        target_delay = base_delay + jitter

        elapsed = time.time() - self.last_request_time
        if elapsed < target_delay:
            wait_time = target_delay - elapsed
            logger.debug(f"Rate limiting ({request_type}): waiting {wait_time:.2f}s (base: {base_delay:.1f}s + jitter: {jitter:.2f}s)")
            time.sleep(wait_time)
