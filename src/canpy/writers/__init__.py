"""Writers for outputting CAN data to various formats.

This module provides format-specific writers (CSV, JSON, Example) that implement
the BaseOutputWriter interface. Writers are registered with WriterFactory via
decorators, enabling plug-and-play extensibility without modifying capture.py.

Example:
    Create a writer via factory:
    
    >>> from canpy.writers import WriterFactory
    >>> writer = WriterFactory.create('csv', output_dir='data')
    >>> writer.start_streaming()
    >>> writer.write_frame(frame_data)
    >>> writer.stop_streaming()
"""

from .base import BaseOutputWriter
from .csv_writer import CSVWriter
from .json_writer import JSONWriter
from .registry import WriterFactory
from .example_writer import ExampleWriter

__all__ = [
    'BaseOutputWriter',
    'CSVWriter',
    'JSONWriter',
    'ExampleWriter',
    'WriterFactory'
]