# USP MTP and LocalAgent Architecture

## Overview

The USP (User Services Platform) specification defines a flexible architecture for configuring how agents communicate with controllers using Message Transfer Protocols (MTPs). This document describes how the data model handles MTP settings and LocalAgent settings.

## Data Model Structure

### 1. Device.LocalAgent

The top-level LocalAgent object contains agent-specific configuration:

```
Device.LocalAgent.EndpointID         # Agent's unique identifier
Device.LocalAgent.SoftwareVersion    # Software version
Device.LocalAgent.HardwareVersion    # Hardware version
Device.LocalAgent.AdvertisedDeviceSubtypes  # Device capabilities
```

### 2. Device.LocalAgent.MTP.{i}

This table defines **agent-initiated MTPs** - the MTPs that the agent uses to connect to controllers. Each instance represents one MTP endpoint that the agent will establish.

#### Common Parameters (All MTP Types)
```
Device.LocalAgent.MTP.{i}.Enable     # Enable/disable this MTP
Device.LocalAgent.MTP.{i}.Protocol   # STOMP, CoAP, WebSocket, UDS
Device.LocalAgent.MTP.{i}.Alias      # User-defined alias
```

#### Protocol-Specific Parameters

##### STOMP MTP
```
Device.LocalAgent.MTP.{i}.STOMP.Reference  # → Device.STOMP.Connection.{i}
Device.LocalAgent.MTP.{i}.STOMP.Destination
```

The STOMP MTP uses a **reference pattern** - it points to a separate `Device.STOMP.Connection.{i}` object that contains the actual broker connection details.

##### CoAP MTP
```
Device.LocalAgent.MTP.{i}.CoAP.Host         # CoAP server host
Device.LocalAgent.MTP.{i}.CoAP.Port         # CoAP server port
Device.LocalAgent.MTP.{i}.CoAP.Path         # CoAP resource path
Device.LocalAgent.MTP.{i}.CoAP.EnableEncryption
```

##### WebSocket MTP
```
Device.LocalAgent.MTP.{i}.WebSocket.Host    # WebSocket server host
Device.LocalAgent.MTP.{i}.WebSocket.Port    # WebSocket server port
Device.LocalAgent.MTP.{i}.WebSocket.Path    # WebSocket endpoint path
Device.LocalAgent.MTP.{i}.WebSocket.EnableEncryption
```

##### UDS (Unix Domain Socket) MTP
```
Device.LocalAgent.MTP.{i}.UDS.UnixSocketPath  # Path to Unix socket
```

### 3. Device.LocalAgent.Controller.{i}

This table defines the controllers that the agent communicates with:

```
Device.LocalAgent.Controller.{i}.Enable
Device.LocalAgent.Controller.{i}.EndpointID        # Controller's endpoint ID
Device.LocalAgent.Controller.{i}.Alias
Device.LocalAgent.Controller.{i}.ProvisioningCode
```

### 4. Device.LocalAgent.Controller.{i}.MTP.{i}

This is the **critical linking table** - it defines which MTPs each controller uses for communication:

```
Device.LocalAgent.Controller.{i}.MTP.{i}.Enable
Device.LocalAgent.Controller.{i}.MTP.{i}.Protocol   # STOMP, CoAP, WebSocket, UDS
Device.LocalAgent.Controller.{i}.MTP.{i}.Alias
```

Each controller can have **multiple MTPs** configured, allowing multi-transport redundancy.

#### Protocol-Specific Parameters

##### STOMP
```
Device.LocalAgent.Controller.{i}.MTP.{i}.STOMP.Reference     # → Device.STOMP.Connection.{i}
Device.LocalAgent.Controller.{i}.MTP.{i}.STOMP.Destination   # Controller's queue/topic
```

##### CoAP
```
Device.LocalAgent.Controller.{i}.MTP.{i}.CoAP.Host
Device.LocalAgent.Controller.{i}.MTP.{i}.CoAP.Port
Device.LocalAgent.Controller.{i}.MTP.{i}.CoAP.Path
Device.LocalAgent.Controller.{i}.MTP.{i}.CoAP.EnableEncryption
```

##### WebSocket
```
Device.LocalAgent.Controller.{i}.MTP.{i}.WebSocket.Host
Device.LocalAgent.Controller.{i}.MTP.{i}.WebSocket.Port
Device.LocalAgent.Controller.{i}.MTP.{i}.WebSocket.Path
Device.LocalAgent.Controller.{i}.MTP.{i}.WebSocket.EnableEncryption
```

##### UDS
```
Device.LocalAgent.Controller.{i}.MTP.{i}.UDS.UnixSocketPath
```

### 5. Device.STOMP.Connection.{i}

STOMP is unique - it separates the **broker connection configuration** from the MTP configuration:

