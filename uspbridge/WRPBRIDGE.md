# WRP Bridge Implementation

## Overview

The WRP Bridge (`wrp_bridge.py`) implements the `UspBridge` abstract interface for WRP (Web Routing Protocol) used in the Xfinity/RDK ecosystem. It translates USP protocol messages to WRP JSON-RPC messages encoded in msgpack format.

## Key Features

1. **Message Translation**: USP messages ↔ WRP JSON-RPC
2. **Msgpack Encoding**: Python objects ↔ msgpack bytes
3. **Context Preservation**: Metadata-based routing and correlation
4. **Operation Differentiation**: Critical for distinguishing get/set/operate
5. **Structured Transaction IDs**: `{usp_msg_id}:{sequence}:{controller_id}`

## Installation

```python
from uspbridge import WrpBridge, BridgeContext
```

## Usage

### Production Usage - with send()

```python
from uspbridge import WrpBridge, BridgeContext
from message.request import GetRequest

# Create bridge with transport
def my_transport_send(data: bytes):
    """Your transport implementation (nanomsg, UDS, etc.)"""
    socket.sendall(data)

bridge = WrpBridge(
    mac_address="112233445566",
    transport_send=my_transport_send
)

# Create USP request
request = GetRequest(
    paths=["Device.DeviceInfo.Manufacturer", "Device.DeviceInfo.ModelName"],
    msg_id="usp-msg-12345"
)

# Create context
context = BridgeContext(
    usp_msg_id=request.msg_id,
    controller_endpoint="proto::controller-1",
    mtp_id="coap",
    mac_address="112233445566",
    controller_id="ctrl-01"
)

# Send (serializes + transmits in one call)
bridge.send(request, context)

# Receive response
response_bytes = transport.receive()

# Deserialize response
operation, data, context = bridge.from_bytes(response_bytes)

# Handle based on operation type
if operation == "get":
    for param in data["parameters"]:
        print(f"{param['name']} = {param['value']}")
```

### Manual Serialization - with to_bytes()

For testing or when you need control over transmission:

```python
from uspbridge import WrpBridge, BridgeContext
from message.request import GetRequest

# Create bridge (no transport needed)
bridge = WrpBridge(mac_address="112233445566")

# Create USP request
request = GetRequest(
    paths=["Device.DeviceInfo.Manufacturer"],
    msg_id="usp-msg-12345"
)

# Create context
context = BridgeContext(
    usp_msg_id=request.msg_id,
    controller_endpoint="proto::controller-1",
    mtp_id="coap",
    mac_address="112233445566"
)

# Serialize to WRP msgpack bytes
wrp_bytes = bridge.to_bytes(request, context)

# Inspect or test
print(f"Serialized {len(wrp_bytes)} bytes")

# Send over transport manually
transport.send(wrp_bytes)

# Receive response
response_bytes = transport.receive()

# Deserialize response
operation, data, context = bridge.from_bytes(response_bytes)

# Handle response
if operation == "get":
    for param in data["parameters"]:
        print(f"{param['name']} = {param['value']}")
```

### Advanced Usage - Direct WRP Messages

```python
# Get WRP message object (without encoding)
wrp_msg = bridge.to_wrp(request, context)

# Inspect WRP message
print(f"WRP dest: {wrp_msg.dest}")
print(f"Metadata: {wrp_msg.metadata}")

# Manually encode to msgpack
msgpack_bytes = wrp_msg.to_bytes()
```

## WRP Message Structure

```python
WrpMessage(
    msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,  # Type of message
    source="mac:112233445566/usp",                  # Source endpoint
    dest="mac:112233445566/usp2wrp",                # Destination endpoint
    transaction_id="usp-12345:001:ctrl-01",         # Structured ID
    content_type="application/json",                # Payload type
    payload=b'{"jsonrpc":"2.0",...}',               # JSON-RPC message
    metadata={                                      # USP context
        "usp_msg_id": "usp-12345",
        "usp_operation": "get",                     # CRITICAL!
        "controller_endpoint": "proto::controller-1",
        "mtp_id": "coap",
        "timestamp": "1234567890"
    }
)
```

