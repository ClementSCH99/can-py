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
                   'timestamp' (float): Unix timestamp
                   'can_id' (str): CAN ID in hex format (e.g., '0x100')
                   'dlc' (int): Data length code
                   'data_hex' (str): Raw CAN data in hex
                   'parsed' (dict, optional): Decoded signals from DBC
        
        Returns:
            None. Side effect: writes frame to output stream/file.
        """
        pass

    @abstractmethod
    def start_streaming(self, filename: Optional[str] = None) -> Dict[str, str]:
        """Initialize streaming and prepare output files.
        
        Called once before writing frames. Each writer handles one format implicitly.
        
        Args:
            filename: Optional base filename for output files. If None, generates
                      default name based on timestamp (e.g., 'can_capture_20260414_120000').
        
        Returns:
            Dict mapping format name to absolute file path.
            Example: {'csv': '/full/path/to/can_capture_20260414_120000.csv'}
        """
        pass
    
    @abstractmethod
    def stop_streaming(self) -> Dict[str, str]:
        """Flush remaining frames and close output files.
        
        Called once after all frames processed. Ensures all buffered data is written
        and file handles are properly closed.
        
        Returns:
            Dict mapping format name to absolute file path (same as start_streaming).
            Example: {'csv': '/full/path/to/can_capture_20260414_120000.csv'}
        """
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Return current capture statistics.
        
        Can be called at any time during capture (e.g., for periodic logging).
        
        Returns:
            Dict with keys:
            - 'frames' (int): Total frames written
            - 'elapsed_seconds' (float): Time since start_streaming() called
            - 'fps' (float): Frames per second rate
            - 'formats' (list): Format name(s) handled by this writer
            
            Example: {'frames': 1000, 'elapsed_seconds': 20.5, 'fps': 48.8, 'formats': ['csv']}
        """
        pass
        pass