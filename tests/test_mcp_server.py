"""
Tests for the USP Controller MCP Server (bin/mcp_server.py)

These tests mock the UDS socket so no live controller is needed.
Each test verifies that a tool correctly:
  - Serialises the outbound JSON-RPC request
  - Deserialises the response and returns the expected value
  - Raises RuntimeError when the controller API is unavailable
  - Raises RuntimeError when the controller returns a JSON-RPC error

Run with:
    pytest tests/test_mcp_server.py -v
"""

import asyncio
import json
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Make sure the project root is on the path when running from tests/
sys.path.insert(0, str(Path(__file__).parent.parent))

from bin.mcp_server import (
    _rpc_call,
    list_agents,
    get_parameters,
    set_parameters,
    operate,
    get_supported_dm,
    get_instances,
    add_object,
    delete_objects,
    SOCKET_PATH,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_connection(result_payload):
    """
    Return (reader, writer) mocks that yield a JSON-RPC success response
    containing *result_payload* when reader.readline() is awaited.
    """
    response = json.dumps({"jsonrpc": "2.0", "result": result_payload, "id": 1}) + "\n"
    reader = AsyncMock()
    reader.readline = AsyncMock(return_value=response.encode())
    writer = AsyncMock()
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    return reader, writer


def _make_error_connection(code, message):
    """Return mocks that yield a JSON-RPC error response."""
    response = (
        json.dumps({"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": 1})
        + "\n"
    )
    reader = AsyncMock()
    reader.readline = AsyncMock(return_value=response.encode())
    writer = AsyncMock()
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    return reader, writer


# ---------------------------------------------------------------------------
# _rpc_call unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rpc_call_success():
    """_rpc_call returns the result field on a success response."""
    reader, writer = _make_mock_connection({"key": "value"})

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        result = await _rpc_call("get", {"agent_id": "test", "paths": []})

    assert result == {"key": "value"}


@pytest.mark.asyncio
async def test_rpc_call_sends_correct_method():
    """_rpc_call writes a correctly-formed JSON-RPC request."""
    reader, writer = _make_mock_connection(None)

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        await _rpc_call("list_agents", {})

    # writer.write is called with bytes; decode and inspect
    written = writer.write.call_args[0][0].decode()
    request = json.loads(written.strip())
    assert request["jsonrpc"] == "2.0"
    assert request["method"] == "list_agents"
    assert request["params"] == {}
    assert "id" in request


@pytest.mark.asyncio
async def test_rpc_call_raises_on_socket_missing():
    """_rpc_call raises RuntimeError when the socket file is absent."""
    with patch(
        "bin.mcp_server.asyncio.open_unix_connection",
        side_effect=FileNotFoundError,
    ):
        with pytest.raises(RuntimeError, match="Controller API not running"):
            await _rpc_call("list_agents", {})


@pytest.mark.asyncio
async def test_rpc_call_raises_on_jsonrpc_error():
    """_rpc_call raises RuntimeError when the controller returns an error."""
    reader, writer = _make_error_connection(-32601, "Method not found: bad_method")

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        with pytest.raises(RuntimeError, match="-32601"):
            await _rpc_call("bad_method", {})


@pytest.mark.asyncio
async def test_rpc_call_raises_on_empty_response():
    """_rpc_call raises RuntimeError when the connection closes with no data."""
    reader = AsyncMock()
    reader.readline = AsyncMock(return_value=b"")
    writer = AsyncMock()
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        with pytest.raises(RuntimeError, match="closed connection"):
            await _rpc_call("list_agents", {})


# ---------------------------------------------------------------------------
# list_agents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_agents_returns_list():
    """list_agents returns the agent list from the controller."""
    payload = [
        {
            "agent_id": "self::uds-agent-001",
            "mtp_type": "uds",
            "last_boot": "2026-02-24T08:00:00Z",
            "last_heartbeat": "2026-02-24T08:01:00Z",
        }
    ]
    reader, writer = _make_mock_connection(payload)

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        result = await list_agents()

    assert result == payload
    assert result[0]["agent_id"] == "self::uds-agent-001"


@pytest.mark.asyncio
async def test_list_agents_empty():
    """list_agents returns an empty list when no agents are connected."""
    reader, writer = _make_mock_connection([])

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        result = await list_agents()

    assert result == []


@pytest.mark.asyncio
async def test_list_agents_none_result():
    """list_agents returns [] when the controller result is null."""
    reader, writer = _make_mock_connection(None)

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        result = await list_agents()

    assert result == []


# ---------------------------------------------------------------------------
# get_parameters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_parameters_returns_dict():
    """get_parameters returns a path→value dict."""
    payload = {
        "Device.DeviceInfo.Manufacturer": "Acme",
        "Device.DeviceInfo.ModelName": "X100",
    }
    reader, writer = _make_mock_connection(payload)

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        result = await get_parameters(
            "self::uds-agent-001",
            ["Device.DeviceInfo.Manufacturer", "Device.DeviceInfo.ModelName"],
        )

    assert result == payload


@pytest.mark.asyncio
async def test_get_parameters_sends_correct_params():
    """get_parameters sends agent_id and paths in the RPC request."""
    reader, writer = _make_mock_connection({})

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        await get_parameters("self::agent-99", ["Device.DeviceInfo."])

    written = json.loads(writer.write.call_args[0][0].decode().strip())
    assert written["method"] == "get"
    assert written["params"]["agent_id"] == "self::agent-99"
    assert written["params"]["paths"] == ["Device.DeviceInfo."]


# ---------------------------------------------------------------------------
# set_parameters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_parameters_returns_updated():
    """set_parameters returns the updated-params dict."""
    payload = {"Device.LocalAgent.Controller.1.PeriodicNotifInterval": "60"}
    reader, writer = _make_mock_connection(payload)

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        result = await set_parameters(
            "self::uds-agent-001",
            [{"path": "Device.LocalAgent.Controller.1.PeriodicNotifInterval", "value": "60"}],
        )

    assert result == payload


@pytest.mark.asyncio
async def test_set_parameters_sends_correct_params():
    """set_parameters includes agent_id and parameters list in the request."""
    reader, writer = _make_mock_connection({})
    params = [{"path": "Device.WiFi.SSID.1.SSID", "value": "TestNet"}]

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        await set_parameters("self::agent-01", params)

    written = json.loads(writer.write.call_args[0][0].decode().strip())
    assert written["method"] == "set"
    assert written["params"]["agent_id"] == "self::agent-01"
    assert written["params"]["parameters"] == params


# ---------------------------------------------------------------------------
# operate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_operate_returns_list():
    """operate returns a list of operation result objects."""
    payload = [{"success": True, "executed_command": "Device.Reboot()", "output_args": {}}]
    reader, writer = _make_mock_connection(payload)

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        result = await operate("self::uds-agent-001", "Device.Reboot()")

    assert result == payload


@pytest.mark.asyncio
async def test_operate_wraps_dict_result_in_list():
    """operate wraps a bare dict result in a list for consistency."""
    payload = {"success": True, "executed_command": "Device.Reboot()", "output_args": {}}
    reader, writer = _make_mock_connection(payload)

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        result = await operate("self::uds-agent-001", "Device.Reboot()")

    assert isinstance(result, list)
    assert result[0] == payload


@pytest.mark.asyncio
async def test_operate_none_result_returns_empty_list():
    """operate returns [] when the controller result is null."""
    reader, writer = _make_mock_connection(None)

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        result = await operate("self::uds-agent-001", "Device.WiFi.Reset()")

    assert result == []


@pytest.mark.asyncio
async def test_operate_sends_args():
    """operate includes command and args in the request."""
    reader, writer = _make_mock_connection([])

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        await operate("self::agent-01", "Device.Reboot()", {"Delay": "5"})

    written = json.loads(writer.write.call_args[0][0].decode().strip())
    assert written["method"] == "operate"
    assert written["params"]["command"] == "Device.Reboot()"
    assert written["params"]["args"] == {"Delay": "5"}


@pytest.mark.asyncio
async def test_operate_defaults_empty_args():
    """operate sends an empty args dict when none are provided."""
    reader, writer = _make_mock_connection([])

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        await operate("self::agent-01", "Device.FactoryReset()")

    written = json.loads(writer.write.call_args[0][0].decode().strip())
    assert written["params"]["args"] == {}


# ---------------------------------------------------------------------------
# get_supported_dm
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_supported_dm_returns_dict():
    """get_supported_dm returns a path→object-info dict."""
    payload = {
        "Device.DeviceInfo.": {
            "access": "read-only",
            "is_multi_instance": False,
            "parameters": {
                "Manufacturer": {"access": "read-only", "type": "string"}
            },
            "commands": {},
            "events": {},
        }
    }
    reader, writer = _make_mock_connection(payload)

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        result = await get_supported_dm("self::uds-agent-001", ["Device.DeviceInfo."])

    assert result == payload


@pytest.mark.asyncio
async def test_get_supported_dm_defaults_device_root():
    """get_supported_dm defaults obj_paths to ['Device.'] when not supplied."""
    reader, writer = _make_mock_connection({})

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        await get_supported_dm("self::agent-01")

    written = json.loads(writer.write.call_args[0][0].decode().strip())
    assert written["params"]["obj_paths"] == ["Device."]


@pytest.mark.asyncio
async def test_get_supported_dm_passes_flags():
    """get_supported_dm forwards all boolean flags to the controller."""
    reader, writer = _make_mock_connection({})

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        await get_supported_dm(
            "self::agent-01",
            obj_paths=["Device.WiFi."],
            first_level_only=True,
            return_commands=False,
            return_events=False,
            return_params=True,
        )

    written = json.loads(writer.write.call_args[0][0].decode().strip())
    p = written["params"]
    assert p["first_level_only"] is True
    assert p["return_commands"] is False
    assert p["return_events"] is False
    assert p["return_params"] is True
    assert p["obj_paths"] == ["Device.WiFi."]


# ---------------------------------------------------------------------------
# Socket path sanity
# ---------------------------------------------------------------------------


def test_socket_path_constant():
    """SOCKET_PATH is the expected Unix socket path."""
    assert SOCKET_PATH == "/tmp/usp-controller-api.sock"


# ---------------------------------------------------------------------------
# get_instances
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_instances_returns_dict():
    """get_instances returns a path→instances dict."""
    payload = {
        "Device.WiFi.SSID.": [
            {"path": "Device.WiFi.SSID.1.", "unique_keys": {"SSID": "HomeNet"}},
            {"path": "Device.WiFi.SSID.2.", "unique_keys": {"SSID": "GuestNet"}},
        ]
    }
    reader, writer = _make_mock_connection(payload)

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        result = await get_instances("self::uds-agent-001", ["Device.WiFi.SSID."])

    assert result == payload
    assert len(result["Device.WiFi.SSID."]) == 2


@pytest.mark.asyncio
async def test_get_instances_sends_correct_params():
    """get_instances sends obj_paths and first_level_only in the RPC request."""
    reader, writer = _make_mock_connection({})

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        await get_instances("self::agent-01", ["Device.NAT.PortMapping."], first_level_only=True)

    written = json.loads(writer.write.call_args[0][0].decode().strip())
    assert written["method"] == "get_instances"
    assert written["params"]["agent_id"] == "self::agent-01"
    assert written["params"]["obj_paths"] == ["Device.NAT.PortMapping."]
    assert written["params"]["first_level_only"] is True


@pytest.mark.asyncio
async def test_get_instances_none_result_returns_empty_dict():
    """get_instances returns {} when the controller result is null."""
    reader, writer = _make_mock_connection(None)

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        result = await get_instances("self::agent-01", ["Device.WiFi.SSID."])

    assert result == {}


# ---------------------------------------------------------------------------
# add_object
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_object_returns_list():
    """add_object returns a list of created-object result records."""
    payload = [
        {
            "requested_path": "Device.WiFi.SSID.",
            "instantiated_path": "Device.WiFi.SSID.3.",
            "unique_keys": {"SSID": "NewNet"},
        }
    ]
    reader, writer = _make_mock_connection(payload)
    create_objs = [
        {
            "obj_path": "Device.WiFi.SSID.",
            "param_settings": [{"param": "SSID", "value": "NewNet", "required": True}],
        }
    ]

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        result = await add_object("self::uds-agent-001", create_objs)

    assert result == payload
    assert result[0]["instantiated_path"] == "Device.WiFi.SSID.3."


@pytest.mark.asyncio
async def test_add_object_sends_correct_params():
    """add_object sends agent_id, create_objs, and allow_partial."""
    reader, writer = _make_mock_connection([])
    create_objs = [{"obj_path": "Device.NAT.PortMapping.", "param_settings": []}]

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        await add_object("self::agent-01", create_objs, allow_partial=False)

    written = json.loads(writer.write.call_args[0][0].decode().strip())
    assert written["method"] == "add"
    assert written["params"]["agent_id"] == "self::agent-01"
    assert written["params"]["create_objs"] == create_objs
    assert written["params"]["allow_partial"] is False


@pytest.mark.asyncio
async def test_add_object_none_result_returns_empty_list():
    """add_object returns [] when the controller result is null."""
    reader, writer = _make_mock_connection(None)

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        result = await add_object("self::agent-01", [{"obj_path": "Device.WiFi.SSID."}])

    assert result == []


# ---------------------------------------------------------------------------
# delete_objects
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_objects_returns_list():
    """delete_objects returns a list of deletion result records."""
    payload = [
        {
            "requested_path": "Device.WiFi.SSID.2.",
            "affected_paths": ["Device.WiFi.SSID.2."],
        }
    ]
    reader, writer = _make_mock_connection(payload)

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        result = await delete_objects("self::uds-agent-001", ["Device.WiFi.SSID.2."])

    assert result == payload
    assert result[0]["affected_paths"] == ["Device.WiFi.SSID.2."]


@pytest.mark.asyncio
async def test_delete_objects_sends_correct_params():
    """delete_objects sends agent_id, obj_paths, and allow_partial."""
    reader, writer = _make_mock_connection([])
    paths = ["Device.NAT.PortMapping.3.", "Device.NAT.PortMapping.4."]

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        await delete_objects("self::agent-01", paths, allow_partial=True)

    written = json.loads(writer.write.call_args[0][0].decode().strip())
    assert written["method"] == "delete"
    assert written["params"]["agent_id"] == "self::agent-01"
    assert written["params"]["obj_paths"] == paths
    assert written["params"]["allow_partial"] is True


@pytest.mark.asyncio
async def test_delete_objects_none_result_returns_empty_list():
    """delete_objects returns [] when the controller result is null."""
    reader, writer = _make_mock_connection(None)

    with patch("bin.mcp_server.asyncio.open_unix_connection", return_value=(reader, writer)):
        result = await delete_objects("self::agent-01", ["Device.WiFi.SSID.2."])

    assert result == []
