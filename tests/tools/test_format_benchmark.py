"""Learning tests for the generic format-candidate benchmark."""

import pytest

from canpy.tools.format_benchmark import benchmark_candidate, benchmark_candidates
from canpy.tools.format_candidates import GzipCsvCandidate

from .sample_can_frames import sample_contract_frames


def test_benchmark_candidate_returns_comparable_measurements(tmp_path):
    frames = sample_contract_frames()
    candidate = GzipCsvCandidate(flush_every=2)

    result = benchmark_candidate(candidate, frames, tmp_path)

    assert result.candidate_name == candidate.name
    assert result.output_path.suffixes[-2:] == [".csv", ".gz"]
    assert result.frames_written == len(frames)
    assert result.frames_read == len(frames)
    assert result.file_size_bytes > 0
    assert result.bytes_per_frame > 0
    assert result.write_seconds >= 0
    assert result.write_frames_per_second > 0
    assert result.read_seconds >= 0
    assert result.read_frames_per_second > 0
    assert result.round_trip_valid is True
    assert result.timestamps_valid is True


def test_benchmark_candidates_preserves_candidate_order(tmp_path):
    frames = sample_contract_frames()
    candidates = [
        GzipCsvCandidate(flush_every=1),
        GzipCsvCandidate(flush_every=3),
    ]

    results = benchmark_candidates(candidates, frames, tmp_path)

    assert len(results) == 2
    assert [result.candidate_name for result in results] == [
        candidate.name for candidate in candidates
    ]
    assert results[0].output_path != results[1].output_path
    assert all(result.output_path.exists() for result in results)
