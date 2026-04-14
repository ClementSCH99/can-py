"""Tests for CSVWriter and JSONWriter implementations"""

import pytest
import tempfile

from canpy.writers import (
    BaseOutputWriter,
    WriterFactory,
    CSVWriter,
    JSONWriter
)


class TestWriterImplementations:
    """Test actual CSVWriter and JSONWriter behavior.
    
    These tests assume writers are already registered via decorators.
    No setup_method() clearing the registry.
    """
    
    # TEST 1: Factory creates correct writer instances
    def test_factory_creates_csv_writer(self):
        """Verify factory can instantiate CSVWriter from registry"""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = WriterFactory.create('csv', output_dir=tmpdir)
            assert isinstance(writer, CSVWriter)
            assert writer.output_dir == tmpdir
    
    # TEST 2: Factory creates JSONWriter instance
    def test_factory_creates_json_writer(self):
        """Verify factory can instantiate JSONWriter from registry"""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = WriterFactory.create('json', output_dir=tmpdir)
            assert isinstance(writer, JSONWriter)
            assert writer.output_dir == tmpdir
    
    # TEST 3: Both writers implement BaseOutputWriter interface
    def test_both_writers_implement_base_interface(self):
        """Verify both writers have BaseOutputWriter interface"""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_writer = WriterFactory.create('csv', output_dir=tmpdir)
            json_writer = WriterFactory.create('json', output_dir=tmpdir)
            
            # Check they're instances of BaseOutputWriter
            assert isinstance(csv_writer, BaseOutputWriter)
            assert isinstance(json_writer, BaseOutputWriter)
            
            # Check they have required methods
            required_methods = ['start_streaming', 'write_frame', 'stop_streaming', 'get_stats']
            for method in required_methods:
                assert hasattr(csv_writer, method), f"CSVWriter missing {method}"
                assert hasattr(json_writer, method), f"JSONWriter missing {method}"
    
    # TEST 4: Verify 'csv' and 'json' formats are registered
    def test_csv_and_json_registered(self):
        """Verify that 'csv' and 'json' formats are in registry"""
        formats = WriterFactory.list_formats()
        assert 'csv' in formats, "CSV format not registered"
        assert 'json' in formats, "JSON format not registered"