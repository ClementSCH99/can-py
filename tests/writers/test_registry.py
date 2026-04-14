# tests/test_registry.py

import pytest
import tempfile

from canpy.writers import (
    BaseOutputWriter,
    WriterFactory,
    CSVWriter,
    JSONWriter
)


# Test fixtures
class DummyWriter(BaseOutputWriter):
    """Minimal writer for testing"""
    def write_frame(self, frame): pass
    def start_streaming(self, formats, filename=None): return {}
    def stop_streaming(self): return {}
    def get_stats(self): return {}


class NotAWriter:
    """Doesn't inherit from BaseOutputWriter"""
    pass


# TODO: Use tempfile.TemporaryDirectory to avoid filesystem side effects ???

class TestWriterFactory:
    
    def setup_method(self):
        """Clear registry before each test"""
        WriterFactory._writers.clear()
    
    # TEST 1: Basic registration and creation
    def test_register_and_create(self):
        """Writer can be registered and retrieved"""
        @WriterFactory.register('dummy')
        class TestWriter(BaseOutputWriter):
            def __init__(self, output_dir='data') -> None:
                super().__init__(output_dir)

            def write_frame(self, frame): pass
            def start_streaming(self, formats, filename=None): return {}
            def stop_streaming(self): return {}
            def get_stats(self): return {}
        
        writer = WriterFactory.create('dummy')
        
        assert isinstance(writer, TestWriter)
    
    # TEST 2: Factory passes kwargs to constructor
    def test_create_with_kwargs(self):
        """Factory forwards kwargs to writer constructor"""
        @WriterFactory.register('test')
        class TestWriter(BaseOutputWriter):
            def __init__(self, output_dir='data') -> None:
                super().__init__(output_dir)
            
            def write_frame(self, frame): pass
            def start_streaming(self, formats, filename=None): return {}
            def stop_streaming(self): return {}
            def get_stats(self): return {}
        
        writer = WriterFactory.create('test', output_dir='data')
        
        assert writer.output_dir == 'data'
    
    # TEST 3: Duplicate registration raises error
    def test_duplicate_registration_fails(self):
        """Cannot register same format twice"""
        @WriterFactory.register('dup')
        class Writer1(BaseOutputWriter):
            def __init__(self, output_dir='data') -> None:
                super().__init__(output_dir)
        
            def write_frame(self, frame): pass
            def start_streaming(self, formats, filename=None): return {}
            def stop_streaming(self): return {}
            def get_stats(self): return {}
        
        with pytest.raises(ValueError):
            @WriterFactory.register('dup')
            class Writer2(BaseOutputWriter):
                def __init__(self, output_dir='data') -> None:
                    super().__init__(output_dir)
                
                def write_frame(self, frame): pass
                def start_streaming(self, formats, filename=None): return {}
                def stop_streaming(self): return {}
                def get_stats(self): return {}
    
    # TEST 4: Invalid format name raises error
    def test_empty_format_name_fails(self):
        """Format name cannot be empty"""
        with pytest.raises(ValueError):
            @WriterFactory.register('')
            class BadWriter(BaseOutputWriter): pass
    
    def test_format_name_with_spaces_fails(self):
        """Format name cannot contain spaces"""
        with pytest.raises(ValueError):
            @WriterFactory.register('bad name')
            class BadWriter(BaseOutputWriter): pass
    
    # TEST 5: Non-BaseOutputWriter raises error
    def test_non_writer_class_fails(self):
        """Class must inherit from BaseOutputWriter"""
        with pytest.raises(TypeError):
            @WriterFactory.register('bad')
            class NotActuallyAWriter:
                pass
    
    # TEST 6: Missing format raises error
    def test_create_unknown_format(self):
        """Creating unknown format raises ValueError"""
        with pytest.raises(ValueError) as exc_info:
            WriterFactory.create('nonexistent')
        
        assert "nonexistent" in str(exc_info.value)
    
    # TEST 7: List formats
    def test_list_formats(self):
        """list_formats returns registered format names"""
        @WriterFactory.register('fmt1')
        class Writer1(BaseOutputWriter):
            def __init__(self, output_dir='data') -> None:
                super().__init__(output_dir)
            
            def write_frame(self, frame): pass
            def start_streaming(self, formats, filename=None): return {}
            def stop_streaming(self): return {}
            def get_stats(self): return {}
        
        @WriterFactory.register('fmt2')
        class Writer2(BaseOutputWriter):
            def __init__(self, output_dir='data') -> None:
                super().__init__(output_dir)
            
            def write_frame(self, frame): pass
            def start_streaming(self, formats, filename=None): return {}
            def stop_streaming(self): return {}
            def get_stats(self): return {}
        
        formats = WriterFactory.list_formats()
        assert set(formats) == {'fmt1', 'fmt2'}