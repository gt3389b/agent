# Bridge Architecture - Single Bridge with Endpoint-Based Routing

## Summary

Successfully refactored the BridgeAgent to use a **single bridge with endpoint-based routing** - the endpoint ID determines whether requests are for internal consumption (agent's own endpoint) or external (controller's endpoint).

## What Changed

### Before (Dual Bridge Approach - Briefly Considered)
```python
class BridgeAgent:
    def __init__(self, endpoint_id, bridge, local_bridge):
        self.bridge = bridge         # For remote paths
        self.local_bridge = local_bridge  # For local paths
```

### After (Single Bridge with Endpoint Routing)
```python
class BridgeAgent:
    def __init__(self, endpoint_id, bridge):
        self.endpoint_id = endpoint_id
        self.bridge = bridge  # Single bridge for all requests
    
    async def _bridge_request(self, request, ctx, internal=False):
        # Use agent's own endpoint for internal requests (local DB)
        # Use controller's endpoint for external requests
        target_endpoint = self.endpoint_id if internal else ctx.endpoint
        
        bridge_context = BridgeContext(
            usp_msg_id=request.msg_id,
            controller_endpoint=target_endpoint,  # <-- Key difference!
            ...
        )
        
        self.bridge.send(request, bridge_context)
```

## Architecture Benefits

### 1. **Endpoint-Based Routing**

The WRP metadata's `controller_endpoint` field distinguishes request types:

**External Request** (from controller to backend):
```
controller_endpoint: "proto::controller-1"
→ MockWrpService processes and returns to controller
```

**Internal Request** (agent querying its own data):
```
controller_endpoint: "proto::test-agent"  # Agent's own ID!
→ MockWrpService processes and returns to agent
→ Agent knows it's for internal consumption
```

### 2. **Single Bridge, Full Data Model**

```
┌──────────────────────────────────────────────────────────┐
│                     BridgeAgent                          │
│  endpoint_id = "proto::test-agent"                       │
│                                                          │
│  External: Uses controller endpoint (proto::controller)  │
│  Internal: Uses agent's own endpoint (proto::test-agent) │
└────────────────────┬─────────────────────────────────────┘
                     │
                     │ Single WrpBridge
                     │
                     ▼
              ┌──────────────┐
              │ WrpBridge    │
              │ (TX/RX)      │
              └──────┬───────┘
                     │
                     ▼
              ┌──────────────┐
              │MockWrpService│
              │ Full DM      │
              │  ├─Database  │
              │  │  193 params
              │  └─JSON-RPC  │
              └──────────────┘
```

### 3. **WRP Message Flow**

**External Request Example:**
```json
{
  "metadata": {
    "usp_msg_id": "get-1",
    "usp_operation": "get",
    "controller_endpoint": "proto::controller-1",  ← Controller ID
    "mtp_id": "websocket"
  },
  "payload": {
    "method": "get",
    "params": {"names": ["Device.WiFi.Radio.1.Channel"]}
  }
}
```

**Internal Request Example:**
```json
{
  "metadata": {
    "usp_msg_id": "get-2",
    "usp_operation": "get",
    "controller_endpoint": "proto::test-agent",  ← Agent's own ID!
    "mtp_id": "websocket"
  },
  "payload": {
    "method": "get",
    "params": {"names": ["Device.LocalAgent.SoftwareVersion"]}
  }
}
```

The agent detects responses meant for itself by checking if `controller_endpoint == self.endpoint_id`.

## Code Examples

### BridgeAgent.__init__
```python
def __init__(self, endpoint_id: str, bridge: UspBridge):
    """
    Initialize bridge agent
    
    Args:
        endpoint_id: Agent endpoint ID (e.g., "proto::agent-1")
        bridge: UspBridge for WRP/backend communication
               Uses endpoint ID to distinguish internal vs external:
               - Internal (local DB): Uses agent's own endpoint_id
               - External (controller): Uses controller's endpoint
    """
    self.endpoint_id = endpoint_id
    self.bridge = bridge
```

### BridgeAgent.handle_get
```python
async def handle_get(self, request: GetRequest, ctx: Any) -> GetResponse:
    local_paths, remote_paths = self._split_paths(request.paths)
    
    results = []
    
    # Handle local paths via bridge (using agent's own endpoint)
    if local_paths:
        local_req = GetRequest(paths=local_paths, msg_id=request.msg_id)
        local_response = await self._bridge_request(
            local_req, ctx, internal=True  # <-- Uses agent's endpoint!
        )
        results.extend(local_response.results)
    
    # Handle remote paths via bridge (using controller's endpoint)
    if remote_paths:
        backend_req = GetRequest(paths=remote_paths, msg_id=request.msg_id)
        backend_response = await self._bridge_request(
            backend_req, ctx  # <-- Uses controller's endpoint
        )
        results.extend(backend_response.results)
    
    return GetResponse(msg_id=request.msg_id, results=results)
```

