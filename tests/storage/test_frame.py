"""Tests for CANFrame dataclass"""

import pytest
from dataclasses import FrozenInstanceError
from canpy.storage.frame import CANFrame

class TestCANFrameBasics:
    """Test basic CANFrame creation and field access."""
    
    def test_can_frame_creation(self):
        """Verify CANFrame can be created with required fields."""
        frame = CANFrame(
            timestamp=1.0,
            can_id=0x123,
            dlc=8,
            data=b'12345678'
        )
        assert frame.timestamp == 1.0
        assert frame.can_id == 0x123
        assert frame.dlc == 8
        assert frame.data == b'12345678'
        assert frame.parsed_signals is None
    
    def test_can_frame_with_signals(self):
        """Verify CANFrame accepts optional parsed_signals."""
        signals = {'Voltage': 48.5, 'Temperature': 65.2}
        frame = CANFrame(
            timestamp=1.0,
            can_id=0x123,
            dlc=8,
            data=b'12345678',
            parsed_signals=signals
        )
        assert frame.parsed_signals == signals
    
    def test_can_frame_requires_timestamp(self):
        """Verify timestamp is required."""
        with pytest.raises(TypeError):
            CANFrame(can_id=0x123, dlc=8, data=b'12345678')
    
    def test_can_frame_requires_can_id(self):
        """Verify can_id is required."""
        with pytest.raises(TypeError):
            CANFrame(timestamp=1.0, dlc=8, data=b'12345678')
    
    def test_can_frame_requires_dlc(self):
        """Verify dlc is required."""
        with pytest.raises(TypeError):
            CANFrame(timestamp=1.0, can_id=0x123, data=b'12345678')
    
    def test_can_frame_requires_data(self):
        """Verify data is required."""
        with pytest.raises(TypeError):
            CANFrame(timestamp=1.0, can_id=0x123, dlc=8)


class TestCANFrameImmutability:
    """Test that CANFrame is frozen (immutable)."""
    
    def test_cannot_modify_timestamp(self):
        """Verify timestamp cannot be modified after creation."""
        frame = CANFrame(timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678')
        with pytest.raises(FrozenInstanceError):
            frame.timestamp = 2.0
    
    def test_cannot_modify_can_id(self):
        """Verify can_id cannot be modified after creation."""
        frame = CANFrame(timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678')
        with pytest.raises(FrozenInstanceError):
            frame.can_id = 0x456
    
    def test_cannot_modify_dlc(self):
        """Verify dlc cannot be modified after creation."""
        frame = CANFrame(timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678')
        with pytest.raises(FrozenInstanceError):
            frame.dlc = 4
    
    def test_cannot_modify_data(self):
        """Verify data cannot be modified after creation."""
        frame = CANFrame(timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678')
        with pytest.raises(FrozenInstanceError):
            frame.data = b'87654321'
    
    def test_cannot_modify_parsed_signals(self):
        """Verify parsed_signals cannot be modified after creation."""
        frame = CANFrame(
            timestamp=1.0,
            can_id=0x123,
            dlc=8,
            data=b'12345678',
            parsed_signals={'Voltage': 48.5}
        )
        with pytest.raises(FrozenInstanceError):
            frame.parsed_signals = {'Voltage': 50.0}
    
    def test_cannot_add_new_fields(self):
        """Verify new fields cannot be added to frozen frame."""
        frame = CANFrame(timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678')
        with pytest.raises(FrozenInstanceError):
            frame.new_field = "should fail"


class TestCANFrameEquality:
    """Test CANFrame equality (frozen dataclasses are hashable)."""
    
    def test_identical_frames_are_equal(self):
        """Verify frames with same data are equal."""
        frame1 = CANFrame(timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678')
        frame2 = CANFrame(timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678')
        assert frame1 == frame2
    
    def test_different_frames_are_not_equal(self):
        """Verify frames with different data are not equal."""
        frame1 = CANFrame(timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678')
        frame2 = CANFrame(timestamp=2.0, can_id=0x123, dlc=8, data=b'12345678')
        assert frame1 != frame2
    
    def test_can_frame_is_hashable(self):
        """Verify frozen frames are hashable (can use in sets/dicts)."""
        frame = CANFrame(timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678')
        # Should not raise
        frame_set = {frame}
        assert frame in frame_set
    
    def test_frames_with_signals_equal(self):
        """Verify equality considers parsed_signals."""
        signals1 = {'Voltage': 48.5}
        signals2 = {'Voltage': 48.5}
        frame1 = CANFrame(
            timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678',
            parsed_signals=signals1
        )
        frame2 = CANFrame(
            timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678',
            parsed_signals=signals2
        )
        assert frame1 == frame2


class TestCANFrameEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_empty_data(self):
        """Verify CANFrame can have empty data."""
        frame = CANFrame(timestamp=1.0, can_id=0x123, dlc=0, data=b'')
        assert frame.dlc == 0
        assert frame.data == b''
    
    def test_max_standard_can_id(self):
        """Verify 11-bit CAN ID boundary (0x7FF)."""
        frame = CANFrame(timestamp=1.0, can_id=0x7FF, dlc=8, data=b'12345678')
        assert frame.can_id == 0x7FF
    
    def test_extended_can_id(self):
        """Verify 29-bit CAN ID support."""
        frame = CANFrame(timestamp=1.0, can_id=0x1FFFFFFF, dlc=8, data=b'12345678')
        assert frame.can_id == 0x1FFFFFFF
    
    def test_zero_timestamp(self):
        """Verify timestamp can be zero."""
        frame = CANFrame(timestamp=0.0, can_id=0x123, dlc=8, data=b'12345678')
        assert frame.timestamp == 0.0
    
    def test_negative_timestamp_allowed(self):
        """Verify negative timestamp is structurally allowed (validation in layer above)."""
        frame = CANFrame(timestamp=-1.0, can_id=0x123, dlc=8, data=b'12345678')
        assert frame.timestamp == -1.0
    
    def test_empty_parsed_signals_dict(self):
        """Verify empty parsed_signals dict is allowed."""
        frame = CANFrame(
            timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678',
            parsed_signals={}
        )
        assert frame.parsed_signals == {}
    
    def test_large_data_payload(self):
        """Verify CANFrame handles larger data (CAN FD)."""
        large_data = bytes(range(256))  # 256 bytes
        frame = CANFrame(
            timestamp=1.0, can_id=0x123, dlc=64, data=large_data
        )
        assert len(frame.data) == 256