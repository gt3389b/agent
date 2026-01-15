#!/usr/bin/env python3
"""
Demo script showing Device.FactoryReset() operation

This demonstrates:
1. Loading an agent database
2. Modifying some parameters
3. Executing factory reset
4. Verifying restoration to defaults
"""

import sys
import os
import json
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.agent_db import Database

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database files
DM_FILE = "database/test-dm.json"
RUNTIME_DB = "database/runtime/test-db.json"
DEFAULTS_DB = "database/defaults/test-defaults.json"


def print_section(title):
    """Print a formatted section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def main():
    """Demonstrate factory reset functionality"""
    
    print_section("Device.FactoryReset() Demonstration")
    
    # 1. Load database
    print_section("1. Loading Agent Database")
    db = Database(DM_FILE, RUNTIME_DB, "eth0")
    
    # Show some initial values
    print(f"\nInitial EndpointID: {db.get('Device.LocalAgent.EndpointID')}")
    print(f"Initial FriendlyName: {db.get('Device.DeviceInfo.FriendlyName')}")
    print(f"Initial SoftwareVersion: {db.get('Device.LocalAgent.SoftwareVersion')}")
    
    # 2. Modify some parameters
    print_section("2. Modifying Parameters (simulating runtime changes)")
    db.update("Device.LocalAgent.EndpointID", "modified-endpoint-123")
    db.update("Device.DeviceInfo.FriendlyName", "Modified Agent")
    db.update("Device.LocalAgent.SoftwareVersion", "9.9.9-test")
    
    print(f"\nModified EndpointID: {db.get('Device.LocalAgent.EndpointID')}")
    print(f"Modified FriendlyName: {db.get('Device.DeviceInfo.FriendlyName')}")
    print(f"Modified SoftwareVersion: {db.get('Device.LocalAgent.SoftwareVersion')}")
    
    # 3. Show backups before reset
    print_section("3. Checking Backups Directory")
    backup_dir = "database/backups"
    if os.path.exists(backup_dir):
        backups_before = len([f for f in os.listdir(backup_dir) if f.endswith('.json')])
        print(f"\nBackups before reset: {backups_before}")
    else:
        backups_before = 0
        print("\nBackups directory doesn't exist yet")
    
    # 4. Execute factory reset
    print_section("4. Executing Device.FactoryReset()")
    print("\n⚠️  WARNING: This will reset all parameters to factory defaults!")
    print("Creating backup and restoring from defaults...")
    
    db.factory_reset()
    print("\n✓ Factory reset completed successfully")
    
    # 5. Verify restoration
    print_section("5. Verifying Restoration to Factory Defaults")
    
    # Load defaults for comparison
    with open(DEFAULTS_DB, 'r') as f:
        defaults = json.load(f)
    
    endpoint_id = db.get('Device.LocalAgent.EndpointID')
    friendly_name = db.get('Device.DeviceInfo.FriendlyName')
    software_version = db.get('Device.LocalAgent.SoftwareVersion')
    
    print(f"\nRestored EndpointID: {endpoint_id}")
    print(f"  Default value: {defaults['Device.LocalAgent.EndpointID']}")
    print(f"  Match: {endpoint_id == defaults['Device.LocalAgent.EndpointID']}")
    
    print(f"\nRestored FriendlyName: {friendly_name}")
    print(f"  Default value: {defaults['Device.DeviceInfo.FriendlyName']}")
    print(f"  Match: {friendly_name == defaults['Device.DeviceInfo.FriendlyName']}")
    
    print(f"\nRestored SoftwareVersion: {software_version}")
    print(f"  Default value: {defaults['Device.LocalAgent.SoftwareVersion']}")
    print(f"  Match: {software_version == defaults['Device.LocalAgent.SoftwareVersion']}")
    
    # 6. Check backups after reset
    print_section("6. Verifying Backup Creation")
    if os.path.exists(backup_dir):
        backups = [f for f in os.listdir(backup_dir) if f.endswith('.json')]
        backups_after = len(backups)
        print(f"\nBackups after reset: {backups_after}")
        print(f"New backups created: {backups_after - backups_before}")
        
        if backups:
            latest_backup = sorted(backups)[-1]
            print(f"\nLatest backup: {latest_backup}")
            backup_path = os.path.join(backup_dir, latest_backup)
            backup_size = os.path.getsize(backup_path)
            print(f"Backup size: {backup_size} bytes")
    
    print_section("✓ Demo Complete")
    print("\nFactory reset successfully demonstrated!")
    print("\nKey features:")
    print("  • Parameters restored to factory defaults")
    print("  • Timestamped backup created before reset")
    print("  • In-memory database reloaded from defaults")
    print("  • Auto-restore from defaults if runtime DB missing")
    print()


if __name__ == "__main__":
    main()
