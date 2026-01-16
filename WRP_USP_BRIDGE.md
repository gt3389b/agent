# WRP-USP Bridge Architecture

## Overview

The **WRPAgent** is a protocol bridge that translates between:
- **USP (User Services Platform)** - TR-369 standard used by broadband controllers
- **WRP (Web Routing Protocol)** - msgpack-encoded message envelope used by Xfinity/RDK device services

```
┌─────────────────┐        ┌──────────────┐        ┌─────────────────┐
│  USP Controller │◄──────►│  WRPAgent    │◄──────►│ WRP Services    │
│  (North)        │  USP   │  (Bridge)    │  WRP   │ (South)         │
│                 │        │              │        │                 │
│ WebSocket/CoAP  │        │ USP ↔ WRP    │        │ Nanomsg/UDS     │
│ TR-369          │        │ Translation  │        │ JSON-RPC        │
└─────────────────┘        └──────────────┘        └─────────────────┘
```

**Key Functions:**
- Acts as USP agent to controllers (implements TR-369)
- Acts as WRP client to device services (implements Parodus protocol)
- Translates USP messages ↔ WRP JSON-RPC calls
- Maintains intrinsic USP functionality (Boot!, Periodic!, etc.)

**WRP Message Types (per xmidt.io spec):**
- `2` = AUTH (authorization status)
- `3` = SIMPLE_REQUEST_RESPONSE (request-response pattern)
- `4` = SIMPLE_EVENT (one-way event)
- `5` = CREATE (CRUD create)
- `6` = RETRIEVE (CRUD retrieve)
- `7` = UPDATE (CRUD update)
- `8` = DELETE (CRUD delete)
- `9` = SERVICE_REGISTRATION (on-device service registration)
- `10` = SERVICE_ALIVE (service keepalive)
- `11` = UNKNOWN (represents lost/missing message)

**Note:** Message types 0 and 1 are deprecated per WRP spec.

### WRP Message Structure

All WRP messages are msgpack-encoded maps with the following fields:

**Required Fields:**
- `msg_type` - Integer message type (see above)
- `source` - Source locator (e.g., `mac:112233445566/usp-agent`)
- `dest` - Destination locator (e.g., `mac:112233445566/tr181`)

**Common Optional Fields:**
- `transaction_uuid` - Unique transaction ID (should be UUID)
- `payload` - Binary message content
- `content_type` - MIME type of payload (e.g., `application/json`, `application/msgpack`)
- `accept` - Accepted response MIME type
- `status` - HTTP-style status code (responses only)
- `headers` - Array of `key=value` header strings
- `metadata` - Array of `key=value` metadata strings
- `partner_ids` - Array of partner ID strings for targeting
- `session_id` - Unique device connection session ID
- `qos` - Quality of service level (0-24: Low, 25-49: Medium, 50-74: High, 75-99: Critical)
- `rdr` - Request delivery response code
- `spans` - Timing/tracing data array
- `span_parent` - Root parent for span tracing
- `include_spans` - Boolean for including timing in response

**CRUD-specific Fields:**
- `path` - Path for CRUD operations (CREATE, RETRIEVE, UPDATE, DELETE)

**SERVICE_REGISTRATION Fields:**
- `service_name` - Name of the service registering
- `url` - Nanomsg URL for the service

**Locator Format:**
- Device: `mac:{mac_address}/{service}/{ignored}` or `serial:{serial}/{service}/{ignored}`
- Event: `event:{event_id}/{ignored}`
- Service: `dns:{hostname}/{service}/{ignored}`

---

## Message Flow Patterns

### Controller-to-Device (C2D): USP → WRP

```
1. USP Controller sends Get Request
2. WRPAgent receives USP GetRequest
3. WRPAgent translates to WRP JSON-RPC get
4. WRPAgent sends WRP message to tr181 service
5. tr181 service responds with WRP JSON-RPC result
6. WRPAgent translates to USP GetResponse
7. WRPAgent sends USP response to controller
```

### Device-to-Controller (D2C): WRP → USP

```
1. Device service sends WRP event
2. WRPAgent receives WRP event message
3. WRPAgent translates to USP Notification
4. WRPAgent sends USP Notify to controller(s)
```

---

## USP → WRP Translation Mappings

### Direct Mappings (Simple 1:1)

These operations map directly to TR-181 JSON-RPC methods:

#### 1. Get Request

**USP:**
```json
{
  "header": {
    "msg_id": "usp-12345",
    "msg_type": "GET"
  },
  "body": {
    "request": {
      "get": {
        "param_paths": [
          "Device.DeviceInfo.Manufacturer",
          "Device.DeviceInfo.ModelName"
        ]
      }
    }
  }
}
```

