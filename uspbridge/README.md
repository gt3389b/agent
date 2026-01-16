# USP Bridge Architecture

## Overview

The USP Bridge system provides a plugin architecture for translating between USP (User Services Platform TR-369) Protobuf messages and various target service protocols. This allows USP agents to communicate with services that don't natively speak USP, such as:

- **WRP** (Web Routing Protocol) - RDK/Xfinity ecosystem - [See WRPBRIDGE.md](WRPBRIDGE.md)
- **RBUS** - RDK Bus for inter-component communication
- **DBUS** - D-Bus IPC for Linux systems
- **UBUS** - OpenWrt micro bus for embedded routers
- **HTTP/REST** - Standard web APIs
- **MQTT** - IoT messaging protocol

## Architecture

```
┌─────────────────┐
│  USP Controller │ (TR-369)
└────────┬────────┘
         │ USP Protobuf Messages
         ▼
┌─────────────────┐
│   USP Agent     │
└────────┬────────┘
         │ UspMessage objects
         ▼
┌─────────────────┐
│   UspBridge     │ (Abstract Interface)
│   (base.py)     │
└────────┬────────┘
         │
    ┌────┴────┬────────────┬──────────┬──────────┐
    │         │            │          │          │
    ▼         ▼            ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌─────────┐ ┌──────┐ ┌──────┐
│  WRP   │ │ Future │ │ Future  │ │ RBUS │ │ DBUS │
│ Bridge │ │ HTTP   │ │ MQTT    │ │ UBUS │ │ etc. │
└────┬───┘ │ Bridge │ │ Bridge  │ └──────┘ └──────┘
     │     └────────┘ └─────────┘
     │ WRP msgpack bytes
     ▼
┌─────────────────┐
│ Parodus/WRP     │ (RDK)
│ Device Services │
└─────────────────┘
```

## Two-Channel Architecture: Simplifying MTP ↔ Bridge ↔ Bus Integration

### Design Philosophy

The bridge uses a **two-channel pattern** that dramatically simplifies binding code when connecting MTP (Message Transport Protocol) layers to service buses:

- **TX Channel**: `send()` or `to_bytes()` → Serialize and transmit outbound requests
- **RX Channel**: `from_bytes()` → Deserialize and parse inbound responses

This separation of concerns eliminates the need for complex synchronous request/response coupling in binding code.

### Data Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                         OUTBOUND (TX)                            │
└──────────────────────────────────────────────────────────────────┘

USP Controller                    USP Agent/MTP                Bridge                  Target Bus
     │                                  │                        │                          │
     │  USP Protobuf                    │                        │                          │
     ├─────────────────────────────────►│                        │                          │
     │                                  │  UspMessage            │                          │
     │                                  ├───────────────────────►│                          │
     │                                  │                        │ to_bytes() or send()     │
     │                                  │                        ├─────────────────────────►│
     │                                  │                        │  Protocol-specific bytes │
     │                                  │                        │  (WRP msgpack, RBUS, etc)│

┌──────────────────────────────────────────────────────────────────┐
│                         INBOUND (RX)                             │
└──────────────────────────────────────────────────────────────────┘

USP Controller              USP Agent/MTP                  Bridge                  Target Bus
     │                          │                           │                          │
     │                          │                           │  Response bytes          │
     │                          │                           │◄─────────────────────────┤
     │                          │                           │ from_bytes()             │
     │                          │  (operation, data, ctx)   │                          │
     │                          │◄──────────────────────────┤                          │
     │  USP Protobuf            │  Build UspResponse        │                          │
     │◄─────────────────────────┤                           │                          │
     │                          │                           │                          │
```

### Binding Code Simplification

**Without Two-Channel Pattern** (Complex):
```python
class ComplexBinding:
    def handle_request(self, usp_msg):
        # Tightly coupled - must handle request AND response together
        if isinstance(usp_msg, GetRequest):
            wrp_msg = self.translate_get(usp_msg)
            wrp_bytes = self.encode(wrp_msg)
            self.bus.send(wrp_bytes)
            
            # Blocking wait - can't handle other requests
            response_bytes = self.bus.receive()
            wrp_response = self.decode(response_bytes)
            
            # Must remember what type of request this was!
            return self.translate_get_response(wrp_response)
        elif isinstance(usp_msg, SetRequest):
            # Duplicate logic for every operation type...
            pass
