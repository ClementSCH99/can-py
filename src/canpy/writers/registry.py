from canpy.writers.base import BaseOutputWriter

class WriterFactory:
    """Factory for creating output writers via plugin registration"""
    
    _writers = {}
    
    @classmethod
    def register(cls, format_name: str):
        """Decorator to register a writer"""
        def wrapper(writer_class):
            # CHECK 1: Is format_name valid? (non-empty, no spaces)
            if not format_name or ' ' in format_name:
                raise ValueError(f"Format name must be non-empty and contain no spaces")
            
            # CHECK 2: Is this format already registered?
            if format_name in cls._writers:
                raise ValueError(f"Writer for format '{format_name}' is already registered")
            
            # CHECK 3: Does writer_class inherit from BaseOutputWriter?
            if not issubclass(writer_class, BaseOutputWriter):
                raise TypeError(f"{writer_class.__name__} must inherit from BaseOutputWriter")
            
            cls._writers[format_name] = writer_class
            return writer_class
        return wrapper
    
    @classmethod
    def create(cls, format_name: str, **kwargs):
        """Create a writer instance"""
        if format_name not in cls._writers:
            available = ', '.join(cls.list_formats()) or 'none'
            raise ValueError(
                f"Writer for format '{format_name}' is not registered. "  
                f"Available: {available}"
            )
        
        writer_class = cls._writers[format_name]
        return writer_class(**kwargs)
    
    @classmethod
    def list_formats(cls):
        """Return available formats"""
        return list(cls._writers.keys())