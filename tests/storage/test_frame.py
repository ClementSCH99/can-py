"""Tests for CANFrame dataclass"""

from datetime import datetime, timezone

import pytest
from dataclasses import FrozenInstanceError
from canpy.storage.frame import CANFrame

TIMESTAMP_UTC = datetime(
    2026, 8, 3, 12, 0, 0,
    tzinfo=timezone.utc,
)

class TestCANFrameBasics:
    """Test basic CANFrame creation and field access."""
    
    def test_can_frame_creation(self):
        """Verify CANFrame can be created with required fields."""
        frame = CANFrame(
            timestamp_utc=TIMESTAMP_UTC,
            source_timestamp=1.0,
            can_id=0x123,
            dlc=8,
            data=b'12345678',
            is_extended=False,
            is_remote=False,
            is_error=False
        )
        assert frame.timestamp_utc is not None
        assert frame.source_timestamp == 1.0
        assert frame.can_id == 0x123
        assert frame.dlc == 8
        assert frame.data == b'12345678'
        assert frame.is_extended is False
        assert frame.is_remote is False
        assert frame.is_error is False
        assert frame.parsed_signals is None
    
    def test_can_frame_with_signals(self):
        """Verify CANFrame accepts optional parsed_signals."""
        signals = {'Voltage': 48.5, 'Temperature': 65.2}
        frame = CANFrame(
            timestamp_utc=TIMESTAMP_UTC,
            source_timestamp=1.0,
            can_id=0x123,
            dlc=8,
            is_extended=False,
            is_remote=False,
            is_error=False,
            data=b'12345678',
            parsed_signals=signals
        )
        assert frame.parsed_signals == signals
    
    def test_can_frame_requires_timestamp(self):
        """Verify timestamps are required."""
        with pytest.raises(TypeError):
            CANFrame(can_id=0x123, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False)

    def test_can_frame_requires_can_id(self):
        """Verify can_id is required."""
        with pytest.raises(TypeError):
            CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False)
    
    def test_can_frame_requires_dlc(self):
        """Verify dlc is required."""
        with pytest.raises(TypeError):
            CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x123, data=b'12345678', is_extended=False, is_remote=False, is_error=False)
    
    def test_can_frame_requires_data(self):
        """Verify data is required."""
        with pytest.raises(TypeError):
            CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x123, dlc=8, is_extended=False, is_remote=False, is_error=False)

    def test_can_frame_requires_flags(self):
        """Verify is_extended, is_remote, and is_error are required."""
        with pytest.raises(TypeError):
            CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678')

    def test_can_frame_rejects_naive_utc_timestamp(self):
        """Verify UTC timestamp cannot silently omit timezone information."""
        with pytest.raises(ValueError, match="timezone-aware"):
            CANFrame(
                timestamp_utc=datetime(2026, 8, 3, 12, 0, 0),
                source_timestamp=1.0,
                can_id=0x123,
                dlc=8,
                data=b'12345678',
                is_extended=False,
                is_remote=False,
                is_error=False,
            )


class TestCANFrameImmutability:
    """Test that CANFrame is frozen (immutable)."""
    
    def test_cannot_modify_timestamp_utc(self):
        """Verify timestamp_utc cannot be modified after creation."""
        frame = CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False)
        with pytest.raises(FrozenInstanceError):
            frame.timestamp_utc = TIMESTAMP_UTC.replace(year=2025)

    def test_cannot_modify_source_timestamp(self):
        """Verify source_timestamp cannot be modified after creation."""
        frame = CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False)
        with pytest.raises(FrozenInstanceError):
            frame.source_timestamp = 2.0
    
    def test_cannot_modify_can_id(self):
        """Verify can_id cannot be modified after creation."""
        frame = CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False)
        with pytest.raises(FrozenInstanceError):
            frame.can_id = 0x456
    
    def test_cannot_modify_dlc(self):
        """Verify dlc cannot be modified after creation."""
        frame = CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False)
        with pytest.raises(FrozenInstanceError):
            frame.dlc = 4
    
    def test_cannot_modify_data(self):
        """Verify data cannot be modified after creation."""
        frame = CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False)
        with pytest.raises(FrozenInstanceError):
            frame.data = b'87654321'

    def test_cannot_modify_flags(self):
        """Verify is_extended, is_remote, and is_error cannot be modified after creation."""
        frame = CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False)
        with pytest.raises(FrozenInstanceError):
            frame.is_extended = True
        with pytest.raises(FrozenInstanceError):
            frame.is_remote = True
        with pytest.raises(FrozenInstanceError):
            frame.is_error = True
    
    def test_cannot_modify_parsed_signals(self):
        """Verify parsed_signals cannot be modified after creation."""
        frame = CANFrame(
            timestamp_utc=TIMESTAMP_UTC,
            source_timestamp=1.0,
            can_id=0x123,
            dlc=8,
            data=b'12345678',
            is_extended=False, is_remote=False, is_error=False,
            parsed_signals={'Voltage': 48.5}
        )
        with pytest.raises(FrozenInstanceError):
            frame.parsed_signals = {'Voltage': 50.0}
    
    def test_cannot_add_new_fields(self):
        """Verify new fields cannot be added to frozen frame."""
        frame = CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False)
        with pytest.raises(FrozenInstanceError):
            frame.new_field = "should fail"


