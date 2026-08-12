"""Generic benchmark harness for experimental recording candidates.

This module measures candidates; it does not select a format or integrate one
into the capture path.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple
from datetime import datetime

import time

from canpy.storage import CANFrame
from .format_candidates import FormatCandidate


@dataclass(frozen=True)
class BenchmarkResult:
    """Comparable measurements produced for one format candidate."""

    candidate_name: str
    output_path: Path
    frames_attempted: int
    frames_written: int
    frames_read: int
    file_size_bytes: int
    bytes_per_frame: float
    write_seconds: float
    write_frames_per_second: float
    read_seconds: float
    read_frames_per_second: float
    round_trip_valid: bool
    timestamps_valid: bool


def _measure_write(
    candidate: FormatCandidate,
    frames: Sequence[CANFrame],
    output_path: Path,
) -> float:
    """Write all frames and return the elapsed time in seconds."""
    start_time = time.perf_counter()

    try:
        candidate.start(output_path)
        for frame in frames:
            candidate.write_frame(frame)
    finally:
        candidate.close()
    
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    return elapsed_time

def _measure_read(
    candidate: FormatCandidate,
    output_path: Path,
) -> Tuple[List[CANFrame], float]:
    """Read all frames and return them with the elapsed time"""
    start_time = time.perf_counter()
    read_frames = list(candidate.read_frames(output_path))  
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    return read_frames, elapsed_time

    
def _raw_round_trip_is_valid(
    expected_frames: Sequence[CANFrame],
    actual_frames: Sequence[CANFrame],
) -> bool:
    """Return whether reconstructed frames preserve the accepted raw contract"""
    if len(expected_frames) != len(actual_frames):
        return False

    for expected, actual in zip(expected_frames, actual_frames):
        if (
            expected.timestamp_utc != actual.timestamp_utc
            or expected.source_timestamp != actual.source_timestamp
            or expected.can_id != actual.can_id
            or expected.dlc != actual.dlc
            or expected.data != actual.data
            or expected.is_extended != actual.is_extended
            or expected.is_remote != actual.is_remote
            or expected.is_error != actual.is_error
        ):
            return False
        
    return True

def _timestamps_are_valid(
    expected_frames: Sequence[CANFrame],
    actual_frames: Sequence[CANFrame],
) -> bool:
    """Return whether both timestamp domains are preserved frame by frame."""
    for expected, actual in zip(expected_frames, actual_frames):
        if (
            expected.timestamp_utc != actual.timestamp_utc
            or expected.source_timestamp != actual.source_timestamp
        ):
            return False

    if len(expected_frames) != len(actual_frames):
        return False
    
    return True


def benchmark_candidate(
    candidate: FormatCandidate,
    frames: Sequence[CANFrame],
    output_dir: Path,
) -> BenchmarkResult:
    """Measure one candidate with a caller-provided, repeatable frame set."""
    if frames is None or len(frames) == 0:
        raise ValueError("frames must be a non-empty sequence of CANFrame objects")

    output_dir = Path(output_dir)
    output_path = output_dir / f"{candidate.name}{candidate.suffix}"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    write_time = _measure_write(candidate, frames, output_path)
    read_frames, read_time = _measure_read(candidate, output_path)
    file_size_bytes = output_path.stat().st_size
    bytes_per_frame = file_size_bytes / len(frames)
    write_frames_per_second = len(frames) / write_time
    read_frames_per_second = len(read_frames) / read_time
    round_trip_valid = _raw_round_trip_is_valid(frames, read_frames)
    timestamps_valid = _timestamps_are_valid(frames, read_frames)

    stats = candidate.get_stats()

    return BenchmarkResult(
        candidate_name=candidate.name,
        output_path=output_path,
        frames_attempted=len(frames),
        frames_written=stats.frames_written if stats else 0,
        frames_read=len(read_frames),
        file_size_bytes=file_size_bytes,
        bytes_per_frame=bytes_per_frame,
        write_seconds=write_time,
        write_frames_per_second=write_frames_per_second,
        read_seconds=read_time,
        read_frames_per_second=read_frames_per_second,
        round_trip_valid=round_trip_valid,
        timestamps_valid=timestamps_valid,
    )


def benchmark_candidates(
    candidates: Sequence[FormatCandidate],
    frames: Sequence[CANFrame],
    output_dir: Path,
) -> List[BenchmarkResult]:
    """Run the same frame set through every candidate in the given order."""

    results = []

    for index, candidate in enumerate(candidates, start=1):
        if not isinstance(candidate, FormatCandidate):
            raise TypeError(f"All candidates must be instances of FormatCandidate, got {type(candidate)}")
        candidate_output_dir = output_dir / f"{index:02d}_{candidate.name}"
        result = benchmark_candidate(candidate, frames, candidate_output_dir)
        results.append(result)
    return results