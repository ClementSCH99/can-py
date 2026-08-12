""" Gzip CSV candidate"""

import csv, gzip

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

from canpy.storage import CANFrame

from .base import FormatCandidate, CandidateStats

_FIELDNAMES = [
    "timestamp_utc",
    "source_timestamp",
    "can_id",
    "dlc",
    "data_hex",
    "is_extended",
    "is_remote",
    "is_error",
]

class GzipCsvCandidate(FormatCandidate):
    """Experimental candidate for a CSV format with gzip compression."""

    def __init__(self, flush_every: int) -> None:
        if flush_every <= 0:
            raise ValueError("flush_every must be a positive integer, greater than zero.")

        self.flush_every = flush_every
        self.name = "gzip_csv"
        self.suffix = ".csv.gz"

        self._csv_file = None
        self._csv_writer = None
        self._header_written = False

        self._frame_count = 0
        self._buffered_frames = 0
        self._flush_count = 0

    def start(self, output_path: Path) -> None:
        """Open one new output and initialize format-specific state."""

        # Verify that no output is currently open; if so, raise an error
        if self._csv_file is not None:
            raise RuntimeError("start() has already been called without a corresponding stop()")
        
        # Ensure the output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Open the gzip-compressed CSV file for writing        
        self._csv_file = gzip.open(output_path, 'wt', newline='', encoding='utf-8')
        self._file_path = output_path

        # Initialize the CSV writer and write headers
        if not self._header_written:
            self._csv_writer = csv.DictWriter(
                self._csv_file,
                fieldnames=_FIELDNAMES,
                restval='',
                extrasaction='ignore'
            )
            self._csv_writer.writeheader()
            self._header_written = True

        # Reset counters
        self._frame_count = 0
        self._buffered_frames = 0
        self._flush_count = 0

    def write_frame(self, frame: CANFrame) -> None:
        """Write one frame, using only bounded internal buffering."""
        if self._csv_file is None:
            raise RuntimeError("start() must be called before write_frame()")

        # Flatten the frame into a dictionary for CSV writing
        flat_row = {
            'timestamp_utc': frame.timestamp_utc.isoformat(),
            'source_timestamp': frame.source_timestamp,
            'can_id': frame.can_id,
            'dlc': frame.dlc,
            'data_hex': frame.data.hex(),
            'is_extended': frame.is_extended,
            'is_remote': frame.is_remote,
            'is_error': frame.is_error,
        }
    
        # Write the flatten frame to the CSV file
        if self._csv_writer is None:
             raise RuntimeError("CSV writer is not initialized. Call _write_csv_header() first.")
        self._csv_writer.writerow(flat_row)
        self._frame_count += 1
        self._buffered_frames += 1

        # Flush every N frames
        if self._buffered_frames >= self.flush_every:
            self._csv_file.flush()
            self._flush_count += 1
            self._buffered_frames = 0

    def close(self) -> None:
        """Flush remaining frames and close the output."""
        if self._csv_file is not None:
            if self._buffered_frames > 0:
                self._csv_file.flush()
                self._flush_count += 1
                self._buffered_frames = 0
            self._csv_file.close()
            self._csv_file = None
            self._csv_writer = None
            self._header_written = False

    def read_frames(self, input_path: Path) -> Iterator[CANFrame]:
        """Yield reconstructed frames progressively from one recording."""
        with gzip.open(input_path, 'rt', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                frame = CANFrame(
                    timestamp_utc=datetime.fromisoformat(row['timestamp_utc']),
                    source_timestamp=float(row['source_timestamp']),
                    can_id=int(row['can_id']),
                    dlc=int(row['dlc']),
                    data=bytes.fromhex(row['data_hex']),
                    is_extended=row['is_extended'].lower() == 'true',
                    is_remote=row['is_remote'].lower() == 'true',
                    is_error=row['is_error'].lower() == 'true'
                )
                yield frame

    def get_stats(self) -> CandidateStats:
        """Return a snapshot of counters owned by the candidate."""
        return CandidateStats(
            frames_written=self._frame_count,
            buffered_frames=self._buffered_frames,
            flush_count=self._flush_count
        )


