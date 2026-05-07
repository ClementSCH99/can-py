"""Comprehensive tests for CSVRepository implementation."""

import os
import tempfile
from pathlib import Path

import pytest

from canpy import BaseRepository, CsvRepository, QueryFilter
from canpy.storage.csv_repository import CSVRepository
from canpy.storage.frame import CANFrame
from canpy.writers.csv_writer import CSVWriter


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_frame():
    """Create a sample CAN frame for testing."""
    return CANFrame(
        timestamp=1.0,
        can_id=0x123,
        dlc=8,
        data=b'\x01\x02\x03\x04\x05\x06\x07\x08',
        parsed_signals={'speed': 50.0, 'rpm': 3000}
    )


@pytest.fixture
def sample_frames():
    """Create multiple sample CAN frames with different properties."""
    frames = [
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
            data=b'\xaa\xbb\xcc\xdd\xee\xff\x00\x11',
            parsed_signals={'speed': 30.0, 'rpm': 2000}
        ),
        CANFrame(
            timestamp=4.0,
            can_id=0x300,
            dlc=4,
            data=b'\xFF\xFF\xFF\xFF',
            parsed_signals={'voltage': 12.5}
        ),
        CANFrame(
            timestamp=5.0,
            can_id=0x100,
            dlc=8,
            data=b'\x12\x34\x56\x78\x9a\xbc\xde\xf0',
            parsed_signals={'speed': 50.0, 'rpm': 3000}
        ),
    ]
    return frames


# ============================================================================
# Test CSVRepository Factory Methods
# ============================================================================

