"""Writer for streaming CAN frame output to CSV format"""

import csv
import os
from datetime import datetime
from typing import Dict, Any, Optional, Set

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
        self._fieldnames = ['timestamp', 'can_id', 'dlc', 'data_hex']
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

    def write_frame(self, frame: Dict[str, Any]) -> None:
        """
        Write a single frame to all active streams.
        
        Args:
            frame: Parsed frame dictionary
        """
        self._frame_count += 1

        if self._csv_file:
            self._write_csv_frame(frame)
    
    def _write_csv_frame(self, frame: Dict[str, Any]):
        """Write frame to CSV file"""
        if not self._csv_writer:
            return
        if not self._header_written:
            self._write_csv_header()

        flat_row = {
            'timestamp': frame['timestamp'],
            'can_id': frame['can_id'],
            'dlc': frame['dlc'],
            'data_hex': frame['data_hex'],
        }

        # Add parsed signals if available
        if frame.get('parsed'):
            for signal_name, signal_value in frame['parsed'].items():
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