**WRP Request Message:**
```python
WrpMessage(
    msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,  # 3
    source="mac:112233445566/usp",
    dest="mac:112233445566/usp2wrp",
    transaction_id="usp-12345:001:ctrl-01",  # {usp_msg_id}:{sequence}:{controller_id}
    content_type="application/json",
    metadata={
        "usp_msg_id": "usp-12345",
        "usp_operation": "get",
        "controller_endpoint": "proto::controller-01",
        "mtp_id": "websocket-1"
    },
    payload=b'''{
      "jsonrpc": "2.0",
      "id": "usp-12345:001:ctrl-01",
      "method": "get",
      "params": {
        "names": [
          "Device.DeviceInfo.Manufacturer",
          "Device.DeviceInfo.ModelName"
        ]
      }
    }'''
)
```

**WRP Response Message:**
```python
WrpMessage(
    msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,  # 3
    source="mac:112233445566/usp2wrp",
    dest="mac:112233445566/usp",
    transaction_id="usp-12345:001:ctrl-01",  # Same as request
    content_type="application/json",
    status=200,
    metadata={
        "usp_msg_id": "usp-12345",
        "usp_operation": "get",
        "controller_endpoint": "proto::controller-01",
        "mtp_id": "websocket-1"
    },
    payload=b'''{
      "jsonrpc": "2.0",
      "id": "usp-12345:001:ctrl-01",
      "result": {
        "parameters": [
          {"name": "Device.DeviceInfo.Manufacturer", "value": "ExampleCorp"},
          {"name": "Device.DeviceInfo.ModelName", "value": "Model-X"}
        ]
      }
    }'''
)
```

#### 2. Set Request

**USP:**
```json
{
  "header": {
    "msg_id": "usp-23456",
    "msg_type": "SET"
  },
  "body": {
    "request": {
      "set": {
        "update_objs": [
          {
            "obj_path": "Device.WiFi.Radio.1.",
            "param_settings": [
              {"param": "Enable", "value": "true", "required": true}
            ]
          }
        ]
      }
    }
  }
}
```

**WRP Request Message:**
```python
WrpMessage(
    msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,  # 3
    source="mac:112233445566/usp",
    dest="mac:112233445566/usp2wrp",
    transaction_id="usp-23456:002:ctrl-01",
    content_type="application/json",
    metadata={
        "usp_msg_id": "usp-23456",
        "usp_operation": "set",
        "usp_path": "Device.WiFi.Radio.1.",
        "controller_endpoint": "proto::controller-01",
        "mtp_id": "websocket-1"
    },
    payload=b'''{
      "jsonrpc": "2.0",
      "id": "usp-23456:002:ctrl-01",
      "method": "set",
      "params": {
        "parameters": [
          {
            "name": "Device.WiFi.Radio.1.Enable",
            "value": "true",
            "dataType": 3
          }
        ]
      }
    }'''
)
```

**WRP Response Message:**
```python
WrpMessage(
    msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,  # 3
    source="mac:112233445566/usp2wrp",
    dest="mac:112233445566/usp",
    transaction_id="usp-23456:002:ctrl-01",
    content_type="application/json",
    status=200,
    metadata={
        "usp_msg_id": "usp-23456",
        "usp_operation": "set",
        "usp_path": "Device.WiFi.Radio.1.",
        "controller_endpoint": "proto::controller-01",
        "mtp_id": "websocket-1"
    },
    payload=b'''{
      "jsonrpc": "2.0",
      "id": "usp-23456:002:ctrl-01",
      "result": {
        "status": "success"
      }
    }'''
)
```

**DataType Mapping:**
- 0: Auto-detect
- 1: string
- 2: int
- 3: boolean
- 4: dateTime
- 5: base64

#### 3. Add Request

**USP:**
```json
{
  "header": {
    "msg_id": "usp-34567",
    "msg_type": "ADD"
  },
  "body": {
    "request": {
      "add": {
        "obj_path": "Device.WiFi.SSID.",
        "param_settings": [
          {"param": "SSID", "value": "MyNetwork"}
        ]
      }
    }
  }
}
```

**WRP Request Message:**
```python
WrpMessage(
    msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,  # 3
    source="mac:112233445566/usp",
    dest="mac:112233445566/usp2wrp",
    transaction_id="usp-34567:003:ctrl-01",
    content_type="application/json",
    metadata={
        "usp_msg_id": "usp-34567",
        "usp_operation": "add",
        "usp_path": "Device.WiFi.SSID.",
        "controller_endpoint": "proto::controller-01",
        "mtp_id": "websocket-1"
    },
    payload=b'''{
      "jsonrpc": "2.0",
      "id": "usp-34567:003:ctrl-01",
      "method": "addObject",
      "params": {
        "objectName": "Device.WiFi.SSID.",
        "parameters": [
          {"name": "SSID", "value": "MyNetwork", "dataType": 1}
        ]
      }
    }'''
)
```