```

**With Two-Channel Pattern** (Simple):
```python
class SimpleBinding:
    def __init__(self, bridge, bus):
        self.bridge = bridge
        self.bus = bus
        
        # TX: Simple pipe - MTP → Bridge → Bus
        def send_to_bus(request, context):
            self.bridge.send(request, context)
        
        # RX: Simple pipe - Bus → Bridge → MTP
        def receive_from_bus():
            response_bytes = self.bus.receive()
            operation, data, context = self.bridge.from_bytes(response_bytes)
            return self.build_response(operation, data, context)
        
        # Done! No request/response coupling, no operation-specific logic
```

### Key Advantages

1. **Decoupled TX/RX**: Outbound and inbound paths are independent
   - TX doesn't block waiting for RX
   - Supports async/event-driven architectures naturally
   - Can handle interleaved requests/responses

2. **No Operation-Specific Logic**: Bridge handles all operation types uniformly
   - Same code for Get, Set, Operate, Add, Delete, etc.
   - Operation type encoded in metadata during TX (e.g., WRP metadata field)
   - `from_bytes()` returns operation type from metadata on RX
   - Binding code doesn't need to know about USP operations

3. **Transport Agnostic**: Works with any MTP or bus transport
   - Nanomsg, Unix Domain Sockets, WebSockets, STOMP, MQTT, etc.
   - Just pipe bytes through - no protocol knowledge needed in binding

4. **Simplified Testing**: Each channel can be tested independently
   ```python
   # Test TX channel
   bytes_out = bridge.to_bytes(request, context)
   assert_valid_wrp_message(bytes_out)
   
   # Test RX channel  
   operation, data, ctx = bridge.from_bytes(response_bytes)
   assert operation == "get"
   ```

5. **Request/Response Correlation**: Context object tracks everything
   - No need to maintain pending request dictionaries in binding code
   - Bridge preserves correlation via transaction IDs and metadata
   - Binding just forwards context through both channels

### Real-World Example: MTP Layer Integration

```python
class UspMtpBinding:
    """Simple binding connecting USP MTP to target bus via bridge"""
    
    def __init__(self, mtp, bridge, bus):
        self.mtp = mtp
        self.bridge = bridge
        self.bus = bus
        
        # Wire up channels
        mtp.on_request(self.handle_outbound)   # TX: MTP → Bus
        bus.on_data(self.handle_inbound)       # RX: Bus → MTP
    
    def handle_outbound(self, usp_request, mtp_context):
        """TX Channel: USP Request → Bridge → Bus"""
        # Create bridge context from MTP context
        bridge_context = BridgeContext(
            usp_msg_id=usp_request.msg_id,
            controller_endpoint=mtp_context.endpoint,
            mtp_id=mtp_context.protocol
        )
        
        # Send through bridge to bus (one line!)
        self.bridge.send(usp_request, bridge_context)
    
    def handle_inbound(self, bus_data):
        """RX Channel: Bus → Bridge → USP Response"""
        # Parse response from bus (one line!)
        operation, data, context = self.bridge.from_bytes(bus_data)
        
        # Build USP response and send to MTP
        usp_response = self.build_usp_response(operation, data)
        self.mtp.send_response(usp_response, context.controller_endpoint)
    
    def build_usp_response(self, operation, data):
        """Helper to construct proper USP response based on operation"""
        if operation == "get":
            return GetResponse(parameters=data["parameters"])
        elif operation == "set":
            return SetResponse(results=data["results"])
        # ... etc - but this is simple mapping, no business logic
```

**Result**: ~20 lines of binding code vs 100+ lines with tight coupling!

## Implemented Bridges

### WRP Bridge (`wrp_bridge.py`)

Complete implementation for RDK/Xfinity ecosystem using WRP (Web Routing Protocol).

**Features:**
- USP ↔ WRP JSON-RPC translation
- Msgpack encoding/decoding
- Metadata-based context preservation
- Structured transaction IDs
- All USP operations supported (Get, Set, Operate, Add, Delete, etc.)

**Documentation**: See [WRPBRIDGE.md](WRPBRIDGE.md) for complete WRP bridge documentation.

**Quick Start:**
```python
from uspbridge import WrpBridge
from message.request import GetRequest

