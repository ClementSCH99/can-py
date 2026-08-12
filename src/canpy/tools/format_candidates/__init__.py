"""Temporary format candidates used by the compact-recording spike."""

from .base import CandidateStats, FormatCandidate
from .gzip_csv import GzipCsvCandidate

__all__ = ["CandidateStats", "FormatCandidate", "GzipCsvCandidate"]
