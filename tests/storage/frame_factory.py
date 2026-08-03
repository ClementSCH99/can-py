"""Concise frame factory for storage tests focused on repository behavior."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from canpy.storage.frame import CANFrame


def make_frame(
    timestamp: float,
    can_id: int,
    dlc: int,
    data: bytes,
    parsed_signals: Optional[Dict[str, Any]] = None,
    *,
    is_extended: bool = False,
    is_remote: bool = False,
    is_error: bool = False,
) -> CANFrame:
    """Build a complete frame on a simple Unix-UTC test timeline."""
    return CANFrame(
        timestamp_utc=datetime.fromtimestamp(timestamp, tz=timezone.utc),
        source_timestamp=timestamp,
        can_id=can_id,
        dlc=dlc,
        data=data,
        is_extended=is_extended,
        is_remote=is_remote,
        is_error=is_error,
        parsed_signals=parsed_signals,
    )
