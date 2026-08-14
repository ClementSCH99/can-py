"""Abrupt-interruption measurements for experimental recording formats.

The writer runs in a spawned child process and is terminated after all
``write_frame`` calls have returned, but before ``close`` can run. This keeps
the test process safe and models a process crash or forced shutdown.
"""

from dataclasses import dataclass
from multiprocessing.connection import Connection
from pathlib import Path
import multiprocessing
import time
from typing import List, Sequence, Tuple

from canpy.storage import CANFrame

from .format_benchmark import _timestamps_are_valid
from .format_candidates import FormatCandidate


@dataclass(frozen=True)
class InterruptionResult:
    """Observed state of one recording after its writer is forcefully stopped."""

    candidate_name: str
    output_path: Path
    frames_attempted: int
    frames_recovered: int
    file_size_bytes: int
    read_completed: bool
    raw_prefix_valid: bool
    timestamps_prefix_valid: bool
    read_error_type: str
    read_error_message: str


def _write_and_wait_for_termination(
    candidate: FormatCandidate,
    frames: Sequence[CANFrame],
    output_path: Path,
    status_connection: Connection,
) -> None:
    """Child-process target: write frames, signal readiness, and never close."""
    try:
        candidate.start(output_path)
        for frame in frames:
            candidate.write_frame(frame)
        status_connection.send(("ready", ""))

        # The parent terminates this process. Staying alive here prevents normal
        # interpreter shutdown from closing and finalizing the writer for us.
        while True:
            time.sleep(60)
    except BaseException as exc:
        status_connection.send((type(exc).__name__, str(exc)))
    finally:
        status_connection.close()


def _recover_frames(
    candidate: FormatCandidate,
    output_path: Path,
) -> Tuple[List[CANFrame], bool, str, str]:
    """Read as much as possible and retain frames yielded before an error."""
    recovered: List[CANFrame] = []
    try:
        recovered.extend(candidate.read_frames(output_path))
    except Exception as exc:
        return recovered, False, type(exc).__name__, str(exc)
    return recovered, True, "", ""


def _raw_payload_prefix_is_valid(
    expected_frames: Sequence[CANFrame],
    recovered_frames: Sequence[CANFrame],
) -> bool:
    """Check raw CAN fields separately from the two timestamp domains."""
    if len(expected_frames) != len(recovered_frames):
        return False

    return all(
        expected.can_id == recovered.can_id
        and expected.dlc == recovered.dlc
        and expected.data == recovered.data
        and expected.is_extended == recovered.is_extended
        and expected.is_remote == recovered.is_remote
        and expected.is_error == recovered.is_error
        for expected, recovered in zip(expected_frames, recovered_frames)
    )


def benchmark_interruption(
    candidate: FormatCandidate,
    frames: Sequence[CANFrame],
    output_dir: Path,
    timeout_seconds: float = 300.0,
) -> InterruptionResult:
    """Force-stop one candidate before close and inspect the resulting file."""
    if not frames:
        raise ValueError("At least one frame is required for interruption testing")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{candidate.name}_interrupted{candidate.suffix}"

    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_write_and_wait_for_termination,
        args=(candidate, frames, output_path, child_connection),
        name=f"{candidate.name}-interruption-writer",
    )

    try:
        process.start()
        child_connection.close()

        if not parent_connection.poll(timeout_seconds):
            process.terminate()
            process.join(timeout=10)
            raise TimeoutError(
                f"{candidate.name} did not finish its write calls within "
                f"{timeout_seconds} seconds"
            )

        status, detail = parent_connection.recv()
        if status != "ready":
            process.join(timeout=10)
            raise RuntimeError(
                f"{candidate.name} failed before interruption: {status}: {detail}"
            )

        process.terminate()
        process.join(timeout=10)
        if process.is_alive():
            process.kill()
            process.join(timeout=10)
        if process.is_alive():
            raise RuntimeError(f"Could not terminate {candidate.name} writer process")
    finally:
        parent_connection.close()
        if process.is_alive():
            process.terminate()
            process.join(timeout=10)

    file_size_bytes = output_path.stat().st_size if output_path.exists() else 0
    recovered, read_completed, error_type, error_message = _recover_frames(
        candidate, output_path
    )
    expected_prefix = frames[: len(recovered)]

    return InterruptionResult(
        candidate_name=candidate.name,
        output_path=output_path,
        frames_attempted=len(frames),
        frames_recovered=len(recovered),
        file_size_bytes=file_size_bytes,
        read_completed=read_completed,
        raw_prefix_valid=bool(recovered)
        and _raw_payload_prefix_is_valid(expected_prefix, recovered),
        timestamps_prefix_valid=bool(recovered)
        and _timestamps_are_valid(expected_prefix, recovered),
        read_error_type=error_type,
        read_error_message=error_message,
    )


def benchmark_candidate_interruptions(
    candidates: Sequence[FormatCandidate],
    frames: Sequence[CANFrame],
    output_dir: Path,
) -> List[InterruptionResult]:
    """Run the same abrupt-stop scenario for every candidate in order."""
    results: List[InterruptionResult] = []
    for index, candidate in enumerate(candidates, start=1):
        candidate_output_dir = Path(output_dir) / f"{index:02d}_{candidate.name}"
        results.append(
            benchmark_interruption(candidate, frames, candidate_output_dir)
        )
    return results
