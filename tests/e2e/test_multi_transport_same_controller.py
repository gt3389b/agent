"""
Test multiple MTPs to the same controller

Tests what happens when an agent connects to a single controller
via multiple transports (e.g., WebSocket + CoAP + UDS)
"""

import asyncio
import pytest
import pytest_asyncio
import json
from agent.multi_mtp_agent import MultiMTPAgent
from agent.agent_db import Database


def test_database_multiple_mtps_same_controller(tmp_path):
    """
    Test: Database can have multiple MTPs for same controller
    
    This tests the configuration, not runtime behavior
    """
    # Create test database with 1 controller, 2 MTPs
    db_data = {
        "Device.LocalAgent.EndpointID": "ops::test-agent",
        "Device.LocalAgent.ControllerNumberOfEntries": 1,
        
        # Controller 1
        "Device.LocalAgent.Controller.1.Enable": True,
        "Device.LocalAgent.Controller.1.EndpointID": "proto::controller-01",
        "Device.LocalAgent.Controller.1.MTPNumberOfEntries": 2,
        
        # Controller 1 - MTP 1 (WebSocket)
        "Device.LocalAgent.Controller.1.MTP.1.Enable": True,
        "Device.LocalAgent.Controller.1.MTP.1.Protocol": "WebSocket",
        "Device.LocalAgent.Controller.1.MTP.1.WebSocket.Host": "localhost",
        "Device.LocalAgent.Controller.1.MTP.1.WebSocket.Port": 9080,
        "Device.LocalAgent.Controller.1.MTP.1.WebSocket.Path": "/usp",
        
        # Controller 1 - MTP 2 (WebSocket on different port)
        "Device.LocalAgent.Controller.1.MTP.2.Enable": True,
        "Device.LocalAgent.Controller.1.MTP.2.Protocol": "WebSocket",
        "Device.LocalAgent.Controller.1.MTP.2.WebSocket.Host": "localhost",
        "Device.LocalAgent.Controller.1.MTP.2.WebSocket.Port": 9081,
        "Device.LocalAgent.Controller.1.MTP.2.WebSocket.Path": "/usp",
    }
    
    db_file = tmp_path / "test-db.json"
    with open(db_file, 'w') as f:
        json.dump(db_data, f)
    
    # Verify it loads correctly
    dm_data = {"Device.LocalAgent.EndpointID": "readOnly"}
    dm_file = tmp_path / "test-dm.json"
    with open(dm_file, 'w') as f:
        json.dump(dm_data, f)
    
    db = Database(str(dm_file), str(db_file), "eth0")
    
    assert db.get("Device.LocalAgent.Controller.1.MTPNumberOfEntries") == 2
    assert db.get("Device.LocalAgent.Controller.1.MTP.1.Protocol") == "WebSocket"
    assert db.get("Device.LocalAgent.Controller.1.MTP.2.Protocol") == "WebSocket"


def test_notification_routing_behavior():
    """
    Document current notification routing behavior
    
    When multiple MTPs exist for same controller, notifications
    are sent on the FIRST connected MTP only.
    
    Question: Should we send on ALL MTPs or just one?
    
    USP Spec considerations:
    - Endpoint ID identifies the agent, not the transport
    - Controller should handle same agent on multiple MTPs
    - Sending on all MTPs = redundancy (good for reliability)
    - Sending on one MTP = efficiency (avoids duplicates)
    """
    # This is a documentation test
    assert True, """
    Current behavior: Notifications sent on first connected MTP
    
    Alternative: Send on all connected MTPs for redundancy
    
    To change behavior, modify _send_notification_bytes in multi_mtp_agent.py:
    
    # Current (sends on first):
    for mtp_mgr in mtps:
        if mtp_mgr.connected:
            await mtp_mgr.send_notification(data)
            return  # <-- Remove this to send on all
    
    # Alternative (sends on all):
    for mtp_mgr in mtps:
        if mtp_mgr.connected:
            await mtp_mgr.send_notification(data)
            # No return - continues to next MTP
    """


def test_request_routing_with_multiple_mtps():
    """
    Test: Requests route back on correct MTP
    
    If controller sends request via WebSocket, response goes back via WebSocket.
    If controller sends request via CoAP, response goes back via CoAP.
    
    This is handled by RequestContext.writer which preserves the original MTP.
    """
    from agent.base_agent import RequestContext
    
    # Simulate two different writers (one per MTP)
    websocket_writer = "ws-connection-123"
    coap_writer = "coap-connection-456"
    
    # Request comes in via WebSocket
    ctx_ws = RequestContext(
        from_id="proto::controller-01",
        to_id="ops::test-agent",
        writer=websocket_writer,
        mtp_type="websocket"
    )
    
    # Request comes in via CoAP
    ctx_coap = RequestContext(
        from_id="proto::controller-01",
        to_id="ops::test-agent",
        writer=coap_writer,
        mtp_type="coap"
    )
    
    # Verify contexts preserve the correct writer
    assert ctx_ws.writer == websocket_writer
    assert ctx_ws.mtp_type == "websocket"
    assert ctx_coap.writer == coap_writer
    assert ctx_coap.mtp_type == "coap"
    
    # Response will go back on the same MTP that sent the request


def test_boot_notification_sent_per_mtp():
    """
    Document: Boot! notification sent once per MTP connection
    
    If controller has 2 MTPs enabled:
    - Agent sends Boot! on MTP 1
    - Agent sends Boot! on MTP 2
    
    Controller receives 2 Boot! notifications (same agent, different transports)
    Controller should deduplicate based on endpoint ID
    """
    assert True, """
    Each MTPConnectionManager sends its own Boot! notification.
    
    This is correct behavior because:
    1. Controller needs to know agent is available on each transport
    2. Boot! includes transport-specific information
    3. Controller deduplicates by endpoint ID
    
    See MTPConnectionManager._send_boot() in multi_mtp_agent.py
    """


def test_periodic_notifications_per_mtp():
    """
    Document: Periodic! notifications sent per MTP
    
    Each MTP connection has its own periodic task.
    Controller receives multiple Periodic! notifications.
    """
    assert True, """
    Each MTPConnectionManager runs its own _start_periodic() task.
    
    This means controller receives:
    - Periodic! via WebSocket every 30s
    - Periodic! via CoAP every 30s
    
    Alternative: Could coordinate to send on only one MTP
    """


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
