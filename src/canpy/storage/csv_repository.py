# src/storage/csv_repository.py

import csv

from .query import QueryFilter
from .repository import BaseRepository
from .frame import CANFrame

from typing import Any, Generator, Optional, Set
import os


class CSVRepository(BaseRepository):
    """
    CSV-based implementation of the BaseRepository.
    
    This class handles reading/writing CAN frames to a CSV file.
    It implements the abstract methods defined in BaseRepository.
    """
    
    def __init__(self,
                 file_path: str,
                 expected_signals: Optional[Set[str]] = None) -> None:
        
        self.file_path = file_path
        self._file = None
        self._mode = None

        self._fieldnames = ['timestamp', 'can_id', 'dlc', 'data_hex']
        if expected_signals:
            self._fieldnames.extend([f"{sig}" for sig in sorted(expected_signals)])
        self._header_written = False
        self._frame_count = 0

    def __enter__(self) -> 'CSVRepository':
        """Enter context manager, open the file and return self."""
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        """Exit context manager, ensure the file is closed properly."""
        self.close()
        return False
    
    @classmethod
    def create(cls, file_path: str, expected_signals: Optional[Set[str]] = None) -> 'CSVRepository':
        """Factory method to create a new CSVRepository instance."""
        if os.path.dirname(file_path) and not os.path.exists(os.path.dirname(file_path)):
            raise FileNotFoundError(f"Directory {os.path.dirname(file_path)} does not exist. Please provide a valid directory.")
        
        if os.path.exists(file_path):
            raise FileExistsError(f"File {file_path} already exists. Please provide a new file path.")
        
        instance = cls(file_path, expected_signals)
        instance._file = open(file_path, 'w', newline='', encoding='utf-8')
        instance._mode = 'w'

        return instance

    @classmethod
    def open(cls, file_path: str, expected_signals: Optional[Set[str]] = None) -> 'CSVRepository':
        """Factory method to open an existing CSVRepository instance."""
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File {file_path} does not exist. Please provide a valid file path.")
        
        instance = cls(file_path, expected_signals)
        instance._file = open(file_path, 'r', newline='', encoding='utf-8')
        instance._mode = 'r'
        instance._header_written = True  # Assume header is already present in existing file 

        if instance._file:
            reader = csv.DictReader(instance._file)
            if reader.fieldnames:
                for field in instance._fieldnames:
                    if field not in reader.fieldnames:
                        raise ValueError(f"Expected field '{field}' not found in CSV header.")
            else:
                print("[INFO] CSV file is empty or missing header.")
        return instance
    
    def get_frames(self, query_filter: Optional[QueryFilter] = None) -> Generator[CANFrame, None, None]:
        """Generator that yields CANFrames matching the query filter."""
        if self._file is None or self._mode != 'r':
            raise RuntimeError("File is not open for reading. Please use 'open' method to open an existing repository for reading.")
        
        self._file.seek(0)  # Ensure we start from the beginning of the file
        reader = csv.DictReader(self._file)

        if query_filter is None:
            query_filter = QueryFilter()  # Create an empty filter that matches all frames

        yielded_frames = 0
        
        for row in reader:
            try:
                frame = self._row_to_frame(row)
                if query_filter.matches(frame):
                    yielded_frames += 1
                    yield frame
                    if query_filter.limit and yielded_frames >= query_filter.limit:
                        break
            except Exception as e:
                print(f"Error parsing row: {e}. Row content: {row}")
    
    def save_frame(self, frame: CANFrame) -> None:
        """Save a CANFrame to the CSV file."""
        if self._file is None or self._mode != 'w':
            raise RuntimeError("File is not open for writing. Please use 'create' method to create a new repository for writing.")
        self._write_frame(frame)
    
    def count(self) -> int:
        """Return the total number of frames in the repository."""
        if self._file is None:
            raise RuntimeError("File is not open. Please use 'open' or 'create' method to open a repository.")
        
        if self._mode == 'w':
            return self._frame_count
        
        elif self._mode == 'r':
            self._file.seek(0)  # Ensure we start from the beginning of the file
            reader = csv.DictReader(self._file)
            return sum(1 for _ in reader)

        else:
            raise RuntimeError("Unknown file mode. Repository is in an invalid state.")
    
    def close(self) -> None:
        """Close the CSV file handle."""
        if self._file:
            try:
                self._file.close()
                self._file = None
            except Exception as e:
                print(f"Error closing file: {e}")


    def _frame_to_row(self, frame: CANFrame) -> dict[str, Any]:
        """Convert CANFrame to a dictionary row for CSV writing."""
        flat_row = {
            'timestamp': str(frame.timestamp),
            'can_id': f"0x{frame.can_id:03X}",
            'dlc': str(frame.dlc),
            'data_hex': ' '.join(f"{b:02X}" for b in frame.data),
        }

        # Only include signals that were declared in expected_signals
        if frame.parsed_signals:
            for sig_name, sig_value in frame.parsed_signals.items():
                # Only write if signal is in fieldnames (was declared upfront)
                # TODO: improve this by allowing dynamic discovery of new signals and updating fieldnames on the fly, but that requires rewriting the CSV header which is non-trivial with DictWriter.
                if sig_name in self._fieldnames:
                    flat_row[sig_name] = str(sig_value)

        # Fill in missing signals with empty strings
        for fieldname in self._fieldnames:
            if fieldname not in flat_row:
                flat_row[fieldname] = ''

        return flat_row
    
    def _row_to_frame(self, row: dict[str, Any]) -> CANFrame:
        """Convert a CSV row dictionary back to a CANFrame."""
        timestamp = float(row['timestamp'])
        can_id = int(row['can_id'], 16)
        dlc = int(row['dlc'])
        data = bytes.fromhex(row['data_hex'].replace(' ', ''))
        
        # Extract signals, skipping base fields and None keys
        parsed_signals = {}
        for key, value in row.items():
            # Skip base fields and None keys (from csv.DictReader with extra columns)
            if key not in ['timestamp', 'can_id', 'dlc', 'data_hex'] and key is not None:
                # Skip empty strings (missing values for optional signals)
                if value == '':
                    continue
                # Try to convert to float, otherwise keep as string
                try:
                    parsed_signals[key] = float(value)
                except (ValueError, TypeError):
                    parsed_signals[key] = value
        
        # Return empty dict if no signals (for cleaner round-trip behavior)
        return CANFrame(timestamp, can_id, dlc, data, parsed_signals if parsed_signals else {})
    
    def _discover_signals(self, frame: CANFrame) -> None:
        """
        Note: Dynamic signal discovery is not supported.
        
        All signals must be declared upfront via expected_signals parameter
        in create() method. This ensures CSV header is stable and DictWriter
        doesn't encounter unexpected columns.
        
        If a frame has signals not in expected_signals, they are silently
        ignored to maintain CSV consistency.
        """
        # This method is kept for compatibility but does nothing.
        # Dynamic signal discovery was problematic with DictWriter.
        # TODO: In the future, consider implementing dynamic signal discovery with a more flexible CSV structure or by rewriting the CSV header when new signals are discovered, but that is non-trivial and may require a different approach than DictWriter.
        pass
    
    def _writer_header(self) -> None:
        """Write the CSV header if it hasn't been written yet."""
        if self._header_written:
            return
        
        # Preconditon: self._file is open and self._mode is 'w'
        writer = csv.DictWriter(self._file, fieldnames=self._fieldnames) 
        writer.writeheader()
        self._header_written = True

    def _write_frame(self, frame: CANFrame) -> None:
        """Write a single CANFrame to the CSV file."""
        self._writer_header()
        
        writer = csv.DictWriter(self._file, fieldnames=self._fieldnames)
        row = self._frame_to_row(frame)
        writer.writerow(row)
        self._frame_count += 1