**WRP Response Message:**
```python
WrpMessage(
    msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,  # 3
    source="mac:112233445566/usp2wrp",
    dest="mac:112233445566/usp",
    transaction_id="usp-34567:003:ctrl-01",
    content_type="application/json",
    status=200,
    metadata={
        "usp_msg_id": "usp-34567",
        "usp_operation": "add",
        "usp_path": "Device.WiFi.SSID.",
        "controller_endpoint": "proto::controller-01",
        "mtp_id": "websocket-1"
    },
    payload=b'''{
      "jsonrpc": "2.0",
      "id": "usp-34567:003:ctrl-01",
      "result": {
        "instanceNumber": 5,
        "objectPath": "Device.WiFi.SSID.5."
      }
    }'''
)
```

#### 4. Delete Request

**USP:**
```json
{
  "header": {
    "msg_id": "usp-45678",
    "msg_type": "DELETE"
  },
  "body": {
    "request": {
      "delete": {
        "obj_paths": ["Device.WiFi.SSID.3."]
      }
    }
  }
}
```

**WRP Request Message:**
```python
WrpMessage(
    msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,  # 3
    source="mac:112233445566/usp",
    dest="mac:112233445566/usp2wrp",
    transaction_id="usp-45678:004:ctrl-01",
    content_type="application/json",
    metadata={
        "usp_msg_id": "usp-45678",
        "usp_operation": "delete",
        "usp_path": "Device.WiFi.SSID.3.",
        "controller_endpoint": "proto::controller-01",
        "mtp_id": "websocket-1"
    },
    payload=b'''{
      "jsonrpc": "2.0",
      "id": "usp-45678:004:ctrl-01",
      "method": "deleteObject",
      "params": {
        "objectName": "Device.WiFi.SSID.3."
      }
    }'''
)
```

**WRP Response Message:**
```python
WrpMessage(
    msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,  # 3
    source="mac:112233445566/usp2wrp",
    dest="mac:112233445566/usp",
    transaction_id="usp-45678:004:ctrl-01",
    content_type="application/json",
    status=200,
    metadata={
        "usp_msg_id": "usp-45678",
        "usp_operation": "delete",
        "usp_path": "Device.WiFi.SSID.3.",
        "controller_endpoint": "proto::controller-01",
        "mtp_id": "websocket-1"
    },
    payload=b'''{
      "jsonrpc": "2.0",
      "id": "usp-45678:004:ctrl-01",
      "result": {
        "status": "success"
      }
    }'''
)
```

### Complex Mappings (Transformation Required)

#### 5. Operate Request → RPC Method Call

**USP:**
```json
{
  "header": {
    "msg_id": "usp-12345",
    "msg_type": "OPERATE"
  },
  "body": {
    "request": {
      "operate": {
        "command": "Device.Reboot()",
        "input_args": {
          "Delay": 10
        }
      }
    }
  }
}
```

**Transformation Strategy:**
1. Preserve full TR-181 path in WRP metadata
2. Encode context in transaction ID for response routing
3. Extract method name for JSON-RPC call

**WRP Request Message (Option 1: Preserve full path in method):**
```python
WrpMessage(
    msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,  # 3
    source="mac:112233445566/usp",
    dest="mac:112233445566/usp2wrp",
    transaction_id="usp-12345:005:ctrl-01",  # {usp_msg_id}:{sequence}:{controller_id}
    content_type="application/json",
    metadata={
        "usp_msg_id": "usp-12345",
        "usp_command": "Device.Reboot()",
        "usp_operation": "operate",
        "controller_endpoint": "proto::controller-01",
        "mtp_id": "websocket-1"
    },
    payload=b'''{
      "jsonrpc": "2.0",
      "id": "usp-12345:005:ctrl-01",
      "method": "Device.Reboot",
      "params": {
        "Delay": 10
      }
    }'''
)
```

