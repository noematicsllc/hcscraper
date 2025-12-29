"""Hallmark Connect API client with retry logic and rate limiting."""

import json
import os
import time
import random
import logging
from pathlib import Path
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
    # HTTP status codes that indicate session expiration
    SESSION_EXPIRED_CODES = {401, 403}

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
        on_break_callback: Optional[Callable[[int, float], None]] = None,
        # Session refresh callback
        on_session_expired: Optional[Callable[[], bool]] = None
    ):
        """Initialize API client.

        Args:
            session: Authenticated requests session (with sid cookie for auth)
            aura_token: Aura authentication token (REQUIRED - cannot be empty)
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
        self.on_session_expired = on_session_expired
        self._session_refresh_attempted = False

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
            logger.warning("API client initialized without Aura token - this may cause API failures")

        # Create request builder
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
        parsed_data = self._parse_aura_response(response_data, order_id)
        
        # If parsing failed, save raw response for debugging
        if parsed_data is None:
            self._save_raw_response_for_debugging(
                entity_type="order",
                entity_id=order_id,
                raw_response=response_data,
                request_spec=request_spec
            )
            logger.debug(f"Response structure for order {order_id}: {list(response_data.keys()) if isinstance(response_data, dict) else type(response_data)}")
        
        return parsed_data

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
        parsed_data = self._parse_aura_response(response_data, billing_document_id)
        
        # If parsing failed, save raw response for debugging
        if parsed_data is None:
            self._save_raw_response_for_debugging(
                entity_type="billing_document",
                entity_id=billing_document_id,
                raw_response=response_data,
                request_spec=request_spec
            )
        
        return parsed_data

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
        parsed_data = self._parse_aura_response(response_data, delivery_id)
        
        # If parsing failed, save raw response for debugging
        if parsed_data is None:
            self._save_raw_response_for_debugging(
                entity_type="delivery",
                entity_id=delivery_id,
                raw_response=response_data,
                request_spec=request_spec
            )
        
        return parsed_data

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

        # Debug: Log response structure for troubleshooting
        logger.debug(f"Search response structure: {list(response_data.keys()) if isinstance(response_data, dict) else type(response_data)}")
        if isinstance(response_data, dict) and 'actions' in response_data:
            actions = response_data.get('actions', [])
            if actions and isinstance(actions[0], dict):
                action = actions[0]
                return_value = action.get('returnValue')
                if return_value:
                    logger.debug(f"Search returnValue keys: {list(return_value.keys()) if isinstance(return_value, dict) else type(return_value)}")
                    # Log if we see orderRecords or records
                    if isinstance(return_value, dict):
                        if 'orderRecords' in return_value:
                            logger.debug(f"Found orderRecords with {len(return_value.get('orderRecords', []))} items")
                        if 'records' in return_value:
                            logger.debug(f"Found records with {len(return_value.get('records', []))} items")
                        if 'totalRecords' in return_value:
                            logger.debug(f"totalRecords: {return_value.get('totalRecords')}")
                        if 'totalCount' in return_value:
                            logger.debug(f"totalCount: {return_value.get('totalCount')}")
                        # Log nested result if it exists
                        if 'result' in return_value:
                            nested = return_value.get('result')
                            logger.debug(f"returnValue.result type: {type(nested)}")
                            if isinstance(nested, dict):
                                logger.debug(f"returnValue.result keys: {list(nested.keys())}")
                            elif isinstance(nested, list):
                                logger.debug(f"returnValue.result is a list with {len(nested)} items")

        # Parse Aura response
        parsed = self._parse_aura_response(response_data, f"search_page_{page_number}")
        
        # If parsing returned something but it has no orders, save raw response for debugging
        if parsed and isinstance(parsed, dict):
            has_orders = False
            if 'orderRecords' in parsed or 'records' in parsed:
                has_orders = True
            elif 'result' in parsed and isinstance(parsed['result'], (dict, list)):
                nested = parsed['result']
                if isinstance(nested, list):
                    has_orders = len(nested) > 0
                elif isinstance(nested, dict):
                    has_orders = 'orderRecords' in nested or 'records' in nested
            
            if not has_orders:
                logger.debug(f"Saving raw search response for debugging (no orders found)")
                self._save_raw_response_for_debugging(
                    entity_type="search",
                    entity_id=f"search_{start_date}_{end_date}_page_{page_number}",
                    raw_response=response_data,
                    request_spec=request_spec
                )
        
        return parsed

    def search_billing_documents(
        self,
        customer_ids: Union[List[str], str],
        start_date: str,
        end_date: str,
        page_size: int = 50,
        page_number: int = 1,
        billing_status: str = "All"
    ) -> Optional[Dict[str, Any]]:
        """Search for billing documents matching criteria.

        Args:
            customer_ids: List of customer IDs or comma-separated string
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            page_size: Number of results per page (default: 50)
            page_number: Page number to retrieve (default: 1)
            billing_status: Billing status filter (default: "All")

        Returns:
            Dict containing search results, or None if request fails
        """
        logger.info(f"Searching billing documents from {start_date} to {end_date}, page {page_number}")

        # Build request
        request_spec = self.request_builder.build_billing_document_search_request(
            customer_ids=customer_ids,
            start_date=start_date,
            end_date=end_date,
            page_size=page_size,
            page_number=page_number,
            billing_status=billing_status
        )

        # Execute with retry logic (search requests use longer timeout)
        response_data = self._execute_request(
            url=request_spec['url'],
            headers=request_spec['headers'],
            data=request_spec['data'],
            request_type=RequestType.SEARCH
        )

        if response_data is None:
            logger.error(f"Failed to search billing documents for page {page_number}")
            return None

        # Debug: Log response structure for troubleshooting
        logger.debug(f"Search response structure: {list(response_data.keys()) if isinstance(response_data, dict) else type(response_data)}")
        if isinstance(response_data, dict) and 'actions' in response_data:
            actions = response_data.get('actions', [])
            if actions and isinstance(actions[0], dict):
                action = actions[0]
                return_value = action.get('returnValue')
                if return_value:
                    logger.debug(f"Search returnValue keys: {list(return_value.keys()) if isinstance(return_value, dict) else type(return_value)}")
                    # Log if we see billing document records
                    if isinstance(return_value, dict):
                        if 'billingDocumentRecords' in return_value:
                            logger.debug(f"Found billingDocumentRecords with {len(return_value.get('billingDocumentRecords', []))} items")
                        if 'records' in return_value:
                            logger.debug(f"Found records with {len(return_value.get('records', []))} items")
                        if 'totalRecords' in return_value:
                            logger.debug(f"totalRecords: {return_value.get('totalRecords')}")
                        if 'totalCount' in return_value:
                            logger.debug(f"totalCount: {return_value.get('totalCount')}")
                        # Log nested result if it exists
                        if 'result' in return_value:
                            nested = return_value.get('result')
                            logger.debug(f"returnValue.result type: {type(nested)}")
                            if isinstance(nested, dict):
                                logger.debug(f"returnValue.result keys: {list(nested.keys())}")
                            elif isinstance(nested, list):
                                logger.debug(f"returnValue.result is a list with {len(nested)} items")

        # Parse Aura response
        parsed = self._parse_aura_response(response_data, f"search_billing_documents_page_{page_number}")
        
        # If parsing returned something but it has no billing documents, save raw response for debugging
        if parsed and isinstance(parsed, dict):
            has_billing_documents = False
            if 'billingDocumentRecords' in parsed or 'records' in parsed:
                has_billing_documents = True
            elif 'result' in parsed and isinstance(parsed['result'], (dict, list)):
                nested = parsed['result']
                if isinstance(nested, list):
                    has_billing_documents = len(nested) > 0
                elif isinstance(nested, dict):
                    has_billing_documents = 'billingDocumentRecords' in nested or 'records' in nested
            
            if not has_billing_documents:
                logger.debug(f"Saving raw search response for debugging (no billing documents found)")
                self._save_raw_response_for_debugging(
                    entity_type="search",
                    entity_id=f"search_billing_documents_{start_date}_{end_date}_page_{page_number}",
                    raw_response=response_data,
                    request_spec=request_spec
                )
        
        return parsed

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
                    # Check if response has content before trying to parse JSON
                    if not response.content or len(response.content) == 0:
                        logger.error(f"Empty response body (status 200)")
                        logger.debug(f"Response headers: {dict(response.headers)}")
                        if attempt < self.max_retries - 1:
                            time.sleep(2 ** attempt)
                            continue
                        return None
                    
                    try:
                        result = response.json()
                        logger.debug(f"Request successful (200 OK)")
                        return result
                    except requests.exceptions.JSONDecodeError as json_error:
                        logger.error(f"Invalid JSON in response: {json_error}")
                        logger.debug(f"Response content (first 500 chars): {response.text[:500]}")
                        if attempt < self.max_retries - 1:
                            time.sleep(2 ** attempt)
                            continue
                        return None

                elif response.status_code in self.SESSION_EXPIRED_CODES:
                    # Session expired - try to refresh session
                    logger.warning(
                        f"Session expired (status {response.status_code}), "
                        f"attempt {attempt + 1}/{self.max_retries}"
                    )
                    
                    # Check if response indicates login redirect
                    response_text = response.text.lower()
                    is_login_redirect = (
                        '/login' in response.url.lower() or
                        'login' in response_text[:500] or
                        'authentication' in response_text[:500] or
                        'unauthorized' in response_text[:500]
                    )
                    
                    if is_login_redirect or response.status_code == 401:
                        # Try to refresh session if callback provided and not already attempted
                        if self.on_session_expired and not self._session_refresh_attempted:
                            logger.info("Attempting to refresh session...")
                            self._session_refresh_attempted = True
                            if self.on_session_expired():
                                logger.info("Session refreshed successfully, retrying request")
                                self._session_refresh_attempted = False
                                continue
                            else:
                                logger.error("Session refresh failed")
                                # Don't retry if refresh failed
                                return None
                        elif self._session_refresh_attempted:
                            logger.error("Session refresh already attempted, giving up")
                            return None
                        else:
                            logger.error("No session refresh callback available")
                            return None
                    
                    # For 403, might be permission issue rather than session expiry
                    if response.status_code == 403:
                        logger.error(f"Access forbidden (403): {response.text[:200]}")
                        if attempt < self.max_retries - 1:
                            backoff_time = 2 ** attempt
                            logger.debug(f"Backing off for {backoff_time} seconds")
                            time.sleep(backoff_time)
                            continue
                        return None

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
                # Log request details for debugging
                logger.debug(f"Request URL: {url}")
                logger.debug(f"Request headers: {headers}")
                logger.debug(f"Request data keys: {list(data.keys())}")
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

        # Check if response has 'actions' array (standard Aura response)
        actions = response_data.get('actions', [])
        if actions:
            # Get first action (should only be one for our requests)
            action = actions[0]
            state = action.get('state')

            if state == 'SUCCESS':
                logger.debug(f"Action successful for order {order_id}")
                return_value = action.get('returnValue')
                
                # Validate that returnValue is not None or empty
                if return_value is None:
                    logger.warning(f"Empty returnValue (None) for order {order_id}")
                    return None
                
                if isinstance(return_value, dict) and len(return_value) == 0:
                    logger.warning(f"Empty returnValue (empty dict) for order {order_id}")
                    return None
                
                # Check if returnValue contains nested returnValue (some API responses wrap it)
                # This happens when the response structure is: {returnValue: {returnValue: {...actual data...}, cacheable: true}}
                if isinstance(return_value, dict) and 'returnValue' in return_value:
                    nested = return_value.get('returnValue')
                    # If nested has expected structure (orderHeader/billingDocumentHeader), use it
                    if isinstance(nested, dict) and ('orderHeader' in nested or 'billingDocumentHeader' in nested):
                        logger.debug(f"Using nested returnValue with expected structure for order {order_id}")
                        return nested
                    # If outer has cacheable but nested doesn't, nested is likely the actual data
                    elif isinstance(nested, dict) and 'cacheable' in return_value and 'cacheable' not in nested:
                        logger.debug(f"Unwrapping nested returnValue (outer has cacheable) for order {order_id}")
                        return nested
                    # If nested exists and is a dict, prefer it over outer wrapper
                    elif isinstance(nested, dict):
                        logger.debug(f"Using nested returnValue for order {order_id}")
                        return nested
                
                return return_value

            elif state == 'ERROR':
                errors = action.get('error', [])
                error_messages = [err.get('message', 'Unknown error') for err in errors]
                logger.error(f"Action failed for order {order_id}: {', '.join(error_messages)}")
                return None

            else:
                logger.error(f"Unknown action state '{state}' for order {order_id}")
                return None
        
        # Handle alternative response structure where returnValue is at top level
        # This can happen if the API response structure is different
        if 'returnValue' in response_data:
            logger.debug(f"Found returnValue at top level for order {order_id}")
            return_value = response_data.get('returnValue')
            
            # Check if returnValue is itself a dict that might contain nested returnValue
            # (some API responses wrap returnValue in another returnValue)
            if isinstance(return_value, dict):
                # If returnValue contains nested 'returnValue' key, check if we should unwrap it
                if 'returnValue' in return_value:
                    nested = return_value.get('returnValue')
                    # If nested has expected structure (orderHeader/billingDocumentHeader), use it
                    if isinstance(nested, dict) and ('orderHeader' in nested or 'billingDocumentHeader' in nested):
                        logger.debug(f"Using nested returnValue with expected structure for order {order_id}")
                        return nested
                    # If nested doesn't have cacheable (meaning it's the actual data), use it
                    elif isinstance(nested, dict) and 'cacheable' not in nested:
                        logger.debug(f"Unwrapping nested returnValue for order {order_id}")
                        return nested
                # If returnValue contains 'orderHeader' or other expected keys directly, use it
                elif 'orderHeader' in return_value or 'billingDocumentHeader' in return_value:
                    logger.debug(f"returnValue contains expected structure for order {order_id}")
                    return return_value
            
            # Validate that returnValue is not None or empty
            if return_value is None:
                logger.warning(f"Empty returnValue (None) at top level for order {order_id}")
                return None
            
            if isinstance(return_value, dict) and len(return_value) == 0:
                logger.warning(f"Empty returnValue (empty dict) at top level for order {order_id}")
                return None
            
            return return_value
        
        else:
            # Log the actual structure for debugging
            logger.error(
                f"Unexpected response structure for order {order_id}. "
                f"Expected 'actions' array or 'returnValue' at top level. "
                f"Available keys: {list(response_data.keys())}"
            )
            logger.debug(f"Full response structure (first 1000 chars): {str(response_data)[:1000]}")
            return None

    def _save_raw_response_for_debugging(
        self,
        entity_type: str,
        entity_id: str,
        raw_response: Dict[str, Any],
        request_spec: Dict[str, Any]
    ) -> None:
        """Save raw API response to debug directory for inspection.
        
        This ensures we have the actual response structure when parsing fails,
        eliminating the need to guess about the structure.
        
        Args:
            entity_type: Type of entity (order, billing_document, delivery)
            entity_id: The entity ID
            raw_response: The raw response JSON from the API
            request_spec: The request specification (url, headers, data)
        """
        try:
            # Get debug directory from environment or use default
            debug_dir = Path(os.getenv('DEBUG_DIRECTORY', './debug_responses'))
            debug_dir.mkdir(parents=True, exist_ok=True)
            
            # Create filename with timestamp and entity info
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{entity_type}_{entity_id}_{timestamp}_raw_response.json"
            filepath = debug_dir / filename
            
            # Prepare debug data with full context
            debug_data = {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "timestamp": timestamp,
                "request": {
                    "url": request_spec.get('url'),
                    "headers": request_spec.get('headers', {}),
                    "data_keys": list(request_spec.get('data', {}).keys()) if isinstance(request_spec.get('data'), dict) else None
                },
                "raw_response": raw_response,
                "response_structure": {
                    "top_level_keys": list(raw_response.keys()) if isinstance(raw_response, dict) else None,
                    "has_actions": isinstance(raw_response, dict) and 'actions' in raw_response,
                    "has_returnValue": isinstance(raw_response, dict) and 'returnValue' in raw_response,
                    "actions_count": len(raw_response.get('actions', [])) if isinstance(raw_response, dict) else 0
                }
            }
            
            # Save to file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(debug_data, f, indent=2, ensure_ascii=False)
            
            logger.warning(
                f"Saved raw API response for {entity_type} {entity_id} to {filepath} "
                f"for debugging. Inspect this file to understand the actual response structure."
            )
            
        except Exception as e:
            logger.error(f"Failed to save raw response for debugging: {e}")

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