bridge = WrpBridge(mac_address="112233445566")
request = GetRequest(paths=["Device.DeviceInfo.Manufacturer"])
wrp_bytes = bridge.to_bytes(request)
```

### Future Bridges

- **RBUS Bridge** - RDK Bus for component communication
- **DBUS Bridge** - D-Bus IPC for Linux systems  
- **UBUS Bridge** - OpenWrt micro bus
- **HTTP Bridge** - RESTful APIs
- **MQTT Bridge** - IoT messaging

## Abstract Interface: `UspBridge`

All bridge implementations must inherit from `UspBridge` (defined in `base.py`) and implement:

### Required Methods

#### Operation Handlers
```python
def get(self, request: GetRequest, context: Optional[Any] = None) -> GetResponse:
    """Retrieve parameter values"""

def set(self, request: SetRequest, context: Optional[Any] = None) -> SetResponse:
    """Set parameter values"""

def operate(self, request: OperateRequest, context: Optional[Any] = None) -> OperateResponse:
    """Execute commands"""

def add(self, request: AddRequest, context: Optional[Any] = None) -> AddResponse:
    """Create object instances"""

def delete(self, request: DeleteRequest, context: Optional[Any] = None) -> DeleteResponse:
    """Delete object instances"""

def get_supported_dm(self, request: GetSupportedDMRequest, context: Optional[Any] = None) -> GetSupportedDMResponse:
    """Query data model metadata"""

def get_instances(self, request: GetInstancesRequest, context: Optional[Any] = None) -> GetInstancesResponse:
    """Query object instances"""

def get_supported_protocol(self, request: GetSupportedProtocolRequest, context: Optional[Any] = None) -> GetSupportedProtocolResponse:
    """Query supported USP protocol versions"""
```

#### Event Handlers
```python
def send_event(self, notify: UspMessage, context: Optional[Any] = None) -> None:
    """Send USP Notify event to target service"""

def on_event(self, event_data: bytes, context: Optional[Any] = None) -> UspMessage:
    """Handle incoming event and return USP Notify message"""
```

#### Subscription Handlers
```python
def subscribe(self, subscription_id: str, reference_list: List[str], 
              notification_type: str = "ValueChange", context: Optional[Any] = None) -> bool:
    """Subscribe to parameter/object notifications"""

def unsubscribe(self, subscription_id: str, context: Optional[Any] = None) -> bool:
    """Unsubscribe from notifications"""

def list_subscriptions(self, context: Optional[Any] = None) -> List[Dict[str, Any]]:
    """List active subscriptions"""
```

#### Wire Format Methods
```python
def to_bytes(self, request: UspMessage, context: Optional[Any] = None) -> bytes:
    """Serialize USP request to wire format bytes (for testing/inspection)"""

def send(self, request: UspMessage, context: Optional[Any] = None) -> None:
    """Send USP request over the transport (production method)"""

def from_bytes(self, data: bytes) -> tuple:
    """Deserialize wire format bytes to USP response"""
```

### Provided Methods

```python
def handle_request(self, request: UspMessage, context: Optional[Any] = None) -> UspMessage:
    """Auto-dispatch to appropriate handler based on request type"""
```

## Using a Bridge

### Two-Channel Pattern

All bridges follow a two-channel pattern for communication:

**Channel 1 (Outbound)**: `to_bytes()` + `send()`
- `to_bytes(request, context) -> bytes`: Serialize USP request (for testing/inspection)
- `send(request, context)`: Serialize and transmit (production method)

**Channel 2 (Inbound)**: `from_bytes()`
- `from_bytes(data) -> (operation, data, context)`: Deserialize response

### Basic Pattern with send()

```python
from uspbridge import WrpBridge
from message.request import GetRequest

# 1. Create bridge with transport
def my_transport_send(data: bytes):
    """Your transport implementation"""
    socket.sendall(data)

bridge = WrpBridge(
    mac_address="112233445566",
    transport_send=my_transport_send
)

# 2. Create USP request
request = GetRequest(paths=["Device.DeviceInfo.Manufacturer"])

# 3. Send directly (serialization + transmission)
bridge.send(request, context)

# 4. Receive response
response_bytes = transport.receive()

# 5. Deserialize response
operation, data, context = bridge.from_bytes(response_bytes)
```

### Manual Serialization Pattern

For testing or when you need to control transmission separately:

```python
from uspbridge import WrpBridge
from message.request import GetRequest

# 1. Create bridge instance
bridge = WrpBridge(mac_address="112233445566")

# 2. Create USP request
request = GetRequest(paths=["Device.DeviceInfo.Manufacturer"])

# 3. Serialize to wire format
wire_bytes = bridge.to_bytes(request, context)

# 4. Inspect or test
print(f"Serialized {len(wire_bytes)} bytes")

