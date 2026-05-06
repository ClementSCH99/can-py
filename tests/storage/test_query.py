# src/tests/storage/test_query.py

import pytest
from canpy.storage.query import QueryFilter
from canpy.storage.frame import CANFrame


class TestQueryFilterConstruction:
    """Test QueryFilter creation and validation."""
    
    def test_default_construction_no_filters(self):
        """All fields default to None — no filters applied."""
        q = QueryFilter()
        assert q.can_ids is None
        assert q.start_time is None
        assert q.end_time is None
        assert q.limit is None
    
    def test_construction_with_can_ids(self):
        """Can specify CAN IDs to filter."""
        q = QueryFilter(can_ids=[0x123, 0x456])
        assert q.can_ids == [0x123, 0x456]
    
    def test_construction_with_time_range(self):
        """Can specify time range."""
        q = QueryFilter(start_time=10.0, end_time=20.0)
        assert q.start_time == 10.0
        assert q.end_time == 20.0
    
    def test_construction_with_limit(self):
        """Can specify limit."""
        q = QueryFilter(limit=100)
        assert q.limit == 100


class TestQueryFilterValidation:
    """Test __post_init__ validation."""
    
    def test_valid_time_range_start_less_than_end(self):
        """Time range with start < end is valid."""
        q = QueryFilter(start_time=5.0, end_time=15.0)
        assert q.start_time == 5.0
        assert q.end_time == 15.0
    
    def test_valid_time_range_start_equals_end(self):
        """Time range with start == end is valid (single point in time)."""
        q = QueryFilter(start_time=10.0, end_time=10.0)
        assert q.start_time == 10.0
        assert q.end_time == 10.0
    
    def test_invalid_time_range_start_greater_than_end(self):
        """Time range with start > end raises ValueError."""
        with pytest.raises(ValueError, match="start_time must be less than or equal to end_time"):
            QueryFilter(start_time=20.0, end_time=10.0)
    
    def test_valid_can_ids_list_of_ints(self):
        """CAN IDs as list of integers is valid."""
        q = QueryFilter(can_ids=[0x100, 0x200, 0x300])
        assert q.can_ids == [0x100, 0x200, 0x300]
    
    def test_valid_can_ids_empty_list(self):
        """Empty CAN IDs list is technically valid (but matches nothing)."""
        q = QueryFilter(can_ids=[])
        assert q.can_ids == []
    
    def test_invalid_can_ids_not_a_list(self):
        """CAN IDs must be a list, not a tuple or single value."""
        with pytest.raises(ValueError, match="can_ids must be a list"):
            QueryFilter(can_ids=(0x100, 0x200))
    
    def test_invalid_can_ids_contains_non_int(self):
        """All elements in can_ids must be integers."""
        with pytest.raises(ValueError, match="Each CAN ID in can_ids must be an integer"):
            QueryFilter(can_ids=[0x100, "0x200", 0x300])
    
    def test_valid_limit_positive(self):
        """Limit must be a positive integer."""
        q = QueryFilter(limit=50)
        assert q.limit == 50
    
    def test_invalid_limit_zero(self):
        """Limit of 0 is invalid (must be positive)."""
        with pytest.raises(ValueError, match="limit must be a positive integer"):
            QueryFilter(limit=0)
    
    def test_invalid_limit_negative(self):
        """Limit must not be negative."""
        with pytest.raises(ValueError, match="limit must be a positive integer"):
            QueryFilter(limit=-10)
    
    def test_invalid_limit_not_an_int(self):
        """Limit must be an integer."""
        with pytest.raises(ValueError, match="limit must be a positive integer"):
            QueryFilter(limit=10.5)