**WRP Request Message (Option 2: Generic RPC wrapper):**
```python
WrpMessage(
    msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,  # 3
    source="mac:112233445566/usp",
    dest="mac:112233445566/usp2wrp",
    transaction_id="usp-12345:005:ctrl-01",
    content_type="application/json",
    metadata={
        "usp_msg_id": "usp-12345",
        "usp_command": "Device.Reboot()",
        "usp_operation": "operate",
        "controller_endpoint": "proto::controller-01",
        "mtp_id": "websocket-1"
    },
    payload=b'''{
      "jsonrpc": "2.0",
      "id": "usp-12345:005:ctrl-01",
      "method": "rpc",
      "params": {
        "command": "Device.Reboot()",
        "args": {"Delay": 10}
      }
    }'''
)
```

**WRP Response Message:**
```python
WrpMessage(
    msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,  # 3
    source="mac:112233445566/usp2wrp",
    dest="mac:112233445566/usp",
    transaction_id="usp-12345:005:ctrl-01",
    content_type="application/json",
    status=200,
    metadata={
        "usp_msg_id": "usp-12345",
        "usp_command": "Device.Reboot()",
        "usp_operation": "operate",
        "controller_endpoint": "proto::controller-01",
        "mtp_id": "websocket-1"
    },
    payload=b'''{
      "jsonrpc": "2.0",
      "id": "usp-12345:005:ctrl-01",
      "result": {
        "status": "rebooting"
      }
    }'''
)
```

**Benefits of this approach:**
- Full TR-181 path preserved in metadata
- Transaction ID contains USP msg_id for correlation
- Response routing info embedded (controller_endpoint, mtp_id)
- Can reconstruct USP response without additional lookups

#### 6. GetSupportedDM → getAttributes

**USP:**
```json
{
  "header": {
    "msg_id": "usp-67890",
    "msg_type": "GET_SUPPORTED_DM"
  },
  "body": {
    "request": {
      "get_supported_dm": {
        "obj_paths": ["Device.WiFi."],
        "return_params": true,
        "return_commands": true
      }
    }
  }
}
```

**WRP Request Message:**
```python
WrpMessage(
    msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,  # 3
    source="mac:112233445566/usp",
    dest="mac:112233445566/usp2wrp",
    transaction_id="usp-67890:006:ctrl-01",  # {usp_msg_id}:{sequence}:{controller_id}
    content_type="application/json",
    metadata={
        "usp_msg_id": "usp-67890",
        "usp_operation": "get_supported_dm",
        "usp_path": "Device.WiFi.",
        "return_params": "true",
        "return_commands": "true",
        "controller_endpoint": "proto::controller-01",
        "mtp_id": "websocket-1"
    },
    payload=b'''{
      "jsonrpc": "2.0",
      "id": "usp-67890:006:ctrl-01",
      "method": "getAttributes",
      "params": {
        "names": ["Device.WiFi."],
        "recursive": true,
        "includeParameters": true,
        "includeCommands": true
      }
    }'''
)
```

**WRP Response Message:**
```python
WrpMessage(
    msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,  # 3
    source="mac:112233445566/usp2wrp",
    dest="mac:112233445566/usp",
    transaction_id="usp-67890:006:ctrl-01",
    content_type="application/json",
    status=200,
    metadata={
        "usp_msg_id": "usp-67890",
        "usp_operation": "get_supported_dm",
        "usp_path": "Device.WiFi.",
        "controller_endpoint": "proto::controller-01",
        "mtp_id": "websocket-1"
    },
    payload=b'''{
      "jsonrpc": "2.0",
      "id": "usp-67890:006:ctrl-01",
      "result": {
        "objects": [
          {
            "name": "Device.WiFi.",
            "parameters": ["RadioNumberOfEntries", "SSIDNumberOfEntries"],
            "commands": ["Reset()"]
          }
        ]
      }
    }'''
)
```

**Alternative (getParameterNames method):**
```python
WrpMessage(
    msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,  # 3
    source="mac:112233445566/usp",
    dest="mac:112233445566/usp2wrp",
    transaction_id="usp-67890:006:ctrl-01",
    content_type="application/json",
    metadata={
        "usp_msg_id": "usp-67890",
        "usp_operation": "get_supported_dm",
        "usp_path": "Device.WiFi.",
        "controller_endpoint": "proto::controller-01",
        "mtp_id": "websocket-1"
    },
    payload=b'''{
      "jsonrpc": "2.0",
      "id": "usp-67890:006:ctrl-01",
      "method": "getParameterNames",
      "params": {
        "path": "Device.WiFi.",
        "nextLevel": false
      }
    }'''
)
```

#### 7. GetInstances → get with wildcards

**USP:**
```json
{
  "header": {
    "msg_id": "usp-11111",
    "msg_type": "GET_INSTANCES"
  },
  "body": {
    "request": {
      "get_instances": {
        "obj_paths": ["Device.WiFi.SSID."]
      }
    }
  }
}
```

