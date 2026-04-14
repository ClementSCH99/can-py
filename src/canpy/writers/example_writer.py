"""Example writer demonstrating extensibility"""

from datetime import datetime
from typing import Dict, Any, Optional, Set

from canpy.writers.base import BaseOutputWriter
from canpy.writers.registry import WriterFactory


@WriterFactory.register('example')
class ExampleWriter(BaseOutputWriter):
    """Example writer - counts frames, doesn't write files.
    
    This demonstrates that NEW formats can be added by:
    1. Creating a new writer class
    2. Adding @WriterFactory.register('format_name')
    3. Implementing the BaseOutputWriter interface
    
    No changes to capture.py needed—proves Open/Closed Principle.
    """
    
    def __init__(self,
                 output_dir: str = 'data',
                 expected_signals: Optional[Set[str]] = None):
        """Initialize example writer"""
        super().__init__(output_dir)
        self._frame_count = 0
        self._start_time = datetime.now()
    
    def start_streaming(self, filename: Optional[str] = None) -> Dict[str, str]:
        """Initialize (no files for this example)"""
        print(f"[ExampleWriter] Starting...")
        return {'example': 'example://memory'}  # Virtual "file"
    
    def write_frame(self, frame: Dict[str, Any]) -> None:
        """Count frame but don't write"""
        self._frame_count += 1
    
    def stop_streaming(self) -> Dict[str, str]:
        """Cleanup (nothing to close)"""
        print(f"[ExampleWriter] {self._frame_count} frames counted (not written)")
        return {'example': 'example://memory'}
    
    def get_stats(self) -> Dict[str, Any]:
        """Return stats"""
        elapsed = (datetime.now() - self._start_time).total_seconds()
        fps = self._frame_count / elapsed if elapsed > 0 else 0
        
        return {
            'frames': self._frame_count,
            'elapsed_seconds': elapsed,
            'fps': fps,
            'formats': ['example']
        }