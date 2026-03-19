"""
E2E tests for Device.FactoryReset() operation
"""

import pytest
import asyncio
import json
import shutil
import os
from pathlib import Path

# Test setup
TEST_DM_FILE = "database/test-dm.json"
TEST_RUNTIME_DB = "database/runtime/test-db.json"
TEST_DEFAULTS_DB = "database/defaults/test-defaults.json"
TEST_BACKUPS_DIR = "database/backups"


@pytest.fixture
def setup_test_db():
    """Setup test database with modified values"""
    # Ensure runtime directory exists
    os.makedirs(os.path.dirname(TEST_RUNTIME_DB), exist_ok=True)
    
    # Create a copy of defaults
    shutil.copy2(TEST_DEFAULTS_DB, TEST_RUNTIME_DB)
    
    # Modify some values to verify reset
    with open(TEST_RUNTIME_DB, 'r') as f:
        db = json.load(f)
    
    original_endpoint_id = db.get("Device.LocalAgent.EndpointID", "")
    original_friendly_name = db.get("Device.DeviceInfo.FriendlyName", "")
    
    # Modify some parameters
    db["Device.LocalAgent.EndpointID"] = "modified-endpoint-id"
    db["Device.DeviceInfo.FriendlyName"] = "Modified FriendlyName"
    
    with open(TEST_RUNTIME_DB, 'w') as f:
        json.dump(db, f, indent=4)
    
    yield {
        "original_endpoint_id": original_endpoint_id,
        "original_friendly_name": original_friendly_name
    }
    
    # Cleanup - restore from defaults
    if os.path.exists(TEST_DEFAULTS_DB):
        shutil.copy2(TEST_DEFAULTS_DB, TEST_RUNTIME_DB)


def test_factory_reset_restores_defaults(setup_test_db):
    """Test that factory_reset() restores database to factory defaults"""
    from agent.agent_db import Database
    
    # Load database with modified values
    db = Database(TEST_DM_FILE, TEST_RUNTIME_DB, "eth0")
    
    # Verify values are modified
    assert db.get("Device.LocalAgent.EndpointID") == "modified-endpoint-id"
    assert db.get("Device.DeviceInfo.FriendlyName") == "Modified FriendlyName"
    
    # Perform factory reset
    db.factory_reset()
    
    # Verify values are restored to defaults
    original_endpoint_id = setup_test_db["original_endpoint_id"]
    original_friendly_name = setup_test_db["original_friendly_name"]
    assert db.get("Device.LocalAgent.EndpointID") == original_endpoint_id
    assert db.get("Device.DeviceInfo.FriendlyName") == original_friendly_name


def test_factory_reset_creates_backup(setup_test_db):
    """Test that factory_reset() creates a timestamped backup"""
    from agent.agent_db import Database
    
    # Clean backups directory
    if os.path.exists(TEST_BACKUPS_DIR):
        shutil.rmtree(TEST_BACKUPS_DIR)
    os.makedirs(TEST_BACKUPS_DIR)
    
    # Load database
    db = Database(TEST_DM_FILE, TEST_RUNTIME_DB, "eth0")
    
    # Count backups before reset
    backups_before = len(os.listdir(TEST_BACKUPS_DIR))
    
    # Perform factory reset
    db.factory_reset()
    
    # Verify backup was created
    backups = os.listdir(TEST_BACKUPS_DIR)
    assert len(backups) == backups_before + 1
    
    # Verify backup filename format (YYYYMMDD_HHMMSS_test-db.json)
    backup_file = backups[-1]
    assert backup_file.endswith("_test-db.json")
    assert len(backup_file.split("_")[0]) == 8  # YYYYMMDD


def test_factory_reset_reloads_database(setup_test_db):
    """Test that factory_reset() reloads the database in memory"""
    from agent.agent_db import Database
    
    # Load database
    db = Database(TEST_DM_FILE, TEST_RUNTIME_DB, "eth0")
    
    # Modify value in memory only
    db._db["Device.DeviceInfo.FriendlyName"] = "Memory-only modification"
    
    # Perform factory reset
    db.factory_reset()
    
    # Verify in-memory value was reloaded from defaults
    original_friendly_name = setup_test_db["original_friendly_name"]
    assert db.get("Device.DeviceInfo.FriendlyName") == original_friendly_name


def test_auto_restore_on_missing_runtime_db():
    """Test that Database.__init__ auto-restores from defaults if runtime DB is missing"""
    from agent.agent_db import Database
    
    # Remove runtime database
    if os.path.exists(TEST_RUNTIME_DB):
        os.remove(TEST_RUNTIME_DB)
    
    # Initialize database - should auto-restore from defaults
    db = Database(TEST_DM_FILE, TEST_RUNTIME_DB, "eth0")
    
    # Verify runtime database was created
    assert os.path.exists(TEST_RUNTIME_DB)
    
    # Verify it contains data from defaults
    with open(TEST_DEFAULTS_DB, 'r') as f:
        defaults = json.load(f)
    
    endpoint_id = defaults.get("Device.LocalAgent.EndpointID")
    assert db.get("Device.LocalAgent.EndpointID") == endpoint_id


@pytest.mark.asyncio
async def test_device_factory_reset_command():
    """Test Device.FactoryReset() USP command end-to-end"""
    from agent.multi_mtp_agent import MultiMTPAgent
    from message.request import OperateRequest
    
    # Setup database with modified values
    shutil.copy2(TEST_DEFAULTS_DB, TEST_RUNTIME_DB)
    with open(TEST_RUNTIME_DB, 'r') as f:
        db = json.load(f)
    
    db["Device.DeviceInfo.FriendlyName"] = "Modified FriendlyName"
    
    with open(TEST_RUNTIME_DB, 'w') as f:
        json.dump(db, f, indent=4)
    
    # Create agent
    agent = MultiMTPAgent(TEST_DM_FILE, TEST_RUNTIME_DB)
    
    # Create factory reset command
    request = OperateRequest(
        msg_id="test-factory-reset",
        command="Device.FactoryReset()",
        input_args={}
    )
    
    # Execute command
    response = await agent.on_operate_request(request)
    
    # Verify response indicates success
    assert response.error is None
    assert response.output_args.get("Status") == "Success"
    
    # Reload database and verify it was reset
    from agent.agent_db import Database
    agent._db = Database(TEST_DM_FILE, TEST_RUNTIME_DB, "eth0")
    
    with open(TEST_DEFAULTS_DB, 'r') as f:
        defaults = json.load(f)
    
    assert agent._db.get("Device.DeviceInfo.FriendlyName") == defaults.get("Device.DeviceInfo.FriendlyName")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
