from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Iterator, List

import pytest

from canpy.storage import CANFrame
from canpy.tools.format_candidates import CandidateStats, FormatCandidate


def test_format_candidate_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        FormatCandidate()


def test_candidate_stats_is_an_immutable_snapshot():
    stats = CandidateStats(
        frames_written=10,
        buffered_frames=2,
        flush_count=1,
    )

    with pytest.raises(FrozenInstanceError):
        stats.frames_written = 11


def test_complete_candidate_implements_the_shared_lifecycle(tmp_path):
    class MemoryCandidate(FormatCandidate):
        name = "memory"
        suffix = ".memory"

        def __init__(self) -> None:
            self.frames: List[CANFrame] = []

        def start(self, output_path: Path) -> None:
            self.output_path = output_path

        def write_frame(self, frame: CANFrame) -> None:
            self.frames.append(frame)

        def close(self) -> None:
            pass

        def read_frames(self, input_path: Path) -> Iterator[CANFrame]:
            yield from self.frames

        def get_stats(self) -> CandidateStats:
            return CandidateStats(
                frames_written=len(self.frames),
                buffered_frames=len(self.frames),
                flush_count=0,
            )

    candidate = MemoryCandidate()
    candidate.start(tmp_path / f"recording{candidate.suffix}")
    stats = candidate.get_stats()

    assert candidate.name == "memory"
    assert stats == CandidateStats(0, 0, 0)
