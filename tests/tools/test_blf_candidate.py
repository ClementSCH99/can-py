"""Learning tests for the standard BLF format candidate."""

import pytest

from canpy.tools.format_benchmark import benchmark_candidate
from canpy.tools.format_candidates import BlfCandidate, CandidateStats
from canpy.tools.recording_baseline import make_synthetic_frames

from .sample_can_frames import sample_contract_frames


def test_blf_candidate_initialization():
    candidate = BlfCandidate(compression_level=6)

    assert candidate.name == "blf"
    assert candidate.suffix == ".blf"
    assert candidate.compression_level == 6
    assert candidate.get_stats() == CandidateStats(0, 0, 0)


def test_blf_candidate_rejects_invalid_compression_level():
    with pytest.raises(ValueError):
        BlfCandidate(compression_level=-2)

    with pytest.raises(ValueError):
        BlfCandidate(compression_level=10)


def test_blf_candidate_writes_and_reads_native_can_fields(tmp_path):
    candidate = BlfCandidate()
    output_path = tmp_path / "nested" / "capture.blf"
    written_frames = sample_contract_frames()

    candidate.start(output_path)
    for frame in written_frames:
        candidate.write_frame(frame)
    candidate.close()

    read_frames = list(candidate.read_frames(output_path))

    assert output_path.exists()
    assert len(read_frames) == len(written_frames)
    assert candidate.get_stats().frames_written == len(written_frames)

    for written, read in zip(written_frames, read_frames):
        assert read.timestamp_utc == written.timestamp_utc
        assert read.can_id == written.can_id
        assert read.dlc == written.dlc
        assert read.data == written.data
        assert read.is_extended == written.is_extended
        assert read.is_remote == written.is_remote
        assert read.is_error == written.is_error
        assert read.parsed_signals is None


def test_blf_candidate_exposes_single_timestamp_limitation(tmp_path):
    candidate = BlfCandidate()
    output_path = tmp_path / "capture.blf"
    written = sample_contract_frames()[0]

    candidate.start(output_path)
    candidate.write_frame(written)
    candidate.close()
    read = list(candidate.read_frames(output_path))[0]

    assert read.source_timestamp == read.timestamp_utc.timestamp()
    assert read.source_timestamp != written.source_timestamp


def test_blf_candidate_rejects_write_before_start():
    candidate = BlfCandidate()

    with pytest.raises(RuntimeError):
        candidate.write_frame(sample_contract_frames()[0])


def test_blf_benchmark_exposes_timestamp_contract_failure(tmp_path):
    result = benchmark_candidate(
        BlfCandidate(),
        make_synthetic_frames(10),
        tmp_path,
    )

    assert result.frames_written == 10
    assert result.frames_read == 10
    assert result.round_trip_valid is False
    assert result.timestamps_valid is False