### Message Type Enum

```python
class MessageType(IntEnum):
    AUTH = 2
    SIMPLE_REQUEST_RESPONSE = 3
    SIMPLE_EVENT = 4
    CREATE = 5
    RETRIEVE = 6
    UPDATE = 7
    DELETE = 8
    SERVICE_REGISTRATION = 9
    SERVICE_ALIVE = 10
    UNKNOWN = 11
```

## Operation Type Differentiation (CRITICAL!)

**Problem**: All USP operations (Get, Set, Operate) translate to JSON-RPC method calls in WRP. When the response comes back, how do we know which USP operation it was?

**Solution**: The `usp_operation` metadata field preserves the original operation type:

```python
# Request metadata
{
    "usp_operation": "get",      # GetRequest
    "usp_operation": "set",      # SetRequest  
    "usp_operation": "operate",  # OperateRequest
    "usp_operation": "add",      # AddRequest
    "usp_operation": "delete",   # DeleteRequest
}
```

**Flow**:
1. **Request**: Bridge stores `usp_operation` in WRP metadata
2. **Transport**: Parodus/service echoes metadata back in response
3. **Response**: Bridge reads `usp_operation` to determine response type
4. **Build Response**: Correct USP response object is constructed

## Context Preservation

The `BridgeContext` dataclass manages context across request-response:

```python
@dataclass
class BridgeContext:
    usp_msg_id: str              # Original USP message ID
    controller_endpoint: str      # Controller for routing responses
    mtp_id: str                  # MTP identifier
    mac_address: str             # Device MAC address
    controller_id: str           # Short controller ID
    sequence: int                # Sequence counter
```

### Structured Transaction IDs

Format: `{usp_msg_id}:{sequence}:{controller_id}`
- Example: `"usp-msg-12345:001:ctrl-01"`
- Enables correlation without metadata

### Metadata Fields

- `usp_msg_id`: Original USP message ID
- `usp_operation`: Operation type (get/set/operate/add/delete/etc.)
- `usp_path`: TR-181 path (optional)
- `usp_command`: Full command for Operate (e.g., "Device.Reboot()")
- `controller_endpoint`: Routing info
- `mtp_id`: MTP identifier
- `timestamp`: Unix timestamp

## Protocol Translation

### Get Request
```
USP GetRequest                          WRP JSON-RPC
─────────────                          ──────────────
paths: [                               {
  "Device.DeviceInfo.Manufacturer",      "jsonrpc": "2.0",
  "Device.DeviceInfo.ModelName"          "id": "usp-12345:001:ctrl-01",
]                                        "method": "get",
                                         "params": {
                                           "names": [...]
                                         }
                                       }
```

### Set Request
```
USP SetRequest                         WRP JSON-RPC
──────────────                         ──────────────
parameters: {                          {
  "Device.WiFi.Radio.1.Enable": "true"   "jsonrpc": "2.0",
}                                        "id": "usp-12345:002:ctrl-01",
                                         "method": "set",
                                         "params": {
                                           "parameters": [
                                             {
                                               "name": "...",
                                               "value": "true",
                                               "dataType": 3
                                             }
                                           ]
                                         }
                                       }
```

### Operate Request
```
USP OperateRequest                     WRP JSON-RPC
──────────────────                     ──────────────
command: "Device.Reboot()"             {
input_args: {"Delay": 10}                "jsonrpc": "2.0",
                                         "id": "usp-12345:003:ctrl-01",
                                         "method": "Device.Reboot",
                                         "params": {"Delay": 10}
                                       }
                                       
                                       metadata: {
                                         "usp_operation": "operate",
                                         "usp_command": "Device.Reboot()"
                                       }
```

