# MCP Frontend for USP Controller

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that exposes the USP controller as a set of tools callable by LLM assistants such as Claude.

## Overview

```
┌──────────────────────────────────────────────────────┐
│  LLM Client (Claude Desktop, MCP Inspector, etc.)    │
└────────────────────┬─────────────────────────────────┘
                     │  MCP (stdio or SSE)
                     ▼
┌──────────────────────────────────────────────────────┐
│  bin/mcp_server.py  (FastMCP)                        │
│                                                      │
│  Tools:                                              │
│  • list_agents          • get_supported_dm           │
│  • get_parameters       • get_instances              │
│  • set_parameters       • add_object                 │
│  • operate              • delete_objects             │
└────────────────────┬─────────────────────────────────┘
                     │  JSON-RPC 2.0 over UDS
                     │  /tmp/usp-controller-api.sock
                     ▼
┌──────────────────────────────────────────────────────┐
│  USP Controller  (controller/main.py)                │
│  Northbound API  (controller/northbound.py)          │
└────────────────────┬─────────────────────────────────┘
                     │  USP / TR-369  (UDS, CoAP, WS, STOMP)
                     ▼
┌──────────────────────────────────────────────────────┐
│  USP Agents  (devices)                               │
└──────────────────────────────────────────────────────┘
```

The MCP server is a **thin adapter**.  It connects to the same Unix domain socket used by the interactive shell (`bin/shell.py`) and translates MCP tool calls into northbound JSON-RPC requests, 1-to-1.

## Prerequisites

- Controller already running: `python controller/main.py`
- `fastmcp>=2.0` installed (`pip install fastmcp`)

## Running

### MCP Inspector (development)

```bash
fastmcp dev bin/mcp_server.py
```

Opens the MCP Inspector UI in the browser where you can invoke each tool manually.

### Claude Desktop

Add to `~/.claude/claude_desktop_config.json` (create if absent):

```json
{
  "mcpServers": {
    "usp-controller": {
      "command": "/path/to/pyagent-old/.penv/bin/python",
      "args": ["/path/to/pyagent-old/bin/mcp_server.py"]
    }
  }
}
```

Restart Claude Desktop — the tools appear automatically in the tool panel.

### stdio (generic MCP client)

```bash
python bin/mcp_server.py
```

The server runs on `stdio` transport (default for Claude Desktop and generic MCP clients).

## Tools

All tools require a running controller and at least one connected agent.  Call `list_agents` first to obtain an `agent_id`.

**Recommended workflow for multi-instance objects (tables):**
1. `get_supported_dm` — find objects where `is_multi_instance=true` and confirm their `access` value
2. `get_instances` — list which rows currently exist
3. `get_parameters` / `set_parameters` — read or update a specific instance
4. `add_object` — create a new instance
5. `delete_objects` — remove an instance

### `list_agents`

List all USP agents currently connected to the controller.

**Inputs:** none

**Returns:** list of agent records, each containing:

| Field | Description |
|---|---|
| `agent_id` | Unique endpoint ID — pass this to all other tools |
| `mtp_type` | Transport in use: `uds`, `coap`, `websocket`, `stomp` |
| `last_boot` | ISO 8601 timestamp of the agent's last boot |
| `last_heartbeat` | ISO 8601 timestamp of the most recent message |
| `manufacturer_oui`, `product_class`, `serial_number`, `ip_address` | When reported by the agent |

---

### `get_parameters`

Read TR-181 parameter values from an agent.

**Inputs:**

| Parameter | Type | Description |
|---|---|---|
| `agent_id` | `string` | From `list_agents` |
| `paths` | `[string]` | One or more TR-181 paths |

Path formats supported:
- Exact: `Device.DeviceInfo.Manufacturer`
- Object (all children): `Device.DeviceInfo.`
- Wildcard: `Device.WiFi.SSID.*.SSID`

**Returns:** `{path: value}` dict

---

### `set_parameters`

Write TR-181 parameter values to an agent.

**Inputs:**

| Parameter | Type | Description |
|---|---|---|
| `agent_id` | `string` | From `list_agents` |
| `parameters` | `[{path, value}]` | List of path/value objects |

**Returns:** `{path: value}` dict of applied values

---

### `operate`

Execute a USP command on an agent.

**Inputs:**

| Parameter | Type | Description |
|---|---|---|
| `agent_id` | `string` | From `list_agents` |
| `command` | `string` | Full TR-181 command path with `()` |
| `args` | `{string: string}` | Optional command arguments |

Common commands:
- `Device.Reboot()` — reboot the device
- `Device.FactoryReset()` — factory reset
- `Device.WiFi.Reset()` — reset Wi-Fi subsystem
- `Device.IP.Diagnostics.IPPing()` — run a ping diagnostic

**Returns:** list of result objects:

```json
[
  {
    "success": true,
    "executed_command": "Device.Reboot()",
    "output_args": {}
  }
]
```

`success` is `true` (sync success), `false` (error), or `null` (async/pending).

---

### `get_supported_dm`

Introspect the TR-181 data model supported by an agent — discover which parameters exist, which are writable, what commands are available, and what events can be subscribed to.

**Inputs:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `agent_id` | `string` | — | From `list_agents` |
| `obj_paths` | `[string]` | `["Device."]` | Object paths to query |
| `first_level_only` | `bool` | `false` | Return only immediate children |
| `return_commands` | `bool` | `true` | Include commands |
| `return_events` | `bool` | `true` | Include events |
| `return_params` | `bool` | `true` | Include parameters |