class TestCANFrameEquality:
    """Test CANFrame equality (frozen dataclasses are hashable)."""
    
    def test_identical_frames_are_equal(self):
        """Verify frames with same data are equal."""
        frame1 = CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False)
        frame2 = CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False)
        assert frame1 == frame2
    
    def test_different_frames_are_not_equal(self):
        """Verify frames with different data are not equal."""
        frame1 = CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False)
        frame2 = CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=2.0, can_id=0x123, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False)
        assert frame1 != frame2
    
    def test_can_frame_is_hashable(self):
        """Verify frozen frames are hashable (can use in sets/dicts)."""
        frame = CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False)
        # Should not raise
        frame_set = {frame}
        assert frame in frame_set
    
    def test_frames_with_signals_equal(self):
        """Verify equality considers parsed_signals."""
        signals1 = {'Voltage': 48.5}
        signals2 = {'Voltage': 48.5}
        frame1 = CANFrame(
            timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False,
            parsed_signals=signals1
        )
        frame2 = CANFrame(
            timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False,
            parsed_signals=signals2
        )
        assert frame1 == frame2


class TestCANFrameEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_empty_data(self):
        """Verify CANFrame can have empty data."""
        frame = CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x123, dlc=0, data=b'', is_extended=False, is_remote=False, is_error=False)
        assert frame.dlc == 0
        assert frame.data == b''
    
    def test_max_standard_can_id(self):
        """Verify 11-bit CAN ID boundary (0x7FF)."""
        frame = CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x7FF, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False)
        assert frame.can_id == 0x7FF
    
    def test_extended_can_id(self):
        """Verify 29-bit CAN ID support."""
        frame = CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x1FFFFFFF, dlc=8, data=b'12345678', is_extended=True, is_remote=False, is_error=False)
        assert frame.can_id == 0x1FFFFFFF
    
    def test_zero_timestamp(self):
        """Verify timestamp can be zero."""
        frame = CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=0.0, can_id=0x123, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False)
        assert frame.source_timestamp == 0.0
    
    def test_negative_timestamp_allowed(self):
        """Verify negative timestamp is structurally allowed (validation in layer above)."""
        frame = CANFrame(timestamp_utc=TIMESTAMP_UTC, source_timestamp=-1.0, can_id=0x123, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False)
        assert frame.source_timestamp == -1.0
    
    def test_empty_parsed_signals_dict(self):
        """Verify empty parsed_signals dict is allowed."""
        frame = CANFrame(
            timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678', is_extended=False, is_remote=False, is_error=False,
            parsed_signals={}
        )
        assert frame.parsed_signals == {}
    
    def test_large_data_payload(self):
        """Verify CANFrame handles larger data (CAN FD)."""
        large_data = bytes(range(256))  # 256 bytes
        frame = CANFrame(
            timestamp_utc=TIMESTAMP_UTC, source_timestamp=1.0, can_id=0x123, dlc=64, data=large_data, is_extended=False, is_remote=False, is_error=False
        )
        assert len(frame.data) == 256
