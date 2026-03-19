"""
Pytest configuration for E2E tests

Shared fixtures and test configuration
"""

import json
import pytest
from pathlib import Path


def _make_ws_agent_db(tmp_path: Path, controller_port: int, periodic_interval: int = 30) -> Path:
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
        "Device.LocalAgent.Controller.1.PeriodicNotifInterval": periodic_interval,
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


def _make_uds_agent_db(tmp_path: Path, socket_path: str) -> Path:
    """Build a minimal UDS-mode agent DB for E2E testing.

    The agent listens on *socket_path*.  No controllers are pre-configured
    (the controller connects to the agent, not the other way around).
    A Subscription table entry is pre-seeded so Delete tests have something
    to remove, and __NextInstNum__ is set to 2 so Add tests get index 2.
    """
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
        "Device.LocalAgent.SupportedProtocols": "UDS",
        "Device.LocalAgent.UpTime": "__UPTIME__",
        "Device.LocalAgent.X_ARRIS-COM_IPAddr": "__IPADDR__",
        "Device.LocalAgent.MTPNumberOfEntries": "__NUM_ENTRIES__",
        "Device.LocalAgent.ControllerNumberOfEntries": "__NUM_ENTRIES__",
        "Device.LocalAgent.SubscriptionNumberOfEntries": "__NUM_ENTRIES__",
        # UDS MTP — agent listens on this socket
        "Device.LocalAgent.MTP.1.Enable": True,
        "Device.LocalAgent.MTP.1.Alias": "e2e-uds-mtp",
        "Device.LocalAgent.MTP.1.Protocol": "UDS",
        "Device.LocalAgent.MTP.1.UDS.UnixSocketPath": socket_path,
        # Pre-seeded subscription so Delete tests have a target
        "Device.LocalAgent.Subscription.1.Enable": False,
        "Device.LocalAgent.Subscription.1.Alias": "e2e-pre-seeded",
        "Device.LocalAgent.Subscription.1.ID": "pre-seeded-sub-1",
        "Device.LocalAgent.Subscription.1.Recipient": "",
        "Device.LocalAgent.Subscription.1.CreationDate": "",
        "Device.LocalAgent.Subscription.1.NotifType": "Event",
        "Device.LocalAgent.Subscription.1.ReferenceList": "",
        "Device.LocalAgent.Subscription.1.Persistent": False,
        "Device.LocalAgent.Subscription.1.TimeToLive": 0,
        # Next Add will create Subscription.2
        "Device.LocalAgent.Subscription.__NextInstNum__": 2,
    }
    db_path = tmp_path / "e2e-uds-agent-db.json"
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


@pytest.fixture
def e2e_ws_db_9080_fast(tmp_path):
    """Agent DB fixture with WebSocket controller on port 9080 and 5s periodic interval."""
    return _make_ws_agent_db(tmp_path, 9080, periodic_interval=5)


@pytest.fixture
def e2e_uds_db(tmp_path):
    """Agent DB fixture for UDS agent tests. Returns (db_path, socket_path)."""
    import os, uuid
    # macOS limits AF_UNIX paths to 104 chars; use /tmp with a short unique name.
    socket_path = f"/tmp/e2e-usp-{uuid.uuid4().hex[:8]}.sock"
    db_path = _make_uds_agent_db(tmp_path, socket_path)
    return db_path, socket_path


def _make_dual_ws_agent_db(tmp_path: Path, port1: int, port2: int) -> Path:
    """Build an agent DB with two WebSocket controllers for multi-MTP E2E testing."""
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
        # Controller 1 -> port1
        "Device.LocalAgent.Controller.1.Enable": True,
        "Device.LocalAgent.Controller.1.Alias": "e2e-ctrl-1",
        "Device.LocalAgent.Controller.1.EndpointID": "proto::controller-01",
        "Device.LocalAgent.Controller.1.ProvisioningCode": "",
        "Device.LocalAgent.Controller.1.PeriodicNotifInterval": 30,
        "Device.LocalAgent.Controller.1.MTPNumberOfEntries": "__NUM_ENTRIES__",
        "Device.LocalAgent.Controller.1.MTP.1.Enable": True,
        "Device.LocalAgent.Controller.1.MTP.1.Alias": "e2e-ctrl-1-mtp",
        "Device.LocalAgent.Controller.1.MTP.1.Protocol": "WebSocket",
        "Device.LocalAgent.Controller.1.MTP.1.WebSocket.Host": "localhost",
        "Device.LocalAgent.Controller.1.MTP.1.WebSocket.Port": port1,
        "Device.LocalAgent.Controller.1.MTP.1.WebSocket.Path": "/usp",
        # Controller 2 -> port2
        "Device.LocalAgent.Controller.2.Enable": True,
        "Device.LocalAgent.Controller.2.Alias": "e2e-ctrl-2",
        "Device.LocalAgent.Controller.2.EndpointID": "proto::controller-02",
        "Device.LocalAgent.Controller.2.ProvisioningCode": "",
        "Device.LocalAgent.Controller.2.PeriodicNotifInterval": 30,
        "Device.LocalAgent.Controller.2.MTPNumberOfEntries": "__NUM_ENTRIES__",
        "Device.LocalAgent.Controller.2.MTP.1.Enable": True,
        "Device.LocalAgent.Controller.2.MTP.1.Alias": "e2e-ctrl-2-mtp",
        "Device.LocalAgent.Controller.2.MTP.1.Protocol": "WebSocket",
        "Device.LocalAgent.Controller.2.MTP.1.WebSocket.Host": "localhost",
        "Device.LocalAgent.Controller.2.MTP.1.WebSocket.Port": port2,
        "Device.LocalAgent.Controller.2.MTP.1.WebSocket.Path": "/usp",
    }
    db_path = tmp_path / f"e2e-dual-ws-db-{port1}-{port2}.json"
    db_path.write_text(json.dumps(db, indent=2))
    return db_path


@pytest.fixture
def e2e_dual_ws_db(tmp_path):
    """Agent DB fixture with two WebSocket controllers on ports 9080 and 9081."""
    return _make_dual_ws_agent_db(tmp_path, 9080, 9081)


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging for each test"""
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