# 5. Send over transport manually
transport.send(wire_bytes)

# 6. Receive response
response_bytes = transport.receive()

# 7. Deserialize response
operation, data, context = bridge.from_bytes(response_bytes)
```

### With Transport Layer

```python
# Using bridge with transport wrapper
class UspAgent:
    def __init__(self, bridge):
        self.bridge = bridge
    
    def get_parameter(self, path):
        request = GetRequest(paths=[path])
        
        # Send using bridge's transport
        self.bridge.send(request)
        
        # Or manually if you need more control
        # wire_bytes = self.bridge.to_bytes(request)
        # self.transport.send(wire_bytes)
        
        response_bytes = self.transport.receive()
        operation, data, context = self.bridge.from_bytes(response_bytes)
        return data
```

## Adding New Bridge Implementations

To add a new bridge (e.g., HTTP Bridge, MQTT Bridge, RBUS Bridge, DBUS Bridge, UBUS Bridge):

1. **Create Bridge Module**: `uspbridge/http_bridge.py` (or `rbus_bridge.py`, `dbus_bridge.py`, etc.)

2. **Inherit from UspBridge**:
```python
from uspbridge.base import UspBridge, BridgeError

class HttpBridge(UspBridge):
    def __init__(self, base_url: str):
        self.base_url = base_url
    
    def get(self, request: GetRequest, context = None):
        # Translate GetRequest to HTTP GET
        # Send HTTP request
        # Parse HTTP response
        # Return GetResponse
        pass
    
    def to_bytes(self, request: UspMessage, context = None) -> bytes:
        # Translate to HTTP request format
        # Return HTTP request bytes
        pass
    
    def from_bytes(self, data: bytes) -> tuple:
        # Parse HTTP response
        # Return (operation, data, context)
        pass
    
    # Implement other required methods...
```

3. **Export from Package**: Add to `uspbridge/__init__.py`
```python
from uspbridge.http_bridge import HttpBridge

__all__ = [
    'UspBridge',
    'WrpBridge',
    'HttpBridge'  # New bridge
]
```

4. **Write Tests**: Create `tests/test_http_bridge.py`

## Testing

All bridge implementations should have comprehensive test coverage:

### Unit Tests
- Message encoding/decoding
- Protocol translation
- Context preservation
- Error handling

### Integration Tests
- End-to-end request-response flows
- Mock service clients
- Operation type differentiation
- Metadata preservation

### Example: WRP Bridge Tests

See `tests/test_usp2wrp_bridge.py` and `tests/test_usp2wrp_integration.py` for comprehensive examples.

**Run tests:**
```bash
# All bridge tests
pytest tests/test_usp2wrp_bridge.py tests/test_usp2wrp_integration.py -v

# Specific test
pytest tests/test_usp2wrp_integration.py::test_operation_type_differentiation -v
```

## Future Enhancements

### Short Term
- [x] Proper return types (GetResponse, SetResponse, etc.)
- [x] Event handling interface (send_event/on_event)
- [x] Subscription management interface
- [ ] Implement Add/Delete/GetSupportedProtocol in WRP bridge
- [ ] Create USP Notify message class
- [ ] Add WRP event → USP notification translation implementation
- [ ] Create WRP transport layer (nanomsg/UDS wrapper)

### Medium Term
- [ ] HTTP Bridge implementation
- [ ] MQTT Bridge implementation
- [ ] RBUS Bridge implementation (RDK Bus)
- [ ] DBUS Bridge implementation (D-Bus IPC)
- [ ] UBUS Bridge implementation (OpenWrt micro bus)
- [ ] Bridge configuration system
- [ ] Async/await support

### Long Term
- [ ] Bridge plugin system
- [ ] Dynamic bridge discovery
- [ ] Bridge composition/chaining
- [ ] Performance monitoring

## References

- **USP Specification**: BBF TR-369
- **TR-181 Data Model**: BBF TR-181
- **WRP Bridge**: [WRPBRIDGE.md](WRPBRIDGE.md)
- **WRP Specification**: https://xmidt.io/docs/wrp/basics/
- **Parodus**: https://github.com/xmidt-org/parodus

## See Also

- [WRPBRIDGE.md](WRPBRIDGE.md) - Complete WRP bridge documentation
- [BRIDGE_INTERFACE_UPDATE.md](../BRIDGE_INTERFACE_UPDATE.md) - Recent interface changes
- [tests/TEST_COVERAGE.md](../tests/TEST_COVERAGE.md) - Test coverage details
