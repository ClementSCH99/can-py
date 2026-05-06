# src/canpy/storage/query.py

from dataclasses import dataclass
from typing import List, Optional

from canpy.storage import CANFrame

@dataclass
class QueryFilter:
    """
    Data class representing filter criteria for querying CAN frames.
    
    This class can be extended with additional fields as needed (e.g., data payload filters).
    """
    can_ids: Optional[List[int]] = None  # List of CAN IDs to filter by
    start_time: Optional[float] = None  # Start time for filtering (timestamp)
    end_time: Optional[float] = None  # End time for filtering (timestamp)
    limit: Optional[int] = None  # Maximum number of frames to return

    # TODO: Add more filter criteria as needed (e.g., data payload filters, signal value filters, etc.)


    def __post_init__(self):
        # Validate that start_time and end_time are in correct order if both are provided
        if self.start_time is not None and self.end_time is not None:
            if self.start_time > self.end_time:
                raise ValueError("start_time must be less than or equal to end_time")
            
        if self.can_ids is not None:
            if not isinstance(self.can_ids, list):
                raise ValueError("can_ids must be a list of integers")
            for can_id in self.can_ids:
                if not isinstance(can_id, int):
                    raise ValueError("Each CAN ID in can_ids must be an integer")
        
        if self.limit is not None and (not isinstance(self.limit, int) or self.limit <= 0):
            raise ValueError("limit must be a positive integer if provided")
                

    def matches(self, frame: CANFrame) -> bool:
        """
        Check if a given CAN frame matches the filter criteria.

        Args:
            frame (CANFrame): The CAN frame to check.

        Returns:
            bool: True if the frame matches the filter criteria, False otherwise.
        """
        if self.can_ids is not None and frame.can_id not in self.can_ids:
            return False
        if self.start_time is not None and frame.timestamp < self.start_time:
            return False
        if self.end_time is not None and frame.timestamp > self.end_time:
            return False
        return True