import dataclasses
import pytest

from canpy.tools import GzipCsvCandidate
from .sample_can_frames import sample_contract_frames
from canpy.storage import CANFrame

from pathlib import Path

def test_gzip_csv_candidate_initialization():
    # Test valid initialization
    candidate = GzipCsvCandidate(flush_every=10)
    assert candidate.flush_every == 10
    assert candidate.name == "gzip_csv"
    assert candidate.suffix == ".csv.gz"

@pytest.mark.parametrize("flush_every", [0, -5])
def test_gzip_csv_candidate_invalid_initialization(flush_every):
    # Test invalid initialization with flush_every <= 0
    with pytest.raises(ValueError):
        GzipCsvCandidate(flush_every=flush_every)

def test_double_start_raises(tmp_path):
    candidate = GzipCsvCandidate(flush_every=2)
    output_file = tmp_path / "test_output.csv.gz"
    candidate.start(output_file)

    # Attempt to start again without closing should raise RuntimeError
    with pytest.raises(RuntimeError):
        candidate.start(output_file)

    # Clean up by closing
    candidate.close()

def test_write_frame_without_start():
    candidate = GzipCsvCandidate(flush_every=2)
    frame = sample_contract_frames()[0]

    # Attempt to write a frame without starting should raise RuntimeError
    with pytest.raises(RuntimeError):
        candidate.write_frame(frame)

def test_gzip_csv_candidate_start_and_write(tmp_path):
    candidate = GzipCsvCandidate(flush_every=2)
    output_file = tmp_path / "test_output.csv.gz"

    # Start the candidate
    candidate.start(output_file)
    assert candidate._csv_file is not None
    assert candidate._csv_writer is not None
    assert candidate._header_written is True

    # Generate list of sample frames
    frames = sample_contract_frames()

    # Write frames and check internal state
    for i, frame in enumerate(frames):
        candidate.write_frame(frame)
        stats = candidate.get_stats()
        assert stats.frames_written == i + 1

        if (i + 1) % candidate.flush_every == 0:
            assert stats.flush_count == (i + 1) // candidate.flush_every
            assert stats.buffered_frames == 0

    # Close the candidate
    candidate.close()
    stats = candidate.get_stats()

    # Verify that after closing, the internal state is reset
    assert candidate._csv_file is None
    assert candidate._csv_writer is None
    assert candidate._header_written is False

    # Verify that after closing, the stats reflect the total frames written and flush count
    assert stats.frames_written == len(frames)
    assert stats.buffered_frames == 0
    assert stats.flush_count == (len(frames) + candidate.flush_every - 1) // candidate.flush_every

def test_gzip_csv_candidate_round_trip(tmp_path):
    candidate = GzipCsvCandidate(flush_every=2)
    output_file = tmp_path / "test_output.csv.gz"

    # Start the candidate and write frames
    candidate.start(output_file)
    frames_written = list(sample_contract_frames())
    for frame in frames_written:
        candidate.write_frame(frame)
    candidate.close()

    # Read back the frames
    frames_read = list(candidate.read_frames(output_file))

    # define expected frames
    expected_frames = [dataclasses.replace(frame, parsed_signals=None) for frame in frames_written]

    # Check that the written and read frames are equal
    assert len(frames_written) == len(frames_read)

    # Check that each written frame matches the corresponding read frame
    for expected, read in zip(expected_frames, frames_read):
        assert read.parsed_signals is None
        assert expected == read