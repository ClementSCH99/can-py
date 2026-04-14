"""CAN message parser with DBC support"""
import cantools
from typing import Optional, Dict, Any


class CANParser:
    """Parse CAN frames with optional DBC signal decoding"""
    
    def __init__(self, dbc_file: Optional[str] = None):
        """
        Initialize CAN parser
        
        Args:
            dbc_file: Path to DBC file for signal decoding (optional)
        """
        self.db = None
        self.dbc_file = dbc_file
        self.expected_signals = set()
        
        if dbc_file:
            try:
                self.db = cantools.database.load_file(dbc_file)
                print(f"[OK] Loaded DBC file: {dbc_file}")
                print(f"  Found {len(self.db.messages)} messages")
            except Exception as e:
                print(f"[ERROR] Failed to load DBC file: {e}")
                print("  Proceeding with raw frame capture only")
            
            try:
                for message in self.db.messages:
                    for signal in message.signals:
                        self.expected_signals.add(signal.name)
            except Exception as e:
                print(f"[ERROR] Failed to extract signals from DBC: {e}")
                self.expected_signals = set()

    
    def parse_frame(self, msg) -> Dict[str, Any]:
        """
        Parse a CAN frame into structured data
        
        Args:
            msg: python-can Message object
            
        Returns:
            Dictionary with frame data
        """
        frame_data = {
            'timestamp': msg.timestamp,
            'can_id': f"0x{msg.arbitration_id:03X}",
            'can_id_dec': msg.arbitration_id,
            'dlc': msg.dlc,
            'data_hex': ' '.join(f"{b:02X}" for b in msg.data),
            'data_bytes': list(msg.data),
            'is_extended': msg.is_extended_id,
            'is_remote': msg.is_remote_frame,
            'is_error': msg.is_error_frame,
        }
        
        # Add parsed signals if DBC is available
        if self.db:
            frame_data['parsed'] = self._decode_signals(msg.arbitration_id, msg.data)
        else:
            frame_data['parsed'] = None
            
        return frame_data
    
    def _decode_signals(self, can_id: int, data: bytes) -> Optional[Dict[str, Any]]:
        """
        Decode CAN signals using DBC
        
        Args:
            can_id: CAN identifier
            data: Raw frame data bytes
            
        Returns:
            Dictionary of signal names and values, or None if message not found
        """
        if not self.db:
            return None
            
        try:
            message = self.db.get_message_by_frame_id(can_id)
            decoded = message.decode(data, allow_truncated=True)
            return decoded
        except Exception as e:
            # Message not found in DBC
            return None
        
    def get_expected_signals(self) -> set[str]:
        """Return set of expected signal names from DBC"""
        return self.expected_signals
    
    def get_message_info(self, can_id: int) -> Optional[Dict[str, Any]]:
        """
        Get message and signal information from DBC
        
        Args:
            can_id: CAN identifier
            
        Returns:
            Dictionary with message info or None
        """
        if not self.db:
            return None
            
        try:
            msg = self.db.get_message_by_frame_id(can_id)
            return {
                'name': msg.name,
                'signals': [s.name for s in msg.signals],
                'cycle_time': msg.cycle_time,
            }
        except:
            return None
