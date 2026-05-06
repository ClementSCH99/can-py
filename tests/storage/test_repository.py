"""Tests for Repository interface"""

from inspect import isabstract
from typing import Generator

import pytest

from canpy.storage.frame import CANFrame
from canpy.storage.repository import BaseRepository


class TestRepositoryInterfaceStructure:
    """Test that BaseRepository defines the interface correctly."""

    def test_base_repository_is_abstract(self):
        """Verify that BaseRepository is abstract (cannot be instantiated)."""
        assert isabstract(BaseRepository), "BaseRepository should be abstract"
    
    def test_has_required_abstract_methods(self):
        """Verify BaseRepository defines all required abstract methods."""
        # Check abstract methods exist
        assert hasattr(BaseRepository, 'save_frame')
        assert hasattr(BaseRepository, 'get_frames')
        assert hasattr(BaseRepository, 'count')
        assert hasattr(BaseRepository, 'close')
        
        # Verify they are marked as abstract
        assert hasattr(BaseRepository.save_frame, '__isabstractmethod__')
        assert hasattr(BaseRepository.get_frames, '__isabstractmethod__')
        assert hasattr(BaseRepository.count, '__isabstractmethod__')
        assert hasattr(BaseRepository.close, '__isabstractmethod__')
    
    def test_has_convenience_methods(self):
        """Verify BaseRepository defines convenience methods."""
        assert hasattr(BaseRepository, 'get_by_can_id')
        assert hasattr(BaseRepository, 'get_by_time_range')


class TestRepositoryAbstractEnforcement:
    """Test that Python enforces the abstract contract."""
    
    def test_incomplete_subclass_cannot_instantiate(self):
        """Verify that incomplete implementations cannot be instantiated."""
        class IncompleteRepo(BaseRepository):
            pass  # Missing all abstract method implementations
        
        with pytest.raises(TypeError) as exc_info:
            repo = IncompleteRepo()
        
        error_msg = str(exc_info.value).lower()
        assert 'abstract' in error_msg, "Error should mention 'abstract'"
    
    def test_partially_implemented_subclass_fails(self):
        """Verify that partially implemented subclasses fail."""
        class PartialRepo(BaseRepository):
            def save_frame(self, frame: CANFrame) -> None:
                pass  # Only implement one method
            # Missing get_frames, count, close
        
        with pytest.raises(TypeError) as exc_info:
            repo = PartialRepo()
        
        assert 'abstract' in str(exc_info.value).lower()


class TestRepositoryImplementationRequirements:
    """Test what a complete implementation must provide."""
    
    def test_complete_implementation_can_instantiate(self):
        """Verify that a complete implementation can be instantiated."""
        class CompleteRepo(BaseRepository):
            def save_frame(self, frame: CANFrame) -> None:
                pass
            
            def get_frames(self, query_filter) -> Generator[CANFrame, None, None]:
                return iter([])  # Return empty generator
            
            def count(self) -> int:
                return 0
            
            def close(self) -> None:
                pass
        
        # Should not raise TypeError
        repo = CompleteRepo()
        assert isinstance(repo, BaseRepository)
    
    def test_save_frame_accepts_can_frame(self):
        """Verify save_frame method signature accepts CANFrame."""
        class DummyRepo(BaseRepository):
            def __init__(self):
                self.saved_frames = []
            
            def save_frame(self, frame: CANFrame) -> None:
                self.saved_frames.append(frame)
            
            def get_frames(self, query_filter) -> Generator[CANFrame, None, None]:
                return iter(self.saved_frames)
            
            def count(self) -> int:
                return len(self.saved_frames)
            
            def close(self) -> None:
                pass
        
        repo = DummyRepo()
        frame = CANFrame(timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678')
        repo.save_frame(frame)
        
        assert len(repo.saved_frames) == 1
        assert repo.saved_frames[0] == frame
    
    def test_get_frames_returns_generator(self):
        """Verify get_frames returns a generator."""
        class DummyRepo(BaseRepository):
            def save_frame(self, frame: CANFrame) -> None:
                pass
            
            def get_frames(self, query_filter) -> Generator[CANFrame, None, None]:
                # Return a generator (using yield)
                yield CANFrame(timestamp=1.0, can_id=0x123, dlc=8, data=b'12345678')
            
            def count(self) -> int:
                return 1
            
            def close(self) -> None:
                pass
        
        repo = DummyRepo()
        frames = repo.get_frames(None)
        
        # Should be a generator
        assert hasattr(frames, '__iter__')
        assert hasattr(frames, '__next__')
        
        # Should be able to iterate
        frame_list = list(frames)
        assert len(frame_list) == 1
    
    def test_count_returns_integer(self):
        """Verify count returns an integer."""
        class DummyRepo(BaseRepository):
            def save_frame(self, frame: CANFrame) -> None:
                pass
            
            def get_frames(self, query_filter) -> Generator[CANFrame, None, None]:
                return iter([])
            
            def count(self) -> int:
                return 42
            
            def close(self) -> None:
                pass
        
        repo = DummyRepo()
        result = repo.count()
        assert isinstance(result, int)
        assert result == 42


class TestConvenienceMethodsExist:
    """Test that convenience methods are available (implementation deferred)."""
    
    def test_get_by_can_id_method_exists(self):
        """Verify get_by_can_id convenience method exists."""
        assert hasattr(BaseRepository, 'get_by_can_id')
        assert callable(getattr(BaseRepository, 'get_by_can_id'))
    
    def test_get_by_time_range_method_exists(self):
        """Verify get_by_time_range convenience method exists."""
        assert hasattr(BaseRepository, 'get_by_time_range')
        assert callable(getattr(BaseRepository, 'get_by_time_range'))
    
    # NOTE: Actual testing of these methods is deferred to Step 1.3.3
    # when QueryFilter is implemented