### BridgeAgent._bridge_request
```python
async def _bridge_request(self, request: Any, ctx: Any,
                        internal: bool = False) -> Any:
    # Use agent's own endpoint for internal requests (local DB)
    # Use controller's endpoint for external requests
    target_endpoint = self.endpoint_id if internal else ctx.endpoint
    
    bridge_context = BridgeContext(
        usp_msg_id=request.msg_id,
        controller_endpoint=target_endpoint,  # <-- Key!
        mtp_id=ctx.mtp_id,
        mac_address=self._get_mac_address(),
        controller_id=ctx.controller_id
    )
    
    # Single bridge handles all requests
    self.bridge.send(request, bridge_context)
    
    response = await asyncio.wait_for(future, timeout=30.0)
    return response
```

## Test Results

```bash
$ python tests/test_dual_bridge.py

================================================================================
Testing Single Bridge Architecture (Endpoint-Based Routing)
================================================================================

✅ Created MockWrpService with full data model
   DB has 193 parameters

✅ Created single WrpBridge

✅ Created BridgeAgent with single bridge
   Internal requests use agent's own endpoint
   External requests use controller's endpoint

Test 1: Get remote parameter (should route to remote bridge)
--------------------------------------------------------------------------------
✅ Response: [{'name': 'Device.DeviceInfo.Manufacturer', 'value': 'ARRIS'}]

Test 2: Get local parameter (should route to local bridge)  
--------------------------------------------------------------------------------
✅ Response: [{'name': 'Device.LocalAgent.SoftwareVersion', 'value': '0.0.1-alpha'}]

Statistics:
--------------------------------------------------------------------------------
Service: 2 requests
         (1 internal for LocalAgent, 1 external for DeviceInfo)

✅ SUCCESS: Single bridge with endpoint-based routing!
   Internal: Uses agent's own endpoint (proto::test-agent)
   External: Uses controller's endpoint (proto::controller)
   MockWrpService fronts real Database architecture
```

## Interactive Demo

```bash
$ python -m tests.test_bridge_agent_interactive

bridge-agent> get Device.DeviceInfo.Manufacturer

📤 OUTBOUND WRP MESSAGE
  Metadata:
    controller_endpoint: proto::controller-1  ← Controller ID

✅ Response: ARRIS

bridge-agent> local Device.LocalAgent.SoftwareVersion

📤 OUTBOUND WRP MESSAGE  
  Metadata:
    controller_endpoint: proto::test-agent  ← Agent's own ID!

✅ Response: 0.0.1-alpha

bridge-agent> stats
📊 Message Statistics:
   WRP sent:     2 messages
   WRP received: 2 messages
   Service:
   Requests:  2
   Responses: 2
   DB Size:   193 parameters
```

## Benefits Realized

1. **Simpler Architecture**: One bridge instead of two
2. **Endpoint-Based Routing**: Controller endpoint distinguishes internal vs external
3. **Full Data Model**: Single MockWrpService serves all paths
4. **Clean Semantics**: Agent's own ID = internal consumption
5. **No Direct DB Access**: Everything through bridge + WRP
6. **Testability**: Easy to verify routing by inspecting metadata

## Key Insight

The `controller_endpoint` field in WRP metadata serves dual purposes:
- **Routing**: Tells backend where to send responses
- **Context**: Tells agent whether response is for internal use (matches own endpoint) or external forwarding (matches controller endpoint)

This elegant pattern eliminates the need for separate bridges while maintaining clean separation of concerns!

## Summary

Successfully refactored the BridgeAgent to use a **pure bridge architecture** where ALL data access goes through bridges - no direct Database dependencies in the agent.

## What Changed

### Before
```python
class BridgeAgent:
    def __init__(self, endpoint_id, bridge, local_dm_file, local_db_file):
        self._db = Database(local_dm_file, local_db_file, "")  # Direct DB!
        self.bridge = bridge  # Only for remote paths
    
    async def handle_get(self, request, ctx):
        if is_local_path(path):
            value = self._db.get(path)  # Direct access
        else:
            value = await self._bridge_request(...)  # Bridged
```

