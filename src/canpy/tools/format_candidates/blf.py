"""Experimental BLF recording candidate.

Standard BLF CAN messages expose one native timestamp. This candidate uses the
UTC correlation clock as that timestamp. On readback, the same value must also
populate ``source_timestamp`` because standard ``python-can`` BLF messages do
not preserve CAN-PY's second timestamp domain. The benchmark is expected to
make this limitation visible.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

import can
from can.io.blf import BLFReader, BLFWriter

from canpy.storage import CANFrame

from .base import CandidateStats, FormatCandidate


class BlfCandidate(FormatCandidate):
    """Experimental adapter around the standard python-can BLF implementation."""

    name = "blf"
    suffix = ".blf"

    def __init__(self, compression_level: int = -1) -> None:
        if compression_level < -1 or compression_level > 9:
            raise ValueError("compression_level must be between -1 and 9")
        self.compression_level = compression_level
        self._writer: Optional[BLFWriter] = None
        self._frame_count = 0

    def start(self, output_path: Path) -> None:
        """Open a new BLF recording and reset candidate-owned counters."""
        if self._writer is not None:
            raise RuntimeError("start() has already been called without a corresponding close()")

        self._file_path = Path(output_path)
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

        self._writer = BLFWriter(self._file_path, compression_level=self.compression_level)
        self._frame_count = 0

    def write_frame(self, frame: CANFrame) -> None:
        """Convert one CANFrame to can.Message and append it to the BLF."""
        if self._writer is None:
            raise RuntimeError("write_frame() called before start()")

        self._writer.on_message_received(
            can.Message(
                timestamp = frame.timestamp_utc.timestamp(),
                arbitration_id = frame.can_id,
                is_extended_id = frame.is_extended,
                is_remote_frame = frame.is_remote,
                is_error_frame = frame.is_error,
                channel = None,                 # CANFrame does not preserve the source channel
                dlc = frame.dlc,
                data = frame.data,
                is_fd = False,                  # CANFrame does not identify CAN FD frames
                is_rx = True,                   # CANFrame does not preserve direction
                bitrate_switch = False,         # CAN FD metadata is outside the current contract
                error_state_indicator = False,  # CAN FD metadata is outside the current contract
                check = True,                   # Validate message-field consistency
            )
        )

        self._frame_count += 1

    def close(self) -> None:
        """Finalize the BLF header, flush its container, and close the file."""
        if self._writer is not None:
            self._writer.stop()
            self._writer = None

    def read_frames(self, input_path: Path) -> Iterator[CANFrame]:
        """Yield CANFrame objects reconstructed from standard BLF messages."""
        with BLFReader(input_path) as reader:
            for message in reader:
                # Rebuild timestamp_utc from message.timestamp in UTC. Because BLF has
                # no second clock, also use message.timestamp for source_timestamp.
                timestamp_utc = datetime.fromtimestamp(message.timestamp, tz=timezone.utc)
                source_timestamp = message.timestamp

                yield CANFrame(
                    timestamp_utc=timestamp_utc,
                    source_timestamp=source_timestamp,
                    can_id=message.arbitration_id,
                    dlc=message.dlc,
                    data=bytes(message.data),
                    is_extended=message.is_extended_id,
                    is_remote=message.is_remote_frame,
                    is_error=message.is_error_frame,
                    parsed_signals=None
                )

    def get_stats(self) -> CandidateStats:
        """Return counters observable by this adapter."""
        return CandidateStats(
            frames_written=self._frame_count,
            buffered_frames=0,
            # BLFWriter flushes internally but does not expose a public counter.
            flush_count=0,
        )
