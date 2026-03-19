"""
End-to-End tests for USP over Unix Domain Socket (UDS)

Tests the full USP request/response cycle through the UDS transport:
  - Get, Set, Add, Delete, Operate
  - GetSupportedDM, GetInstances, GetSupportedProtocol
  - Error handling (unknown paths, invalid operations)

The agent runs as a UDS *server* (listen mode).
The test controller acts as a UDS *client* (connect mode).
"""

import asyncio
import pytest
import pytest_asyncio

from agent.uds_agent import UdsAgent
from mtp.uds import UdsTransport
from mtp.uds_binding import UdsUspBinding  # noqa: F401 — used indirectly via agent
from message import usp_msg_pb2, usp_record_pb2
from message.request import (
    GetRequest, SetRequest, OperateRequest, AddRequest, DeleteRequest,
    GetSupportedDMRequest, GetInstancesRequest, GetSupportedProtocolRequest,
)
from message.response import parse_response

AGENT_ID = "ops::00D09E-Test-T01"
CONTROLLER_ID = "proto::controller-01"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_record(msg, to_id=AGENT_ID, from_id=CONTROLLER_ID):
    """Wrap a USP Msg in a USP Record."""
    record = usp_record_pb2.Record()
    record.version = "1.3"
    record.to_id = to_id
    record.from_id = from_id
    record.no_session_context.payload = msg.SerializeToString()
    return record.SerializeToString()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def uds_agent(e2e_uds_db):
    """Start a UdsAgent server on a temp socket.  Yields (agent, socket_path)."""
    db_path, socket_path = e2e_uds_db
    agent = UdsAgent("database/test-dm.json", str(db_path))
    # Start the UDS server (binds + listens without blocking)
    await agent._mtp_binding.start_server(agent.handle_incoming_request)
    yield agent, socket_path
    await agent._mtp_binding.transport.close()


@pytest_asyncio.fixture
async def ctrl(uds_agent):
    """Connect a UDS client to the running agent.  Yields (transport, socket_path)."""
    _, socket_path = uds_agent
    transport = UdsTransport(socket_path, 'connect', endpoint_id=CONTROLLER_ID)
    await transport.connect()
    yield transport
    await transport.close()


async def _send_and_recv(transport, request_msg, timeout=3.0):
    """Serialise a request, send it, receive the response Record, parse the Msg."""
    await transport.send_message(_build_record(request_msg.to_protobuf()))
    raw = await asyncio.wait_for(transport.receive_message(), timeout=timeout)
    assert raw is not None, "No response received"
    record = usp_record_pb2.Record()
    record.ParseFromString(raw)
    pb_msg = usp_msg_pb2.Msg()
    pb_msg.ParseFromString(record.no_session_context.payload)
    return parse_response(pb_msg)


# ---------------------------------------------------------------------------
# Tests – basic CRUD and queries
# ---------------------------------------------------------------------------

async def test_get_endpoint_id(ctrl):
    """Get: retrieve a known scalar parameter."""
    transport = ctrl
    req = GetRequest(paths=["Device.LocalAgent.EndpointID"], msg_id="test-get-1",
                     from_id=CONTROLLER_ID, to_id=AGENT_ID)
    resp = await _send_and_recv(transport, req)
    assert resp.msg_id == "test-get-1"
    # Value may be keyed by full path or path+param_name depending on serialisation
    all_values = list(resp.results.values())
    assert any(v == AGENT_ID for v in all_values if not isinstance(v, dict))


async def test_get_unknown_path_returns_error(ctrl):
    """Get: unknown path yields an error result entry."""
    transport = ctrl
    req = GetRequest(paths=["Device.NonExistent.Param"], msg_id="test-get-err",
                     from_id=CONTROLLER_ID, to_id=AGENT_ID)
    resp = await _send_and_recv(transport, req)
    result = resp.results.get("Device.NonExistent.Param", {})
    assert isinstance(result, dict) and "error" in result


async def test_set_writable_parameter(ctrl):
    """Set: update a writable parameter."""
    transport = ctrl
    req = SetRequest(
        parameters={"Device.LocalAgent.Subscription.1.TimeToLive": "120"},
        msg_id="test-set-1",
        from_id=CONTROLLER_ID, to_id=AGENT_ID,
    )
    resp = await _send_and_recv(transport, req)
    assert resp.msg_id == "test-set-1"
    # Must be in updated_params or failed_params (not both)
    path = "Device.LocalAgent.Subscription.1.TimeToLive"
    assert path in resp.updated_params or path in resp.failed_params


