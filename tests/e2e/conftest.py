"""
Pytest configuration for E2E tests

Shared fixtures and test configuration
"""

import json
import pytest
from pathlib import Path


def _make_ws_agent_db(tmp_path: Path, controller_port: int) -> Path:
    """Build a minimal WebSocket-enabled agent DB for E2E testing."""
    db = {
        "Device.DeviceInfo.Manufacturer": "ARRIS",
        "Device.DeviceInfo.ManufacturerOUI": "00D09E",
        "Device.DeviceInfo.ProductClass": "Test",
        "Device.DeviceInfo.SerialNumber": "T01",
        "Device.DeviceInfo.ModelName": "PoC-USP-Agent-Test",
        "Device.DeviceInfo.FriendlyName": "dummy",
        "Device.LocalAgent.EndpointID": "ops::00D09E-Test-T01",
        "Device.LocalAgent.AdvertisedDeviceSubtypes": "test",
        "Device.LocalAgent.HardwareVersion": "laptop",
        "Device.LocalAgent.SoftwareVersion": "0.0.1-alpha",
        "Device.LocalAgent.SupportedProtocols": "WebSocket",
        "Device.LocalAgent.UpTime": "__UPTIME__",
        "Device.LocalAgent.X_ARRIS-COM_IPAddr": "__IPADDR__",
        "Device.LocalAgent.MTPNumberOfEntries": "__NUM_ENTRIES__",
        "Device.LocalAgent.ControllerNumberOfEntries": "__NUM_ENTRIES__",
        "Device.LocalAgent.SubscriptionNumberOfEntries": "__NUM_ENTRIES__",
        # Single enabled WebSocket controller
        "Device.LocalAgent.Controller.1.Enable": True,
        "Device.LocalAgent.Controller.1.Alias": "e2e-ws-ctrl",
        "Device.LocalAgent.Controller.1.EndpointID": "proto::controller-01",
        "Device.LocalAgent.Controller.1.ProvisioningCode": "",
        "Device.LocalAgent.Controller.1.PeriodicNotifInterval": 30,
        "Device.LocalAgent.Controller.1.MTPNumberOfEntries": "__NUM_ENTRIES__",
        "Device.LocalAgent.Controller.1.MTP.1.Enable": True,
        "Device.LocalAgent.Controller.1.MTP.1.Alias": "e2e-ws-mtp",
        "Device.LocalAgent.Controller.1.MTP.1.Protocol": "WebSocket",
        "Device.LocalAgent.Controller.1.MTP.1.WebSocket.Host": "localhost",
        "Device.LocalAgent.Controller.1.MTP.1.WebSocket.Port": controller_port,
        "Device.LocalAgent.Controller.1.MTP.1.WebSocket.Path": "/usp",
    }
    db_path = tmp_path / f"e2e-test-db-{controller_port}.json"
    db_path.write_text(json.dumps(db, indent=2))
    return db_path


@pytest.fixture
def e2e_ws_db_8080(tmp_path):
    """Agent DB fixture with WebSocket controller on port 8080."""
    return _make_ws_agent_db(tmp_path, 8080)


@pytest.fixture
def e2e_ws_db_9080(tmp_path):
    """Agent DB fixture with WebSocket controller on port 9080."""
    return _make_ws_agent_db(tmp_path, 9080)


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging for each test"""
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