**WRP Request Message (Option 1: get with wildcard):**
```python
WrpMessage(
    msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,  # 3
    source="mac:112233445566/usp",
    dest="mac:112233445566/usp2wrp",
    transaction_id="usp-11111:007:ctrl-01",  # {usp_msg_id}:{sequence}:{controller_id}
    content_type="application/json",
    metadata={
        "usp_msg_id": "usp-11111",
        "usp_operation": "get_instances",
        "usp_path": "Device.WiFi.SSID.",
        "controller_endpoint": "proto::controller-01",
        "mtp_id": "websocket-1"
    },
    payload=b'''{
      "jsonrpc": "2.0",
      "id": "usp-11111:007:ctrl-01",
      "method": "get",
      "params": {
        "names": ["Device.WiFi.SSID.*.SSID"]
      }
    }'''
)
```

**WRP Request Message (Option 2: dedicated method):**
```python
WrpMessage(
    msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,  # 3
    source="mac:112233445566/usp",
    dest="mac:112233445566/usp2wrp",
    transaction_id="usp-11111:007:ctrl-01",
    content_type="application/json",
    metadata={
        "usp_msg_id": "usp-11111",
        "usp_operation": "get_instances",
        "usp_path": "Device.WiFi.SSID.",
        "controller_endpoint": "proto::controller-01",
        "mtp_id": "websocket-1"
    },
    payload=b'''{
      "jsonrpc": "2.0",
      "id": "usp-11111:007:ctrl-01",
      "method": "getInstances",
      "params": {
        "objectPath": "Device.WiFi.SSID."
      }
    }'''
)
```

**WRP Response Message:**
```python
WrpMessage(
    msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,  # 3
    source="mac:112233445566/usp2wrp",
    dest="mac:112233445566/usp",
    transaction_id="usp-11111:007:ctrl-01",
    content_type="application/json",
    status=200,
    metadata={
        "usp_msg_id": "usp-11111",
        "usp_operation": "get_instances",
        "usp_path": "Device.WiFi.SSID.",
        "controller_endpoint": "proto::controller-01",
        "mtp_id": "websocket-1"
    },
    payload=b'''{
      "jsonrpc": "2.0",
      "id": "usp-11111:007:ctrl-01",
      "result": {
        "instances": [
          "Device.WiFi.SSID.1.",
          "Device.WiFi.SSID.2.",
          "Device.WiFi.SSID.5."
        ]
      }
    }'''
)
```

---

## WRP → USP Translation Mappings

### Event Types

WRP events are published by device services and need translation to USP notifications.

#### 1. Boot Event → Boot! Notification

**WRP Event:**
```python
WrpMessage(
    msg_type=MessageType.SIMPLE_EVENT,
    source="mac:112233445566/tr181",
    dest="event:device-status/mac:112233445566",
    content_type="application/json",
    payload=b'''{
        "event": "device.boot",
        "cause": "LocalReboot",
        "firmware_updated": false
    }'''
)
```

**USP Boot! Notification:**
```json
{
  "header": {
    "msg_id": "notify-boot-001",
    "msg_type": "NOTIFY"
  },
  "body": {
    "request": {
      "notify": {
        "subscription_id": "boot-subscription",
        "event": {
          "obj_path": "Device.LocalAgent.",
          "event_name": "Boot!",
          "params": {
            "Cause": "LocalReboot",
            "CommandKey": "",
            "FirmwareUpdated": "false"
          }
        }
      }
    }
  }
}
```

#### 2. Parameter Change Event → ValueChange! Notification

**WRP Event:**
```json
{
  "event": "parameter.change",
  "parameters": [
    {
      "name": "Device.WiFi.Radio.1.Enable",
      "value": "true",
      "oldValue": "false"
    }
  ]
}
```

**USP ValueChange! Notification:**
```json
{
  "body": {
    "request": {
      "notify": {
        "subscription_id": "value-change-sub-1",
        "value_change": {
          "param_path": "Device.WiFi.Radio.1.Enable",
          "param_value": "true"
        }
      }
    }
  }
}
```

#### 3. Periodic Stats → Periodic! Notification

**WRP Event:**
```json
{
  "event": "periodic.stats",
  "interval": 300
}
```

**USP Periodic! Notification:**
```json
{
  "body": {
    "request": {
      "notify": {
        "subscription_id": "periodic-sub-1",
        "event": {
          "obj_path": "Device.LocalAgent.",
          "event_name": "Periodic!",
          "params": {}
        }
      }
    }
  }
}
```

#### 4. Custom Events → USP Custom Events