### After
```python
class BridgeAgent:
    def __init__(self, endpoint_id, bridge, local_bridge=None):
        # NO Database instance!
        self.bridge = bridge         # For remote paths
        self.local_bridge = local_bridge  # For local paths
    
    async def handle_get(self, request, ctx):
        if is_local_path(path):
            response = await self._bridge_request(..., use_local=True)  # Bridge!
        else:
            response = await self._bridge_request(...)  # Bridge!
```

## Architecture Benefits

### 1. **Separation of Concerns**
- Agent focuses on USP protocol logic, routing, and event generation
- Database concerns handled by backend services (MockWrpService)
- Clean interface boundary via bridges

### 2. **Dual Bridge Pattern**

```
┌──────────────────────────────────────────────────────────────┐
│                       BridgeAgent                            │
│  - Owns Boot!/Periodic! events                              │
│  - Routes based on path prefix                               │
│  - NO direct Database access                                 │
└──────┬──────────────────────────────────────────┬────────────┘
       │                                          │
       │ remote_bridge                            │ local_bridge
       │ (Device.WiFi.*, etc)                     │ (Device.LocalAgent.*)
       ▼                                          ▼
┌──────────────┐                          ┌──────────────┐
│ WrpBridge    │                          │ WrpBridge    │
│ (TX/RX)      │                          │ (TX/RX)      │
└──────┬───────┘                          └──────┬───────┘
       │                                          │
       ▼                                          ▼
┌──────────────┐                          ┌──────────────┐
│ MockWrpService│                         │ MockWrpService│
│ (Remote)     │                          │ (Local)      │
│  ├─Database  │                          │  ├─Database  │
│  ├─DM/DB     │                          │  ├─DM/DB     │
│  └─JSON-RPC  │                          │  └─JSON-RPC  │
└──────────────┘                          └──────────────┘
```

### 3. **MockWrpService Fronts Real Database**

```python
class MockWrpService:
    def __init__(self, dm_file, db_file, response_callback=None):
        # Uses REAL Database architecture from agent_db.py
        self.db = Database(dm_file, db_file, "")
    
    def _handle_get(self, wrp_request):
        # Extract JSON-RPC request
        path = request["params"]["path"]
        
        # Use real Database!
        value = self.db.get(path)
        
        # Return JSON-RPC response via WRP
        return self._build_response(...)
```

This isn't mock data - it's the **actual Database** class used in production!

### 4. **Two-Channel Flow**

**TX Channel (Outbound)**:
```
Request → bridge.send() → to_bytes() → WRP msgpack → transport → MockWrpService
```

**RX Channel (Inbound)**:
```
MockWrpService → response_callback → WRP msgpack → from_bytes() → fulfill Future
```

Operation type preserved in WRP metadata throughout the flow.

## Test Results

```bash
$ python tests/test_dual_bridge.py

================================================================================
Testing Dual Bridge Architecture
================================================================================

✅ Created two MockWrpService instances (remote + local)
   Remote DB has 193 parameters
   Local DB has 193 parameters

✅ Created two WrpBridge instances (remote + local)

✅ Created BridgeAgent with NO direct Database access
   All data access goes through bridges

Test 1: Get remote parameter (should route to remote bridge)
--------------------------------------------------------------------------------
✅ Response: [{'name': 'Device.DeviceInfo.Manufacturer', 'value': 'ARRIS', 'type': 'string'}]

Test 2: Get local parameter (should route to local bridge)
--------------------------------------------------------------------------------
✅ Response: [{'name': 'Device.LocalAgent.SoftwareVersion', 'value': '0.0.1-alpha', 'type': 'string'}]

Statistics:
--------------------------------------------------------------------------------
Remote service: 1 requests
Local service:  1 requests

================================================================================
✅ SUCCESS: BridgeAgent uses bridges for ALL data access!
   No direct Database dependency in agent
   MockWrpService fronts real Database architecture
================================================================================
```

## Files Modified

### Core Architecture
- **agent/bridge_agent.py**: Removed `self._db`, added `local_bridge` parameter, updated all handlers to use bridges
- **tests/mock_wrp_service.py**: Now uses real `Database` class instead of mock dictionary

### Test Infrastructure  
- **tests/test_dual_bridge.py**: Automated test demonstrating dual bridge architecture
- **tests/test_bridge_agent_interactive.py**: Interactive shell with dual bridge sniffing

## Key Code Changes

