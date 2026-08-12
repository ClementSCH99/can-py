"""Reusable frames for compact-format candidate round-trip tests."""

from datetime import datetime, timezone
from typing import List

from canpy.storage import CANFrame


def sample_contract_frames() -> List[CANFrame]:
    """Cover standard, extended, remote, error, and decoded-frame fields."""
    return [
        CANFrame(
            timestamp_utc=datetime(
                2026, 8, 3, 12, 0, 0, 1000, tzinfo=timezone.utc
            ),
            source_timestamp=100.001,
            can_id=0x123,
            dlc=4,
            data=bytes.fromhex("01 02 03 04"),
            is_extended=False,
            is_remote=False,
            is_error=False,
            parsed_signals={"Voltage": 48.5},
        ),
        CANFrame(
            timestamp_utc=datetime(
                2026, 8, 3, 12, 0, 0, 2000, tzinfo=timezone.utc
            ),
            source_timestamp=100.002,
            can_id=0x18FF50E5,
            dlc=0,
            data=b"",
            is_extended=True,
            is_remote=True,
            is_error=False,
            parsed_signals=None,
        ),
        CANFrame(
            timestamp_utc=datetime(
                2026, 8, 3, 12, 0, 0, 3000, tzinfo=timezone.utc
            ),
            source_timestamp=100.003,
            can_id=0x0,
            dlc=0,
            data=b"",
            is_extended=False,
            is_remote=False,
            is_error=True,
            parsed_signals=None,
        ),
    ]
