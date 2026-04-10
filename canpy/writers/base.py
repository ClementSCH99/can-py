from abc import ABC, abstractmethod
import os
from typing import Dict, Any, Optional, List

class BaseOutputWriter(ABC):
    """Abstract base class for CAN data writers.
    
    Implementations handle frame buffering, file I/O, and format-specific
    serialization transparently. The caller just calls write_frame() in a loop.
    """

    def __init__(self, output_dir: str) -> None:
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
    
    @abstractmethod
    def write_frame(self, frame: Dict[str, Any]) -> None:
        """Write a single CAN frame.
        
        Buffering is handled transparently by the implementation.
        Raises IOError if write fails.
        
        Args:
            frame: Parsed frame dictionary with keys:
                   'timestamp', 'can_id', 'dlc', 'data_hex', 'parsed' (optional)
        """
        pass

    @abstractmethod
    def start_streaming(self, formats: List[str], filename: Optional[str] = None) -> Dict[str, str]:
        """Initialize streaming to selected formats and return file paths.
        
        Args:
            formats: List of format names to stream, e.g., ['csv', 'json']
            filename: Optional base filename for output files. If None, a default
                      name based on timestamp will be used.
        
        Returns:
            Dict mapping format name to file path, e.g.:
            {'csv': '/data/capture_20260410_120000.csv', 
             'json': '/data/capture_20260410_120000.ndjson'}
        """
        pass
    
    @abstractmethod
    def stop_streaming(self) -> Dict[str, str]:
        """Flush remaining frames, close files, and return file paths.
        
        Returns:
            Dict mapping format name to file path, e.g.:
            {'csv': '/data/capture_20260410_120000.csv', 
             'json': '/data/capture_20260410_120000.ndjson'}
        """
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Return current capture statistics.
        
        Returns:
            Dict with keys: 'frames', 'elapsed_seconds', 'fps', 'formats'
        """
        pass