class TestCSVRepositoryFactories:
    """Test create() and open() factory methods."""

    def test_public_api_exports_roadmap_names(self):
        """Verify the roadmap public API is exported from canpy."""
        assert issubclass(CsvRepository, BaseRepository)
        assert CSVRepository is CsvRepository

    def test_create_opens_file_for_writing(self, temp_dir):
        """Verify create() opens a file in write mode."""
        file_path = os.path.join(temp_dir, 'test_write.csv')
        repo = CsvRepository.create(file_path)
        
        assert repo._file is not None
        assert repo._mode == 'w'
        assert repo._header_written is False
        assert repo._frame_count == 0
        assert os.path.exists(file_path)
        
        repo.close()

    def test_create_raises_file_exists_error(self, temp_dir):
        """Verify create() raises error if file already exists."""
        file_path = os.path.join(temp_dir, 'existing.csv')
        # Create file first
        Path(file_path).touch()
        
        with pytest.raises(FileExistsError):
            CsvRepository.create(file_path)

    def test_create_raises_directory_not_found_error(self):
        """Verify create() raises error if directory doesn't exist."""
        file_path = '/nonexistent/path/file.csv'
        
        with pytest.raises(FileNotFoundError):
            CsvRepository.create(file_path)

    def test_open_opens_file_for_reading(self, temp_dir, sample_frame):
        """Verify open() opens an existing file in read mode."""
        file_path = os.path.join(temp_dir, 'test_read.csv')
        
        # First create and write a frame
        repo_write = CsvRepository.create(file_path)
        repo_write.save_frame(sample_frame)
        repo_write.close()
        
        # Now open for reading
        repo_read = CsvRepository.open(file_path)
        
        assert repo_read._file is not None
        assert repo_read._mode == 'r'
        assert repo_read._header_written is True
        
        repo_read.close()

    def test_open_raises_file_not_found_error(self):
        """Verify open() raises error if file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            CsvRepository.open('/nonexistent/file.csv')

    def test_context_manager_write(self, temp_dir, sample_frame):
        """Verify context manager works with create()."""
        file_path = os.path.join(temp_dir, 'test_context_write.csv')
        
        with CsvRepository.create(file_path) as repo:
            repo.save_frame(sample_frame)
            assert repo._file is not None
        
        # After context exit, file should be closed
        assert repo._file is None
        assert os.path.exists(file_path)

    def test_context_manager_read(self, temp_dir, sample_frame):
        """Verify context manager works with open()."""
        file_path = os.path.join(temp_dir, 'test_context_read.csv')
        
        # Create file
        repo_write = CsvRepository.create(file_path)
        repo_write.save_frame(sample_frame)
        repo_write.close()
        
        # Read with context manager
        with CsvRepository.open(file_path) as repo:
            frames = list(repo.get_frames(QueryFilter()))
            assert len(frames) == 1
        
        # After context exit, file should be closed
        assert repo._file is None


# ============================================================================
# Test Write Path (save_frame + count)
# ============================================================================

class TestCSVRepositoryWrite:
    """Test writing frames to CSV."""

    def test_save_single_frame(self, temp_dir, sample_frame):
        """Verify save_frame() writes a frame to CSV."""
        file_path = os.path.join(temp_dir, 'single_frame.csv')
        repo = CsvRepository.create(file_path)
        
        repo.save_frame(sample_frame)
        repo.close()
        
        # Verify file has content (header + 1 data row)
        with open(file_path, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 2  # Header + 1 row

    def test_save_multiple_frames(self, temp_dir, sample_frames):
        """Verify save_frame() writes multiple frames."""
        file_path = os.path.join(temp_dir, 'multiple_frames.csv')
        repo = CsvRepository.create(file_path)
        
        for frame in sample_frames:
            repo.save_frame(frame)
        
        repo.close()
        
        # Verify file has header + 5 data rows
        with open(file_path, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 6  # Header + 5 rows

    def test_count_during_write(self, temp_dir, sample_frames):
        """Verify count() returns correct frame count during write."""
        file_path = os.path.join(temp_dir, 'count_write.csv')
        repo = CsvRepository.create(file_path)
        
        assert repo.count() == 0
        
        for i, frame in enumerate(sample_frames, 1):
            repo.save_frame(frame)
            assert repo.count() == i
        
        repo.close()

    def test_frame_fields_preserved(self, temp_dir, sample_frame):
        """Verify all frame fields are preserved in CSV."""
        file_path = os.path.join(temp_dir, 'fields_preserved.csv')
        repo = CsvRepository.create(file_path)
        
        repo.save_frame(sample_frame)
        repo.close()
        
        # Read back and verify
        repo_read = CsvRepository.open(file_path)
        frames = list(repo_read.get_frames(QueryFilter()))
        repo_read.close()
        
        assert len(frames) == 1
        read_frame = frames[0]
        
        assert read_frame.timestamp == sample_frame.timestamp
        assert read_frame.can_id == sample_frame.can_id
        assert read_frame.dlc == sample_frame.dlc
        assert read_frame.data == sample_frame.data
        assert read_frame.parsed_signals == sample_frame.parsed_signals

    def test_different_signals_per_frame(self, temp_dir):
        """Verify frames with different signals are handled without signal loss."""
        file_path = os.path.join(temp_dir, 'diff_signals.csv')
        
        frame1 = CANFrame(1.0, 0x100, 8, b'\x00' * 8, {'speed': 10.0})
        frame2 = CANFrame(2.0, 0x200, 8, b'\x00' * 8, {'temp': 25.0, 'humidity': 60.0})
        frame3 = CANFrame(3.0, 0x100, 8, b'\x00' * 8, {'speed': 20.0})
        
        repo = CsvRepository.create(file_path)
        repo.save_frame(frame1)
        repo.save_frame(frame2)
        repo.save_frame(frame3)
        repo.close()
        
        # Verify all rows written
        with open(file_path, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 4  # Header + 3 rows
            # Header should have all discovered signals
            header = lines[0]
            assert 'speed' in header
            assert 'temp' in header
            assert 'humidity' in header


# ============================================================================
# Test Read Path (get_frames + count)
# ============================================================================

class TestCSVRepositoryRead:
    """Test reading frames from CSV."""

    def _setup_test_file(self, temp_dir, sample_frames):
        """Helper to create and write test file."""
        file_path = os.path.join(temp_dir, 'read_test.csv')
        
        # Collect all signals from all frames
        all_signals = set()
        for frame in sample_frames:
            if frame.parsed_signals:
                all_signals.update(frame.parsed_signals.keys())
        
        repo = CsvRepository.create(file_path)
        for frame in sample_frames:
            repo.save_frame(frame)
        repo.close()
        return file_path

    def test_get_frames_yields_all(self, temp_dir, sample_frames):
        """Verify get_frames() yields all frames."""
        file_path = self._setup_test_file(temp_dir, sample_frames)
        
        repo = CsvRepository.open(file_path)
        frames = list(repo.get_frames(QueryFilter()))
        repo.close()
        
        assert len(frames) == len(sample_frames)

    def test_get_frames_by_can_id(self, temp_dir, sample_frames):
        """Verify get_frames() filters by CAN ID."""
        file_path = self._setup_test_file(temp_dir, sample_frames)
        
        repo = CsvRepository.open(file_path)
        query = QueryFilter(can_ids=[0x100])
        frames = list(repo.get_frames(query))
        repo.close()
        
        # Should have 3 frames with CAN ID 0x100
        assert len(frames) == 3
        for frame in frames:
            assert frame.can_id == 0x100

    def test_get_frames_by_multiple_can_ids(self, temp_dir, sample_frames):
        """Verify get_frames() filters by multiple CAN IDs."""
        file_path = self._setup_test_file(temp_dir, sample_frames)
        
        repo = CsvRepository.open(file_path)
        query = QueryFilter(can_ids=[0x100, 0x200])
        frames = list(repo.get_frames(query))
        repo.close()
        
        # Should have 4 frames (3 with 0x100, 1 with 0x200)
        assert len(frames) == 4
        can_ids = {frame.can_id for frame in frames}
        assert can_ids == {0x100, 0x200}

    def test_get_frames_by_time_range(self, temp_dir, sample_frames):
        """Verify get_frames() filters by time range."""
        file_path = self._setup_test_file(temp_dir, sample_frames)
        
        repo = CsvRepository.open(file_path)
        query = QueryFilter(time_start=2.0, time_end=4.0)
        frames = list(repo.get_frames(query))
        repo.close()
        
        # Should have 3 frames (timestamps 2, 3, 4)
        assert len(frames) == 3
        for frame in frames:
            assert 2.0 <= frame.timestamp <= 4.0

    def test_get_frames_with_limit(self, temp_dir, sample_frames):
        """Verify get_frames() respects limit."""
        file_path = self._setup_test_file(temp_dir, sample_frames)
        
        repo = CsvRepository.open(file_path)
        query = QueryFilter(limit=3)
        frames = list(repo.get_frames(query))
        repo.close()
        
        assert len(frames) == 3

    def test_get_frames_combined_filters(self, temp_dir, sample_frames):
        """Verify get_frames() with combined filters."""
        file_path = self._setup_test_file(temp_dir, sample_frames)
        
        repo = CsvRepository.open(file_path)
        query = QueryFilter(can_ids=[0x100], time_start=1.0, time_end=5.0, limit=2)
        frames = list(repo.get_frames(query))
        repo.close()
        
        # Should have 2 frames (limited to 2)
        assert len(frames) == 2
        for frame in frames:
            assert frame.can_id == 0x100
            assert 1.0 <= frame.timestamp <= 5.0

    def test_count_on_existing_file(self, temp_dir, sample_frames):
        """Verify count() returns correct total for existing file."""
        file_path = self._setup_test_file(temp_dir, sample_frames)
        
        repo = CsvRepository.open(file_path)
        count = repo.count()
        repo.close()
        
        assert count == len(sample_frames)

    def test_multiple_get_frames_calls(self, temp_dir, sample_frames):
        """Verify multiple get_frames() calls work correctly."""
        file_path = self._setup_test_file(temp_dir, sample_frames)
        
        repo = CsvRepository.open(file_path)
        
        # First query
        query1 = QueryFilter(can_ids=[0x100])
        frames1 = list(repo.get_frames(query1))
        
        # Second query
        query2 = QueryFilter(can_ids=[0x200])
        frames2 = list(repo.get_frames(query2))
        
        repo.close()
        
        assert len(frames1) == 3
        assert len(frames2) == 1

    def test_type_conversions(self, temp_dir):
        """Verify type conversions from CSV to CANFrame."""
        file_path = os.path.join(temp_dir, 'type_conversion.csv')
        
        # Create frame with specific types
        frame = CANFrame(
            timestamp=123.456,
            can_id=0xABC,
            dlc=8,
            data=bytes(range(8)),
            parsed_signals={'signal1': 99.99, 'signal2': 'text_value'}
        )
        
        repo_write = CsvRepository.create(file_path)
        repo_write.save_frame(frame)
        repo_write.close()
        
        # Read back and verify types
        repo_read = CsvRepository.open(file_path)
        frames = list(repo_read.get_frames(QueryFilter()))
        repo_read.close()
        
        read_frame = frames[0]
        
        assert isinstance(read_frame.timestamp, float)
        assert read_frame.timestamp == 123.456
        
        assert isinstance(read_frame.can_id, int)
        assert read_frame.can_id == 0xABC
        
        assert isinstance(read_frame.dlc, int)
        assert read_frame.dlc == 8
        
        assert isinstance(read_frame.data, bytes)
        assert read_frame.data == bytes(range(8))
        
        assert isinstance(read_frame.parsed_signals['signal1'], float)
        assert read_frame.parsed_signals['signal1'] == 99.99
        
        # Non-numeric signals kept as strings
        assert isinstance(read_frame.parsed_signals['signal2'], str)
        assert read_frame.parsed_signals['signal2'] == 'text_value'


# ============================================================================
# Test Integration (write → read → query)
# ============================================================================

class TestCSVRepositoryIntegration:
    """Integration tests for write-read-query cycle."""

    def test_write_then_read_lossless(self, temp_dir, sample_frames):
        """Verify data is lossless through write-read cycle."""
        file_path = os.path.join(temp_dir, 'integration.csv')
        
        # Collect all signals from all frames
        all_signals = set()
        for frame in sample_frames:
            if frame.parsed_signals:
                all_signals.update(frame.parsed_signals.keys())
        
        repo_write = CsvRepository.create(file_path)
        for frame in sample_frames:
            repo_write.save_frame(frame)
        repo_write.close()
        
        # Read
        repo_read = CsvRepository.open(file_path)
        read_frames = list(repo_read.get_frames(QueryFilter()))
        repo_read.close()
        
        # Verify
        assert len(read_frames) == len(sample_frames)
        for original, read in zip(sample_frames, read_frames):
            assert original == read

    def test_write_100_frames_query_subset(self, temp_dir):
        """Integration test with 100 frames and various queries."""
        file_path = os.path.join(temp_dir, 'integration_100.csv')
        
        # Create 100 frames with patterns
        frames = []
        for i in range(100):
            frame = CANFrame(
                timestamp=float(i),
                can_id=0x100 if i % 2 == 0 else 0x200,
                dlc=8,
                data=bytes([(i % 256)] * 8),
                parsed_signals={'index': float(i), 'type': 'even' if i % 2 == 0 else 'odd'}
            )
            frames.append(frame)
        
        # Write all
        repo_write = CsvRepository.create(file_path)
        for frame in frames:
            repo_write.save_frame(frame)
        repo_write.close()
        
        # Query: CAN ID 0x100 only
        repo_read = CsvRepository.open(file_path)
        query1 = QueryFilter(can_ids=[0x100])
        results1 = list(repo_read.get_frames(query1))
        
        # Query: time 20-30
        query2 = QueryFilter(time_start=20.0, time_end=30.0)
        results2 = list(repo_read.get_frames(query2))
        
        # Query: combined
        query3 = QueryFilter(can_ids=[0x200], time_start=10.0, time_end=50.0, limit=5)
        results3 = list(repo_read.get_frames(query3))
        
        repo_read.close()
        
        # Verify counts
        assert len(results1) == 50  # Even indices
        assert len(results2) == 11  # 20-30 inclusive
        assert len(results3) == 5   # Limited to 5

    def test_open_reads_csv_writer_output(self, temp_dir):
        """Verify repository can read files produced by CSVWriter."""
        writer = CSVWriter(output_dir=temp_dir, expected_signals={'speed', 'status'})
        filepaths = writer.start_streaming(filename='writer_capture')
        writer.write_frame({
            'timestamp': 12.5,
            'can_id': '0x123',
            'dlc': 8,
            'data_hex': '01 02 03 04 05 06 07 08',
            'parsed': {'speed': 88.5, 'status': 'ready'},
        })
        writer.stop_streaming()

        repo = CsvRepository.open(filepaths['csv'])
        frames = list(repo.get_frames(QueryFilter(can_ids=[0x123])))
        repo.close()

        assert len(frames) == 1
        assert frames[0].timestamp == 12.5
        assert frames[0].can_id == 0x123
        assert frames[0].parsed_signals == {'speed': 88.5, 'status': 'ready'}


# ============================================================================
# Test Error Handling
# ============================================================================

class TestCSVRepositoryErrors:
    """Test error conditions and validation."""

    def test_cannot_get_frames_on_write_repo(self, temp_dir):
        """Verify get_frames() raises error on write-mode repo."""
        file_path = os.path.join(temp_dir, 'write_only.csv')
        repo = CsvRepository.create(file_path)
        
        with pytest.raises(RuntimeError, match="not open for reading"):
            list(repo.get_frames(QueryFilter()))
        
        repo.close()

    def test_cannot_save_frame_on_read_repo(self, temp_dir, sample_frame):
        """Verify save_frame() raises error on read-mode repo."""
        file_path = os.path.join(temp_dir, 'read_only.csv')
        
        # Create file first
        repo_write = CsvRepository.create(file_path)
        repo_write.save_frame(sample_frame)
        repo_write.close()
        
        # Try to save on read-mode repo
        repo_read = CsvRepository.open(file_path)
        
        with pytest.raises(RuntimeError, match="not open for writing"):
            repo_read.save_frame(sample_frame)
        
        repo_read.close()

    def test_cannot_count_uninitialized_repo(self):
        """Verify count() raises error on uninitialized repo."""
        repo = CsvRepository('dummy.csv')
        
        with pytest.raises(RuntimeError, match="not open"):
            repo.count()

    def test_cannot_save_frame_uninitialized_repo(self, sample_frame):
        """Verify save_frame() raises error on uninitialized repo."""
        repo = CsvRepository('dummy.csv')
        
        with pytest.raises(RuntimeError, match="not open for writing"):
            repo.save_frame(sample_frame)

    def test_cannot_get_frames_uninitialized_repo(self):
        """Verify get_frames() raises error on uninitialized repo."""
        repo = CsvRepository('dummy.csv')
        
        with pytest.raises(RuntimeError, match="not open for reading"):
            list(repo.get_frames(QueryFilter()))


# ============================================================================
# Test Edge Cases
# ============================================================================

class TestCSVRepositoryEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_file(self, temp_dir):
        """Verify handling of empty CSV file."""
        file_path = os.path.join(temp_dir, 'empty.csv')
        
        # Create empty file with just header
        repo = CsvRepository.create(file_path)
        repo.close()
        
        # Open and read
        repo_read = CsvRepository.open(file_path)
        frames = list(repo_read.get_frames(QueryFilter()))
        count = repo_read.count()
        repo_read.close()
        
        assert len(frames) == 0
        assert count == 0

    def test_single_frame(self, temp_dir, sample_frame):
        """Verify handling of single frame."""
        file_path = os.path.join(temp_dir, 'single.csv')
        
        repo_write = CsvRepository.create(file_path)
        repo_write.save_frame(sample_frame)
        repo_write.close()
        
        repo_read = CsvRepository.open(file_path)
        frames = list(repo_read.get_frames(QueryFilter()))
        repo_read.close()
        
        assert len(frames) == 1
        assert frames[0] == sample_frame

    def test_no_parsed_signals(self, temp_dir):
        """Verify frames with no parsed signals."""
        file_path = os.path.join(temp_dir, 'no_signals.csv')
        
        frame = CANFrame(
            timestamp=1.0,
            can_id=0x123,
            dlc=8,
            data=b'\x00' * 8,
            parsed_signals=None
        )
        
        repo_write = CsvRepository.create(file_path)
        repo_write.save_frame(frame)
        repo_write.close()
        
        repo_read = CsvRepository.open(file_path)
        frames = list(repo_read.get_frames(QueryFilter()))
        repo_read.close()
        
        assert len(frames) == 1
        # parsed_signals becomes empty dict (not None) after round-trip for consistency
        assert frames[0].parsed_signals == {}

    def test_many_signals_per_frame(self, temp_dir):
        """Verify frames with many signals."""
        file_path = os.path.join(temp_dir, 'many_signals.csv')
        
        signals = {f'signal_{i}': float(i * 1.5) for i in range(50)}
        frame = CANFrame(
            timestamp=1.0,
            can_id=0x123,
            dlc=8,
            data=b'\x00' * 8,
            parsed_signals=signals
        )
        
        repo_write = CsvRepository.create(file_path)
        repo_write.save_frame(frame)
        repo_write.close()
        
        repo_read = CsvRepository.open(file_path)
        frames = list(repo_read.get_frames(QueryFilter()))
        repo_read.close()
        
        assert len(frames) == 1
        assert len(frames[0].parsed_signals) == 50

    def test_zero_dlc_frame(self, temp_dir):
        """Verify frames with DLC 0."""
        file_path = os.path.join(temp_dir, 'zero_dlc.csv')
        
        frame = CANFrame(
            timestamp=1.0,
            can_id=0x123,
            dlc=0,
            data=b'',
            parsed_signals=None
        )
        
        repo_write = CsvRepository.create(file_path)
        repo_write.save_frame(frame)
        repo_write.close()
        
        repo_read = CsvRepository.open(file_path)
        frames = list(repo_read.get_frames(QueryFilter()))
        repo_read.close()
        
        assert len(frames) == 1
        assert frames[0].dlc == 0
        assert frames[0].data == b''

    def test_filter_matches_no_frames(self, temp_dir, sample_frames):
        """Verify query that matches no frames."""
        file_path = os.path.join(temp_dir, 'no_match.csv')
        
        repo_write = CsvRepository.create(file_path)
        for frame in sample_frames:
            repo_write.save_frame(frame)
        repo_write.close()
        
        repo_read = CsvRepository.open(file_path)
        query = QueryFilter(can_ids=[0x999])  # Doesn't exist
        frames = list(repo_read.get_frames(query))
        repo_read.close()
        
        assert len(frames) == 0

    def test_limit_larger_than_result_set(self, temp_dir, sample_frames):
        """Verify limit that's larger than available frames."""
        file_path = os.path.join(temp_dir, 'large_limit.csv')
        
        repo_write = CsvRepository.create(file_path)
        for frame in sample_frames:
            repo_write.save_frame(frame)
        repo_write.close()
        
        repo_read = CsvRepository.open(file_path)
        query = QueryFilter(limit=1000)  # Much larger than 5 frames
        frames = list(repo_read.get_frames(query))
        repo_read.close()
        
        assert len(frames) == len(sample_frames)
