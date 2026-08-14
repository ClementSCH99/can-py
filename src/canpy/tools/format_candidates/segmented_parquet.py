"""Minimal segmented-Parquet prototype for the format-decision spike."""

import os
import shutil
from pathlib import Path
from typing import Callable, Iterator, List, Optional

import pyarrow.parquet as pq

from canpy.storage import CANFrame

from .base import CandidateStats, FormatCandidate
from .parquet import PARQUET_SCHEMA, ParquetCandidate, _validate_positive_int


MergeProgressHook = Callable[[int, Path], None]


def staging_directory(final_path: Path) -> Path:
    """Return the persistent working directory associated with one recording."""
    final_path = Path(final_path)
    return final_path.with_name(f"{final_path.name}.inprogress")


def merged_partial_path(final_path: Path) -> Path:
    """Return the temporary output used while finalized segments are merged."""
    final_path = Path(final_path)
    return final_path.with_name(f"{final_path.name}.partial")


def finalized_segment_paths(final_path: Path) -> List[Path]:
    """List committed segments in deterministic recording order."""
    return sorted(staging_directory(final_path).glob("segment_*.parquet"))


def merge_finalized_segments(
    final_path: Path,
    compression: str = "zstd",
    after_segment: Optional[MergeProgressHook] = None,
) -> int:
    """Merge committed segments atomically, retaining them if merging fails."""
    final_path = Path(final_path)
    segments = finalized_segment_paths(final_path)
    if not segments:
        raise ValueError("No finalized Parquet segments are available to merge")

    partial_path = merged_partial_path(final_path)
    expected_rows = 0
    writer = pq.ParquetWriter(partial_path, PARQUET_SCHEMA, compression=compression)
    try:
        for index, segment_path in enumerate(segments, start=1):
            with pq.ParquetFile(segment_path) as segment_file:
                if segment_file.schema_arrow != PARQUET_SCHEMA:
                    raise ValueError(f"Unexpected schema in segment: {segment_path}")
                expected_rows += segment_file.metadata.num_rows
                for row_group_index in range(segment_file.num_row_groups):
                    writer.write_table(segment_file.read_row_group(row_group_index))

            if after_segment is not None:
                after_segment(index, segment_path)
    finally:
        writer.close()

    merged_rows = pq.ParquetFile(partial_path).metadata.num_rows
    if merged_rows != expected_rows:
        raise RuntimeError(
            f"Merged Parquet row count mismatch: {merged_rows} != {expected_rows}"
        )

    os.replace(partial_path, final_path)
    shutil.rmtree(staging_directory(final_path))
    return merged_rows


class SegmentedParquetCandidate(FormatCandidate):
    """Finalize bounded Parquet segments before producing one final file."""

    name = "segmented_parquet"
    suffix = ".parquet"

    def __init__(
        self,
        segment_frames: int = 10_000,
        row_group_size: int = 10_000,
        compression: str = "zstd",
    ) -> None:
        self.segment_frames = _validate_positive_int(segment_frames)
        self.row_group_size = _validate_positive_int(row_group_size)
        self.compression = compression

        # Reuse ParquetCandidate validation for the selected codec.
        ParquetCandidate(row_group_size=row_group_size, compression=compression)

        self._final_path: Optional[Path] = None
        self._current_candidate: Optional[ParquetCandidate] = None
        self._current_partial_path: Optional[Path] = None
        self._segment_index = 0
        self._frames_in_segment = 0
        self._frame_count = 0
        self._flush_count = 0

    def start(self, output_path: Path) -> None:
        """Create a persistent staging directory beside the final recording."""
        if self._final_path is not None:
            raise RuntimeError("Segmented Parquet writer already started")

        output_path = Path(output_path)
        work_dir = staging_directory(output_path)
        if output_path.exists() or work_dir.exists():
            raise FileExistsError(f"Recording output already exists: {output_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        work_dir.mkdir()
        self._final_path = output_path
        self._segment_index = 0
        self._frames_in_segment = 0
        self._frame_count = 0
        self._flush_count = 0

    def _start_segment(self) -> None:
        if self._final_path is None:
            raise RuntimeError("start() must be called before writing frames")

        self._segment_index += 1
        segment_name = f"segment_{self._segment_index:06d}.parquet.partial"
        self._current_partial_path = staging_directory(self._final_path) / segment_name
        self._current_candidate = ParquetCandidate(
            row_group_size=self.row_group_size,
            compression=self.compression,
        )
        self._current_candidate.start(self._current_partial_path)
        self._frames_in_segment = 0

    def _finalize_current_segment(self) -> None:
        if self._current_candidate is None or self._current_partial_path is None:
            return

        self._current_candidate.close()
        self._flush_count += self._current_candidate.get_stats().flush_count
        finalized_path = self._current_partial_path.with_suffix("")
        os.replace(self._current_partial_path, finalized_path)
        self._current_candidate = None
        self._current_partial_path = None
        self._frames_in_segment = 0

    def write_frame(self, frame: CANFrame) -> None:
        """Write one frame and finalize the segment at its configured boundary."""
        if self._final_path is None:
            raise RuntimeError("start() must be called before write_frame()")
        if self._current_candidate is None:
            self._start_segment()

        assert self._current_candidate is not None
        self._current_candidate.write_frame(frame)
        self._frames_in_segment += 1
        self._frame_count += 1

        if self._frames_in_segment >= self.segment_frames:
            self._finalize_current_segment()

    def close(self) -> None:
        """Finalize the active segment, merge atomically, then remove staging."""
        if self._final_path is None:
            return

        self._finalize_current_segment()
        merge_finalized_segments(self._final_path, compression=self.compression)
        self._final_path = None

    def read_frames(self, input_path: Path) -> Iterator[CANFrame]:
        """Read the final file, or committed segments when finalization was interrupted."""
        input_path = Path(input_path)
        reader = ParquetCandidate(
            row_group_size=self.row_group_size,
            compression=self.compression,
        )
        if input_path.exists():
            yield from reader.read_frames(input_path)
            return

        for segment_path in finalized_segment_paths(input_path):
            yield from reader.read_frames(segment_path)

    def get_stats(self) -> CandidateStats:
        """Return counters for this prototype recording."""
        buffered_frames = 0
        if self._current_candidate is not None:
            buffered_frames = self._current_candidate.get_stats().buffered_frames
        return CandidateStats(
            frames_written=self._frame_count,
            buffered_frames=buffered_frames,
            flush_count=self._flush_count,
        )
