"""Tests for Phase 4: Extensibility - proving new writers can be added without modifying capture.py

This test suite validates the Open/Closed Principle: the system is open for extension
(adding new writers) but closed for modification (capture.py remains unchanged).

Key Learning:
    - Factory pattern decouples capture.py from writer implementations
    - Decorators enable self-registration without central configuration
    - New formats require only a new file + import, zero capture.py changes
"""

import tempfile
import pytest

from canpy.writers.registry import WriterFactory
from canpy.writers.example_writer import ExampleWriter
from canpy.writers.csv_writer import CSVWriter
from canpy.writers.json_writer import JSONWriter
from canpy.writers.base import BaseOutputWriter


class TestPhase4Extensibility:
    """Prove Open/Closed Principle: new writers work without changing capture.py"""
    
    def test_example_writer_is_registered(self):
        """Verify ExampleWriter is automatically registered in WriterFactory.
        
        This tests decorator-based self-registration: @WriterFactory.register()
        should have been triggered on import, making 'example' format available.
        """
        formats = WriterFactory.list_formats()
        assert 'example' in formats, (
            "ExampleWriter not registered. Ensure @WriterFactory.register('example') "
            "decorator is present and module is imported."
        )
    
    def test_example_writer_can_be_instantiated_via_factory(self):
        """Verify WriterFactory can create ExampleWriter instances.
        
        This tests the factory pattern decouples capture.py from concrete classes.
        capture.py never imports ExampleWriter directly; it just requests 'example'.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = WriterFactory.create('example', output_dir=tmpdir)
            assert isinstance(writer, ExampleWriter), (
                f"Factory returned {type(writer)}, expected ExampleWriter"
            )
            assert writer.output_dir == tmpdir
    
    def test_example_writer_implements_base_interface(self):
        """Verify ExampleWriter implements all BaseOutputWriter abstract methods.
        
        This ensures any writer registered with factory meets the contract,
        making them compatible with capture.py's writer loop.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = WriterFactory.create('example', output_dir=tmpdir)
            
            # Verify it's a BaseOutputWriter
            assert isinstance(writer, BaseOutputWriter), (
                "ExampleWriter must inherit from BaseOutputWriter"
            )
            
            # Verify all required methods exist
            required_methods = ['start_streaming', 'write_frame', 'stop_streaming', 'get_stats']
            for method_name in required_methods:
                assert hasattr(writer, method_name), (
                    f"ExampleWriter missing required method: {method_name}"
                )
                assert callable(getattr(writer, method_name)), (
                    f"{method_name} must be callable"
                )
    
    def test_example_writer_lifecycle(self):
        """Verify ExampleWriter follows the lifecycle used by capture.py.
        
        capture.py does:
            1. writer = factory.create(fmt, ...)
            2. writer.start_streaming()
            3. writer.write_frame(frame) in loop
            4. writer.stop_streaming()
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = WriterFactory.create('example', output_dir=tmpdir)
            
            # Start streaming
            paths = writer.start_streaming()
            assert isinstance(paths, dict), "start_streaming() must return dict"
            
            # Write frames (like capture.py does in loop)
            frame = {
                'timestamp': 1234567890.123,
                'can_id': 0x100,
                'dlc': 8,
                'data_hex': '0102030405060708',
                'parsed': {'RPM': 5000, 'Speed': 120}
            }
            
            for i in range(10):
                writer.write_frame(frame)
            
            # Get stats
            stats = writer.get_stats()
            assert stats['frames'] == 10, f"Expected 10 frames, got {stats['frames']}"
            assert 'elapsed_seconds' in stats
            assert 'fps' in stats
            assert 'formats' in stats
            assert stats['formats'] == ['example']
            
            # Stop streaming
            paths = writer.stop_streaming()
            assert isinstance(paths, dict), "stop_streaming() must return dict"
    
    def test_three_formats_coexist_without_capture_modification(self):
        """Prove extensibility: capture.py code works with CSV, JSON, and Example.
        
        This test mimics capture.py's writer loop (lines 172-178 in capture.py):
            for fmt in log_formats:
                writer = WriterFactory.create(fmt, ...)
                writer.start_streaming()
                writers[fmt] = writer
        
        The key: capture.py code is UNCHANGED and works with all three formats.
        Adding a 4th format (BinaryWriter, etc.) requires no capture.py modification.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # This is capture.py's loop (unchanged)
            log_formats = ['csv', 'json', 'example']
            writers = {}
            
            for fmt in log_formats:
                writer = WriterFactory.create(
                    fmt,
                    output_dir=tmpdir,
                    expected_signals={'RPM', 'Speed'}
                )
                writer.start_streaming()
                writers[fmt] = writer
            
            # Verify all three were created
            assert len(writers) == 3, f"Expected 3 writers, got {len(writers)}"
            assert 'csv' in writers
            assert 'json' in writers
            assert 'example' in writers
            
            # Simulate frame processing (capture.py's write loop)
            frame = {
                'timestamp': 1234567890.123,
                'can_id': 0x100,
                'dlc': 8,
                'data_hex': 'AABBCCDD',
                'parsed': {'RPM': 5000, 'Speed': 120}
            }
            
            for writer in writers.values():
                writer.write_frame(frame)
            
            # Verify all writers processed the frame
            for fmt, writer in writers.items():
                stats = writer.get_stats()
                assert stats['frames'] == 1, (
                    f"{fmt} writer didn't record frame: {stats['frames']}"
                )
            
            # Cleanup (capture.py's finally block)
            for writer in writers.values():
                writer.stop_streaming()
    
    def test_open_closed_principle(self):
        """Meta-test: Verify architecture satisfies Open/Closed Principle.
        
        Definition:
            - Open for extension: Can add new writers (ExampleWriter added ✓)
            - Closed for modification: capture.py unchanged ✓
        
        This test documents the architectural achievement of Phase 1.1.
        """
        # Extension: ExampleWriter added
        formats_before = {'csv', 'json'}
        formats_after = set(WriterFactory.list_formats())
        
        assert 'example' in formats_after, "New format should be registered"
        assert 'csv' in formats_after, "Existing formats preserved"
        assert 'json' in formats_after, "Existing formats preserved"
        
        # No modification: capture.py doesn't import ExampleWriter
        # (This is a documentation assertion, not testable directly)
        # Instead, we verify that factory creates it without capture.py knowing
        writer = WriterFactory.create('example', output_dir='data')
        assert isinstance(writer, ExampleWriter), (
            "Factory can create ExampleWriter without capture.py importing it"
        )
