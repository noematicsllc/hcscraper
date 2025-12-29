"""Centralized date parsing utilities."""

from datetime import datetime
from typing import Optional, Tuple, Any
import logging

logger = logging.getLogger(__name__)


def parse_date_string(date_str: str) -> Optional[datetime]:
    """Parse date string in various formats.
    
    Args:
        date_str: Date string (MM/DD/YYYY, YYYY-MM-DD, ISO format, etc.)
        
    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None
    
    try:
        # Try MM/DD/YYYY format first
        if '/' in date_str and len(date_str.split('/')) == 3:
            return datetime.strptime(date_str, '%m/%d/%Y')
        # Try ISO format
        elif 'T' in date_str:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        # Try YYYY-MM-DD
        else:
            return datetime.strptime(date_str[:10], '%Y-%m-%d')
    except (ValueError, AttributeError) as e:
        logger.debug(f"Failed to parse date string '{date_str}': {e}")
        return None


def parse_date_value(value: Any) -> Optional[datetime]:
    """Parse date from various value types.
    
    Args:
        value: Can be string, int (timestamp), float (timestamp), datetime, or None
        
    Returns:
        datetime object or None if parsing fails
    """
    if value is None:
        return None
    
    # If already a datetime, return as-is
    if isinstance(value, datetime):
        return value
    
    # Try parsing as string
    if isinstance(value, str):
        return parse_date_string(value)
    
    # Try parsing as timestamp
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value)
        except (ValueError, OSError) as e:
            logger.debug(f"Failed to parse timestamp {value}: {e}")
            return None
    
    return None


def extract_year_month(date_value: Any) -> Tuple[str, str]:
    """Extract year and month from date value.
    
    Args:
        date_value: Date string, datetime, timestamp, or None
        
    Returns:
        Tuple of (year, month) as strings (e.g., ("2025", "01"))
        Falls back to current date if parsing fails
    """
    date_obj = parse_date_value(date_value)
    
    if date_obj:
        return date_obj.strftime('%Y'), date_obj.strftime('%m')
    
    # Fallback to current date
    now = datetime.now()
    return now.strftime('%Y'), now.strftime('%m')

