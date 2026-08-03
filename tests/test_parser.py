from datetime import datetime, timezone
from types import SimpleNamespace

from canpy.parser import CANParser
from canpy.storage import CANFrame


def test_parse_frame_returns_complete_can_frame():
    received_at = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    message = SimpleNamespace(
        timestamp=123.456,
        arbitration_id=0x18FF50E5,
        dlc=4,
        data=bytearray.fromhex("01 02 03 04"),
        is_extended_id=True,
        is_remote_frame=False,
        is_error_frame=True,
    )

    frame = CANParser().parse_frame(message, timestamp_utc=received_at)

    assert isinstance(frame, CANFrame)
    assert frame.timestamp_utc == received_at
    assert frame.source_timestamp == 123.456
    assert frame.can_id == 0x18FF50E5
    assert frame.dlc == 4
    assert frame.data == bytes.fromhex("01 02 03 04")
    assert frame.is_extended is True
    assert frame.is_remote is False
    assert frame.is_error is True
    assert frame.parsed_signals is None
