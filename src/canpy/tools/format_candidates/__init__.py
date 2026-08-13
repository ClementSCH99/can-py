"""Temporary format candidates used by the compact-recording spike."""

from .base import CandidateStats, FormatCandidate
from .blf import BlfCandidate
from .gzip_csv import GzipCsvCandidate

__all__ = [
    "BlfCandidate",
    "CandidateStats",
    "FormatCandidate",
    "GzipCsvCandidate",
]
