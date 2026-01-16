# USP Bridge Interface Updates

## Summary

Updated the USP Bridge abstract interface to include:
1. **Proper return type annotations** - All methods now return typed response objects
2. **Event handling support** - Added `send_event()` and `on_event()` methods
3. **Subscription management** - Added `subscribe()`, `unsubscribe()`, and `list_subscriptions()` methods

## Changes to `uspbridge/base.py`

### 1. Added Response Type Imports

```python
from message.response import (
    GetResponse,
    SetResponse,
    OperateResponse,
    GetSupportedDMResponse,
    GetInstancesResponse
)
```

### 2. Updated Method Return Types

Changed from generic `Any` to specific response types:

```python
# Before
def get(self, request: GetRequest, context: Optional[Any] = None) -> Any:

# After
def get(self, request: GetRequest, context: Optional[Any] = None) -> GetResponse:
```

All USP operations now have proper return types:
- `get()` → `GetResponse`
- `set()` → `SetResponse`
- `operate()` → `OperateResponse`
- `get_supported_dm()` → `GetSupportedDMResponse`
- `get_instances()` → `GetInstancesResponse`

### 3. Added Event Handling Methods

#### `send_event()`
Sends event notifications to the target service (e.g., Boot!, ValueChange!).

```python
@abstractmethod
def send_event(self, event_name: str, obj_path: str, params: Dict[str, Any], 
               context: Optional[Any] = None) -> None:
    """
    Send event notification to target service
    
    Common USP Events:
    - "Boot!": Device booted
    - "ValueChange!": Parameter value changed
    - "OperationComplete!": Async operation completed
    - "ObjectCreation!": Object instance created
    - "ObjectDeletion!": Object instance deleted
    """
```

**Example Usage:**
```python
bridge.send_event(
    event_name="ValueChange!",
    obj_path="Device.WiFi.Radio.1.",
    params={
        "ParamName": "Channel",
        "ParamValue": "11"
    }
)
```

#### `on_event()`
Handles incoming events from the target service.

```python
@abstractmethod
def on_event(self, event_data: bytes, context: Optional[Any] = None) -> Dict[str, Any]:
    """
    Handle incoming event from target service
    
    Returns:
        Dictionary with event details:
        {
            "event_name": "Boot!" | "ValueChange!" | ...,
            "obj_path": "Device.WiFi.Radio.1.",
            "params": {...}
        }
    """
```

**Example Usage:**
```python
event = bridge.on_event(wrp_event_bytes)
# Returns:
# {
#     "event_name": "ValueChange!",
#     "obj_path": "Device.WiFi.Radio.1.",
#     "params": {
#         "ParamName": "Channel",
#         "ParamValue": "11"
#     }
# }
```

### 4. Added Subscription Management Methods

#### `subscribe()`
Subscribes to notifications for specified paths (maps to USP init_subscriptions).

```python
@abstractmethod
def subscribe(self, subscription_id: str, reference_list: List[str], 
              notification_type: str = "ValueChange",
              context: Optional[Any] = None) -> bool:
    """
    Subscribe to notifications for specified paths
    
    Args:
        subscription_id: Unique subscription identifier
        reference_list: List of parameter/object paths to monitor
            Examples:
            - "Device.WiFi.Radio.1.Channel" (specific parameter)
            - "Device.WiFi.Radio.*." (all radios)
            - "Device.WiFi.SSID.*.SSID" (SSID parameter for all instances)
        notification_type: Type of notifications to receive
            - "ValueChange": Parameter value changes
            - "ObjectCreation": Object instance created
            - "ObjectDeletion": Object instance deleted
            - "OperationComplete": Async operation completed
            - "Event": Data model events (Boot!, etc.)
    """
```

**Example Usage:**
```python
# Subscribe to WiFi channel changes on all radios
bridge.subscribe(
    subscription_id="sub-wifi-channels",
    reference_list=["Device.WiFi.Radio.*.Channel"],
    notification_type="ValueChange"
)
```

#### `unsubscribe()`
Cancels an active subscription.

