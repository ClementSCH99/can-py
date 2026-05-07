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
    can_ids: Optional[List[int]] = None
    time_start: Optional[float] = None
    time_end: Optional[float] = None
    limit: Optional[int] = None

    # TODO: Add more filter criteria as needed (e.g., data payload filters, signal value filters, etc.)


    def __post_init__(self):
        if self.time_start is not None and self.time_end is not None:
            if self.time_start > self.time_end:
                raise ValueError("time_start must be less than or equal to time_end")
            
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
        if self.time_start is not None and frame.timestamp < self.time_start:
            return False
        if self.time_end is not None and frame.timestamp > self.time_end:
            return False
        return True