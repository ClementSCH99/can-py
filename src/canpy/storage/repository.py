# src/canpy/storage/repository.py

from abc import ABC, abstractmethod
from typing import Generator, Optional
from .frame import CANFrame
from .query import QueryFilter

class BaseRepository(ABC):
    """
    Abstract repository interface for CAN frame storage.
    
    All storage backends (CSV, SQLite, Parquet) implement this
    to provide a consistent API for reading/writing CAN frames.
    """
    
    @abstractmethod
    def save_frame(self, frame: CANFrame) -> None:
        """Store a single CAN frame."""
        pass
    
    @abstractmethod
    def count(self) -> int:
        """Total number of frames in storage."""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Release resources (file handles, connections)."""
        pass
    
    @abstractmethod
    def get_frames(self, query_filter: QueryFilter) -> Generator[CANFrame, None, None]:
        """
        Retrieve frames matching the query filter.
        
        Returns a generator to support lazy loading (memory efficient).
        """
        pass

    # Optional: Add methods for convenience
    def get_by_can_id(self, can_id: int) -> Generator[CANFrame, None, None]:
        """Convenience method to get frames by CAN ID."""
        return self.get_frames(QueryFilter(can_ids=[can_id]))
    
    def get_by_time_range(self, start_time: float, end_time: float) -> Generator[CANFrame, None, None]:
        """Convenience method to get frames within a time range."""
        return self.get_frames(QueryFilter(start_time=start_time, end_time=end_time))