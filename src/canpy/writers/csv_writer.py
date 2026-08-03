"""Writer for streaming CAN frame output to CSV format"""

import csv
import os
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Set

from canpy.storage import CANFrame
from canpy.writers.base import BaseOutputWriter
from canpy.writers.registry import WriterFactory

@WriterFactory.register('csv')
class CSVWriter(BaseOutputWriter):
    """Writer for streaming CAN frame output to CSV format"""
    
    def __init__(self,
                 output_dir: str = 'data',
                 expected_signals: Optional[Set[str]] = None):
        """
        Initialize CSV output writer.
        
        Args:
            output_dir: Directory to save output files
            expected_signals: Optional set of expected signal names to predefine CSV columns
        """

        # Call base constructor to set up output directory
        super().__init__(output_dir)
        
        # Generate timestamp for filename
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Streaming file handles
        self._csv_file = None
        self._csv_writer = None
        self._fieldnames = [
            'timestamp_utc',
            'source_timestamp',
            'can_id',
            'dlc',
            'data_hex',
            'is_extended',
            'is_remote',
            'is_error',
        ]
        if expected_signals:
            self._fieldnames.extend([f"{sig}" for sig in sorted(expected_signals)])
        self._frame_count = 0
        self._start_time = datetime.now()
        self._filepaths = {}
        self._header_written = False
    
    def start_streaming(self,
                        filename: Optional[str] = None,
                        ) -> Dict[str, str]:
        """
        Initialize streaming to specified formats.
        Write headers at initialization.
        
        Args:
            filename: Custom filename base (without extension)
        """
        if filename is None:
            filename = f"can_capture_{self.timestamp}"
        
        self._filename = filename
        
        # Initialize CSV
        csv_path = os.path.join(self.output_dir, f"{filename}.csv")
        self._csv_file = open(csv_path, 'w', newline='', encoding='utf-8')
        self._write_csv_header()
        self._filepaths['csv'] = csv_path
        
        return self._filepaths

    def write_frame(self, frame: CANFrame) -> None:
        """
        Write a single frame to all active streams.
        
        Args:
            frame: Standardized CAN frame
        """
        frame = self._coerce_legacy_frame(frame)
        self._frame_count += 1

        if self._csv_file:
            self._write_csv_frame(frame)

    @staticmethod
    def _coerce_legacy_frame(frame: CANFrame) -> CANFrame:
        """Keep historical callers working while CANFrame becomes canonical."""
        if isinstance(frame, CANFrame):
            return frame
        if not isinstance(frame, Mapping):
            raise TypeError("frame must be a CANFrame")

        timestamp = float(frame['timestamp'])
        can_id_value = frame['can_id']
        can_id = (
            int(can_id_value, 0)
            if isinstance(can_id_value, str)
            else int(can_id_value)
        )
        return CANFrame(
            timestamp_utc=datetime.fromtimestamp(timestamp, tz=timezone.utc),
            source_timestamp=timestamp,
            can_id=can_id,
            dlc=int(frame['dlc']),
            data=bytes.fromhex(str(frame['data_hex'])),
            is_extended=bool(frame.get('is_extended', False)),
            is_remote=bool(frame.get('is_remote', False)),
            is_error=bool(frame.get('is_error', False)),
            parsed_signals=frame.get('parsed'),
        )
    
    def _write_csv_frame(self, frame: CANFrame):
        """Write frame to CSV file"""
        if not self._csv_writer:
            return
        if not self._header_written:
            self._write_csv_header()

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

        # Add parsed signals if available
        if frame.parsed_signals:
            for signal_name, signal_value in frame.parsed_signals.items():
                flat_row[signal_name] = signal_value
            
        self._csv_writer.writerow(flat_row)
        self._csv_file.flush()
    
    def _write_csv_header(self) -> None:
        """Write CSV header with detected signal fields"""
        if not self._header_written:
            self._csv_writer = csv.DictWriter(
                self._csv_file,
                fieldnames=self._fieldnames,
                restval='',
                extrasaction='ignore'
            )
            self._csv_writer.writeheader()
            self._header_written = True
    
    def stop_streaming(self) -> Dict[str, str]:
        """Close all streaming files"""        
        if self._csv_file:
            self._csv_file.close()
            print(f"[OK] CSV file saved: {self._filepaths['csv']}")
        
        return self._filepaths
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current capture statistics"""
        elapsed = (datetime.now() - self._start_time).total_seconds()
        fps = self._frame_count / elapsed if elapsed > 0 else 0
        
        return {
            'frames': self._frame_count,
            'elapsed_seconds': elapsed,
            'fps': fps,
            'formats': ['csv']
        }
