"""Focused resilience checks for the segmented-Parquet prototype."""

import pytest

from canpy.tools.format_benchmark import (
    _raw_round_trip_is_valid,
    _timestamps_are_valid,
)
from canpy.tools.format_candidates.segmented_parquet import (
    SegmentedParquetCandidate,
    finalized_segment_paths,
    merge_finalized_segments,
    merged_partial_path,
    staging_directory,
)
from canpy.tools.format_interruption import benchmark_interruption
from canpy.tools.recording_baseline import make_synthetic_frames


def test_interruption_during_segment_recovers_only_finalized_segments(tmp_path):
    frames = make_synthetic_frames(5)
    candidate = SegmentedParquetCandidate(segment_frames=3, row_group_size=2)

    result = benchmark_interruption(candidate, frames, tmp_path)

    assert result.frames_recovered == 3
    assert result.read_completed is True
    assert result.raw_prefix_valid is True
    assert result.timestamps_prefix_valid is True
    assert len(finalized_segment_paths(result.output_path)) == 1
    assert len(list(staging_directory(result.output_path).glob("*.partial"))) == 1


def test_interruption_after_segment_boundary_recovers_every_frame(tmp_path):
    frames = make_synthetic_frames(6)
    candidate = SegmentedParquetCandidate(segment_frames=3, row_group_size=2)

    result = benchmark_interruption(candidate, frames, tmp_path)

    assert result.frames_recovered == len(frames)
    assert result.read_completed is True
    assert result.raw_prefix_valid is True
    assert result.timestamps_prefix_valid is True
    assert len(finalized_segment_paths(result.output_path)) == 2
    assert list(staging_directory(result.output_path).glob("*.partial")) == []


def test_interruption_during_merge_keeps_segments_and_allows_retry(tmp_path):
    frames = make_synthetic_frames(6)
    final_path = tmp_path / "recording.parquet"
    candidate = SegmentedParquetCandidate(segment_frames=3, row_group_size=2)
    candidate.start(final_path)
    for frame in frames:
        candidate.write_frame(frame)

    def interrupt_after_first_segment(index, _segment_path):
        if index == 1:
            raise RuntimeError("simulated merge interruption")

    with pytest.raises(RuntimeError, match="simulated merge interruption"):
        merge_finalized_segments(
            final_path,
            compression="zstd",
            after_segment=interrupt_after_first_segment,
        )

    assert final_path.exists() is False
    assert merged_partial_path(final_path).exists() is True
    assert len(finalized_segment_paths(final_path)) == 2

    merged_rows = merge_finalized_segments(final_path, compression="zstd")

    assert merged_rows == len(frames)
    assert final_path.exists() is True
    assert staging_directory(final_path).exists() is False
    recovered_frames = list(candidate.read_frames(final_path))
    assert _raw_round_trip_is_valid(frames, recovered_frames) is True
    assert _timestamps_are_valid(frames, recovered_frames) is True
