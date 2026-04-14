"""Configuration settings for CAN data capture"""

# CAN Interface Settings
CAN_INTERFACE = 'slcan'  # CANable Z pro+ uses SLCAN protocol
CAN_BITRATE = 500000     # 500 kbps

# Serial port for CANable device (auto-detect if None)
# Common ports: 'COM3', 'COM4', '/dev/ttyUSB0', etc.
SERIAL_PORT = None

# DBC file path (optional, set to None if not using)
DBC_FILE = None

# Output Settings
OUTPUT_DIR = 'data'
OUTPUT_FORMAT = []  # Legacy: deprecated, use --log flag instead

# Capture Settings
CAPTURE_MODE = 'duration'  # Options: 'duration', 'count', 'continuous'
CAPTURE_DURATION = 60      # Duration in seconds (used if mode is 'duration')
CAPTURE_COUNT = 0          # Number of frames (0 = unlimited, used if mode is 'count')

# Display Settings
SHOW_CONSOLE = True        # Print captured frames to console
SHOW_PARSED = True         # Show parsed signals when DBC available (if available)
VERBOSE = False            # Enable verbose logging

# NOTE: Use command-line flags to control behavior:
# - Default: console output only (like candump)
# - Use --log csv,json to enable file logging with streaming
# - Use --no-console to disable console output