### Add Request
```
USP AddRequest                         WRP JSON-RPC
──────────────                         ──────────────
obj_path: "Device.WiFi.SSID."          {
params: {                                "jsonrpc": "2.0",
  "SSID": "MyNetwork",                   "id": "usp-12345:004:ctrl-01",
  "Enable": "true"                       "method": "addObject",
}                                        "params": {
                                           "objectPath": "Device.WiFi.SSID.",
                                           "parameters": [
                                             {"name": "SSID", "value": "MyNetwork", "dataType": 1},
                                             {"name": "Enable", "value": "true", "dataType": 3}
                                           ]
                                         }
                                       }
                                       
                                       metadata: {
                                         "usp_operation": "add"
                                       }
```

### Delete Request
```
USP DeleteRequest                      WRP JSON-RPC
─────────────────                      ──────────────
obj_paths: [                           {
  "Device.WiFi.SSID.3."                  "jsonrpc": "2.0",
]                                        "id": "usp-12345:005:ctrl-01",
                                         "method": "deleteObject",
                                         "params": {
                                           "objectPath": "Device.WiFi.SSID.3."
                                         }
                                       }
                                       
                                       metadata: {
                                         "usp_operation": "delete"
                                       }
```

## Data Type Inference

The bridge automatically infers TR-181 data types from string values:

```python
"true" / "false"  → dataType: 3 (boolean)
"42" / "-123"     → dataType: 2 (int)
"hello"           → dataType: 1 (string)
```

### Data Type Mapping

- 0: Auto-detect
- 1: string
- 2: int
- 3: boolean
- 4: dateTime
- 5: base64

## Error Mapping

### USP → WRP

```python
7000 (Internal error)       → 500
7004 (Invalid arguments)    → 400
7006 (Permission denied)    → 403
7026 (Invalid path)         → 404
7024 (Resources exceeded)   → 503
7022 (Command failed)       → 507
```

### WRP → USP

```python
200 (Success)              → 0
400 (Bad Request)          → 7004
403 (Forbidden)            → 7006
404 (Not Found)            → 7026
500 (Internal Error)       → 7000
503 (Service Unavailable)  → 7024
```

## WRP Endpoints

### Source Endpoint
Format: `mac:{MAC_ADDRESS}/{SERVICE}`
- Example: `mac:112233445566/usp`
- Identifies the USP agent

### Destination Endpoint
Format: `mac:{MAC_ADDRESS}/{SERVICE}`
- Example: `mac:112233445566/usp2wrp`
- Routes to WRP translation service

### Event Endpoints
Format: `event:{EVENT_TYPE}/mac:{MAC_ADDRESS}/{SERVICE}`
- Example: `event:device-status/mac:112233445566/usp`
- Used for WRP SIMPLE_EVENT messages

## Testing

The WRP bridge has comprehensive test coverage:

- **Unit Tests**: `tests/test_usp2wrp_bridge.py` (32 tests)
  - Message encoding/decoding
  - Protocol translation
  - Context preservation
  - Helper methods

- **Integration Tests**: `tests/test_usp2wrp_integration.py` (14 tests)
  - End-to-end request-response flows
  - Mock Parodus client
  - Operation type differentiation
  - Metadata preservation

Run tests:
```bash
pytest tests/test_usp2wrp_bridge.py tests/test_usp2wrp_integration.py -v
```

## Transport Layer Integration

The WRP bridge is designed to work with a separate transport layer:

```python
# Example transport wrapper (not implemented)
class WrpTransport:
    def __init__(self, bridge, socket_path="/tmp/parodus_usp"):
        self.bridge = bridge
        self.socket = connect_to_parodus(socket_path)
    
    def send_request(self, request, context):
        # Serialize using bridge
        wrp_bytes = self.bridge.to_bytes(request, context)
        
        # Send over nanomsg/UDS
        self.socket.send(wrp_bytes)
        
        # Receive response
        response_bytes = self.socket.recv()
        
        # Deserialize using bridge
        operation, data, context = self.bridge.from_bytes(response_bytes)
        
        return operation, data, context
```

## References

- **WRP Specification**: https://xmidt.io/docs/wrp/basics/
- **Parodus**: https://github.com/xmidt-org/parodus
- **TR-181 Data Model**: BBF TR-181
- **USP Specification**: BBF TR-369
