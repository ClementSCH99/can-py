"""Experimental Parquet candidate for structured raw CAN records.

This spike-only module requires the optional ``benchmark`` dependencies, which
keep PyArrow out of the normal CAN-PY installation.
"""

from datetime import timezone
from pathlib import Path
from typing import Iterator, List, Optional

import pyarrow as pa
import pyarrow.parquet as pq

from canpy.storage import CANFrame

from .base import CandidateStats, FormatCandidate


PARQUET_SCHEMA = pa.schema(
    [
        # The value is always UTC by CANFrame contract. Omitting Arrow's timezone
        # metadata avoids requiring a separate Windows timezone database merely
        # to reconstruct the Python datetime.
        pa.field("timestamp_utc", pa.timestamp("us"), nullable=False),
        pa.field("source_timestamp", pa.float64(), nullable=False),
        pa.field("can_id", pa.uint32(), nullable=False),
        pa.field("dlc", pa.uint8(), nullable=False),
        pa.field("data", pa.binary(), nullable=False),
        pa.field("is_extended", pa.bool_(), nullable=False),
        pa.field("is_remote", pa.bool_(), nullable=False),
        pa.field("is_error", pa.bool_(), nullable=False),
    ]
)
SUPPORTED_COMPRESSIONS = frozenset(
    {
        "snappy",
        "zstd",
        "gzip",
        "brotli",
        "lz4",
    }
)


def _validate_positive_int(value: int) -> int:
    """Reject non-integer and non-positive batch sizes."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("row_group_size must be an integer")
    if value <= 0:
        raise ValueError("row_group_size must be greater than zero")
    return value

class ParquetCandidate(FormatCandidate):
    """Write bounded frame batches as Parquet row groups."""

    name = "parquet"
    suffix = ".parquet"

    def __init__(
        self,
        row_group_size: int = 10_000,
        compression: str = "zstd",
    ) -> None:
        # Validation of arguments
        row_group_size = _validate_positive_int(row_group_size)
        if not isinstance(compression, str):
            raise TypeError("compression must be a string")
        compression = compression.lower()
        if compression not in SUPPORTED_COMPRESSIONS:
            raise ValueError(f"Unsupported compression: {compression}")
        if not pa.Codec.is_available(compression):
            raise ValueError(f"Compression codec is unavailable: {compression}")
        
        self.row_group_size = row_group_size
        self.compression = compression
        self._writer: Optional[pq.ParquetWriter] = None
        self._buffer: List[CANFrame] = []
        self._frame_count = 0
        self._flush_count = 0

    def start(self, output_path: Path) -> None:
        """Open a Parquet writer with the accepted raw-frame schema."""
        if self._writer is not None:
            raise RuntimeError("Parquet writer already started")

        self._file_path = Path(output_path)
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

        # Keep other Parquet options at their defaults until measurements show
        # that a format-specific tuning option is necessary.
        self._writer = pq.ParquetWriter(
            self._file_path,
            PARQUET_SCHEMA,
            compression=self.compression,
        )

        # Reset internal state for this recording
        self._buffer.clear()
        self._frame_count = 0
        self._flush_count = 0

    def write_frame(self, frame: CANFrame) -> None:
        """Buffer one frame and flush one bounded row group when full."""
        if self._writer is None:
            raise RuntimeError("Parquet writer not started. Call start() before writing frames.")
        if isinstance(frame, CANFrame) is False:
            raise TypeError(f"Expected CANFrame, got {type(frame).__name__}")

        self._buffer.append(frame)
        self._frame_count += 1

        if len(self._buffer) >= self.row_group_size:
            self._flush_buffer()

    def _flush_buffer(self) -> None:
        """Convert buffered frames to an Arrow table and write one row group."""
        if len(self._buffer) == 0:
            return

        if self._writer is None:
            raise RuntimeError("Parquet writer not started. Call start() before flushing.")

        columns = {
            "timestamp_utc": [],
            "source_timestamp": [],
            "can_id": [],
            "dlc": [],
            "data": [],
            "is_extended": [],
            "is_remote": [],
            "is_error": [],
        }

        for frame in self._buffer:
            columns["timestamp_utc"].append(frame.timestamp_utc)
            columns["source_timestamp"].append(frame.source_timestamp)
            columns["can_id"].append(frame.can_id)
            columns["dlc"].append(frame.dlc)
            columns["data"].append(frame.data)
            columns["is_extended"].append(frame.is_extended)
            columns["is_remote"].append(frame.is_remote)
            columns["is_error"].append(frame.is_error)

        arrow_table = pa.table(columns, schema=PARQUET_SCHEMA)

        self._writer.write_table(arrow_table)

        self._buffer.clear()
        self._flush_count += 1


    def close(self) -> None:
        """Write the final partial row group and close the Parquet footer."""
        if self._writer is not None:
            self._flush_buffer()
            self._writer.close()
            self._writer = None

    def read_frames(self, input_path: Path) -> Iterator[CANFrame]:
        """Yield reconstructed frames progressively from Parquet batches."""
        with pq.ParquetFile(input_path) as parquet_file:
            for batch in parquet_file.iter_batches(batch_size=self.row_group_size):
                for row in batch.to_pylist():
                    timestamp_utc = row["timestamp_utc"].replace(tzinfo=timezone.utc)
                    source_timestamp = row["source_timestamp"]
                    can_id = row["can_id"]
                    dlc = row["dlc"]
                    data = row["data"]
                    is_extended = row["is_extended"]
                    is_remote = row["is_remote"]
                    is_error = row["is_error"]

                    yield CANFrame(
                        timestamp_utc=timestamp_utc,
                        source_timestamp=source_timestamp,
                        can_id=can_id,
                        dlc=dlc,
                        data=data,
                        is_extended=is_extended,
                        is_remote=is_remote,
                        is_error=is_error,
                        parsed_signals=None
                    )

    def get_stats(self) -> CandidateStats:
        """Return observable candidate-owned counters."""
        return CandidateStats(
            frames_written=self._frame_count,
            buffered_frames=len(self._buffer),
            flush_count=self._flush_count,
        )
