"""Integration tests for CSVWriter → CsvRepository write→read→query cycle."""

import os
import tempfile
from pathlib import Path

import pytest

from canpy import CsvRepository, QueryFilter
from canpy.storage.frame import CANFrame
from canpy.writers.csv_writer import CSVWriter
from .frame_factory import make_frame

CANFrame = make_frame


class TestWriterRepositoryIntegration:
    """Test integration between CSVWriter (Phase 1.1) and CsvRepository (Phase 1.3)."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def sample_frames(self):
        """Create test frames spanning different CAN IDs and timestamps."""
        return [
            CANFrame(
                timestamp=1.0,
                can_id=0x100,
                dlc=8,
                data=b'\x01\x02\x03\x04\x05\x06\x07\x08',
                parsed_signals={'speed': 10.0, 'rpm': 1000}
            ),
            CANFrame(
                timestamp=2.0,
                can_id=0x200,
                dlc=8,
                data=b'\x11\x22\x33\x44\x55\x66\x77\x88',
                parsed_signals={'temp': 25.5}
            ),
            CANFrame(
                timestamp=3.0,
                can_id=0x100,
                dlc=8,
                data=b'\xAA\xBB\xCC\xDD\xEE\xFF\x00\x11',
                parsed_signals={'speed': 15.0, 'rpm': 1500}
            ),
            CANFrame(
                timestamp=4.0,
                can_id=0x300,
                dlc=4,
                data=b'\xFF\xFE\xFD\xFC',
                parsed_signals={'pressure': 101.3}
            ),
            CANFrame(
                timestamp=5.0,
                can_id=0x200,
                dlc=8,
                data=b'\x22\x33\x44\x55\x66\x77\x88\x99',
                parsed_signals={'temp': 26.0}
            ),
        ]

    def test_write_via_csvwriter_read_via_repository(self, temp_dir, sample_frames):
        """
        Integration: Write frames via CSVWriter, read back via CsvRepository.
        Verify data is lossless and complete.
        """
        csv_path = os.path.join(temp_dir, "test_output.csv")

        # Step 1: Write frames using CSVWriter
        writer = CSVWriter(output_dir=temp_dir, expected_signals={'speed', 'rpm', 'temp', 'pressure'})
        writer.start_streaming(filename="test_output")
        
        for frame in sample_frames:
            frame_dict = {
                'timestamp': frame.timestamp,
                'can_id': f"0x{frame.can_id:03X}",
                'dlc': frame.dlc,
                'data_hex': ' '.join(f"{b:02X}" for b in frame.data),
                'parsed': frame.parsed_signals
            }
            writer.write_frame(frame_dict)
        
        writer.stop_streaming()

        # Step 2: Open and read via CsvRepository
        repo = CsvRepository.open(csv_path)

        # Step 3: Verify all frames are readable
        retrieved_frames = list(repo.get_frames())
        assert len(retrieved_frames) == len(sample_frames), \
            f"Expected {len(sample_frames)} frames, got {len(retrieved_frames)}"

        # Step 4: Verify data integrity (no data loss)
        for expected, retrieved in zip(sample_frames, retrieved_frames):
            assert retrieved.timestamp == expected.timestamp
            assert retrieved.can_id == expected.can_id
            assert retrieved.dlc == expected.dlc
            assert retrieved.data == expected.data
            # Parsed signals should match (accounting for float conversions)
            for key, value in expected.parsed_signals.items():
                assert key in retrieved.parsed_signals
                assert float(retrieved.parsed_signals[key]) == float(value)

        repo.close()

    def test_query_by_can_id(self, temp_dir, sample_frames):
        """
        Integration: Write frames via CSVWriter, query by CAN ID via CsvRepository.
        Verify filtering works correctly.
        """
        csv_path = os.path.join(temp_dir, "test_query_canid.csv")

        # Write frames
        writer = CSVWriter(output_dir=temp_dir, expected_signals={'speed', 'rpm', 'temp', 'pressure'})
        writer.start_streaming(filename="test_query_canid")
        
        for frame in sample_frames:
            frame_dict = {
                'timestamp': frame.timestamp,
                'can_id': f"0x{frame.can_id:03X}",
                'dlc': frame.dlc,
                'data_hex': ' '.join(f"{b:02X}" for b in frame.data),
                'parsed': frame.parsed_signals
            }
            writer.write_frame(frame_dict)
        
        writer.stop_streaming()

        # Query by CAN ID 0x100
        repo = CsvRepository.open(csv_path)
        query = QueryFilter(can_ids=[0x100])
        filtered_frames = list(repo.get_frames(query))

        # Should get only frames with CAN ID 0x100 (timestamps 1.0 and 3.0)
        assert len(filtered_frames) == 2
        assert all(f.can_id == 0x100 for f in filtered_frames)
        assert filtered_frames[0].timestamp == 1.0
        assert filtered_frames[1].timestamp == 3.0

        repo.close()

    def test_query_by_time_range(self, temp_dir, sample_frames):
        """
        Integration: Write frames via CSVWriter, query by time range via CsvRepository.
        Verify time filtering works correctly.
        """
        csv_path = os.path.join(temp_dir, "test_query_time.csv")

        # Write frames
        writer = CSVWriter(output_dir=temp_dir, expected_signals={'speed', 'rpm', 'temp', 'pressure'})
        writer.start_streaming(filename="test_query_time")
        
        for frame in sample_frames:
            frame_dict = {
                'timestamp': frame.timestamp,
                'can_id': f"0x{frame.can_id:03X}",
                'dlc': frame.dlc,
                'data_hex': ' '.join(f"{b:02X}" for b in frame.data),
                'parsed': frame.parsed_signals
            }
            writer.write_frame(frame_dict)
        
        writer.stop_streaming()

        # Query time range: 2.0 to 4.0 (inclusive)
        repo = CsvRepository.open(csv_path)
        query = QueryFilter(time_start=2.0, time_end=4.0)
        filtered_frames = list(repo.get_frames(query))

        # Should get frames at timestamps 2.0, 3.0, 4.0
        assert len(filtered_frames) == 3
        assert filtered_frames[0].timestamp == 2.0
        assert filtered_frames[1].timestamp == 3.0
        assert filtered_frames[2].timestamp == 4.0

        repo.close()

    def test_query_combined_can_id_and_time(self, temp_dir, sample_frames):
        """
        Integration: Write frames via CSVWriter, query by both CAN ID and time range.
        Verify combined filtering works correctly.
        """
        csv_path = os.path.join(temp_dir, "test_query_combined.csv")

        # Write frames
        writer = CSVWriter(output_dir=temp_dir, expected_signals={'speed', 'rpm', 'temp', 'pressure'})
        writer.start_streaming(filename="test_query_combined")
        
        for frame in sample_frames:
            frame_dict = {
                'timestamp': frame.timestamp,
                'can_id': f"0x{frame.can_id:03X}",
                'dlc': frame.dlc,
                'data_hex': ' '.join(f"{b:02X}" for b in frame.data),
                'parsed': frame.parsed_signals
            }
            writer.write_frame(frame_dict)
        
        writer.stop_streaming()

        # Query: CAN ID 0x200 AND time 1.0-4.5
        repo = CsvRepository.open(csv_path)
        query = QueryFilter(can_ids=[0x200], time_start=1.0, time_end=4.5)
        filtered_frames = list(repo.get_frames(query))

        # Should get frames: 0x200 at timestamps 2.0 and 5.0, but only 2.0 is in range
        # Actually looking at sample_frames: 0x200 at 2.0 and 5.0
        # Time range 1.0-4.5 includes 2.0 but not 5.0
        assert len(filtered_frames) == 1
        assert filtered_frames[0].can_id == 0x200
        assert filtered_frames[0].timestamp == 2.0

        repo.close()

    def test_query_with_limit(self, temp_dir, sample_frames):
        """
        Integration: Write frames via CSVWriter, query with limit parameter.
        Verify limit stops reading after N frames.
        """
        csv_path = os.path.join(temp_dir, "test_query_limit.csv")

        # Write frames
        writer = CSVWriter(output_dir=temp_dir, expected_signals={'speed', 'rpm', 'temp', 'pressure'})
        writer.start_streaming(filename="test_query_limit")
        
        for frame in sample_frames:
            frame_dict = {
                'timestamp': frame.timestamp,
                'can_id': f"0x{frame.can_id:03X}",
                'dlc': frame.dlc,
                'data_hex': ' '.join(f"{b:02X}" for b in frame.data),
                'parsed': frame.parsed_signals
            }
            writer.write_frame(frame_dict)
        
        writer.stop_streaming()

        # Query with limit=2
        repo = CsvRepository.open(csv_path)
        query = QueryFilter(limit=2)
        filtered_frames = list(repo.get_frames(query))

        # Should get only first 2 frames
        assert len(filtered_frames) == 2
        assert filtered_frames[0].timestamp == 1.0
        assert filtered_frames[1].timestamp == 2.0

        repo.close()

    def test_multiple_reads_same_repository(self, temp_dir, sample_frames):
        """
        Integration: Verify that a single repository instance can be queried multiple times.
        Ensures the file pointer is properly reset between reads.
        """
        csv_path = os.path.join(temp_dir, "test_multi_read.csv")

        # Write frames
        writer = CSVWriter(output_dir=temp_dir, expected_signals={'speed', 'rpm', 'temp', 'pressure'})
        writer.start_streaming(filename="test_multi_read")
        
        for frame in sample_frames:
            frame_dict = {
                'timestamp': frame.timestamp,
                'can_id': f"0x{frame.can_id:03X}",
                'dlc': frame.dlc,
                'data_hex': ' '.join(f"{b:02X}" for b in frame.data),
                'parsed': frame.parsed_signals
            }
            writer.write_frame(frame_dict)
        
        writer.stop_streaming()

        # Multiple reads with different filters
        repo = CsvRepository.open(csv_path)

        # First query: all frames
        all_frames = list(repo.get_frames())
        assert len(all_frames) == len(sample_frames)

        # Second query: filtered by CAN ID
        query_0x100 = QueryFilter(can_ids=[0x100])
        frames_0x100 = list(repo.get_frames(query_0x100))
        assert len(frames_0x100) == 2

        # Third query: filtered by time
        query_time = QueryFilter(time_start=2.0, time_end=5.0)
        frames_time = list(repo.get_frames(query_time))
        assert len(frames_time) == 4

        repo.close()

    def test_context_manager_auto_close(self, temp_dir, sample_frames):
        """
        Integration: Verify that using CsvRepository with context manager auto-closes.
        """
        csv_path = os.path.join(temp_dir, "test_context.csv")

        # Write frames
        writer = CSVWriter(output_dir=temp_dir, expected_signals={'speed', 'rpm', 'temp', 'pressure'})
        writer.start_streaming(filename="test_context")
        
        for frame in sample_frames:
            frame_dict = {
                'timestamp': frame.timestamp,
                'can_id': f"0x{frame.can_id:03X}",
                'dlc': frame.dlc,
                'data_hex': ' '.join(f"{b:02X}" for b in frame.data),
                'parsed': frame.parsed_signals
            }
            writer.write_frame(frame_dict)
        
        writer.stop_streaming()

        # Use context manager
        with CsvRepository.open(csv_path) as repo:
            frames = list(repo.get_frames())
            assert len(frames) == len(sample_frames)
        
        # After exiting context, file should be closed
        assert repo._file is None


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error conditions for write→read→query cycle."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_write_single_frame_read_back(self, temp_dir):
        """Edge case: Single frame round-trip."""
        csv_path = os.path.join(temp_dir, "single_frame.csv")
        frame = CANFrame(
            timestamp=0.0,
            can_id=0x7FF,  # Max 11-bit CAN ID
            dlc=8,
            data=b'\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF',
            parsed_signals={}
        )

        writer = CSVWriter(output_dir=temp_dir, expected_signals=set())
        writer.start_streaming(filename="single_frame")
        writer.write_frame({
            'timestamp': frame.timestamp,
            'can_id': f"0x{frame.can_id:03X}",
            'dlc': frame.dlc,
            'data_hex': ' '.join(f"{b:02X}" for b in frame.data),
            'parsed': frame.parsed_signals
        })
        writer.stop_streaming()

        repo = CsvRepository.open(csv_path)
        frames = list(repo.get_frames())
        assert len(frames) == 1
        assert frames[0].timestamp == 0.0
        assert frames[0].can_id == 0x7FF
        repo.close()

    def test_write_frame_no_parsed_signals(self, temp_dir):
        """Edge case: Frame with no parsed signals (empty dict)."""
        csv_path = os.path.join(temp_dir, "no_signals.csv")
        frame = CANFrame(
            timestamp=1.5,
            can_id=0x123,
            dlc=4,
            data=b'\x12\x34\x56\x78',
            parsed_signals={}
        )

        writer = CSVWriter(output_dir=temp_dir, expected_signals=set())
        writer.start_streaming(filename="no_signals")
        writer.write_frame({
            'timestamp': frame.timestamp,
            'can_id': f"0x{frame.can_id:03X}",
            'dlc': frame.dlc,
            'data_hex': ' '.join(f"{b:02X}" for b in frame.data),
            'parsed': frame.parsed_signals
        })
        writer.stop_streaming()

        repo = CsvRepository.open(csv_path)
        frames = list(repo.get_frames())
        assert len(frames) == 1
        assert frames[0].parsed_signals == {}
        repo.close()

    def test_frames_with_numeric_string_signals(self, temp_dir):
        """Edge case: Parsed signals that are numeric strings (should convert to float)."""
        csv_path = os.path.join(temp_dir, "numeric_strings.csv")
        
        frames = [
            CANFrame(
                timestamp=1.0,
                can_id=0x100,
                dlc=8,
                data=b'\x01\x02\x03\x04\x05\x06\x07\x08',
                parsed_signals={'value1': 42.0, 'value2': -3.14}
            ),
        ]

        writer = CSVWriter(output_dir=temp_dir, expected_signals={'value1', 'value2'})
        writer.start_streaming(filename="numeric_strings")
        for frame in frames:
            writer.write_frame({
                'timestamp': frame.timestamp,
                'can_id': f"0x{frame.can_id:03X}",
                'dlc': frame.dlc,
                'data_hex': ' '.join(f"{b:02X}" for b in frame.data),
                'parsed': frame.parsed_signals
            })
        writer.stop_streaming()

        repo = CsvRepository.open(csv_path)
        retrieved = list(repo.get_frames())
        assert len(retrieved) == 1
        assert float(retrieved[0].parsed_signals['value1']) == 42.0
        assert float(retrieved[0].parsed_signals['value2']) == -3.14
        repo.close()

    def test_frames_with_non_numeric_signals(self, temp_dir):
        """Edge case: Parsed signals with string values (should stay as strings)."""
        csv_path = os.path.join(temp_dir, "string_signals.csv")
        
        frames = [
            CANFrame(
                timestamp=1.0,
                can_id=0x100,
                dlc=8,
                data=b'\x01\x02\x03\x04\x05\x06\x07\x08',
                parsed_signals={'status': 'active', 'mode': 'normal'}
            ),
        ]

        writer = CSVWriter(output_dir=temp_dir, expected_signals={'status', 'mode'})
        writer.start_streaming(filename="string_signals")
        for frame in frames:
            writer.write_frame({
                'timestamp': frame.timestamp,
                'can_id': f"0x{frame.can_id:03X}",
                'dlc': frame.dlc,
                'data_hex': ' '.join(f"{b:02X}" for b in frame.data),
                'parsed': frame.parsed_signals
            })
        writer.stop_streaming()

        repo = CsvRepository.open(csv_path)
        retrieved = list(repo.get_frames())
        assert len(retrieved) == 1
        assert retrieved[0].parsed_signals['status'] == 'active'
        assert retrieved[0].parsed_signals['mode'] == 'normal'
        repo.close()

    def test_query_empty_result_set(self, temp_dir):
        """Edge case: Query with no matching frames returns empty."""
        csv_path = os.path.join(temp_dir, "empty_result.csv")
        
        frames = [
            CANFrame(timestamp=1.0, can_id=0x100, dlc=8, data=b'\x00' * 8, parsed_signals={}),
            CANFrame(timestamp=2.0, can_id=0x200, dlc=8, data=b'\x00' * 8, parsed_signals={}),
        ]

        writer = CSVWriter(output_dir=temp_dir, expected_signals=set())
        writer.start_streaming(filename="empty_result")
        for frame in frames:
            writer.write_frame({
                'timestamp': frame.timestamp,
                'can_id': f"0x{frame.can_id:03X}",
                'dlc': frame.dlc,
                'data_hex': ' '.join(f"{b:02X}" for b in frame.data),
                'parsed': frame.parsed_signals
            })
        writer.stop_streaming()

        # Query for non-existent CAN ID
        repo = CsvRepository.open(csv_path)
        query = QueryFilter(can_ids=[0x999])
        results = list(repo.get_frames(query))
        assert len(results) == 0
        repo.close()

    def test_query_time_boundaries_inclusive(self, temp_dir):
        """Edge case: Time boundaries should be inclusive (start ≤ t ≤ end)."""
        csv_path = os.path.join(temp_dir, "time_bounds.csv")
        
        frames = [
            CANFrame(timestamp=1.0, can_id=0x100, dlc=8, data=b'\x00' * 8, parsed_signals={}),
            CANFrame(timestamp=5.0, can_id=0x100, dlc=8, data=b'\x00' * 8, parsed_signals={}),
            CANFrame(timestamp=10.0, can_id=0x100, dlc=8, data=b'\x00' * 8, parsed_signals={}),
        ]

        writer = CSVWriter(output_dir=temp_dir, expected_signals=set())
        writer.start_streaming(filename="time_bounds")
        for frame in frames:
            writer.write_frame({
                'timestamp': frame.timestamp,
                'can_id': f"0x{frame.can_id:03X}",
                'dlc': frame.dlc,
                'data_hex': ' '.join(f"{b:02X}" for b in frame.data),
                'parsed': frame.parsed_signals
            })
        writer.stop_streaming()

        # Query: 5.0 to 10.0 (inclusive)
        repo = CsvRepository.open(csv_path)
        query = QueryFilter(time_start=5.0, time_end=10.0)
        results = list(repo.get_frames(query))
        assert len(results) == 2
        assert results[0].timestamp == 5.0
        assert results[1].timestamp == 10.0
        repo.close()

    def test_large_can_id_values(self, temp_dir):
        """Edge case: Extended CAN IDs (29-bit)."""
        csv_path = os.path.join(temp_dir, "large_can_id.csv")
        
        frame = CANFrame(
            timestamp=1.0,
            can_id=0x1FFFFFFF,  # Max 29-bit CAN ID
            dlc=8,
            data=b'\x00' * 8,
            parsed_signals={}
        )

        writer = CSVWriter(output_dir=temp_dir, expected_signals=set())
        writer.start_streaming(filename="large_can_id")
        writer.write_frame({
            'timestamp': frame.timestamp,
            'can_id': f"0x{frame.can_id:03X}",
            'dlc': frame.dlc,
            'data_hex': ' '.join(f"{b:02X}" for b in frame.data),
            'parsed': frame.parsed_signals
        })
        writer.stop_streaming()

        repo = CsvRepository.open(csv_path)
        retrieved = list(repo.get_frames())
        assert len(retrieved) == 1
        assert retrieved[0].can_id == 0x1FFFFFFF
        repo.close()

    def test_query_multiple_can_ids(self, temp_dir):
        """Edge case: Query with multiple CAN IDs (should match any)."""
        csv_path = os.path.join(temp_dir, "multi_can_id.csv")
        
        frames = [
            CANFrame(timestamp=1.0, can_id=0x100, dlc=8, data=b'\x00' * 8, parsed_signals={}),
            CANFrame(timestamp=2.0, can_id=0x200, dlc=8, data=b'\x00' * 8, parsed_signals={}),
            CANFrame(timestamp=3.0, can_id=0x300, dlc=8, data=b'\x00' * 8, parsed_signals={}),
            CANFrame(timestamp=4.0, can_id=0x400, dlc=8, data=b'\x00' * 8, parsed_signals={}),
        ]

        writer = CSVWriter(output_dir=temp_dir, expected_signals=set())
        writer.start_streaming(filename="multi_can_id")
        for frame in frames:
            writer.write_frame({
                'timestamp': frame.timestamp,
                'can_id': f"0x{frame.can_id:03X}",
                'dlc': frame.dlc,
                'data_hex': ' '.join(f"{b:02X}" for b in frame.data),
                'parsed': frame.parsed_signals
            })
        writer.stop_streaming()

        # Query: multiple CAN IDs
        repo = CsvRepository.open(csv_path)
        query = QueryFilter(can_ids=[0x100, 0x300])
        results = list(repo.get_frames(query))
        assert len(results) == 2
        assert results[0].can_id == 0x100
        assert results[1].can_id == 0x300
        repo.close()

    def test_query_error_on_closed_repository(self, temp_dir):
        """Error case: Querying a closed repository should raise error."""
        csv_path = os.path.join(temp_dir, "closed_repo.csv")
        
        frame = CANFrame(timestamp=1.0, can_id=0x100, dlc=8, data=b'\x00' * 8, parsed_signals={})
        
        writer = CSVWriter(output_dir=temp_dir, expected_signals=set())
        writer.start_streaming(filename="closed_repo")
        writer.write_frame({
            'timestamp': frame.timestamp,
            'can_id': f"0x{frame.can_id:03X}",
            'dlc': frame.dlc,
            'data_hex': ' '.join(f"{b:02X}" for b in frame.data),
            'parsed': frame.parsed_signals
        })
        writer.stop_streaming()

        repo = CsvRepository.open(csv_path)
        repo.close()

        # Attempting to query closed repo should raise error
        with pytest.raises(RuntimeError, match="not open for reading"):
            list(repo.get_frames())

    def test_frame_with_zero_dlc(self, temp_dir):
        """Edge case: Frame with DLC=0 (valid CAN frame)."""
        csv_path = os.path.join(temp_dir, "zero_dlc.csv")
        
        frame = CANFrame(
            timestamp=1.0,
            can_id=0x100,
            dlc=0,
            data=b'',
            parsed_signals={}
        )

        writer = CSVWriter(output_dir=temp_dir, expected_signals=set())
        writer.start_streaming(filename="zero_dlc")
        writer.write_frame({
            'timestamp': frame.timestamp,
            'can_id': f"0x{frame.can_id:03X}",
            'dlc': frame.dlc,
            'data_hex': '',
            'parsed': frame.parsed_signals
        })
        writer.stop_streaming()

        repo = CsvRepository.open(csv_path)
        retrieved = list(repo.get_frames())
        assert len(retrieved) == 1
        assert retrieved[0].dlc == 0
        assert retrieved[0].data == b''
        repo.close()

    def test_count_frames_in_repository(self, temp_dir):
        """Test counting total frames in repository."""
        csv_path = os.path.join(temp_dir, "count_frames.csv")
        
        frames = [
            CANFrame(timestamp=float(i), can_id=0x100 + i, dlc=8, data=b'\x00' * 8, parsed_signals={})
            for i in range(10)
        ]

        writer = CSVWriter(output_dir=temp_dir, expected_signals=set())
        writer.start_streaming(filename="count_frames")
        for frame in frames:
            writer.write_frame({
                'timestamp': frame.timestamp,
                'can_id': f"0x{frame.can_id:03X}",
                'dlc': frame.dlc,
                'data_hex': ' '.join(f"{b:02X}" for b in frame.data),
                'parsed': frame.parsed_signals
            })
        writer.stop_streaming()

        repo = CsvRepository.open(csv_path)
        count = repo.count()
        assert count == 10
        repo.close()
