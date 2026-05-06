# src/canpy/storage/frame.py

from dataclasses import dataclass
from typing import Any, List, Optional, Dict

@dataclass(frozen=True)
class CANFrame:
    """Standardized CAN frame representation."""
    timestamp: float        # Unix timestamp (seconds)
    can_id: int            # 11-bit or 29-bit CAN ID
    dlc: int               # Data Length Code (0-8)
    data: bytes            # Raw data bytes (0-8 bytes)
    parsed_signals: Optional[Dict[str, Any]] = None  # Decoded signal values