**Returns:** `{obj_path: object_info}` dict where each value contains:

```json
{
  "access": "add-delete",
  "is_multi_instance": true,
  "parameters": {
    "SSID": {"access": "read-write", "type": "string"}
  },
  "commands": {},
  "events": {}
}
```

The `access` field values for objects are: `read-only`, `add-delete`, `add-only`, `delete-only`.

---

### `get_instances`

List all existing instances of one or more multi-instance TR-181 objects.  Use after `get_supported_dm` reveals `is_multi_instance=true`.

**Inputs:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `agent_id` | `string` | — | From `list_agents` |
| `obj_paths` | `[string]` | — | Multi-instance object paths, e.g. `["Device.WiFi.SSID."]` |
| `first_level_only` | `bool` | `false` | Return only immediate-level instances |

**Returns:** `{obj_path: [instance, ...]}` dict:

```json
{
  "Device.WiFi.SSID.": [
    {"path": "Device.WiFi.SSID.1.", "unique_keys": {"SSID": "HomeNet"}},
    {"path": "Device.WiFi.SSID.2.", "unique_keys": {"SSID": "GuestNet"}}
  ]
}
```

On per-path error the value is `{"error": "..."}` instead of a list.

---

### `add_object`

Create new instances of multi-instance TR-181 objects.  Confirm `access` is `add-delete` or `add-only` with `get_supported_dm` first.

**Inputs:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `agent_id` | `string` | — | From `list_agents` |
| `create_objs` | `[object]` | — | List of objects to create (see below) |
| `allow_partial` | `bool` | `true` | Keep successful creates even if others fail |

Each entry in `create_objs`:

```json
{
  "obj_path": "Device.WiFi.SSID.",
  "param_settings": [
    {"param": "SSID", "value": "NewNetwork", "required": true},
    {"param": "Enable", "value": "true",       "required": false}
  ]
}
```

**Returns:** list of result records:

```json
[
  {
    "requested_path":    "Device.WiFi.SSID.",
    "instantiated_path": "Device.WiFi.SSID.3.",
    "unique_keys":       {"SSID": "NewNetwork"},
    "param_errors":      []
  }
]
```

On failure an entry contains `{"requested_path": ..., "error": "Error <code>: <msg>"}` instead.

---

### `delete_objects`

Delete existing instances of multi-instance TR-181 objects.  Call `get_instances` first to obtain exact instance paths.

**Inputs:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `agent_id` | `string` | — | From `list_agents` |
| `obj_paths` | `[string]` | — | Fully-qualified instance paths to delete |
| `allow_partial` | `bool` | `true` | Remove successful deletes even if others fail |

**Returns:** list of result records:

```json
[
  {
    "requested_path": "Device.WiFi.SSID.2.",
    "affected_paths":  ["Device.WiFi.SSID.2."],
    "unaffected_errors": []
  }
]
```

On failure an entry contains `{"requested_path": ..., "error": "Error <code>: <msg>"}` instead.

## Example LLM Session

```
User: What devices do we have connected?

Claude: [calls list_agents]
        → One agent: self::uds-agent-001 (UDS, last seen 2 s ago)

User: What's the manufacturer and firmware version?

Claude: [calls get_parameters with ["Device.DeviceInfo.Manufacturer",
                                    "Device.DeviceInfo.SoftwareVersion"]]
        → Manufacturer: Acme Corp
          SoftwareVersion: 3.14.1

User: Show me the Wi-Fi SSIDs that are configured.

Claude: [calls get_instances with obj_paths=["Device.WiFi.SSID."]]
        → SSID.1. → "HomeNet", SSID.2. → "GuestNet"

User: Add a third SSID called IoTNet.

Claude: [calls add_object with create_objs=[{obj_path: "Device.WiFi.SSID.",
         param_settings: [{param:"SSID",value:"IoTNet",required:true}]}]]
        → Created at Device.WiFi.SSID.3.

User: Delete the guest SSID.

Claude: [calls delete_objects with obj_paths=["Device.WiFi.SSID.2."]]
        → Deleted Device.WiFi.SSID.2.

User: Reboot the device with a 30-second delay.

Claude: [calls operate with command="Device.Reboot()", args={"Delay":"30"}]
        → Command executed successfully. Device will reboot in 30 seconds.
```

## Testing

Tests are in `tests/test_mcp_server.py` and use mocked UDS sockets — no live controller needed.  30 tests cover all 8 tools plus the `_rpc_call` helper.

```bash
pytest tests/test_mcp_server.py -v
```

## Architecture Notes

- **Transport**: `stdio` by default (compatible with Claude Desktop and MCP Inspector); `fastmcp` also supports `sse` for HTTP-based clients — change `mcp.run()` to `mcp.run(transport="sse")`.
- **Connection model**: a new UDS connection is opened per tool call (same as the shell) — no persistent connection or reconnect logic required.
- **Timeout**: 10 seconds per request (matches the controller's own agent timeout).
- **Error propagation**: JSON-RPC errors from the controller are re-raised as `RuntimeError`, which MCP surfaces to the LLM as a tool error with the full message.

## Files

| File | Purpose |
|---|---|
| `bin/mcp_server.py` | MCP server entry point |
| `tests/test_mcp_server.py` | Unit tests (mocked UDS) |
| `controller/northbound.py` | Northbound JSON-RPC server the MCP server connects to |
| `docs/CONTROLLER_API.md` | Full northbound API reference |
