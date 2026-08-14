"""Learning tests for the structured Parquet candidate."""

import pytest

from canpy.tools.format_benchmark import benchmark_candidate
from canpy.tools.format_candidates.base import CandidateStats
from canpy.tools.format_candidates.parquet import ParquetCandidate
from canpy.tools.recording_baseline import make_synthetic_frames

from .sample_can_frames import sample_contract_frames


def test_parquet_candidate_initialization():
    candidate = ParquetCandidate(row_group_size=250, compression="zstd")

    assert candidate.name == "parquet"
    assert candidate.suffix == ".parquet"
    assert candidate.row_group_size == 250
    assert candidate.compression == "zstd"
    assert candidate.get_stats() == CandidateStats(0, 0, 0)


def test_parquet_candidate_rejects_invalid_row_group_size():
    with pytest.raises(ValueError):
        ParquetCandidate(row_group_size=0)

    with pytest.raises(TypeError):
        ParquetCandidate(row_group_size=2.5)


def test_parquet_candidate_validates_compression():
    candidate = ParquetCandidate(compression="ZSTD")

    assert candidate.compression == "zstd"

    with pytest.raises(ValueError, match="Unsupported compression"):
        ParquetCandidate(compression="lz4_raw")


def test_parquet_candidate_rejects_write_before_start():
    candidate = ParquetCandidate()

    with pytest.raises(RuntimeError):
        candidate.write_frame(sample_contract_frames()[0])


def test_parquet_candidate_rejects_double_start(tmp_path):
    candidate = ParquetCandidate()
    output_path = tmp_path / "capture.parquet"
    candidate.start(output_path)

    try:
        with pytest.raises(RuntimeError):
            candidate.start(output_path)
    finally:
        candidate.close()


def test_parquet_candidate_round_trip_preserves_raw_contract(tmp_path):
    candidate = ParquetCandidate(row_group_size=2)
    output_path = tmp_path / "nested" / "capture.parquet"
    written_frames = sample_contract_frames()

    candidate.start(output_path)
    for frame in written_frames:
        candidate.write_frame(frame)
    candidate.close()

    read_frames = list(candidate.read_frames(output_path))

    assert output_path.exists()
    assert len(read_frames) == len(written_frames)
    for written, read in zip(written_frames, read_frames):
        assert read.timestamp_utc == written.timestamp_utc
        assert read.source_timestamp == written.source_timestamp
        assert read.can_id == written.can_id
        assert read.dlc == written.dlc
        assert read.data == written.data
        assert read.is_extended == written.is_extended
        assert read.is_remote == written.is_remote
        assert read.is_error == written.is_error
        assert read.parsed_signals is None


def test_parquet_candidate_reports_bounded_buffer_and_flushes(tmp_path):
    candidate = ParquetCandidate(row_group_size=2)
    output_path = tmp_path / "capture.parquet"
    frames = sample_contract_frames()

    candidate.start(output_path)
    candidate.write_frame(frames[0])
    assert candidate.get_stats() == CandidateStats(1, 1, 0)

    candidate.write_frame(frames[1])
    assert candidate.get_stats() == CandidateStats(2, 0, 1)

    candidate.write_frame(frames[2])
    candidate.close()
    assert candidate.get_stats() == CandidateStats(3, 0, 2)


def test_parquet_benchmark_preserves_both_timestamp_domains(tmp_path):
    result = benchmark_candidate(
        ParquetCandidate(row_group_size=4),
        make_synthetic_frames(10),
        tmp_path,
    )

    assert result.frames_written == 10
    assert result.frames_read == 10
    assert result.round_trip_valid is True
    assert result.timestamps_valid is True
