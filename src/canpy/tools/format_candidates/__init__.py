"""Temporary format candidates used by the compact-recording spike."""

from .base import CandidateStats, FormatCandidate
from .blf import BlfCandidate
from .gzip_csv import GzipCsvCandidate

__all__ = [
    "BlfCandidate",
    "CandidateStats",
    "FormatCandidate",
    "GzipCsvCandidate",
    "ParquetCandidate",
    "SegmentedParquetCandidate",
]


def __getattr__(name: str):
    """Load PyArrow-backed candidates only when they are requested."""
    if name == "ParquetCandidate":
        from .parquet import ParquetCandidate

        return ParquetCandidate
    if name == "SegmentedParquetCandidate":
        from .segmented_parquet import SegmentedParquetCandidate

        return SegmentedParquetCandidate
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