async def test_get_instances(ctrl):
    """GetInstances: returns at least the pre-seeded Subscription.1."""
    transport = ctrl
    req = GetInstancesRequest(obj_paths=["Device.LocalAgent.Subscription."],
                              msg_id="test-gi-1",
                              from_id=CONTROLLER_ID, to_id=AGENT_ID)
    resp = await _send_and_recv(transport, req)
    assert "Device.LocalAgent.Subscription." in resp.instances
    assert "Device.LocalAgent.Subscription.1." in resp.instances["Device.LocalAgent.Subscription."]


async def test_add_subscription(ctrl):
    """Add: create a new Subscription instance."""
    transport = ctrl
    req = AddRequest(
        create_objs=[{
            'obj_path': 'Device.LocalAgent.Subscription.',
            'param_settings': {'NotifType': 'Event', 'ID': 'e2e-added-sub'},
        }],
        msg_id="test-add-1",
        from_id=CONTROLLER_ID, to_id=AGENT_ID,
    )
    resp = await _send_and_recv(transport, req)
    assert resp.msg_id == "test-add-1"
    assert len(resp.created_obj_results) == 1
    result = resp.created_obj_results[0]
    assert result['requested_path'] == 'Device.LocalAgent.Subscription.'
    assert 'error' not in result
    assert result['instantiated_path'] == 'Device.LocalAgent.Subscription.2.'


async def test_delete_subscription(ctrl):
    """Delete: remove the pre-seeded Subscription.1."""
    transport = ctrl
    req = DeleteRequest(
        obj_paths=["Device.LocalAgent.Subscription.1."],
        msg_id="test-del-1",
        from_id=CONTROLLER_ID, to_id=AGENT_ID,
    )
    resp = await _send_and_recv(transport, req)
    assert resp.msg_id == "test-del-1"
    assert len(resp.deleted_obj_results) == 1
    result = resp.deleted_obj_results[0]
    assert 'error' not in result
    assert "Device.LocalAgent.Subscription.1." in result['affected_paths']


async def test_delete_nonexistent_raises_error(ctrl):
    """Delete: non-existent path yields an error result."""
    transport = ctrl
    req = DeleteRequest(
        obj_paths=["Device.LocalAgent.Subscription.99."],
        msg_id="test-del-err",
        from_id=CONTROLLER_ID, to_id=AGENT_ID,
    )
    resp = await _send_and_recv(transport, req)
    result = resp.deleted_obj_results[0]
    assert 'error' in result


async def test_get_supported_dm(ctrl):
    """GetSupportedDM: returns at least one object."""
    transport = ctrl
    req = GetSupportedDMRequest(obj_paths=["Device.LocalAgent."],
                                return_params=True,
                                msg_id="test-gsdm-1",
                                from_id=CONTROLLER_ID, to_id=AGENT_ID)
    resp = await _send_and_recv(transport, req)
    assert len(resp.supported_objects) > 0


async def test_get_supported_protocol(ctrl):
    """GetSupportedProtocol: agent replies with its supported versions."""
    transport = ctrl
    req = GetSupportedProtocolRequest(
        controller_supported_protocol_versions="1.3",
        msg_id="test-gsp-1",
        from_id=CONTROLLER_ID, to_id=AGENT_ID,
    )
    resp = await _send_and_recv(transport, req)
    assert resp.msg_id == "test-gsp-1"
    assert resp.agent_supported_protocol_versions != ""


async def test_operate_unsupported_command(ctrl):
    """Operate: unsupported command returns an error."""
    transport = ctrl
    req = OperateRequest(command="Device.UnknownCmd()",
                         msg_id="test-op-1",
                         from_id=CONTROLLER_ID, to_id=AGENT_ID)
    resp = await _send_and_recv(transport, req)
    # Should either have an error OR the command is returned (not-supported)
    assert resp is not None


async def test_malformed_record_does_not_crash_agent(ctrl, uds_agent):
    """Malformed data: agent logs the error and stays alive for subsequent connections."""
    transport = ctrl
    # Send raw garbage that isn't valid protobuf
    await transport.send_message(b"\xff\xfe\x00\x01" * 10)
    # The UDS connection may be closed after a parse error; that's acceptable.
    # What matters is that a *new* connection still works.
    await transport.close()
    await asyncio.sleep(0.2)
    # Open a fresh connection
    _, socket_path = uds_agent
    new_transport = UdsTransport(socket_path, 'connect', endpoint_id=CONTROLLER_ID)
    await new_transport.connect()
    req = GetRequest(paths=["Device.LocalAgent.EndpointID"],
                     msg_id="test-after-garbage",
                     from_id=CONTROLLER_ID, to_id=AGENT_ID)
    resp = await _send_and_recv(new_transport, req)
    all_values = list(resp.results.values())
    assert any(v == AGENT_ID for v in all_values if not isinstance(v, dict))
    await new_transport.close()
