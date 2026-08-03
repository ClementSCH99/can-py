# src/canpy/storage/frame.py

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class CANFrame:
    """Standardized CAN frame representation."""
    timestamp_utc: datetime
    source_timestamp: float
    can_id: int
    dlc: int
    data: bytes
    is_extended: bool
    is_remote: bool
    is_error: bool
    parsed_signals: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        """Reject timestamps that do not satisfy the explicit UTC contract."""
        if self.timestamp_utc.utcoffset() is None:
            raise ValueError("timestamp_utc must be timezone-aware")
        if self.timestamp_utc.utcoffset() != timedelta(0):
            raise ValueError("timestamp_utc must use UTC")

    @property
    def timestamp(self) -> float:
        """Legacy UTC Unix value used by the existing repository API."""
        return self.timestamp_utc.timestamp()