```
Device.STOMP.Connection.{i}.Enable
Device.STOMP.Connection.{i}.Host            # STOMP broker host
Device.STOMP.Connection.{i}.Port            # STOMP broker port
Device.STOMP.Connection.{i}.Username        # Authentication
Device.STOMP.Connection.{i}.Password
Device.STOMP.Connection.{i}.VirtualHost
Device.STOMP.Connection.{i}.EnableEncryption
Device.STOMP.Connection.{i}.ServerRetryInitialInterval
Device.STOMP.Connection.{i}.ServerRetryIntervalMultiplier
Device.STOMP.Connection.{i}.ServerRetryMaxInterval
```

**Why separate?** Multiple STOMP MTPs can share the same broker connection by referencing the same `Device.STOMP.Connection.{i}` instance.

### 6. Device.LocalAgent.Subscription.{i}

Subscriptions define what events/parameters the controller wants to be notified about:

```
Device.LocalAgent.Subscription.{i}.Enable
Device.LocalAgent.Subscription.{i}.ID              # Subscription ID
Device.LocalAgent.Subscription.{i}.Recipient       # Controller endpoint ID
Device.LocalAgent.Subscription.{i}.NotifType       # ValueChange, Event, etc.
Device.LocalAgent.Subscription.{i}.ReferenceList   # Paths to monitor
```

## Architecture Patterns

### Pattern 1: Agent-Initiated Connection (Client Mode)

The modern USP agent acts as a **client** that connects to controller endpoints:

```
Agent (Device.LocalAgent.MTP.1)
  ↓ WebSocket Client Connection
  ↓ ws://controller.example.com:8080/usp
Controller WebSocket Server
```

**Configuration:**
```
Device.LocalAgent.MTP.1.Enable = true
Device.LocalAgent.MTP.1.Protocol = "WebSocket"
Device.LocalAgent.MTP.1.WebSocket.Host = "controller.example.com"
Device.LocalAgent.MTP.1.WebSocket.Port = 8080
Device.LocalAgent.MTP.1.WebSocket.Path = "/usp"
```

### Pattern 2: Multi-MTP Controller Communication

A single controller can be reached via multiple MTPs:

```
Agent
  ├─ STOMP MTP #1 → Controller via broker.example.com
  └─ WebSocket MTP #2 → Controller via ws://controller.example.com:8080
```

**Configuration:**
```
Device.LocalAgent.Controller.1.EndpointID = "os::controller-123"

Device.LocalAgent.Controller.1.MTP.1.Protocol = "STOMP"
Device.LocalAgent.Controller.1.MTP.1.STOMP.Reference = "Device.STOMP.Connection.1"
Device.LocalAgent.Controller.1.MTP.1.STOMP.Destination = "/queue/controller-123"

Device.LocalAgent.Controller.1.MTP.2.Protocol = "WebSocket"
Device.LocalAgent.Controller.1.MTP.2.WebSocket.Host = "controller.example.com"
Device.LocalAgent.Controller.1.MTP.2.WebSocket.Port = 8080
```

### Pattern 3: Multi-Controller Agent

An agent can communicate with multiple controllers simultaneously:

```
Agent
  ├─ Controller 1 (via STOMP)
  ├─ Controller 2 (via WebSocket)
  └─ Controller 3 (via CoAP)
```

**Configuration:**
```
Device.LocalAgent.Controller.1.EndpointID = "os::controller-primary"
Device.LocalAgent.Controller.1.MTP.1.Protocol = "STOMP"

Device.LocalAgent.Controller.2.EndpointID = "os::controller-backup"
Device.LocalAgent.Controller.2.MTP.1.Protocol = "WebSocket"

Device.LocalAgent.Controller.3.EndpointID = "os::controller-local"
Device.LocalAgent.Controller.3.MTP.1.Protocol = "UDS"
```

### Pattern 4: STOMP Reference Pattern

Multiple MTPs can share a STOMP broker connection:

```
STOMP.Connection.1 (broker.example.com:61613)
  ↑ referenced by
  ├─ LocalAgent.MTP.1.STOMP.Reference
  ├─ Controller.1.MTP.1.STOMP.Reference
  └─ Controller.2.MTP.1.STOMP.Reference
```

**Benefits:**
- Single TCP connection to broker
- Shared authentication
- Centralized broker configuration
- Multiple destinations over same connection

## Message Flow

### 1. Agent Startup

```
1. Agent reads Device.LocalAgent.Controller.{i} table
2. For each enabled controller:
   a. Read Device.LocalAgent.Controller.{i}.MTP.{i} table
   b. For each enabled MTP:
      i.  Create MTP connection based on protocol
      ii. Connect to controller endpoint
3. Once connected, send Boot! notification
```

### 2. Incoming Request Handling

```
1. Request arrives on MTP connection
2. MTP binding creates RequestContext:
   - from_id: sender endpoint ID
   - to_id: recipient endpoint ID  
   - writer: response writer for this MTP
   - mtp_type: protocol type
3. BaseAgent dispatches to appropriate handler
4. Handler generates response
5. Agent sends response via context.writer (same MTP)
```

