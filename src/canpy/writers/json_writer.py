"""Writer for streaming CAN frame output to JSON format"""

import json
import os
from datetime import datetime
from typing import Dict, Any, Optional, Set

from canpy.writers.base import BaseOutputWriter
from canpy.writers.registry import WriterFactory

@WriterFactory.register('json')
class JSONWriter(BaseOutputWriter):
    """Writer for streaming CAN frame output to JSON format"""
    
    def __init__(self,
                 output_dir: str = 'data',
                 expected_signals: Optional[Set[str]] = None):
        """
        Initialize JSON output writer.
        
        Args:
            output_dir: Directory to save output files
            expected_signals: Optional set of expected signal names to predefine JSON fields
        """

        # Call base constructor to set up output directory
        super().__init__(output_dir)
        
        # Generate timestamp for filename
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Streaming file handles
        self._json_file = None
        self._frame_count = 0
        self._start_time = datetime.now()
        self._filepaths = {}
    
    def start_streaming(self,
                        filename: Optional[str] = None,
                        ) -> Dict[str, str]:
        """
        Initialize streaming to specified formats.
        Prepare JSON file for newline-delimited output.
        
        Args:
            filename: Custom filename base (without extension)
        """
        if filename is None:
            filename = f"can_capture_{self.timestamp}"
        
        self._filename = filename
        
        # Initialize JSON
        json_path = os.path.join(self.output_dir, f"{filename}.ndjson")
        self._json_file = open(json_path, 'w', encoding='utf-8')
        self._filepaths['json'] = json_path
        
        return self._filepaths

    def write_frame(self, frame: Dict[str, Any]) -> None:
        """
        Write a single frame to all active streams.
        
        Args:
            frame: Parsed frame dictionary
        """
        self._frame_count += 1
        
        if self._json_file:
            self._write_json_frame(frame)
    
    def _write_json_frame(self, frame: Dict[str, Any]):
        """Write frame to JSON stream (newline-delimited)"""
        json_frame = self._make_json_serializable(frame)
        self._json_file.write(json.dumps(json_frame) + '\n')
        self._json_file.flush()
    
    def _make_json_serializable(self, obj):
        """Convert objects to JSON-serializable types"""
        if isinstance(obj, dict):
            return {k: self._make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._make_json_serializable(item) for item in obj]
        elif isinstance(obj, bytes):
            return obj.hex()
        elif isinstance(obj, (int, float, str, bool, type(None))):
            return obj
        else:
            return str(obj)
    
    def stop_streaming(self) -> Dict[str, str]:
        """Close all streaming files"""        
        if self._json_file:
            self._json_file.close()
            print(f"[OK] NDJSON file saved: {self._filepaths['json']}")
        
        return self._filepaths
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current capture statistics"""
        elapsed = (datetime.now() - self._start_time).total_seconds()
        fps = self._frame_count / elapsed if elapsed > 0 else 0
        
        return {
            'frames': self._frame_count,
            'elapsed_seconds': elapsed,
            'fps': fps,
            'formats': ['json']
        }