**WRP Event:**
```json
{
  "event": "wifi.client.connected",
  "mac": "AA:BB:CC:DD:EE:FF",
  "ssid": "MyNetwork",
  "signal": -45
}
```

**USP Event Notification:**
```json
{
  "body": {
    "request": {
      "notify": {
        "subscription_id": "wifi-events",
        "event": {
          "obj_path": "Device.WiFi.AccessPoint.1.",
          "event_name": "ClientConnected!",
          "params": {
            "MACAddress": "AA:BB:CC:DD:EE:FF",
            "SSID": "MyNetwork",
            "SignalStrength": "-45"
          }
        }
      }
    }
  }
}
```

---

## Intrinsic USP Operations

These operations are handled natively by WRPAgent **without** WRP translation:

### 1. Boot! Notification

**Behavior:**
- Sent automatically when WRPAgent starts
- Sent when connection to controller is established
- Uses standard USP Boot! format
- Does NOT forward to WRP services

**Implementation:**
```python
async def on_connect(self):
    """Override from BaseAgent - send Boot! on connection"""
    await self.send_boot_notification()
```

### 2. Periodic! Notification

**Behavior:**
- Timer-based in WRPAgent
- Configured via `Device.LocalAgent.Subscription.{i}` with `NotifType = Periodic`
- Can optionally query WRP services for periodic stats
- Primary notification is USP-native

**Implementation:**
```python
async def _periodic_notification_task(self):
    """Send periodic notifications based on subscriptions"""
    while True:
        await asyncio.sleep(self.periodic_interval)
        
        # Optional: fetch stats from WRP services
        if self.include_wrp_stats:
            stats = await self._fetch_wrp_stats()
        
        await self.send_periodic_notification()
```

### 3. ValueChange! Notification

**Two modes:**

**Mode 1: USP-Native (database-driven)**
- WRPAgent tracks parameter changes in its own database
- Sends ValueChange! when database is modified via USP Set

**Mode 2: WRP-Event-Driven**
- WRP service sends `parameter.change` event
- WRPAgent translates to ValueChange! notification
- Forwarded to subscribed controllers

### 4. Subscription Management

**Behavior:**
- Subscriptions stored in `Device.LocalAgent.Subscription.{i}`
- Managed entirely within WRPAgent
- Does NOT involve WRP services

---

## Transaction Correlation

### Request-Response Correlation

**Challenge:** Map USP msg_id ↔ WRP transaction_uuid and preserve context for response routing

**Strategy 1: Structured Transaction IDs (Recommended)**

Encode USP context directly in the WRP transaction ID:

```
Format: {usp_msg_id}:{wrp_sequence}:{controller_id}
Example: "usp-12345:001:ctrl-01"
```

**Benefits:**
- No lookup table needed
- Context embedded in response
- Stateless response handling
- Easy debugging

**Implementation:**
```python
class TransactionIDBuilder:
    """Build structured transaction IDs"""
    
    def __init__(self):
        self._sequence = 0
    
    def build(self, usp_msg_id: str, controller_id: str) -> str:
        """Build composite transaction ID"""
        self._sequence = (self._sequence + 1) % 1000
        return f"{usp_msg_id}:{self._sequence:03d}:{controller_id}"
    
    @staticmethod
    def parse(transaction_id: str) -> dict:
        """Parse composite transaction ID"""
        parts = transaction_id.split(':')
        if len(parts) >= 3:
            return {
                'usp_msg_id': parts[0],
                'sequence': int(parts[1]),
                'controller_id': parts[2]
            }
        return {'usp_msg_id': transaction_id}
```

**Strategy 2: Metadata-Based Context (Recommended for complex scenarios)**

Store context in WRP metadata field:

