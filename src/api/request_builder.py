"""Salesforce Aura API request builder."""

import json
from typing import Dict, Any, Optional, List, Union
from urllib.parse import urlencode


class AuraRequestBuilder:
    """Builds properly formatted requests for Salesforce Aura framework API."""

    def __init__(self, base_url: str, aura_token: str, aura_context: str, fwuid: str):
        """Initialize request builder.

        Args:
            base_url: Base URL for Hallmark Connect
            aura_token: Aura authentication token (can be empty if using session auth)
            aura_context: Aura context (encoded, can be empty)
            fwuid: Framework unique identifier (can be empty)
        """
        self.base_url = base_url.rstrip('/')
        self.aura_token = aura_token or ''  # Empty string is OK for session-based auth
        self.aura_context = aura_context or ''
        self.fwuid = fwuid or ''
        self.request_counter = 81  # Initial request number

    def build_order_detail_request(self, order_id: str) -> Dict[str, Any]:
        """Build request for order detail retrieval.

        Args:
            order_id: The order ID to retrieve

        Returns:
            Dict with 'url', 'headers', and 'data' for the request
        """
        # Build action payload
        action_payload = {
            "actions": [{
                "id": "761;a",
                "descriptor": "aura://ApexActionController/ACTION$execute",
                "callingDescriptor": "UNKNOWN",
                "params": {
                    "namespace": "",
                    "classname": "Portal_OrderDetailController",
                    "method": "getOrderDetailSAPSearchResult",
                    "params": {
                        "pageSize": -1,
                        "pageNumber": -1,
                        "searchSort": json.dumps([{
                            "columnName": "materialNumber",
                            "sortorder": "asc",
                            "priority": 1
                        }]),
                        "orderId": order_id,
                        "cacheable": False,
                        "isContinuation": False
                    }
                }
            }]
        }

        return self._build_request(
            message=action_payload,
            page_uri=f"/s/orderdetail?orderId={order_id}"
        )

    def build_billing_document_detail_request(self, billing_document_id: str) -> Dict[str, Any]:
        """Build request for billing document detail retrieval.

        Args:
            billing_document_id: The billing document ID to retrieve

        Returns:
            Dict with 'url', 'headers', and 'data' for the request
        """
        # Build action payload following the same pattern as orders
        action_payload = {
            "actions": [{
                "id": "761;a",
                "descriptor": "aura://ApexActionController/ACTION$execute",
                "callingDescriptor": "UNKNOWN",
                "params": {
                    "namespace": "",
                    "classname": "Portal_BillingDocumentDetailController",
                    "method": "getBillingDocumentDetailSAPSearchResult",
                    "params": {
                        "pageSize": -1,
                        "pageNumber": -1,
                        "searchSort": json.dumps([
                            {"columnName": "wholesales", "sortorder": "Desc", "priority": 1},
                            {"columnName": "materialDescription", "sortorder": "asc", "priority": 2},
                            {"columnName": "pricePerWholesaleUnit", "sortorder": "Desc", "priority": 3}
                        ]),
                        "invoiceId": billing_document_id,
                        "cacheable": False,
                        "isContinuation": False
                    }
                }
            }]
        }

        return self._build_request(
            message=action_payload,
            page_uri=f"/s/billingdocumentdetail?billingDocumentId={billing_document_id}"
        )

    def build_delivery_detail_request(self, delivery_id: str) -> Dict[str, Any]:
        """Build request for delivery detail retrieval.

        Args:
            delivery_id: The delivery ID to retrieve

        Returns:
            Dict with 'url', 'headers', and 'data' for the request
        """
        # Build action payload following the same pattern as orders/billing
        action_payload = {
            "actions": [{
                "id": "761;a",
                "descriptor": "aura://ApexActionController/ACTION$execute",
                "callingDescriptor": "UNKNOWN",
                "params": {
                    "namespace": "",
                    "classname": "Portal_DeliveryDetailController",
                    "method": "getDeliveryDetailSAPSearchResult",
                    "params": {
                        "pageSize": -1,
                        "pageNumber": -1,
                        "searchSort": json.dumps([
                            {"columnName": "cartonNumber", "sortorder": "asc", "priority": 1},
                            {"columnName": "serialCartonContainerCode", "sortorder": "Desc", "priority": 2},
                            {"columnName": "cartonValue", "sortorder": "Desc", "priority": 3}
                        ]),
                        "deliveryId": delivery_id,
                        "cacheable": False,
                        "isContinuation": False
                    }
                }
            }]
        }

        return self._build_request(
            message=action_payload,
            page_uri=f"/s/deliverydetail?deliveryId={delivery_id}"
        )

    def _build_request(self, message: Dict[str, Any], page_uri: str) -> Dict[str, Any]:
        """Build generic Aura API request.

        Args:
            message: The action message payload
            page_uri: The page URI for the request

        Returns:
            Dict with 'url', 'headers', and 'data'
        """
        # Build URL with query parameters
        url_params = {
            'r': self.request_counter,
            'aura.ApexAction.execute': 1
        }
        url = f"{self.base_url}/s/sfsites/aura?{urlencode(url_params)}"

        # Increment request counter for next call
        self.request_counter += 1

        # Build headers
        headers = {
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
            'Host': self.base_url.replace('https://', '').replace('http://', ''),
            'Origin': self.base_url,
            'Referer': f"{self.base_url}{page_uri}",
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:145.0) Gecko/20100101 Firefox/145.0'
        }

        # Build form data
        # Use the aura.context if we have it, otherwise build a minimal one
        if self.aura_context:
            context = self.aura_context
        else:
            # Minimal context structure
            context = json.dumps({
                "mode": "PROD",
                "fwuid": self.fwuid,
                "app": "siteforce:communityApp",
                "loaded": {
                    "APPLICATION@markup://siteforce:communityApp": "1419_b1bLMAu5pI9zwW1jkVMf-w"
                },
                "dn": [],
                "globals": {},
                "uad": True
            })

        form_data = {
            'message': json.dumps(message),
            'aura.context': context,
            'aura.pageURI': page_uri,
            'aura.token': self.aura_token
        }

        return {
            'url': url,
            'headers': headers,
            'data': form_data
        }

    def build_generic_action(
        self,
        classname: str,
        method: str,
        params: Dict[str, Any],
        page_uri: str = "/s/"
    ) -> Dict[str, Any]:
        """Build a generic Aura action request.

        Args:
            classname: The Apex controller class name
            method: The method name to call
            params: Method parameters
            page_uri: The page URI (default: /s/)

        Returns:
            Dict with 'url', 'headers', and 'data'
        """
        action_payload = {
            "actions": [{
                "id": "761;a",
                "descriptor": "aura://ApexActionController/ACTION$execute",
                "callingDescriptor": "UNKNOWN",
                "params": {
                    "namespace": "",
                    "classname": classname,
                    "method": method,
                    "params": params
                }
            }]
        }

        return self._build_request(message=action_payload, page_uri=page_uri)

    def build_order_search_request(
        self,
        customer_ids: Union[List[str], str],
        start_date: str,
        end_date: str,
        page_size: int = 50,
        page_number: int = 1
    ) -> Dict[str, Any]:
        """Build request for order search.

        Args:
            customer_ids: List of customer IDs or comma-separated string
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            page_size: Number of results per page (default: 50)
            page_number: Page number to retrieve (default: 1)

        Returns:
            Dict with 'url', 'headers', and 'data' for the request
        """
        # Convert list to comma-separated string if necessary
        if isinstance(customer_ids, list):
            customer_ids_str = ",".join(customer_ids)
        else:
            customer_ids_str = customer_ids

        # Build search filters JSON
        search_filters = json.dumps({
            "customerIds": customer_ids_str,
            "customerSearchType": "combobox",
            "orderCreationStartDate": start_date,
            "orderCreationEndDate": end_date
        })

        # Build search sort JSON
        search_sort = json.dumps([
            {"columnName": "storeName", "sortorder": "asc", "priority": 1},
            {"columnName": "orderCreationDate", "sortorder": "Desc", "priority": 2},
            {"columnName": "orderId", "sortorder": "Desc", "priority": 3}
        ])

        # Build action payload
        action_payload = {
            "actions": [{
                "id": "761;a",
                "descriptor": "aura://ApexActionController/ACTION$execute",
                "callingDescriptor": "UNKNOWN",
                "params": {
                    "namespace": "",
                    "classname": "Portal_OrderController",
                    "method": "getOrderSAPSearchResult",
                    "params": {
                        "pageSize": page_size,
                        "pageNumber": page_number,
                        "searchFilters": search_filters,
                        "searchSort": search_sort,
                        "searchType": "Orders"
                    }
                }
            }]
        }

        return self._build_request(
            message=action_payload,
            page_uri="/s/orders"
        )

    def build_search_filter_request(
        self,
        customer_ids: Union[List[str], str],
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """Build request to construct search filter for download.

        Args:
            customer_ids: List of customer IDs or comma-separated string
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            Dict with 'url', 'headers', and 'data' for the request
        """
        # Convert list to comma-separated string if necessary
        if isinstance(customer_ids, list):
            customer_ids_str = ",".join(customer_ids)
        else:
            customer_ids_str = customer_ids

        # Build search filters JSON
        search_filters = json.dumps({
            "customerIds": customer_ids_str,
            "customerSearchType": "combobox",
            "orderCreationStartDate": start_date,
            "orderCreationEndDate": end_date
        })

        # Build action payload
        action_payload = {
            "actions": [{
                "id": "761;a",
                "descriptor": "aura://ApexActionController/ACTION$execute",
                "callingDescriptor": "UNKNOWN",
                "params": {
                    "namespace": "",
                    "classname": "Portal_OrderController",
                    "method": "constructSearchFilterRequest",
                    "params": {
                        "searchFilters": search_filters
                    }
                }
            }]
        }

        return self._build_request(
            message=action_payload,
            page_uri="/s/orders"
        )