```python
@abstractmethod
def unsubscribe(self, subscription_id: str, context: Optional[Any] = None) -> bool:
    """Unsubscribe from notifications"""
```

#### `list_subscriptions()`
Lists all active subscriptions.

```python
@abstractmethod
def list_subscriptions(self, context: Optional[Any] = None) -> List[Dict[str, Any]]:
    """
    Returns:
        List of subscription dictionaries:
        [
            {
                "subscription_id": "sub-1",
                "reference_list": ["Device.WiFi.Radio.*.Channel"],
                "notification_type": "ValueChange",
                "enabled": True
            },
            ...
        ]
    """
```

## Changes to `uspbridge/wrp_bridge.py`

Added stub implementations for all new abstract methods. These raise `NotImplementedError` with informative messages since they require:
- Transport layer (for event sending/receiving)
- Subscription manager (for persistent subscription state)
- Data model integration (for change notifications)

### Event Handling Stubs

```python
def send_event(self, event_name: str, obj_path: str, params: Dict[str, Any], 
               context: Optional[BridgeContext] = None) -> None:
    """Send event notification via WRP SIMPLE_EVENT"""
    raise NotImplementedError(
        "send_event() requires transport layer - WRP events need SIMPLE_EVENT message type"
    )

def on_event(self, event_data: bytes, context: Optional[BridgeContext] = None) -> Dict[str, Any]:
    """Handle incoming WRP SIMPLE_EVENT"""
    raise NotImplementedError(
        "on_event() requires transport layer - WRP events use SIMPLE_EVENT message type"
    )
```

### Subscription Management Stubs

```python
def subscribe(self, subscription_id: str, reference_list: List[str], 
              notification_type: str = "ValueChange",
              context: Optional[BridgeContext] = None) -> bool:
    """Subscribe to parameter/object notifications"""
    raise NotImplementedError(
        "subscribe() requires subscription manager and transport layer"
    )

def unsubscribe(self, subscription_id: str, context: Optional[BridgeContext] = None) -> bool:
    """Unsubscribe from notifications"""
    raise NotImplementedError(
        "unsubscribe() requires subscription manager and transport layer"
    )

def list_subscriptions(self, context: Optional[BridgeContext] = None) -> List[Dict[str, Any]]:
    """List active subscriptions"""
    raise NotImplementedError(
        "list_subscriptions() requires subscription manager and transport layer"
    )
```

## Testing

All 46 existing tests pass:
- ✅ 32 unit tests (test_usp2wrp_bridge.py)
- ✅ 14 integration tests (test_usp2wrp_integration.py)

No breaking changes to existing functionality.

## Next Steps

To fully implement event and subscription support, you'll need to:

1. **Transport Layer**
   - Implement nanomsg or Unix Domain Socket client
   - Connect to Parodus/XMiDT infrastructure
   - Handle WRP SIMPLE_EVENT message type

2. **Subscription Manager**
   - Persistent storage for subscription state
   - Integration with data model for change notifications
   - Event queue for outgoing notifications

3. **Data Model Integration**
   - Register callbacks for parameter value changes
   - Detect object creation/deletion
   - Track async operation completion

4. **Event Translation**
   - Map USP event names to WRP event format
   - Handle event parameters and metadata
   - Correlate events with subscriptions

## WRP Event Message Format

For reference, WRP events use the `SIMPLE_EVENT` message type (value `4`):

```python
event_msg = WrpMessage(
    msg_type=MessageType.SIMPLE_EVENT,
    source="mac:112233445566/usp",
    dest="event:device-status/mac:112233445566/usp",  # Event routing
    payload=json.dumps({
        "event_name": "ValueChange!",
        "obj_path": "Device.WiFi.Radio.1.",
        "params": {
            "ParamName": "Channel",
            "ParamValue": "11"
        }
    }).encode('utf-8'),
    content_type="application/json"
)
```

## Migration Guide

If you have existing code using the bridge interface, update return type annotations:

```python
# Before
response: Any = bridge.get(request)

# After
response: GetResponse = bridge.get(request)
```

The actual runtime behavior hasn't changed - only the type annotations are more specific now.