```python
@dataclass
class RequestContext:
    """Context for USP request"""
    usp_msg_id: str
    controller_endpoint: str
    mtp_id: str
    operation_type: str  # 'get', 'set', 'operate', etc.
    object_path: str     # Original TR-181 path
    timestamp: float
    
    def to_metadata(self) -> Dict[str, str]:
        """Convert to WRP metadata format"""
        return {
            'usp_msg_id': self.usp_msg_id,
            'controller_endpoint': self.controller_endpoint,
            'mtp_id': self.mtp_id,
            'usp_operation': self.operation_type,
            'usp_path': self.object_path,
            'timestamp': str(int(self.timestamp))
        }
    
    @classmethod
    def from_metadata(cls, metadata: Dict[str, str]) -> 'RequestContext':
        """Parse from WRP metadata"""
        return cls(
            usp_msg_id=metadata.get('usp_msg_id', ''),
            controller_endpoint=metadata.get('controller_endpoint', ''),
            mtp_id=metadata.get('mtp_id', ''),
            operation_type=metadata.get('usp_operation', 'unknown'),
            object_path=metadata.get('usp_path', ''),
            timestamp=float(metadata.get('timestamp', '0'))
        )

def create_wrp_request(usp_request, context: RequestContext) -> WrpMessage:
    """Create WRP request with embedded context"""
    return WrpMessage(
        msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,
        source=get_wrp_source(),
        dest=get_wrp_service_dest('tr181'),
        transaction_id=f"{context.usp_msg_id}:{uuid.uuid4().hex[:8]}",
        content_type='application/json',
        metadata=context.to_metadata(),
        payload=build_json_rpc_payload(usp_request)
    )

def handle_wrp_response(wrp_response: WrpMessage) -> USPMessage:
    """Handle WRP response using embedded context"""
    # Extract context from metadata
    context = RequestContext.from_metadata(wrp_response.metadata)
    
    # Parse transaction ID if needed
    txn_parts = TransactionIDBuilder.parse(wrp_response.transaction_id)
    
    # Build USP response with proper msg_id
    usp_response = build_usp_response(
        msg_id=context.usp_msg_id,
        operation=context.operation_type,
        wrp_payload=wrp_response.payload,
        original_path=context.object_path
    )
    
    # Route to correct controller
    await self.send_to_controller(
        controller_endpoint=context.controller_endpoint,
        mtp_id=context.mtp_id,
        message=usp_response
    )
    
    return usp_response
```

**Strategy 3: Hybrid Approach (Recommended)**

Combine both strategies for robustness:

```python
class TransactionManager:
    """Manage USP-WRP transaction correlation"""
    
    def __init__(self):
        self._id_builder = TransactionIDBuilder()
        self._pending = {}  # Fallback map: wrp_txn_id -> context
    
    def create_wrp_request(self, usp_msg_id: str, controller_id: str,
                          context: RequestContext) -> str:
        """Create WRP transaction ID with embedded context"""
        wrp_txn_id = self._id_builder.build(usp_msg_id, controller_id)
        
        # Store in fallback map with timeout
        self._pending[wrp_txn_id] = (context, time.time() + 30)
        
        return wrp_txn_id
    
    def resolve_response(self, wrp_txn_id: str, 
                        metadata: Dict[str, str]) -> Optional[RequestContext]:
        """Resolve context from transaction ID or metadata"""
        # Try metadata first (most reliable)
        if metadata and 'usp_msg_id' in metadata:
            return RequestContext.from_metadata(metadata)
        
        # Try structured ID parsing
        txn_info = TransactionIDBuilder.parse(wrp_txn_id)
        if 'controller_id' in txn_info:
            # Look up in pending map for full context
            if wrp_txn_id in self._pending:
                context, _ = self._pending.pop(wrp_txn_id)
                return context
        
        # Fallback: just the USP msg_id
        return RequestContext(
            usp_msg_id=txn_info['usp_msg_id'],
            controller_endpoint='unknown',
            mtp_id='unknown',
            operation_type='unknown',
            object_path='',
            timestamp=time.time()
        )
    
    def cleanup_expired(self):
        """Remove expired transactions"""
        now = time.time()
        expired = [tid for tid, (_, timeout) in self._pending.items() 
                  if timeout < now]
        for tid in expired:
            del self._pending[tid]
```

---

## WRP Endpoint Addressing

### Endpoint Format

WRP uses hierarchical endpoint addressing:

```
mac:AABBCCDDEEFF/service/component
```

**Examples:**
- `mac:112233445566/usp` - This WRPAgent (source)
- `mac:112233445566/usp2wrp` - USP-WRP bridge service (destination)
- `mac:112233445566/tr181` - TR-181 parameter service
- `mac:112233445566/parodus` - Parodus proxy
- `event:device-status/mac:112233445566` - Event destination

### Endpoint Mapping

**From USP Endpoint ID to WRP Source:**

```python
def usp_to_wrp_source(endpoint_id: str) -> str:
    """
    Convert USP endpoint ID to WRP source
    
    ops::112233445566-wrp-bridge → mac:112233445566/usp
    """
    # Extract device identifier
    parts = endpoint_id.split('::')[1].split('-')
    mac = parts[0]
    
    return f"mac:{mac}/usp"
```

**WRP Service Destinations:**

| Service | Destination | Purpose |
|---------|-------------|---------|
| USP-WRP Bridge | `mac:{MAC}/usp2wrp` | Primary translation service |
| TR-181 (legacy) | `mac:{MAC}/tr181` | Direct TR-181 access |
---

## Error Handling

### USP Error Codes → WRP Status Codes

