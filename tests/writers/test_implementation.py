"""Tests for CSVWriter and JSONWriter implementations"""

import csv
import json
import pytest
import tempfile
from datetime import datetime, timezone

from canpy.storage import CANFrame
from canpy.writers import (
    BaseOutputWriter,
    WriterFactory,
    CSVWriter,
    JSONWriter
)

TIMESTAMP_UTC = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


def complete_frame():
    return CANFrame(
        timestamp_utc=TIMESTAMP_UTC,
        source_timestamp=123.456,
        can_id=0x18FF50E5,
        dlc=4,
        data=bytes.fromhex("01 02 03 04"),
        is_extended=True,
        is_remote=False,
        is_error=True,
        parsed_signals={"Voltage": 48.5},
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

    def test_csv_writer_preserves_can_frame_contract(self, tmp_path):
        writer = CSVWriter(
            output_dir=str(tmp_path),
            expected_signals={"Voltage"},
        )
        paths = writer.start_streaming(filename="contract")
        writer.write_frame(complete_frame())
        writer.stop_streaming()

        with open(paths["csv"], newline="", encoding="utf-8") as handle:
            row = next(csv.DictReader(handle))

        assert row["timestamp_utc"] == TIMESTAMP_UTC.isoformat()
        assert row["source_timestamp"] == "123.456"
        assert row["can_id"] == str(0x18FF50E5)
        assert row["dlc"] == "4"
        assert row["data_hex"] == "01020304"
        assert row["is_extended"] == "True"
        assert row["is_remote"] == "False"
        assert row["is_error"] == "True"
        assert row["Voltage"] == "48.5"

    def test_json_writer_preserves_can_frame_contract(self, tmp_path):
        writer = JSONWriter(output_dir=str(tmp_path))
        paths = writer.start_streaming(filename="contract")
        writer.write_frame(complete_frame())
        writer.stop_streaming()

        with open(paths["json"], encoding="utf-8") as handle:
            row = json.loads(handle.readline())

        assert row == {
            "timestamp_utc": TIMESTAMP_UTC.isoformat(),
            "source_timestamp": 123.456,
            "can_id": 0x18FF50E5,
            "dlc": 4,
            "data_hex": "01020304",
            "is_extended": True,
            "is_remote": False,
            "is_error": True,
            "parsed_signals": {"Voltage": 48.5},
        }
