#!/usr/bin/env python3
"""
USP Controller MCP Server

Exposes USP controller operations as MCP tools so LLM assistants (e.g. Claude)
can interact with connected USP agents directly.

Connects to the controller northbound JSON-RPC 2.0 API over the Unix domain
socket at /tmp/usp-controller-api.sock — the same socket the interactive
shell uses.

Usage
-----
  # Run with stdio transport (for Claude Desktop / MCP Inspector):
  python bin/mcp_server.py

  # Inspect interactively:
  fastmcp dev bin/mcp_server.py

Claude Desktop config (~/.claude/claude_desktop_config.json):
  {
    "mcpServers": {
      "usp-controller": {
        "command": "python",
        "args": ["/path/to/pyagent-old/bin/mcp_server.py"]
      }
    }
  }
"""

import asyncio
import json
from typing import Any

from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "USP Controller",
    instructions=(
        "Tools for managing USP (User Services Platform) agents via a TR-369 controller. "
        "USP agents expose a TR-181 data model of device parameters, commands, and events. "
        "Always call list_agents first to discover available agent IDs before using any "
        "other tool, as every tool requires an agent_id."
    ),
)

# ---------------------------------------------------------------------------
# JSON-RPC client helpers
# ---------------------------------------------------------------------------

SOCKET_PATH = "/tmp/usp-controller-api.sock"
REQUEST_TIMEOUT = 10.0

_request_id = 0


def _next_id() -> int:
    global _request_id
    _request_id += 1
    return _request_id


async def _rpc_call(method: str, params: dict) -> Any:
    """
    Send a JSON-RPC 2.0 request to the controller northbound API and return
    the ``result`` field.  Raises ``RuntimeError`` on connection failure or a
    JSON-RPC error response.
    """
    try:
        reader, writer = await asyncio.open_unix_connection(SOCKET_PATH)
    except FileNotFoundError:
        raise RuntimeError(
            f"Controller API not running — socket not found at {SOCKET_PATH}. "
            "Start the controller with: python controller/main.py"
        )
    except Exception as e:
        raise RuntimeError(f"Cannot connect to controller API: {e}")

    try:
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": _next_id(),
        }
        writer.write((json.dumps(request) + "\n").encode())
        await writer.drain()

        data = await asyncio.wait_for(reader.readline(), timeout=REQUEST_TIMEOUT)
        if not data:
            raise RuntimeError("Controller closed connection without responding")

        response = json.loads(data.decode().strip())

        if "error" in response:
            err = response["error"]
            raise RuntimeError(
                f"Controller error {err.get('code')}: {err.get('message')}"
            )

        return response.get("result")

    finally:
        writer.close()
        await writer.wait_closed()


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_agents() -> list[dict]:
    """
    List all USP agents currently connected to the controller.

    Returns a list of agent records. Use the ``agent_id`` field from each
    record as the first argument to all other tools.

    Each record contains:
    - agent_id: unique endpoint identifier (e.g. "self::uds-agent-001")
    - mtp_type: transport in use — uds, coap, websocket, or stomp
    - last_boot: ISO timestamp of the agent's last boot
    - last_heartbeat: ISO timestamp of the most recent message from the agent
    - manufacturer_oui, product_class, serial_number, ip_address (when known)
    """
    result = await _rpc_call("list_agents", {})
    return result or []


@mcp.tool()
async def get_parameters(agent_id: str, paths: list[str]) -> dict[str, str]:
    """
    Read one or more TR-181 parameter values from a USP agent.

    Args:
        agent_id: Agent endpoint ID obtained from list_agents.
        paths: One or more TR-181 paths to resolve. Supports:
               - Exact parameter:  ["Device.DeviceInfo.Manufacturer"]
               - Partial/object:   ["Device.DeviceInfo."]   (all children)
               - Wildcards:        ["Device.WiFi.SSID.*.SSID"]

    Returns:
        Dict mapping each resolved parameter path to its current string value.
        Example: {"Device.DeviceInfo.Manufacturer": "Acme",
                  "Device.DeviceInfo.ModelName": "X100"}
    """
    result = await _rpc_call("get", {"agent_id": agent_id, "paths": paths})
    return result or {}


@mcp.tool()
async def set_parameters(
    agent_id: str,
    parameters: list[dict[str, str]],
) -> dict[str, str]:
    """
    Write one or more TR-181 parameter values on a USP agent.

    Args:
        agent_id: Agent endpoint ID obtained from list_agents.
        parameters: List of {"path": "<tr181-path>", "value": "<new-value>"}
                    objects. Example:
                    [{"path": "Device.LocalAgent.Controller.1.PeriodicNotifInterval",
                      "value": "60"}]

    Returns:
        Dict mapping each updated parameter path to the value that was applied.
    """
    result = await _rpc_call(
        "set", {"agent_id": agent_id, "parameters": parameters}
    )
    return result or {}


@mcp.tool()
async def operate(
    agent_id: str,
    command: str,
    args: dict[str, str] | None = None,
) -> list[dict]:
    """
    Execute a USP command (Operate request) on an agent.

    Args:
        agent_id: Agent endpoint ID obtained from list_agents.
        command: Full TR-181 command path including parentheses.
                 Examples: "Device.Reboot()"
                           "Device.WiFi.Reset()"
                           "Device.IP.Diagnostics.IPPing()"
        args: Optional input arguments for the command.
              Example: {"Delay": "10"}

    Returns:
        List of result objects. Each contains:
        - success: true (synchronous success), false (error), or null (async/pending)
        - executed_command: the command that was run
        - output_args: dict of return values (on synchronous success)
        - error_code / error_message (on failure)
        - requested_obj_path (on async/pending — poll separately)
    """
    result = await _rpc_call(
        "operate",
        {"agent_id": agent_id, "command": command, "args": args or {}},
    )
    if result is None:
        return []
    return result if isinstance(result, list) else [result]


