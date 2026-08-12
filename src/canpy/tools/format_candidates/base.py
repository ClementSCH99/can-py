"""Shared contract for compact-recording format experiments."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from canpy.storage import CANFrame


@dataclass(frozen=True)
class CandidateStats:
    """Format-owned counters returned as an immutable snapshot."""

    frames_written: int
    buffered_frames: int
    flush_count: int


class FormatCandidate(ABC):
    """Small lifecycle shared by each experimental recording format."""

    name: str
    suffix: str

    @abstractmethod
    def start(self, output_path: Path) -> None:
        """Open one new output and initialize format-specific state."""

    @abstractmethod
    def write_frame(self, frame: CANFrame) -> None:
        """Write one frame, using only bounded internal buffering."""

    @abstractmethod
    def close(self) -> None:
        """Flush remaining frames and close the output."""

    @abstractmethod
    def read_frames(self, input_path: Path) -> Iterator[CANFrame]:
        """Yield reconstructed frames progressively from one recording."""

    @abstractmethod
    def get_stats(self) -> CandidateStats:
        """Return a snapshot of counters owned by the candidate."""