class TestQueryFilterMatching:
    """Test matches() method against CANFrame objects."""
    
    @pytest.fixture
    def sample_frames(self):
        """Create sample frames for testing."""
        return {
            "frame_id_0x100": CANFrame(
                timestamp=5.0,
                can_id=0x100,
                dlc=8,
                data=b'\x01\x02\x03\x04\x05\x06\x07\x08'
            ),
            "frame_id_0x200": CANFrame(
                timestamp=10.0,
                can_id=0x200,
                dlc=8,
                data=b'\x00\x00\x00\x00\x00\x00\x00\x00'
            ),
            "frame_id_0x300": CANFrame(
                timestamp=15.0,
                can_id=0x300,
                dlc=4,
                data=b'\xFF\xFF\xFF\xFF'
            ),
            "frame_id_0x100_later": CANFrame(
                timestamp=20.0,
                can_id=0x100,
                dlc=8,
                data=b'\x11\x22\x33\x44\x55\x66\x77\x88'
            ),
        }
    
    def test_no_filter_matches_all_frames(self, sample_frames):
        """QueryFilter with no criteria matches all frames."""
        q = QueryFilter()
        for frame in sample_frames.values():
            assert q.matches(frame) is True
    
    def test_can_id_filter_single_id(self, sample_frames):
        """Filter by single CAN ID."""
        q = QueryFilter(can_ids=[0x100])
        assert q.matches(sample_frames["frame_id_0x100"]) is True
        assert q.matches(sample_frames["frame_id_0x200"]) is False
        assert q.matches(sample_frames["frame_id_0x300"]) is False
        assert q.matches(sample_frames["frame_id_0x100_later"]) is True
    
    def test_can_id_filter_multiple_ids(self, sample_frames):
        """Filter by multiple CAN IDs."""
        q = QueryFilter(can_ids=[0x100, 0x300])
        assert q.matches(sample_frames["frame_id_0x100"]) is True
        assert q.matches(sample_frames["frame_id_0x200"]) is False
        assert q.matches(sample_frames["frame_id_0x300"]) is True
        assert q.matches(sample_frames["frame_id_0x100_later"]) is True
    
    def test_can_id_filter_empty_list(self, sample_frames):
        """Filter with empty CAN IDs list matches nothing."""
        q = QueryFilter(can_ids=[])
        for frame in sample_frames.values():
            assert q.matches(frame) is False
    
    def test_time_range_filter_start_only(self, sample_frames):
        """Filter by start time only (>= start_time)."""
        q = QueryFilter(start_time=10.0)
        assert q.matches(sample_frames["frame_id_0x100"]) is False  # 5.0 < 10.0
        assert q.matches(sample_frames["frame_id_0x200"]) is True   # 10.0 >= 10.0
        assert q.matches(sample_frames["frame_id_0x300"]) is True   # 15.0 >= 10.0
        assert q.matches(sample_frames["frame_id_0x100_later"]) is True  # 20.0 >= 10.0
    
    def test_time_range_filter_end_only(self, sample_frames):
        """Filter by end time only (<= end_time)."""
        q = QueryFilter(end_time=12.0)
        assert q.matches(sample_frames["frame_id_0x100"]) is True   # 5.0 <= 12.0
        assert q.matches(sample_frames["frame_id_0x200"]) is True   # 10.0 <= 12.0
        assert q.matches(sample_frames["frame_id_0x300"]) is False  # 15.0 > 12.0
        assert q.matches(sample_frames["frame_id_0x100_later"]) is False  # 20.0 > 12.0
    
    def test_time_range_filter_both_start_and_end(self, sample_frames):
        """Filter by time range (start_time <= timestamp <= end_time)."""
        q = QueryFilter(start_time=8.0, end_time=18.0)
        assert q.matches(sample_frames["frame_id_0x100"]) is False       # 5.0 < 8.0
        assert q.matches(sample_frames["frame_id_0x200"]) is True        # 10.0 in [8.0, 18.0]
        assert q.matches(sample_frames["frame_id_0x300"]) is True        # 15.0 in [8.0, 18.0]
        assert q.matches(sample_frames["frame_id_0x100_later"]) is False # 20.0 > 18.0
    
    def test_time_range_filter_exact_boundaries(self, sample_frames):
        """Time range filters at exact boundary times."""
        q = QueryFilter(start_time=5.0, end_time=20.0)
        assert q.matches(sample_frames["frame_id_0x100"]) is True        # 5.0 == start
        assert q.matches(sample_frames["frame_id_0x100_later"]) is True  # 20.0 == end
    
    def test_combined_can_id_and_time_filter(self, sample_frames):
        """Both filters must pass (AND logic)."""
        q = QueryFilter(can_ids=[0x100], start_time=8.0, end_time=18.0)
        # Only frame_id_0x100_later matches: ID is 0x100 AND 20.0 is outside range
        assert q.matches(sample_frames["frame_id_0x100"]) is False       # right ID, wrong time
        assert q.matches(sample_frames["frame_id_0x200"]) is False       # wrong ID
        assert q.matches(sample_frames["frame_id_0x300"]) is False       # wrong ID
        assert q.matches(sample_frames["frame_id_0x100_later"]) is False # right ID, but 20.0 > 18.0
        
        # Now with a wider time range
        q2 = QueryFilter(can_ids=[0x100], start_time=5.0, end_time=20.0)
        assert q2.matches(sample_frames["frame_id_0x100"]) is True        # both conditions pass
        assert q2.matches(sample_frames["frame_id_0x100_later"]) is True  # both conditions pass
        assert q2.matches(sample_frames["frame_id_0x200"]) is False       # wrong ID