### BridgeAgent.__init__
```python
def __init__(self, endpoint_id: str, bridge: UspBridge,
             local_bridge: Optional[UspBridge] = None):
    self.endpoint_id = endpoint_id
    self.bridge = bridge
    self.local_bridge = local_bridge
    # NO self._db = Database(...)
```

### BridgeAgent.handle_get
```python
async def handle_get(self, request: GetRequest,
                    controller_context: Any) -> GetResponse:
    local_paths, remote_paths = self._split_paths(request.paths)
    
    results = []
    
    # Use local_bridge for Device.LocalAgent.* paths
    if local_paths and self.local_bridge:
        local_req = GetRequest(paths=local_paths, msg_id=request.msg_id)
        local_response = await self._bridge_request(
            local_req, controller_context, use_local=True
        )
        results.extend(local_response.results)
    
    # Use bridge for remote paths
    if remote_paths:
        backend_req = GetRequest(paths=remote_paths, msg_id=request.msg_id)
        backend_response = await self._bridge_request(
            backend_req, controller_context
        )
        results.extend(backend_response.results)
    
    return GetResponse(msg_id=request.msg_id, results=results)
```

### BridgeAgent._bridge_request (Updated)
```python
async def _bridge_request(self, request: Any, controller_context: Any,
                        use_local: bool = False) -> Any:
    # Select appropriate bridge
    active_bridge = self.local_bridge if use_local else self.bridge
    
    # ... create context and future ...
    
    # TX Channel: Send to backend or local bridge
    active_bridge.send(request, bridge_context)
    
    # Wait for response from RX channel
    response = await asyncio.wait_for(future, timeout=30.0)
    return response
```

## Interactive Demo

Run the interactive shell to see live WRP message sniffing:

```bash
$ python -m tests.test_bridge_agent_interactive

bridge-agent> get Device.DeviceInfo.Manufacturer

================================================================================
📤 OUTBOUND WRP MESSAGE (TX Channel)
================================================================================
Source:         mac:112233445566/usp
Destination:    mac:112233445566/backend
Message Type:   SimpleRequestResponse
Transaction ID: abc-123
Content Type:   application/json

JSON-RPC Payload:
{
  "jsonrpc": "2.0",
  "method": "usp.get",
  "params": {
    "paths": ["Device.DeviceInfo.Manufacturer"]
  },
  "id": "get-1"
}

Metadata (USP Context):
  usp_msg_id: get-1
  usp_operation: Get
  controller_endpoint: proto::controller-1

Wire Format:
  Bytes: 386 bytes
  Hex: 8aa3737263ad6d61633a313132323333343435353636...
================================================================================

================================================================================
📥 INBOUND WRP MESSAGE (RX Channel)
================================================================================
...Response with value "ARRIS"...
================================================================================

✅ Response received:
   Results: [{'name': 'Device.DeviceInfo.Manufacturer', 'value': 'ARRIS', 'type': 'string'}]

bridge-agent> local Device.LocalAgent.SoftwareVersion

▶️  Getting local parameter: Device.LocalAgent.SoftwareVersion
   Routing: via LOCAL BRIDGE (no direct DB access!)

[Shows WRP messages for local bridge...]

✅ Response received:
   Results: [{'name': 'Device.LocalAgent.SoftwareVersion', 'value': '0.0.1-alpha', 'type': 'string'}]

bridge-agent> stats

📊 Message Statistics:
   Remote sent:     1 WRP messages
   Remote received: 1 WRP messages
   Local sent:      1 WRP messages
   Local received:  1 WRP messages
   Agent pending:   0 requests

   Remote Service (backend):
   Requests:  1
   Responses: 1
   DB Size:   193 parameters

   Local Service (Device.LocalAgent):
   Requests:  1
   Responses: 1
   DB Size:   193 parameters
```

## Benefits Realized

1. **Clean Architecture**: Agent has no database coupling
2. **Testability**: Can swap bridge implementations without changing agent
3. **Scalability**: Local and remote services can be on different transports
4. **Realism**: MockWrpService uses actual Database class (not fake data)
5. **Consistency**: Same two-channel pattern for all data access
6. **Visibility**: WRP message sniffing shows complete TX/RX flow

## Next Steps

This architecture enables:
- Running local_bridge in-process (function calls)
- Running remote bridge over real WRP/Parodus
- Deploying services independently (microservices)
- Adding more bridges (e.g., separate bridge for Device.WiFi.*)
- Testing with different backend implementations

The bridge pattern provides **complete decoupling** while maintaining **operation type preservation** and **clean asynchronous flow**.
