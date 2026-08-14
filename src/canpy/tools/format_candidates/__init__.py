"""Temporary format candidates used by the compact-recording spike."""

from .base import CandidateStats, FormatCandidate
from .blf import BlfCandidate
from .gzip_csv import GzipCsvCandidate
from .parquet import ParquetCandidate
from .segmented_parquet import SegmentedParquetCandidate

__all__ = [
    "BlfCandidate",
    "CandidateStats",
    "FormatCandidate",
    "GzipCsvCandidate",
    "ParquetCandidate",
    "SegmentedParquetCandidate",
]