### 3. Outgoing Notification

```
1. Agent needs to send notification to controller
2. Lookup controller by endpoint ID
3. Find first connected MTP for that controller
4. Send notification via that MTP
```

## Implementation Example

Based on our multi-MTP agent implementation:

```python
class MTPConnectionManager:
    """Manages a single MTP connection to a controller"""
    
    def __init__(self, controller_id, mtp_config):
        self.controller_id = controller_id
        self.protocol = mtp_config.get("Protocol")
        self.config = mtp_config
        
    async def connect(self):
        if self.protocol == "WebSocket":
            await self._connect_websocket()
        elif self.protocol == "STOMP":
            await self._connect_stomp()
        # etc.

class MultiMTPAgent:
    """Agent that supports multiple MTPs to multiple controllers"""
    
    def __init__(self):
        self.controller_mtps = {}  # controller_id → [MTPConnectionManager]
        
    async def _discover_and_connect_mtps(self):
        # Read Controller.{i} table
        controllers = self.db.find_instances("Device.LocalAgent.Controller.")
        
        for controller in controllers:
            controller_id = controller["EndpointID"]
            
            # Read Controller.{i}.MTP.{i} table for this controller
            mtps = self.db.find_instances(
                f"Device.LocalAgent.Controller.{instance}.MTP."
            )
            
            # Create connection manager for each MTP
            mtp_list = []
            for mtp_config in mtps:
                mgr = MTPConnectionManager(controller_id, mtp_config)
                await mgr.connect()
                mtp_list.append(mgr)
            
            self.controller_mtps[controller_id] = mtp_list
```

## Key Design Principles

### 1. Separation of Concerns

- **Agent MTPs** (`LocalAgent.MTP.{i}`): What MTPs the agent supports
- **Controller MTPs** (`Controller.{i}.MTP.{i}`): How to reach each controller
- **STOMP Connections** (`STOMP.Connection.{i}`): Broker connection details

### 2. Protocol Independence

Each MTP protocol has its own namespace under both:
- `LocalAgent.MTP.{i}.{Protocol}.*`
- `Controller.{i}.MTP.{i}.{Protocol}.*`

This allows protocol-specific parameters without naming conflicts.

### 3. Multi-Transport Redundancy

Controllers can be configured with multiple MTPs for:
- **Failover**: If one MTP fails, use another
- **Load balancing**: Distribute traffic across MTPs
- **Network flexibility**: Different transports for different networks

### 4. Reference Pattern for Shared Resources

STOMP uses references to avoid duplicating broker configuration. Other protocols (CoAP, WebSocket, UDS) use direct configuration since they typically don't share connections.

## Database Example

From our test database (`database/defaults/test-defaults.json`):

```json
{
  "Device.LocalAgent.EndpointID": "os::000000-test",
  
  "Device.LocalAgent.Controller.1.EndpointID": "os::controller-1",
  "Device.LocalAgent.Controller.1.MTP.1.Enable": true,
  "Device.LocalAgent.Controller.1.MTP.1.Protocol": "STOMP",
  "Device.LocalAgent.Controller.1.MTP.1.STOMP.Reference": "Device.STOMP.Connection.1",
  "Device.LocalAgent.Controller.1.MTP.1.STOMP.Destination": "/queue/controller-1",
  
  "Device.STOMP.Connection.1.Enable": true,
  "Device.STOMP.Connection.1.Host": "localhost",
  "Device.STOMP.Connection.1.Port": 61613,
  "Device.STOMP.Connection.1.Username": "test-agent",
  "Device.STOMP.Connection.1.VirtualHost": "/"
}
```

This configuration:
1. Defines the agent's endpoint ID
2. Defines controller #1 with endpoint ID "os::controller-1"
3. Configures controller #1 to use STOMP MTP #1
4. STOMP MTP #1 references STOMP Connection #1
5. STOMP Connection #1 contains the actual broker details

## Testing Multi-MTP Behavior

See `tests/e2e/test_multi_transport_same_controller.py` for validation of:

1. ✅ Agent connects to all enabled MTPs for a controller
2. ✅ Boot! notification sent on each MTP connection
3. ✅ Requests route correctly via RequestContext
4. ✅ Responses sent back via same MTP that received request
5. ✅ Notifications sent on first connected MTP only

## References

- **TR-369 (USP Specification)**: Message Transfer Protocol (MTP) specifications
- **TR-181 (Device:2 Data Model)**: USP Agent data model definitions
- **Implementation**: `agent/multi_mtp_agent.py` - Multi-MTP orchestration
- **Database Structure**: `database/defaults/test-defaults.json` - Example configuration
- **Data Model**: `database/test-dm.json` - Complete parameter definitions
