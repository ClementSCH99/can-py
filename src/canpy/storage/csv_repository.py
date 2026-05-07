import csv
import json
import os
import tempfile
from typing import Any, Generator, Optional, Set

from .query import QueryFilter
from .repository import BaseRepository
from .frame import CANFrame

class CsvRepository(BaseRepository):
    """
    CSV-based implementation of the BaseRepository.
    
    This class handles reading/writing CAN frames to a CSV file.
    It implements the abstract methods defined in BaseRepository.
    """
    _BASE_FIELDNAMES = ['timestamp', 'can_id', 'dlc', 'data_hex']
    
    def __init__(self,
                 file_path: str,
                 expected_signals: Optional[Set[str]] = None) -> None:
        
        self.file_path = file_path
        self._file = None
        self._mode = None

        self._signal_fieldnames = sorted(expected_signals) if expected_signals else []
        self._fieldnames = [*self._BASE_FIELDNAMES, *self._signal_fieldnames]
        self._header_written = False
        self._frame_count = 0
        self._staging_file = None

    def __enter__(self) -> 'CsvRepository':
        """Enter context manager, open the file and return self."""
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        """Exit context manager, ensure the file is closed properly."""
        self.close()
        return False
    
    @classmethod
    def create(cls, file_path: str, expected_signals: Optional[Set[str]] = None) -> 'CsvRepository':
        """Factory method to create a new CsvRepository instance."""
        if os.path.dirname(file_path) and not os.path.exists(os.path.dirname(file_path)):
            raise FileNotFoundError(f"Directory {os.path.dirname(file_path)} does not exist. Please provide a valid directory.")
        
        if os.path.exists(file_path):
            raise FileExistsError(f"File {file_path} already exists. Please provide a new file path.")
        
        instance = cls(file_path, expected_signals)
        instance._file = open(file_path, 'w', newline='', encoding='utf-8')
        instance._staging_file = tempfile.TemporaryFile(mode='w+', encoding='utf-8')
        instance._mode = 'w'

        return instance

    @classmethod
    def open(cls, file_path: str, expected_signals: Optional[Set[str]] = None) -> 'CsvRepository':
        """Factory method to open an existing CsvRepository instance."""
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File {file_path} does not exist. Please provide a valid file path.")
        
        instance = cls(file_path, expected_signals)
        instance._file = open(file_path, 'r', newline='', encoding='utf-8')
        instance._mode = 'r'
        instance._header_written = True

        reader = csv.DictReader(instance._file)
        if reader.fieldnames:
            missing_fields = [field for field in cls._BASE_FIELDNAMES if field not in reader.fieldnames]
            if missing_fields:
                raise ValueError(f"Missing required CSV fields: {', '.join(missing_fields)}")
            instance._fieldnames = list(reader.fieldnames)
            instance._signal_fieldnames = [
                field for field in reader.fieldnames if field not in cls._BASE_FIELDNAMES
            ]
        else:
            instance._fieldnames = list(cls._BASE_FIELDNAMES)
            instance._signal_fieldnames = []
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
                raise ValueError(f"Failed to parse CSV row: {row}") from e
    
    def save_frame(self, frame: CANFrame) -> None:
        """Save a CANFrame to the CSV file."""
        if self._file is None or self._mode != 'w':
            raise RuntimeError("File is not open for writing. Please use 'create' method to create a new repository for writing.")
        self._register_signal_fields(frame)
        self._stage_frame(frame)
        self._frame_count += 1
    
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
                if self._mode == 'w':
                    self._flush_staged_frames()
                self._file.close()
                self._file = None
                if self._staging_file:
                    self._staging_file.close()
                    self._staging_file = None
            except Exception as e:
                raise RuntimeError(f"Error closing repository file: {e}") from e


    def _frame_to_row(self, frame: CANFrame) -> dict[str, Any]:
        """Convert CANFrame to a dictionary row for CSV writing."""
        flat_row = {
            'timestamp': str(frame.timestamp),
            'can_id': f"0x{frame.can_id:03X}",
            'dlc': str(frame.dlc),
            'data_hex': ' '.join(f"{b:02X}" for b in frame.data),
        }

        if frame.parsed_signals:
            for sig_name, sig_value in frame.parsed_signals.items():
                if sig_name in self._fieldnames:
                    flat_row[sig_name] = str(sig_value)

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
        
        parsed_signals = {}
        for key, value in row.items():
            if key not in self._BASE_FIELDNAMES and key is not None:
                if value == '':
                    continue
                try:
                    parsed_signals[key] = float(value)
                except (ValueError, TypeError):
                    parsed_signals[key] = value
        
        return CANFrame(timestamp, can_id, dlc, data, parsed_signals if parsed_signals else {})

    def _register_signal_fields(self, frame: CANFrame) -> None:
        if not frame.parsed_signals:
            return

        combined_signals = set(self._signal_fieldnames)
        combined_signals.update(frame.parsed_signals.keys())
        self._signal_fieldnames = sorted(combined_signals)
        self._fieldnames = [*self._BASE_FIELDNAMES, *self._signal_fieldnames]

    def _stage_frame(self, frame: CANFrame) -> None:
        if self._staging_file is None:
            raise RuntimeError("Repository staging file is not initialized for writing.")

        staging_record = {
            'timestamp': frame.timestamp,
            'can_id': frame.can_id,
            'dlc': frame.dlc,
            'data_hex': frame.data.hex(),
            'parsed_signals': frame.parsed_signals or {},
        }
        self._staging_file.write(json.dumps(staging_record) + '\n')

    def _flush_staged_frames(self) -> None:
        if self._header_written:
            return

        if self._staging_file is None:
            raise RuntimeError("Repository staging file is not initialized for writing.")

        writer = csv.DictWriter(
            self._file,
            fieldnames=self._fieldnames,
            restval='',
            extrasaction='ignore',
        )
        writer.writeheader()

        self._staging_file.seek(0)
        for line in self._staging_file:
            if not line.strip():
                continue

            record = json.loads(line)
            frame = CANFrame(
                timestamp=float(record['timestamp']),
                can_id=int(record['can_id']),
                dlc=int(record['dlc']),
                data=bytes.fromhex(record['data_hex']),
                parsed_signals=record.get('parsed_signals') or {},
            )
            writer.writerow(self._frame_to_row(frame))

        self._file.flush()
        self._header_written = True


CSVRepository = CsvRepository