class TestQueryFilterEdgeCases:
    """Test edge cases and corner conditions."""
    
    def test_matches_with_parsed_signals(self):
        """Matching works regardless of parsed_signals content."""
        frame_with_signals = CANFrame(
            timestamp=10.0,
            can_id=0x123,
            dlc=8,
            data=b'\x00' * 8,
            parsed_signals={"temperature": 23.5, "pressure": 101.3}
        )
        frame_without_signals = CANFrame(
            timestamp=10.0,
            can_id=0x123,
            dlc=8,
            data=b'\x00' * 8,
            parsed_signals=None
        )
        q = QueryFilter(can_ids=[0x123])
        assert q.matches(frame_with_signals) is True
        assert q.matches(frame_without_signals) is True
    
    def test_zero_timestamp(self):
        """Filtering works with zero timestamps (start of capture)."""
        frame = CANFrame(timestamp=0.0, can_id=0x100, dlc=8, data=b'\x00' * 8)
        q = QueryFilter(start_time=0.0, end_time=10.0)
        assert q.matches(frame) is True
    
    def test_large_can_id_value(self):
        """Filtering works with maximum CAN ID (0x7FF for 11-bit, 0x1FFFFFFF for 29-bit)."""
        frame_11bit = CANFrame(timestamp=1.0, can_id=0x7FF, dlc=8, data=b'\x00' * 8)
        frame_29bit = CANFrame(timestamp=1.0, can_id=0x1FFFFFFF, dlc=8, data=b'\x00' * 8)
        
        q11 = QueryFilter(can_ids=[0x7FF])
        q29 = QueryFilter(can_ids=[0x1FFFFFFF])
        
        assert q11.matches(frame_11bit) is True
        assert q29.matches(frame_29bit) is True
    
    def test_negative_timestamps(self):
        """Filtering works with negative timestamps (shouldn't normally happen, but robustness)."""
        frame = CANFrame(timestamp=-5.0, can_id=0x100, dlc=8, data=b'\x00' * 8)
        q = QueryFilter(start_time=-10.0, end_time=0.0)
        assert q.matches(frame) is True
    
    def test_very_large_time_ranges(self):
        """Filtering works with very large time ranges."""
        frame = CANFrame(timestamp=1000000.0, can_id=0x100, dlc=8, data=b'\x00' * 8)
        q = QueryFilter(start_time=0.0, end_time=1e9)
        assert q.matches(frame) is True


class TestQueryFilterRepr:
    """Test string representation for debugging."""
    
    def test_repr_shows_all_fields(self):
        """__repr__ includes all filter fields."""
        q = QueryFilter(can_ids=[0x100], start_time=5.0, end_time=15.0, limit=50)
        repr_str = repr(q)
        # Dataclass repr should show: QueryFilter(can_ids=[...], start_time=5.0, ...)
        assert "QueryFilter" in repr_str
        assert "0x100" in repr_str or "256" in repr_str  # 0x100 in hex or decimal