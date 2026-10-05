"""Small command-line tools used to validate CAN-PY behavior."""

# Import the lightweight candidate directly.  Importing the package-level
# ``format_candidates`` module also imports the optional Parquet candidates,
# which would make unrelated tools (including the NHR CSV merger) require
# PyArrow merely to start.
from .format_candidates.gzip_csv import GzipCsvCandidate

__all__ = ["GzipCsvCandidate"]
