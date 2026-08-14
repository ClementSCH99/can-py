"""Command-line executor for the compact-format benchmark spike.

The benchmark module owns measurements. This module owns user input, frame
loading, candidate construction, result presentation, and process exit status.
"""

import argparse
from pathlib import Path
from typing import List, Optional, Sequence

from canpy.storage import CANFrame

from .format_benchmark import BenchmarkResult, benchmark_candidates
from .format_interruption import InterruptionResult, benchmark_candidate_interruptions
from .format_candidates import FormatCandidate, BlfCandidate, GzipCsvCandidate, ParquetCandidate
from .recording_baseline import load_ndjson_frames, make_synthetic_frames


DEFAULT_GZIP_FLUSH_EVERY = 1_000


def _positive_int(value: str) -> int:
    """Parse a positive integer from a string, raising an error for invalid input."""
    try:
        parsed_value = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} must be an integer") from exc

    if parsed_value <= 0:
        raise argparse.ArgumentTypeError("Value must be greater than zero")

    return parsed_value

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse one explicit frame source and one persistent output directory."""

    parser = argparse.ArgumentParser(
        description="Run a benchmark spike for compact CAN frame formats",
        prog=Path(__file__).name,
    )
    group = parser.add_mutually_exclusive_group(required=True)

    # Add arguments for input frame sources
    group.add_argument(
        "--input-ndjson",
        type=Path,
        help="Path to a real capture in NDJSON format (one frame per line)",
    )
    group.add_argument(
        "--synthetic-frames",
        type=_positive_int,
        help="Generate a deterministic number of synthetic frames for testing",
    )

    # Add optional arguments for limiting frames and specifying flush frequency
    parser.add_argument(
        "--limit",
        type=_positive_int,
        required=False,
        default=None,
        help="Limit the number of frames to process from the input source",
    )
    parser.add_argument(
        "--gzip-flush-every",
        type=_positive_int,
        required=False,
        default=None,
        help="Flush gzip output every N frames (only relevant for GzipCsvCandidate)",
    )

    # Add required argument for output directory
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for persistent benchmark artifacts",
    )

    # Add optional argument for testing interruption behavior
    parser.add_argument(
        "--test-interruption",
        action="store_true",
        help="Also force-stop each writer before close and inspect recovery",
    )

    # Validate argument combinations and parse the arguments
    args = parser.parse_args(argv)
    if args.input_ndjson is None and args.limit is not None:
        parser.error("--limit can only be used with --input-ndjson")

    return args


def load_frames(args: argparse.Namespace) -> List[CANFrame]:
    """Load real frames or generate deterministic frames from parsed arguments."""
    # Build synthetic frames if requested
    if args.synthetic_frames is not None:
        return make_synthetic_frames(args.synthetic_frames)

    # Load real frames from NDJSON if requested
    if args.input_ndjson is not None:
        return load_ndjson_frames(args.input_ndjson, args.limit)

    raise ValueError("No valid frame source specified. Use --synthetic-frames or --input-ndjson.")


def build_candidates(args: argparse.Namespace) -> List[FormatCandidate]:
    """Construct the candidates included in this comparison run."""
    candidates: List[FormatCandidate] = []

    # Build the GzipCsvCandidate with the specified flush frequency
    if args.gzip_flush_every is not None:
        gzip_flush_every = args.gzip_flush_every
    else:
        gzip_flush_every = DEFAULT_GZIP_FLUSH_EVERY
    candidates.append(GzipCsvCandidate(flush_every=gzip_flush_every))

    candidates.append(BlfCandidate())
    candidates.append(ParquetCandidate())

    return candidates


def print_results(results: Sequence[BenchmarkResult]) -> None:
    """Print a concise comparison table suitable for reviewing a spike run."""
    print()
    print(
        "Format | Attempted | Written | Read | Size (bytes) | Bytes/frame | "
        "Write (s) | Write frames/s | Read (s) | Read frames/s | Validation"
    )
    print("-" * 139)

    for result in results:
        validation = (
            "OK"
            if result.round_trip_valid and result.timestamps_valid
            else "FAILED"
        )
        print(
            f"{result.candidate_name} | "
            f"{result.frames_attempted} | "
            f"{result.frames_written} | "
            f"{result.frames_read} | "
            f"{result.file_size_bytes} | "
            f"{result.bytes_per_frame:.2f} | "
            f"{result.write_seconds:.4f} | "
            f"{result.write_frames_per_second:.1f} | "
            f"{result.read_seconds:.4f} | "
            f"{result.read_frames_per_second:.1f} | "
            f"{validation}"
        )
    for result in results:
        print(f"Output: {result.output_path}")


def print_interruption_results(results: Sequence[InterruptionResult]) -> None:
    """Print recoverability separately from clean round-trip measurements."""
    print()
    print(
        "Interrupted format | Attempted | Recovered | Size (bytes) | "
        "Read completed | Raw prefix | Timestamp prefix | Read error"
    )
    print("-" * 128)

    for result in results:
        read_error = result.read_error_type or "None"
        raw_prefix = str(result.raw_prefix_valid) if result.frames_recovered else "N/A"
        timestamp_prefix = (
            str(result.timestamps_prefix_valid) if result.frames_recovered else "N/A"
        )
        print(
            f"{result.candidate_name} | "
            f"{result.frames_attempted} | "
            f"{result.frames_recovered} | "
            f"{result.file_size_bytes} | "
            f"{result.read_completed} | "
            f"{raw_prefix} | "
            f"{timestamp_prefix} | "
            f"{read_error}"
        )
        print(f"Interrupted output: {result.output_path}")


def run_benchmark(args: argparse.Namespace) -> List[BenchmarkResult]:
    """Load data, build candidates, and execute one persistent benchmark run."""
    frames = load_frames(args)
    candidates = build_candidates(args)
    return benchmark_candidates(candidates, frames, Path(args.output_dir))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Execute the comparison, reporting candidate failures without hiding data."""
    args = parse_args(argv)
    results = run_benchmark(args)
    print_results(results)

    all_valid = all(
        result.round_trip_valid and result.timestamps_valid for result in results
    )
    if not all_valid:
        print("\n!!! One or more candidates failed validation. See above for details. !!!")

    if args.test_interruption:
        frames = load_frames(args)
        interruption_results = benchmark_candidate_interruptions(
            build_candidates(args),
            frames,
            Path(args.output_dir) / "interruption",
        )
        print_interruption_results(interruption_results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