| USP Error | WRP Status | Mapping |
|-----------|------------|---------|
| 0 (No Error) | 200 | Success |
| 7000-7799 (Invalid arguments) | 400 | Bad Request |
| 7800-7999 (Permission denied) | 403 | Forbidden |
| 7001 (Resources exceeded) | 507 | Insufficient Storage |
| 7xxx (Other errors) | 500 | Internal Error |

### WRP Status Codes → USP Error Codes

| WRP Status | USP Error | Error Message |
|------------|-----------|---------------|
| 200 | 0 | Success |
| 400 | 7004 | Invalid arguments |
| 403 | 7006 | Permission denied |
| 404 | 7026 | Invalid path |
| 500 | 7000 | Internal error |
| 503 | 7024 | Resources exceeded |

### Timeout Handling

```python
async def _send_wrp_request(self, wrp_msg: WrpMessage, timeout: float = 30.0):
    """Send WRP request and wait for response"""
    try:
        response = await asyncio.wait_for(
            self._wrp_transport.send_and_receive(wrp_msg),
            timeout=timeout
        )
        return response
    except asyncio.TimeoutError:
        logger.error(f"WRP request timeout: {wrp_msg.transaction_id}")
        raise USPError(7024, "Request timeout")
```

---

## Implementation Architecture

### Class Structure

```python
class WRPAgent(MultiMTPAgent):
    """
    USP-WRP Bridge Agent
    
    Inherits:
        MultiMTPAgent - USP multi-MTP functionality
    
    Adds:
        - WRP transport layer
        - USP ↔ WRP translation
        - Event subscription
    """
    
    def __init__(self, endpoint_id, dm_file, db_file, wrp_config):
        super().__init__(endpoint_id, dm_file, db_file)
        
        # WRP transport configuration
        self._wrp_endpoint = wrp_config['endpoint']
        self._wrp_transport = None
        self._wrp_services = wrp_config['services']
        
        # Transaction management
        self._txn_map = TransactionMap()
        
        # Event subscriptions
        self._wrp_event_subscriptions = {}
```

### Configuration File

```json
{
  "agent": {
    "endpoint_id": "ops::112233445566-wrp-bridge",
    "data_model": "database/test-dm.json",
    "database": "database/runtime/wrp-db.json"
  },
  
  "usp": {
    "controllers": [
      {
        "endpoint_id": "proto::controller-01",
        "mtp": {
          "protocol": "WebSocket",
          "host": "controller.example.com",
          "port": 8080,
          "path": "/usp"
        }
      }
    ]
  },
  
  "wrp": {
    "transport": "nanomsg",
    "endpoint": "tcp://127.0.0.1:6666",
    "services": {
      "usp2wrp": "mac:112233445566/usp2wrp",
      "tr181": "mac:112233445566/tr181",
      "rpc": "mac:112233445566/rpc",
      "parodus": "mac:112233445566/parodus"
    },
    "events": {
      "subscribe": [
        "device.boot",
        "parameter.change",
        "periodic.stats"
      ]
    }
  },
  
  "intrinsic": {
    "boot_notification": true,
    "periodic_interval": 300,
    "value_change_tracking": true
  }
}
```

---

## Testing Strategy

### Unit Tests

1. **Translation Tests** - Verify USP ↔ WRP conversions
2. **Endpoint Mapping Tests** - Verify address conversions
3. **Error Mapping Tests** - Verify error code translations

### Integration Tests

1. **Mock WRP Service** - Test with simulated WRP backend
2. **Mock USP Controller** - Test with simulated controller
3. **Round-trip Tests** - USP → WRP → USP verification

### E2E Tests

1. **With Parodus** - Real WRP service integration
2. **With USP Controller** - Real controller integration
3. **Multi-service** - Multiple WRP services simultaneously

---

## Next Steps

### Phase 1: Core Implementation
- [ ] Implement WRPAgent class skeleton
- [ ] Create WRP transport layer (nanomsg wrapper)
- [ ] Implement basic USP → WRP translation (Get/Set)
- [ ] Implement basic WRP → USP translation (events)

### Phase 2: Complex Operations
- [ ] Implement Operate → RPC translation
- [ ] Implement GetSupportedDM → getAttributes
- [ ] Implement GetInstances translation
- [ ] Add transaction correlation

### Phase 3: Testing
- [ ] Create mock WRP service
- [ ] Write unit tests for translations
- [ ] Write integration tests
- [ ] Test with real Parodus

### Phase 4: Production Readiness
- [ ] Error handling and recovery
- [ ] Logging and debugging
- [ ] Performance optimization
- [ ] Documentation
