#!/usr/bin/env python3
"""
Simple CAN device detector
"""
import sys

try:
    import can
    print("Detecting CAN devices...")
    print()
    
    configs = can.interface.detect_available_configs()
    
    if not configs:
        print("No CAN devices detected")
        sys.exit(1)
    
    print(f"Found {len(configs)} device(s):\n")
    for i, config in enumerate(configs, 1):
        print(f"{i}. Interface: {config.get('interface')}")
        print(f"   Channel: {config.get('channel')}")
        if hasattr(config, 'keys'):
            for key in config:
                if key not in ['interface', 'channel']:
                    print(f"   {key}: {config[key]}")
        print()
    
    sys.exit(0)
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