@mcp.tool()
async def get_supported_dm(
    agent_id: str,
    obj_paths: list[str] | None = None,
    first_level_only: bool = False,
    return_commands: bool = True,
    return_events: bool = True,
    return_params: bool = True,
) -> dict[str, dict]:
    """
    Introspect the TR-181 data model supported by a USP agent.

    Call this before get_parameters, set_parameters, or operate to discover
    what the device actually supports — valid parameter names, writable fields,
    available commands and their arguments, and subscribable events.

    Args:
        agent_id: Agent endpoint ID obtained from list_agents.
        obj_paths: Object paths to query. Defaults to ["Device."] (full model).
                   Narrow the scope for faster results:
                   ["Device.WiFi.", "Device.IP."]
        first_level_only: Return only immediate children rather than recursing.
        return_commands: Include supported commands in the response.
        return_events: Include supported events in the response.
        return_params: Include supported parameters in the response.

    Returns:
        Dict keyed by object path. Each value is an object describing:
        - access: "read-only", "add-delete", "add-only", or "delete-only"
        - is_multi_instance: whether this is a multi-instance object (table)
        - parameters: {name: {access, type}}          (when return_params=true)
        - commands:   {name: {type, input_args, output_args}} (when return_commands=true)
        - events:     {name: {arg_names}}              (when return_events=true)
    """
    result = await _rpc_call(
        "get_supported_dm",
        {
            "agent_id": agent_id,
            "obj_paths": obj_paths or ["Device."],
            "first_level_only": first_level_only,
            "return_commands": return_commands,
            "return_events": return_events,
            "return_params": return_params,
        },
    )
    return result or {}


@mcp.tool()
async def get_instances(
    agent_id: str,
    obj_paths: list[str],
    first_level_only: bool = False,
) -> dict[str, list]:
    """
    List the existing instances of one or more multi-instance TR-181 objects.

    Use get_supported_dm first to discover which objects are multi-instance
    (is_multi_instance=true). Then call get_instances to find out which
    concrete rows exist before using get_parameters, set_parameters, or
    delete_objects on a specific instance.

    Args:
        agent_id: Agent endpoint ID obtained from list_agents.
        obj_paths: Multi-instance object paths to query.
                   Examples: ["Device.WiFi.SSID.", "Device.NAT.PortMapping."]
        first_level_only: Return only immediate-level instances.

    Returns:
        Dict keyed by the requested object path. Each value is a list of
        instance records:
        {
          "Device.WiFi.SSID.": [
            {"path": "Device.WiFi.SSID.1.", "unique_keys": {"SSID": "HomeNet"}},
            {"path": "Device.WiFi.SSID.2.", "unique_keys": {"SSID": "GuestNet"}}
          ]
        }
        On error for a path, the value is {"error": "..."}.
    """
    result = await _rpc_call(
        "get_instances",
        {
            "agent_id": agent_id,
            "obj_paths": obj_paths,
            "first_level_only": first_level_only,
        },
    )
    return result or {}


@mcp.tool()
async def add_object(
    agent_id: str,
    create_objs: list[dict],
    allow_partial: bool = True,
) -> list[dict]:
    """
    Create new instances of multi-instance TR-181 objects on a USP agent.

    Use get_supported_dm to confirm the object has access "add-delete" or
    "add-only" before calling this. Use get_instances afterwards to verify
    the new instance path.

    Args:
        agent_id: Agent endpoint ID obtained from list_agents.
        create_objs: List of objects to create. Each entry:
          {
            "obj_path": "Device.WiFi.SSID.",
            "param_settings": [
              {"param": "SSID", "value": "NewNetwork", "required": true},
              {"param": "Enable", "value": "true", "required": false}
            ]
          }
        allow_partial: If true, successfully-created objects are kept even
                       when other objects in the same request fail.

    Returns:
        List of result records, one per requested object:
        - On success: {"requested_path": ..., "instantiated_path": ...,
                       "unique_keys": {...}, "param_errors": [...]}
        - On failure: {"requested_path": ..., "error": "Error <code>: <msg>"}
    """
    result = await _rpc_call(
        "add",
        {
            "agent_id": agent_id,
            "create_objs": create_objs,
            "allow_partial": allow_partial,
        },
    )
    return result or []


@mcp.tool()
async def delete_objects(
    agent_id: str,
    obj_paths: list[str],
    allow_partial: bool = True,
) -> list[dict]:
    """
    Delete existing instances of multi-instance TR-181 objects from a USP agent.

    Call get_instances first to obtain the exact instance paths to delete.
    Use get_supported_dm to confirm the object has access "add-delete" or
    "delete-only" before calling this.

    Args:
        agent_id: Agent endpoint ID obtained from list_agents.
        obj_paths: Fully-qualified instance paths to delete.
                   Examples: ["Device.WiFi.SSID.2.",
                              "Device.NAT.PortMapping.3."]
        allow_partial: If true, successfully-deleted paths are removed even
                       when other paths in the same request fail.

    Returns:
        List of result records, one per requested path:
        - On success: {"requested_path": ..., "affected_paths": [...],
                       "unaffected_errors": [...]}
        - On failure: {"requested_path": ..., "error": "Error <code>: <msg>"}
    """
    result = await _rpc_call(
        "delete",
        {
            "agent_id": agent_id,
            "obj_paths": obj_paths,
            "allow_partial": allow_partial,
        },
    )
    return result or []


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
