"""Tests for the abrupt-interruption benchmark harness."""

from canpy.tools.format_candidates import GzipCsvCandidate
from canpy.tools.format_interruption import (
    benchmark_candidate_interruptions,
    benchmark_interruption,
)

from .sample_can_frames import sample_contract_frames


def test_interruption_keeps_writer_open_until_child_is_terminated(tmp_path):
    frames = sample_contract_frames()
    candidate = GzipCsvCandidate(flush_every=1)

    result = benchmark_interruption(candidate, frames, tmp_path)

    assert result.frames_attempted == len(frames)
    assert result.output_path.exists()
    assert result.file_size_bytes > 0
    assert result.frames_recovered == len(frames)
    assert result.raw_prefix_valid is True
    assert result.timestamps_prefix_valid is True
    # A gzip stream without close has no final trailer. Its rows can be
    # recovered, but normal reading must report the truncation.
    assert result.read_completed is False
    assert result.read_error_type == "EOFError"


def test_candidate_interruptions_use_distinct_output_paths(tmp_path):
    frames = sample_contract_frames()
    candidates = [
        GzipCsvCandidate(flush_every=1),
        GzipCsvCandidate(flush_every=2),
    ]

    results = benchmark_candidate_interruptions(candidates, frames, tmp_path)

    assert len(results) == 2
    assert results[0].output_path != results[1].output_path
    assert all(result.output_path.exists() for result in results)
