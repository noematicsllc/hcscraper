"""Hallmark Connect API client with retry logic and rate limiting."""

import time
import logging
from typing import Dict, Any, Optional
import requests

from .request_builder import AuraRequestBuilder


logger = logging.getLogger(__name__)


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
        max_retries: int = 3
    ):
        """Initialize API client.

        Args:
            session: Authenticated requests session
            aura_token: Aura authentication token
            aura_context: Aura context (encoded)
            fwuid: Framework unique identifier
            base_url: Base URL for Hallmark Connect
            rate_limit_seconds: Seconds to wait between requests (default: 2.5)
            max_retries: Maximum retry attempts (default: 3)
        """
        self.session = session
        self.base_url = base_url
        self.rate_limit_seconds = rate_limit_seconds
        self.max_retries = max_retries
        self.last_request_time: Optional[float] = None

        # Create request builder
        self.request_builder = AuraRequestBuilder(
            base_url=base_url,
            aura_token=aura_token,
            aura_context=aura_context,
            fwuid=fwuid
        )

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

    def _execute_request(
        self,
        url: str,
        headers: Dict[str, str],
        data: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """Execute HTTP request with retry logic and rate limiting.

        Args:
            url: Request URL
            headers: Request headers
            data: Form data

        Returns:
            Response JSON data, or None if request fails
        """
        # Apply rate limiting
        self._apply_rate_limit()

        # Retry loop
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Request attempt {attempt + 1}/{self.max_retries}: POST {url}")

                response = self.session.post(
                    url=url,
                    headers=headers,
                    data=data,
                    timeout=30
                )

                # Update last request time
                self.last_request_time = time.time()

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
                logger.warning(f"Request timeout, attempt {attempt + 1}/{self.max_retries}")
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

    def _apply_rate_limit(self) -> None:
        """Apply rate limiting by waiting if necessary.

        Ensures minimum delay between requests to avoid overwhelming the server.
        """
        if self.last_request_time is None:
            return

        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_seconds:
            wait_time = self.rate_limit_seconds - elapsed
            logger.debug(f"Rate limiting: waiting {wait_time:.2f} seconds")
            time.sleep(wait_time)
