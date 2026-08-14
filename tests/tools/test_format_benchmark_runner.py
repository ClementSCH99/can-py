"""Learning tests for the persistent format-benchmark executor."""

import argparse
from pathlib import Path

import pytest

from canpy.storage import CANFrame
from canpy.tools.format_benchmark import BenchmarkResult
from canpy.tools.format_benchmark_runner import (
    DEFAULT_GZIP_FLUSH_EVERY,
    build_candidates,
    load_frames,
    parse_args,
    print_interruption_results,
    print_results,
)
from canpy.tools.format_interruption import InterruptionResult
from canpy.tools.format_candidates import BlfCandidate, GzipCsvCandidate


def test_parse_args_accepts_one_synthetic_source():
    args = parse_args(
        [
            "--synthetic-frames",
            "1000",
            "--output-dir",
            "benchmark-output",
            "--gzip-flush-every",
            "100",
        ]
    )

    assert args.synthetic_frames == 1000
    assert args.input_ndjson is None
    assert args.output_dir == Path("benchmark-output")
    assert args.gzip_flush_every == 100
    assert args.test_interruption is False


def test_parse_args_accepts_interruption_test():
    args = parse_args(
        [
            "--synthetic-frames",
            "10",
            "--output-dir",
            "benchmark-output",
            "--test-interruption",
        ]
    )

    assert args.test_interruption is True


@pytest.mark.parametrize(
    "argv",
    [
        ["--output-dir", "benchmark-output"],
        [
            "--synthetic-frames",
            "10",
            "--input-ndjson",
            "capture.ndjson",
            "--output-dir",
            "benchmark-output",
        ],
    ],
)
def test_parse_args_requires_exactly_one_frame_source(argv):
    with pytest.raises(SystemExit):
        parse_args(argv)


@pytest.mark.parametrize(
    "argv",
    [
        ["--synthetic-frames", "-10", "--output-dir", "benchmark-output"],
        ["--synthetic-frames", "0", "--output-dir", "benchmark-output"],
        ["--input-ndjson", "capture.ndjson", "--limit", "-5", "--output-dir", "benchmark-output"],
        ["--input-ndjson", "capture.ndjson", "--limit", "0", "--output-dir", "benchmark-output"],
        ["--synthetic-frames", "10", "--gzip-flush-every", "-5", "--output-dir", "benchmark-output"],
        ["--synthetic-frames", "10", "--gzip-flush-every", "0", "--output-dir", "benchmark-output"],
        ["--synthetic-frames", "10", "--limit", "5", "--output-dir", "benchmark-output"],
    ],
)
def test_parse_args_rejects_invalid_values(argv):
    with pytest.raises(SystemExit):
        parse_args(argv)


def test_load_frames_accepts_synthetic_source(tmp_path):
    args = parse_args(
        [
            "--synthetic-frames",
            "1000",
            "--output-dir",
            str(tmp_path),
        ]
    )
    frames = load_frames(args)

    assert len(frames) == 1000
    assert all(isinstance(frame, CANFrame) for frame in frames)


def test_load_frames_accepts_ndjson_source(tmp_path):
    # Create a temporary NDJSON file with 5 frames
    ndjson_path = tmp_path / "capture.ndjson"
    ndjson_content = """{"timestamp": 0.0, "can_id": 1, "dlc": 3, "data_bytes": [0, 1, 2]}
{"timestamp": 0.1, "can_id": 2, "dlc": 3, "data_bytes": [3, 4, 5]}
{"timestamp": 0.2, "can_id": 3, "dlc": 3, "data_bytes": [6, 7, 8]}
{"timestamp": 0.3, "can_id": 4, "dlc": 3, "data_bytes": [9, 10, 11]}
{"timestamp": 0.4, "can_id": 5, "dlc": 3, "data_bytes": [12, 13, 14]}"""
    ndjson_path.write_text(ndjson_content, encoding="utf-8")

    args = parse_args(
        [
            "--input-ndjson",
            str(ndjson_path),
            "--limit",
            "3",
            "--output-dir",
            str(tmp_path),
        ]
    )
    frames = load_frames(args)

    assert len(frames) == 3
    assert frames[0].can_id == 1
    assert frames[0].data == bytes([0, 1, 2])


def test_load_frames_rejects_missing_source():
    args = argparse.Namespace(
        synthetic_frames=None,
        input_ndjson=None,
        limit=None,
    )

    with pytest.raises(ValueError, match="No valid frame source"):
        load_frames(args)


def test_build_candidates_uses_requested_gzip_flush_interval():
    args = argparse.Namespace(gzip_flush_every=250)

    candidates = build_candidates(args)

    assert len(candidates) == 3
    assert isinstance(candidates[0], GzipCsvCandidate)
    assert candidates[0].flush_every == 250
    assert isinstance(candidates[1], BlfCandidate)


def test_build_candidates_uses_explicit_default():
    args = argparse.Namespace(gzip_flush_every=None)

    candidates = build_candidates(args)

    assert len(candidates) == 3
    assert isinstance(candidates[0], GzipCsvCandidate)
    assert candidates[0].flush_every == DEFAULT_GZIP_FLUSH_EVERY
    assert isinstance(candidates[1], BlfCandidate)


def test_print_results_displays_comparison_metrics(capsys, tmp_path):
    result = BenchmarkResult(
        candidate_name="gzip_csv",
        output_path=tmp_path / "gzip_csv.csv.gz",
        frames_attempted=1_000,
        frames_written=1_000,
        frames_read=1_000,
        file_size_bytes=8_000,
        bytes_per_frame=8.0,
        write_seconds=0.5,
        write_frames_per_second=2_000.0,
        read_seconds=1.0,
        read_frames_per_second=1_000.0,
        round_trip_valid=True,
        timestamps_valid=True,
    )

    print_results([result])
    output = capsys.readouterr().out

    assert "Format" in output
    assert "gzip_csv" in output
    assert "1000" in output
    assert "8000" in output
    assert "8.00" in output
    assert "2000.0" in output
    assert "1000.0" in output
    assert "OK" in output
    assert str(result.output_path) in output


def test_print_results_marks_invalid_round_trip(capsys, tmp_path):
    result = BenchmarkResult(
        candidate_name="broken_candidate",
        output_path=tmp_path / "broken.output",
        frames_attempted=10,
        frames_written=9,
        frames_read=8,
        file_size_bytes=100,
        bytes_per_frame=10.0,
        write_seconds=1.0,
        write_frames_per_second=9.0,
        read_seconds=1.0,
        read_frames_per_second=8.0,
        round_trip_valid=False,
        timestamps_valid=False,
    )

    print_results([result])
    output = capsys.readouterr().out

    assert "broken_candidate" in output
    assert "FAILED" in output


def test_print_interruption_results_displays_recovery_state(capsys, tmp_path):
    result = InterruptionResult(
        candidate_name="gzip_csv",
        output_path=tmp_path / "gzip_csv_interrupted.csv.gz",
        frames_attempted=1_001,
        frames_recovered=1_000,
        file_size_bytes=8_000,
        read_completed=False,
        raw_prefix_valid=True,
        timestamps_prefix_valid=True,
        read_error_type="EOFError",
        read_error_message="Compressed file ended before the end-of-stream marker",
    )

    print_interruption_results([result])
    output = capsys.readouterr().out

    assert "Interrupted format" in output
    assert "gzip_csv" in output
    assert "1001" in output
    assert "1000" in output
    assert "EOFError" in output
