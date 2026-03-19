# TODO List & Action Plan
**Project**: pyagent-old (USP Agent Implementation)  
**Last Updated**: March 19, 2026

---

## Completed Items

### ✅ ~~TODO-002: Update Python Dependencies~~ (COMPLETED)
**Status**: ✅ **COMPLETED** - January 14, 2026
- Updated all dependencies to 2024+ versions
- Removed 5 obsolete packages (six, enum-compat, cov-core, nose2-cov, LinkHeader)
- All 80 tests passing with new dependencies
- Updated: aiocoap, bottle, stomp.py, zeroconf, prometheus-client, protobuf

### ✅ ~~TODO-019: Update USP Protocol Specification~~ (COMPLETED)
**Status**: ✅ **COMPLETED** - January 14, 2026
- Upgraded from WT-369 Draft 1 (June 2017, expired) to TR-369 v1.4.2 (July 2025)
- Downloaded official schemas from BroadbandForum/usp GitHub v1.4.2 tag
- Regenerated protobuf files with protoc 33.0
- All 80 tests passing with new protocol

### ✅ ~~TODO-021: Implement UDS MTP Support~~ (COMPLETED)
**Status**: ✅ **COMPLETED** - January 14, 2026  
**Issue**: TR-369 v1.4 introduces Unix Domain Socket (UDS) MTP, not present in original draft spec

**Implementation**:
- **Created Files**:
  - `database/uds-db.json`: UDS agent database configuration
  - `database/uds-dm.json`: UDS data model with permissions
  - `mtp/uds.py`: UDS transport layer (242 lines)
    - Message framing with 4-byte length prefix (network byte order)
    - Listen/connect modes for server/client operation
    - Thread-safe send/receive with connection management
    - MAX_MESSAGE_SIZE=65536 bytes
  - `agent/uds_usp_binding.py`: UDS USP binding (211 lines)
    - Extends GenericUspBinding
    - USP Record serialization/deserialization
    - Receiver thread with reconnection logic
    - Handles both no_session_context and session_context
  - `agent/uds_agent.py`: UDS agent implementation (193 lines)
    - Extends AbstractAgent
    - UdsNotificationSender for outbound notifications
    - UdsPeriodicNotifHandler for subscription support
  - `tests/test_uds_usp_binding.py`: Unit tests (10 test cases)

- **Modified Files**:
  - `agent/main.py`: Added --uds, --uds-path, --uds-mode CLI arguments

- **Test Results**:
  - All 90 tests passing (80 original + 10 new UDS tests)
  - Full backward compatibility maintained

---

## Table of Contents
1. [Critical Security & Infrastructure](#critical-security--infrastructure)
2. [Code TODOs from Source](#code-todos-from-source)
3. [Technical Debt & Modernization](#technical-debt--modernization)
4. [USP Protocol Compliance — Missing Message Handlers](#usp-protocol-compliance--missing-message-handlers)
5. [USP v1.5 Upgrade Path](#usp-v15-upgrade-path)
6. [Testing & Quality](#testing--quality)
7. [Documentation](#documentation)
8. [Long-term Improvements](#long-term-improvements)

---

## Critical Security & Infrastructure

### � TODO-001: Upgrade Docker Base Image
**Priority**: MEDIUM  
**Location**: `Dockerfile`  
**Current**: Ubuntu 16.04 (EOL: April 2021)  
**Issue**: Security vulnerabilities, no security patches available

**Action Plan**:
1. **Evaluate Options**:
   - Option A: Ubuntu 22.04 LTS (supported until 2027)
   - Option B: Ubuntu 24.04 LTS (supported until 2029)
   - Option C: Alpine Linux (minimal footprint, security-focused)
   
2. **Implementation Steps**:
   ```dockerfile
   # Replace:
   FROM ubuntu:16.04
   
   # With one of:
   FROM ubuntu:24.04
   # OR
   FROM python:3.11-slim-bookworm  # Debian-based, maintained
   # OR
   FROM python:3.11-alpine  # Minimal
   ```

3. **Update Package Installation**:
   - Replace `apt-get` commands with consolidated RUN statements
   - Use `--no-install-recommends` flag
   - Clean up apt cache: `rm -rf /var/lib/apt/lists/*`
   - Update protobuf version (currently 3.2.0 from 2017)

4. **Test Migration**:
   ```bash
   docker build -t coap-usp-agent:test -f Dockerfile.new .
   docker run -p 15683:15683/udp -it coap-usp-agent:test
   # Run integration tests
   make test
   ```

5. **Considerations**:
   - Python 3 may have version changes (currently using system python3)
   - npm package availability in newer repos
   - Protobuf compatibility (may need newer protoc)

**Estimated Effort**: 4-8 hours  
**Dependencies**: None  
**Risk**: Medium (breaking changes possible in newer OS)

---

### ~~🔴 TODO-002: Update Python Dependencies~~ ✅ COMPLETED
**Priority**: ~~CRITICAL~~ DONE  
**Location**: `requirements.txt`  
**Issue**: ~~Outdated packages with known security vulnerabilities~~ RESOLVED

**Action Plan**:
1. **Audit Current Versions**:
   ```bash
   pip list --outdated
   # Check for CVEs:
   pip install safety
   safety check -r requirements.txt
   ```

2. **Update Strategy** (per package):
   
   | Package | Current | Latest (Jan 2026) | Breaking Changes? |
   |---------|---------|-------------------|-------------------|
   | `aiocoap` | 0.3 | ~0.4.7 | Yes - API changes |
   | `bottle` | 0.12.9 | 0.12.25 | Minimal |
   | `stomp.py` | 4.1.11 | 8.1.0 | Yes - connection API |
   | `zeroconf` | 0.18.0 | 0.131.0 | Yes - major refactor |
   | `prometheus-client` | 0.3.1 | 0.19.0 | Minimal |
   | `protobuf` | (unversioned) | 4.25.1 | Yes - v4 breaking |

3. **Incremental Update Process**:
   ```bash
   # Step 1: Create test environment
   python3 -m venv test-env
   source test-env/bin/activate
   
   # Step 2: Update one package at a time
   pip install bottle==0.12.25
   # Run tests after each update
   make test
   
   # Step 3: Update requirements.txt
   pip freeze > requirements-new.txt
   ```

4. **Code Changes Required**:
   - **aiocoap**: Review `agent/coap_usp_binding.py` and `mtp/coap_usp_binding.py`
     - Check resource registration API
     - Update context manager usage
   - **stomp.py**: Review `agent/stomp_usp_binding.py`
     - Connection parameters may have changed
     - SSL/TLS configuration updates
   - **zeroconf**: Review `agent/mdns.py` and `controller/mdns.py`
     - ServiceInfo constructor changes
     - Registration API updates
   - **protobuf**: May need to regenerate `.proto` files
     ```bash
     make schema  # Regenerate with new protoc
     ```

5. **Remove Deprecated Packages**:
   ```diff
   - enum-compat==0.0.2  # Not needed in Python 3.4+
   - six==1.10.0         # Not needed in Python 3+
   ```

**Estimated Effort**: 16-24 hours  
**Dependencies**: TODO-001 (for testing environment)  
**Risk**: High (API breaking changes likely)

---

### ~~🔴 TODO-022: Fix CoAP Agent asyncio.coroutine Deprecation~~ ✅ COMPLETED
**Status**: ✅ **COMPLETED** - March 19, 2026  
**Location**: `mtp/coap.py`

- Replaced `@asyncio.coroutine` decorator with `async def` on `CoapSendingThread._issue_request()`
- Replaced `yield from` with `await` on both `aiocoap.Context.create_client_context()` and `context.request().response`
- Removed dead Python 3.4 compatibility shim for `asyncio.ensure_future`
- `mtp/coap.py` now imports cleanly on Python 3.11+/3.14; all 118 passing tests remain green

---

### 🔴 TODO-003: Implement Payload Validation (CoAP)
**Priority**: HIGH  
**Location**: 
- `mtp/coap_usp_binding.py:255`
- `agent/coap_usp_binding.py:255`

**Current Code**:
```python
# TODO: Implement payload validation
```

**Issue**: No validation of incoming CoAP payloads - security risk for malformed/malicious messages

**Action Plan**:

1. **Define Validation Requirements**:
   - Check CoAP content-format (should be application/octet-stream for protobuf)
   - Validate message size limits
   - Verify protobuf structure before parsing
   - Check USP Record wrapper integrity
   - Validate endpoint IDs

2. **Implementation**:
   ```python
   def _validate_coap_payload(self, request):
       """
       Validate incoming CoAP request payload
       
       Args:
           request: aiocoap request object
           
       Returns:
           tuple: (is_valid, error_message)
       
       Raises:
           ValueError: If payload is invalid
       """
       # 1. Check content format
       content_format = request.opt.content_format
       if content_format != aiocoap.numbers.media_types.APPLICATION_OCTET_STREAM:
           return False, f"Invalid content-format: {content_format}"
       
       # 2. Check payload size
       MAX_PAYLOAD_SIZE = 65536  # 64KB - configurable
       if len(request.payload) > MAX_PAYLOAD_SIZE:
           return False, f"Payload too large: {len(request.payload)} bytes"
       
       if len(request.payload) == 0:
           return False, "Empty payload"
       
       # 3. Try to parse protobuf
       try:
           from agent.usp_record_pb2 import Record
           record = Record()
           record.ParseFromString(request.payload)
           
           # 4. Validate record structure
           if not record.HasField('version'):
               return False, "Missing version field"
           
           if not record.HasField('to_id'):
               return False, "Missing to_id field"
               
           if not record.HasField('from_id'):
               return False, "Missing from_id field"
           
           # 5. Validate endpoint IDs format (should be URN)
           import re
           urn_pattern = r'^(proto|doc|os|ops|dev|self):.*'
           if not re.match(urn_pattern, record.to_id):
               return False, f"Invalid to_id format: {record.to_id}"
           
           if not re.match(urn_pattern, record.from_id):
               return False, f"Invalid from_id format: {record.from_id}"
           
       except Exception as e:
           return False, f"Protobuf parsing failed: {str(e)}"
       
       return True, None
   ```

3. **Integration Points**:
   - Add validation before `self._binding.process_msg()` call
   - Return appropriate CoAP error codes:
     - 4.00 Bad Request - for invalid format
     - 4.13 Request Entity Too Large - for size limits
     - 4.15 Unsupported Content-Format - for wrong content type
   
   ```python
   def process_coap_msg(self, request):
       # Add validation
       is_valid, error_msg = self._validate_coap_payload(request)
       if not is_valid:
           logger.warning(f"Invalid CoAP payload: {error_msg}")
           return aiocoap.Message(code=aiocoap.Code.BAD_REQUEST, 
                                 payload=error_msg.encode('utf-8'))
       
       # Continue with existing logic
       return self._binding.process_msg(request.payload)
   ```

4. **Add Configuration**:
   Update `cfg/agent.json`:
   ```json
   {
     "coap.max_payload_size": 65536,
     "coap.strict_validation": true,
     "coap.allowed_content_formats": ["application/octet-stream"]
   }
   ```

5. **Add Metrics**:
   ```python
   PAYLOAD_VALIDATION_ERRORS = prometheus_client.Counter(
       'coap_payload_validation_errors_total',
       'Total number of CoAP payload validation failures',
       ['error_type']
   )
   ```

6. **Write Tests**:
   ```python
   # tests/test_coap_validation.py
   def test_valid_payload():
       # Test with valid USP Record
       
   def test_invalid_content_format():
       # Test with wrong content-format
       
   def test_oversized_payload():
       # Test with payload > max size
       
   def test_malformed_protobuf():
       # Test with corrupted protobuf data
       
   def test_missing_required_fields():
       # Test with incomplete USP Record
   ```

**Estimated Effort**: 8-12 hours  
**Dependencies**: None  
**Risk**: Low (adds new functionality)

---

### 🔴 TODO-004: Implement Payload Validation (STOMP)
**Priority**: HIGH  
**Location**: `agent/stomp_usp_binding.py`  
**Issue**: Similar to TODO-003 but for STOMP transport

**Action Plan**:
1. Add similar validation as CoAP (see TODO-003)
2. Validate STOMP headers (destination, content-type)
3. Check message size limits
4. Validate USP Record structure
5. Add STOMP-specific error handling (NACK messages)

**Estimated Effort**: 6-8 hours  
**Dependencies**: TODO-003 (reuse validation logic)  
**Risk**: Low

---

## Code TODOs from Source

### 🟡 TODO-005: Terminate Listening Thread on Shutdown
**Priority**: MEDIUM  
**Location**: 
- `mtp/coap_usp_binding.py:282`
- `agent/coap_usp_binding.py:282`

**Current Code**:
```python
# TODO: Maybe terminate the listening thread???
```

**Issue**: Unclear cleanup of CoAP listening threads on agent shutdown

**Action Plan**:

1. **Analyze Current Cleanup**:
   ```bash
   # Review clean_up() method
   grep -n "clean_up\|shutdown\|stop" agent/coap_agent.py
   grep -n "clean_up\|shutdown\|stop" agent/coap_usp_binding.py
   ```

2. **Implement Proper Thread Shutdown**:
   ```python
   class CoapBinding:
       def __init__(self):
           self._shutdown_event = threading.Event()
           self._listener_thread = None
       
       def start_listening(self):
           self._listener_thread = threading.Thread(
               target=self._listen_loop,
               name="CoAP-Listener"
           )
           self._listener_thread.daemon = False  # Explicit non-daemon
           self._listener_thread.start()
       
       def _listen_loop(self):
           while not self._shutdown_event.is_set():
               # Listen for messages with timeout
               # Use shutdown_event.wait(timeout) instead of time.sleep()
               pass
       
       def clean_up(self):
           """Graceful shutdown of CoAP binding"""
           logger.info("Shutting down CoAP binding...")
           
           # 1. Signal shutdown
           self._shutdown_event.set()
           
           # 2. Wait for thread to finish (with timeout)
           if self._listener_thread and self._listener_thread.is_alive():
               self._listener_thread.join(timeout=5.0)
               
               if self._listener_thread.is_alive():
                   logger.warning("CoAP listener thread did not stop gracefully")
               else:
                   logger.info("CoAP listener thread stopped")
           
           # 3. Close CoAP context
           if hasattr(self, '_context'):
               self._context.shutdown()
           
           logger.info("CoAP binding shutdown complete")
   ```

3. **Signal Handling**:
   ```python
   # In main.py
   import signal
   
   def signal_handler(signum, frame):
       logger.info(f"Received signal {signum}, shutting down...")
       agent.clean_up()
       sys.exit(0)
   
   signal.signal(signal.SIGINT, signal_handler)
   signal.signal(signal.SIGTERM, signal_handler)
   ```

4. **Test Shutdown**:
   ```bash
   # Start agent
   python3 -m agent.main -t test -c
   
   # Send SIGTERM
   kill -TERM <pid>
   
   # Check logs for graceful shutdown
   # Verify no zombie threads: ps -ef | grep python
   ```

**Estimated Effort**: 4-6 hours  
**Dependencies**: None  
**Risk**: Low

---

### 🟡 TODO-006: Check Shutdown with Message Handler
**Priority**: MEDIUM  
**Location**: `agent/abstract_agent.py:373`

**Current Code**:
```python
# TODO: Check with the self._msg_handler if should shutdown, and raise a GeneratorExit
```

**Issue**: No coordination between message handler and shutdown process

**Action Plan**:

1. **Add Shutdown State to Message Handler**:
   ```python
   class RequestHandler:
       def __init__(self):
           self._shutdown_requested = False
       
       def request_shutdown(self):
           """Request graceful shutdown"""
           self._shutdown_requested = True
       
       def should_shutdown(self):
           """Check if shutdown has been requested"""
           return self._shutdown_requested
   ```

2. **Update AbstractAgent Generator**:
   ```python
   # In abstract_agent.py around line 373
   def _message_generator(self):
       while True:
           # Check shutdown condition
           if self._msg_handler.should_shutdown():
               logger.info("Message handler shutdown requested")
               raise GeneratorExit
           
           # Yield messages...
           yield next_message
   ```

3. **Add Shutdown Triggers**:
   - Fatal errors in message processing
   - Configuration changes requiring restart
   - External shutdown command via USP
   - Resource exhaustion conditions

4. **Test Shutdown Flow**:
   ```python
   # tests/test_shutdown.py
   def test_graceful_shutdown():
       agent = AbstractAgent(...)
       agent.start_listening()
       
       # Request shutdown
       agent._msg_handler.request_shutdown()
       
       # Verify generator exits
       # Verify threads stop
       # Verify resources released
   ```

**Estimated Effort**: 4-6 hours  
**Dependencies**: TODO-005  
**Risk**: Low

---

### 🟡 TODO-007: Prevent Sets on Immutable Parameters
**Priority**: MEDIUM  
**Location**: `agent/request_handler.py:335`

**Current Code**:
```python
# TODO: Also need to not allow sets against unmutable parameters and objects
```

**Issue**: No enforcement of read-only parameter restrictions

**Action Plan**:

1. **Analyze Data Model**:
   ```python
   # In database/*-dm.json, parameters are marked as:
   # "Device.DeviceInfo.Manufacturer": "readOnly"
   # "Device.LocalAgent.MTP.{i}.Enable": "readWrite"
   ```

2. **Add Validation in Request Handler**:
   ```python
   def handle_set_request(self, msg):
       """Handle USP Set request with immutability checks"""
       set_resp = SetResp()
       
       for update_obj in msg.body.request.set.update_objs:
           for param_setting in update_obj.param_settings:
               param_path = param_setting.param
               
               # Check if parameter is mutable
               access_type = self._db.get_param_access_type(param_path)
               
               if access_type == "readOnly":
                   # Add error to response
                   oper_failure = set_resp.updated_obj_results.add()
                   oper_failure.requested_path = update_obj.obj_path
                   
                   param_err = oper_failure.oper_status.oper_failure.updated_params_failures.add()
                   param_err.affected_path = param_path
                   param_err.param_err_code = 7006  # Invalid arguments
                   param_err.param_err_msg = f"Parameter {param_path} is read-only"
                   
                   logger.warning(f"Attempt to set read-only parameter: {param_path}")
                   continue
               
               # Proceed with set operation for read-write params
               # ... existing code ...
   ```

3. **Update Database Interface**:
   ```python
   # In agent_db.py
   class AgentDB:
       def get_param_access_type(self, param_path):
           """
           Get access type for a parameter
           
           Returns:
               str: "readOnly", "readWrite", or None if not found
           """
           # Resolve wildcards in path
           resolved_path = self._resolve_path(param_path)
           
           if resolved_path in self._dm_dict:
               return self._dm_dict[resolved_path]
           
           # Check pattern match for instance parameters
           return self._match_param_pattern(param_path)
   ```

4. **Add Error Codes**:
   ```python
   # USP Error Codes (TR-369)
   USP_ERR_PERMISSION_DENIED = 7005
   USP_ERR_INVALID_ARGUMENTS = 7006
   USP_ERR_RESOURCES_EXCEEDED = 7008
   USP_ERR_OBJECT_NOT_CREATABLE = 7011
   USP_ERR_OBJECT_NOT_DELETABLE = 7012
   USP_ERR_REQUIRED_PARAM_FAILED = 7018
   ```

5. **Write Tests**:
   ```python
   def test_set_readonly_parameter():
       """Test that setting read-only params returns error"""
       # Try to set Device.DeviceInfo.Manufacturer
       # Assert error code 7006
       
   def test_set_readwrite_parameter():
       """Test that setting read-write params succeeds"""
       # Try to set Device.LocalAgent.MTP.{i}.Enable
       # Assert success
   ```

**Estimated Effort**: 6-8 hours  
**Dependencies**: None  
**Risk**: Low (improves protocol compliance)

---

### 🟡 TODO-008: Make Camera Logic Dynamic
**Priority**: MEDIUM  
**Location**: `agent/request_handler.py:430`

**Current Code**:
```python
# TODO: This is hard-coded for the Camera, but needs to be dynamic
```

**Issue**: Camera-specific operations hard-coded in generic request handler

**Action Plan**:

1. **Create Plugin Architecture**:
   ```python
   # New file: agent/device_plugins.py
   from abc import ABC, abstractmethod
   
   class DevicePlugin(ABC):
       """Base class for device-specific implementations"""
       
       @abstractmethod
       def get_supported_operations(self):
           """Return list of supported operation paths"""
           pass
       
       @abstractmethod
       def handle_operation(self, operation_path, input_args):
           """Execute device-specific operation"""
           pass
       
       @abstractmethod
       def get_device_type(self):
           """Return device type identifier"""
           pass
   
   
   class CameraPlugin(DevicePlugin):
       """Camera-specific operations"""
       
       def get_supported_operations(self):
           return [
               "Device.Camera.Capture()",
               "Device.Camera.Stream()",
               "Device.Camera.GetImage()"
           ]
       
       def handle_operation(self, operation_path, input_args):
           if operation_path == "Device.Camera.Capture()":
               return self._capture_image(input_args)
           elif operation_path == "Device.Camera.Stream()":
               return self._start_stream(input_args)
           # ...
       
       def get_device_type(self):
           return "camera"
       
       def _capture_image(self, args):
           # Existing camera logic from request_handler.py
           pass
   
   
   class MotionPlugin(DevicePlugin):
       """Motion sensor operations"""
       
       def get_supported_operations(self):
           return [
               "Device.Motion.Calibrate()",
               "Device.Motion.GetStatus()"
           ]
       
       # ... implementation ...
   ```

2. **Create Plugin Registry**:
   ```python
   # In agent/device_plugins.py
   class PluginRegistry:
       """Registry for device plugins"""
       
       def __init__(self):
           self._plugins = {}
       
       def register(self, plugin):
           """Register a device plugin"""
           device_type = plugin.get_device_type()
           self._plugins[device_type] = plugin
           logger.info(f"Registered plugin: {device_type}")
       
       def get_plugin(self, device_type):
           """Get plugin for device type"""
           return self._plugins.get(device_type)
       
       def handle_operation(self, device_type, operation_path, input_args):
           """Route operation to appropriate plugin"""
           plugin = self.get_plugin(device_type)
           if not plugin:
               raise ValueError(f"No plugin for device type: {device_type}")
           
           if operation_path not in plugin.get_supported_operations():
               raise ValueError(f"Unsupported operation: {operation_path}")
           
           return plugin.handle_operation(operation_path, input_args)
   ```

3. **Update Request Handler**:
   ```python
   # In agent/request_handler.py
   class RequestHandler:
       def __init__(self, db, dm, device_type):
           self._db = db
           self._dm = dm
           self._device_type = device_type
           
           # Initialize plugin registry
           self._plugin_registry = PluginRegistry()
           self._load_plugins()
       
       def _load_plugins(self):
           """Load plugins based on device type"""
           if self._device_type == "camera":
               from agent.camera import CameraPlugin
               self._plugin_registry.register(CameraPlugin())
           elif self._device_type == "motion":
               from agent.motion import MotionPlugin
               self._plugin_registry.register(MotionPlugin())
       
       def handle_operate_request(self, msg):
           """Handle USP Operate request"""
           operate_req = msg.body.request.operate
           
           # Route to plugin instead of hard-coded logic
           try:
               result = self._plugin_registry.handle_operation(
                   self._device_type,
                   operate_req.command,
                   operate_req.command_key
               )
               return self._create_operate_response(result)
           except Exception as e:
               return self._create_error_response(str(e))
   ```

4. **Move Camera Code**:
   ```python
   # Refactor agent/camera.py to use plugin pattern
   # Move hard-coded logic from request_handler.py to CameraPlugin
   ```

5. **Add Configuration**:
   ```json
   // cfg/agent.json
   {
     "device.type": "camera",
     "device.plugins": ["camera", "motion"],
     "camera.image.dir": "pictures",
     "motion.gpio.pin": "4"
   }
   ```

**Estimated Effort**: 12-16 hours  
**Dependencies**: None  
**Risk**: Medium (significant refactoring)

---

### 🟢 TODO-009: File Cleanup on Deletion
**Priority**: LOW  
**Location**: `agent/camera.py:122`

**Current Code**:
```python
# TODO - what about removing the file too?
```

**Issue**: When camera image database entry is deleted, physical file may remain

**Action Plan**:

1. **Add File Tracking**:
   ```python
   # In agent/camera.py
   class CameraHandler:
       def __init__(self, db, image_dir):
           self._db = db
           self._image_dir = image_dir
           self._file_registry = {}  # Maps DB entry to file path
       
       def capture_image(self, params):
           # ... capture logic ...
           
           # Track file
           db_entry_id = self._db.add_entry(image_metadata)
           self._file_registry[db_entry_id] = file_path
       
       def delete_image(self, entry_id):
           """Delete image from database and filesystem"""
           # 1. Remove from database
           self._db.delete_entry(entry_id)
           
           # 2. Delete physical file
           if entry_id in self._file_registry:
               file_path = self._file_registry[entry_id]
               try:
                   if os.path.exists(file_path):
                       os.remove(file_path)
                       logger.info(f"Deleted image file: {file_path}")
                   del self._file_registry[entry_id]
               except OSError as e:
                   logger.error(f"Failed to delete {file_path}: {e}")
                   # Don't fail the operation, just log
   ```

2. **Add Configuration**:
   ```json
   {
     "camera.delete_files_on_removal": true,
     "camera.keep_deleted_files_days": 0
   }
   ```

3. **Add Cleanup on Startup**:
   ```python
   def cleanup_orphaned_files(self):
       """Remove image files that don't have DB entries"""
       db_files = set(self._db.get_all_image_paths())
       disk_files = set(glob.glob(os.path.join(self._image_dir, "*.jpg")))
       
       orphaned = disk_files - db_files
       for file_path in orphaned:
           logger.warning(f"Orphaned file found: {file_path}")
           if self._config.get("camera.delete_orphaned_files", False):
               os.remove(file_path)
   ```

**Estimated Effort**: 3-4 hours  
**Dependencies**: None  
**Risk**: Low

---

### 🟢 TODO-010: Better ID Handling (STOMP)
**Priority**: LOW  
**Location**: `agent/stomp_usp_binding.py:143`

**Current Code**:
```python
# TODO: Handle the ID Better
```

**Action Plan**:

1. **Review Current ID Generation**:
   ```bash
   grep -n "msg_id\|message_id\|msg-id" agent/stomp_usp_binding.py
   ```

2. **Implement Robust ID Generation**:
   ```python
   import uuid
   from datetime import datetime
   
   class StompBinding:
       def __init__(self):
           self._endpoint_id = self._load_endpoint_id()
           self._msg_counter = 0
           self._counter_lock = threading.Lock()
       
       def generate_message_id(self):
           """
           Generate unique message ID following USP spec
           
           Format: <endpoint-id>.<timestamp>.<counter>.<uuid>
           Example: proto::agent-001.1705267890.0042.a1b2c3d4
           """
           with self._counter_lock:
               self._msg_counter += 1
               if self._msg_counter > 9999:
                   self._msg_counter = 1
               
               counter = self._msg_counter
           
           timestamp = int(datetime.utcnow().timestamp())
           unique_part = uuid.uuid4().hex[:8]
           
           return f"{self._endpoint_id}.{timestamp}.{counter:04d}.{unique_part}"
       
       def generate_stomp_frame_id(self):
           """Generate STOMP frame-level message-id"""
           return str(uuid.uuid4())
   ```

3. **Add ID Validation**:
   ```python
   def validate_message_id(self, msg_id):
       """Validate incoming message ID format"""
       # Should be a string, unique, not empty
       if not msg_id or not isinstance(msg_id, str):
           return False
       
       # Check length (reasonable bounds)
       if len(msg_id) > 256:
           return False
       
       return True
   ```

4. **Track Message IDs**:
   ```python
   class MessageIdTracker:
       """Track recent message IDs to detect duplicates"""
       def __init__(self, max_size=10000):
           self._recent_ids = collections.deque(maxlen=max_size)
           self._lock = threading.Lock()
       
       def is_duplicate(self, msg_id):
           with self._lock:
               if msg_id in self._recent_ids:
                   return True
               self._recent_ids.append(msg_id)
               return False
   ```

**Estimated Effort**: 4-6 hours  
**Dependencies**: None  
**Risk**: Low

---

### ✅ ~~TODO-011: Replace Hard-coded List (Notifications)~~ (COMPLETED)
**Priority**: LOW  
**Location**: `agent/notify.py:94`

**Current Code**:
```python
# TODO: Replace hard-coded list with data model driven list
```

**Action Plan**:

1. **Identify Hard-coded List**:
   ```bash
   sed -n '90,100p' agent/notify.py
   ```

2. **Create Data Model Driven Approach**:
   ```python
   # In agent/notify.py
   class NotificationHandler:
       def __init__(self, db, dm):
           self._db = db
           self._dm = dm
           self._notif_params = self._load_notifiable_params()
       
       def _load_notifiable_params(self):
           """
           Load list of notifiable parameters from data model
           
           Returns:
               dict: {param_path: notification_type}
           """
           notif_params = {}
           
           # Query data model for parameters with notification capabilities
           for param_path in self._dm.get_all_params():
               # Check if parameter supports ValueChange notification
               if self._dm.supports_value_change(param_path):
                   notif_params[param_path] = "ValueChange"
               
               # Check if parameter supports Event notification
               if self._dm.is_event(param_path):
                   notif_params[param_path] = "Event"
           
           return notif_params
   ```

3. **Update Data Model Format**:
   ```json
   // database/*-dm.json
   {
     "Device.LocalAgent.UpTime": {
       "access": "readOnly",
       "type": "unsignedInt",
       "notifications": ["ValueChange"]
     },
     "Device.Boot!": {
       "type": "event",
       "notifications": ["Event"]
     }
   }
   ```

4. **Add Notification Configuration**:
   ```json
   // cfg/agent.json
   {
     "notifications.enabled": true,
     "notifications.value_change.default_enabled": false,
     "notifications.events.default_enabled": true
   }
   ```

**Estimated Effort**: 4-6 hours  
**Dependencies**: May require data model schema changes  
**Risk**: Low

---

### 🟢 TODO-012: Add Binding in Message Module
**Priority**: LOW  
**Location**: `message/message.py:120`

**Current Code**:
```python
#TODO:  We need a binding here
```

**Action Plan**:

1. **Analyze Context**:
   ```bash
   sed -n '115,125p' message/message.py
   ```

2. **Determine Required Binding**:
   - Review what object/method needs binding
   - Check if it's related to MTP abstraction
   - Determine if it's a missing callback

3. **Implement Solution** (once context is clear):
   - Add appropriate method binding
   - Update tests
   - Document purpose

**Estimated Effort**: 2-4 hours  
**Dependencies**: Need to review code context  
**Risk**: Very Low

---

## Technical Debt & Modernization

### 🟡 TODO-013: Python 3 Only Migration
**Priority**: MEDIUM  
**Current**: Mixed Python 2/3 compatibility code  
**Goal**: Python 3.10+ only

**Action Plan**:

1. **Remove Compatibility Layers**:
   ```bash
   # Remove from requirements.txt:
   - enum-compat==0.0.2
   - six==1.10.0
   ```

2. **Update Code Patterns**:
   ```python
   # Remove six usage
   - from six import string_types
   + # Use str directly
   
   # Update super() calls
   - super(ClassName, self).__init__()
   + super().__init__()
   
   # Use f-strings
   - "Value: {}".format(value)
   + f"Value: {value}"
   
   # Type hints
   def process_message(self, msg: Message) -> Response:
       pass
   ```

3. **Add Type Annotations**:
   ```python
   from typing import Dict, List, Optional, Union
   
   class AgentDB:
       def get_value(self, path: str) -> Optional[Union[str, int, bool]]:
           pass
       
       def get_instance_ids(self, obj_path: str) -> List[str]:
           pass
   ```

4. **Use Modern Python Features**:
   - Data classes for configuration
   - asyncio for concurrent operations
   - pathlib instead of os.path
   - Context managers everywhere

**Estimated Effort**: 20-30 hours  
**Dependencies**: TODO-001, TODO-002  
**Risk**: Medium

---

### 🟡 TODO-014: Containerization Improvements
**Priority**: MEDIUM  
**Current**: Inefficient Dockerfile, security issues

**Action Plan**:

1. **Multi-stage Build**:
   ```dockerfile
   # Stage 1: Build
   FROM python:3.11-slim as builder
   
   WORKDIR /build
   COPY requirements.txt .
   RUN pip install --user --no-cache-dir -r requirements.txt
   
   # Stage 2: Runtime
   FROM python:3.11-slim
   
   # Create non-root user
   RUN useradd -ms /bin/bash uspagent
   
   WORKDIR /app
   COPY --from=builder /root/.local /home/uspagent/.local
   COPY --chown=uspagent:uspagent . .
   
   USER uspagent
   ENV PATH=/home/uspagent/.local/bin:$PATH
   
   EXPOSE 15683/udp
   CMD ["python3", "-m", "agent.main", "-t", "test", "-c"]
   ```

2. **Add .dockerignore**:
   ```
   .git
   .pytest_cache
   __pycache__
   *.pyc
   .coverage
   htmlcov/
   dist/
   build/
   *.egg-info
   ```

3. **Health Checks**:
   ```dockerfile
   HEALTHCHECK --interval=30s --timeout=3s \
     CMD python3 -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('localhost', 15683)); s.close()" || exit 1
   ```

4. **Docker Compose**:
   ```yaml
   version: '3.8'
   services:
     usp-agent:
       build: .
       ports:
         - "15683:15683/udp"
         - "9001:9001"  # Prometheus
       environment:
         - DEVICE_TYPE=test
       volumes:
         - ./database:/app/database
         - ./logs:/app/logs
       restart: unless-stopped
   ```

**Estimated Effort**: 6-8 hours  
**Dependencies**: TODO-001  
**Risk**: Low

---

## USP Protocol Compliance — Missing Message Handlers

These message types are fully defined in the protobuf schema (`schema/usp-msg-1-4.proto`) but have **no Python wrapper classes, no agent handler, and no controller handling**. They are required for full TR-369 conformance and are prerequisites for v1.5 compliance (especially Register/Deregister which underpin USPServices).

---

### 🔴 TODO-024: Implement Add & Delete Message Handlers
**Priority**: HIGH  
**Location**: `message/request.py`, `message/response.py`, `agent/base_agent.py`, `agent/request_handler.py`, `agent/agent_db.py`  
**Spec Reference**: TR-369 §7.4 (Creating, Updating, and Deleting Objects)

**Current State**: The proto schema defines `Add`/`AddResp` and `Delete`/`DeleteResp` with full field sets. `MsgType.ADD`, `ADD_RESP`, `DELETE`, `DELETE_RESP` are registered as enum values. There are **no Python wrapper classes** and the request handler falls through to a generic error for both types.

The controller (`controller/controller.py`) already **imports** `Add` and `Delete` from `message/` but those symbols don't exist yet — this is a latent import error.

**Action Plan**:

1. **Add Python wrapper classes in `message/request.py`**:
   ```python
   class AddRequest:
       """Wraps USP Add request"""
       def __init__(self, allow_partial=True, create_objs=None):
           self.allow_partial = allow_partial
           self.create_objs = create_objs or []  # list of {obj_path, param_settings}

       def to_protobuf(self):
           msg = usp_msg_pb2.Msg()
           msg.header.msg_id = str(uuid.uuid4())
           msg.header.msg_type = usp_msg_pb2.Header.ADD
           add = msg.body.request.add
           add.allow_partial = self.allow_partial
           for co in self.create_objs:
               obj = add.create_objs.add()
               obj.obj_path = co['obj_path']
               for k, v in co.get('param_settings', {}).items():
                   ps = obj.param_settings.add()
                   ps.param = k
                   ps.value = v
                   ps.required = co.get('required', {}).get(k, False)
           return msg

   class DeleteRequest:
       """Wraps USP Delete request"""
       def __init__(self, allow_partial=True, obj_paths=None):
           self.allow_partial = allow_partial
           self.obj_paths = obj_paths or []

       def to_protobuf(self):
           msg = usp_msg_pb2.Msg()
           msg.header.msg_id = str(uuid.uuid4())
           msg.header.msg_type = usp_msg_pb2.Header.DELETE
           delete = msg.body.request.delete
           delete.allow_partial = self.allow_partial
           delete.obj_paths.extend(self.obj_paths)
           return msg
   ```

2. **Add response wrapper classes in `message/response.py`**:
   - `AddResponse`: wraps `AddResp`, exposes `created_obj_results`
   - `DeleteResponse`: wraps `DeleteResp`, exposes `deleted_obj_results`

3. **Update `message/__init__.py`** to export `AddRequest`, `DeleteRequest`, `AddResponse`, `DeleteResponse` and add to `REQUEST_TYPES` dispatch dict.

4. **Implement `on_add_request()` in `agent/base_agent.py`**:
   - Validate `obj_path` exists in the data model and is multi-instance
   - Call `agent_db.Database.insert()` for each `create_obj`
   - Handle `allow_partial`: on first failure, either continue (True) or roll back all (False)
   - Return `AddResp` with `instantiated_path` and `unique_keys` per created object
   - USP error 7011 (`Object not creatable`) if path disallows creation

5. **Implement `on_delete_request()` in `agent/base_agent.py`**:
   - Validate each `obj_path` exists (search paths allowed per v1.3+)
   - Call `agent_db.Database.delete()` for each resolved instance
   - Handle `allow_partial`
   - Return `DeleteResp` with `affected_paths` and `unaffected_path_errs`
   - USP error 7012 (`Object not deletable`) if path disallows deletion

6. **Update `agent/request_handler.py`** `REQUEST_TYPES` dict to include `ADD` → `on_add_request` and `DELETE` → `on_delete_request`.

7. **Extend `agent/agent_db.py`**:
   - `insert(path, params)` → assigns next instance number, writes to runtime DB, returns instantiated path
   - `delete(path)` → removes instance and all sub-keys from runtime DB

8. **Write tests**:
   - `tests/test_add_delete.py`: happy path, `allow_partial=False` rollback, non-creatable path, non-existent path, unique key conflicts

**Estimated Effort**: 12–16 hours  
**Dependencies**: None  
**Risk**: Medium — `agent_db` insert/delete needs careful instance-numbering logic

---

### 🔴 TODO-025: Implement Notify (Inbound) & NotifyResp Handlers
**Priority**: HIGH  
**Location**: `message/request.py`, `message/response.py`, `agent/base_agent.py`, `agent/request_handler.py`  
**Spec Reference**: TR-369 §7.6 (Notifications and Subscription Mechanism)

**Current State**: The agent **sends** notifications outbound (see `agent/notify.py`). But when a **controller sends a Notify** to the agent (e.g., relaying an event through a broker), or when the agent acts in a dual-role scenario, there is no inbound handler. `MsgType.NOTIFY` falls through to an error. `NotifyResp` is also unhandled.

**Action Plan**:

1. **Add `NotifyRequest` wrapper in `message/request.py`**:
   - Expose `subscription_id`, `send_resp`, and the `oneof notification` variant (Event, ValueChange, ObjectCreation, ObjectDeletion, OperationComplete, OnBoardRequest)
   - Add `from_protobuf()` class method

2. **Add `NotifyResponse` wrapper in `message/response.py`**:
   - Wraps `NotifyResp`: just echoes `subscription_id`

3. **Implement `on_notify_request()` in `agent/base_agent.py`**:
   - Log the notification type and payload
   - If `send_resp=True`, return a `NotifyResp` echoing `subscription_id`
   - Default implementation is a no-op log (agent as proxy/broker scenario)

4. **Update `REQUEST_TYPES`** dispatch in `agent/request_handler.py`.

5. **Handle `NotifyResp` on the controller side** (`controller/response_handler.py`): currently ignored; add a branch that marks the pending subscription ACK complete.

6. **Write tests**:
   - `tests/test_notify_inbound.py`: verify agent responds to incoming Notify with NotifyResp when `send_resp=True`; verify no response when `send_resp=False`

**Estimated Effort**: 6–8 hours  
**Dependencies**: None  
**Risk**: Low

---

### 🟡 TODO-026: Implement GetSupportedProtocol Handler
**Priority**: MEDIUM  
**Location**: `message/request.py`, `message/response.py`, `agent/base_agent.py`  
**Spec Reference**: TR-369 §7.5.5

**Current State**: `MsgType.GET_SUPPORTED_PROTO` / `GET_SUPPORTED_PROTO_RESP` are defined in the schema. No Python wrappers. Falls through to error in the request handler.

**Action Plan**:

1. **Add `GetSupportedProtocolRequest` wrapper** in `message/request.py`:
   - Single field: `controller_supported_protocol_versions` (comma-separated string, e.g. `"1.0,1.1,1.2,1.3,1.4,1.5"`)

2. **Add `GetSupportedProtocolResponse` wrapper** in `message/response.py`:
   - Single field: `agent_supported_protocol_versions`

3. **Implement `on_get_supported_protocol_request()` in `agent/base_agent.py`**:
   ```python
   async def on_get_supported_protocol_request(self, request):
       resp = GetSupportedProtocolResponse()
       resp.agent_supported_protocol_versions = "1.0,1.1,1.2,1.3,1.4,1.5"
       return resp
   ```
   - Version string should be read from config / a constant; bump when upgrading.

4. **Update dispatch** in `agent/request_handler.py`.

**Estimated Effort**: 2–4 hours  
**Dependencies**: TODO-028 (version string should reflect actual supported version)  
**Risk**: Very Low

---

### 🔴 TODO-027: Implement Register & Deregister Handlers
**Priority**: HIGH  
**Location**: `message/request.py`, `message/response.py`, `agent/base_agent.py`, `agent/request_handler.py`, `database/`  
**Spec Reference**: TR-369 §7 (Register/Deregister), Appendix VI (USP Services)

**Current State**: `MsgType.REGISTER` and `DEREGISTER` are in the schema (added in v1.3). The proto includes `Register` / `RegisterResp` / `Deregister` / `DeregisterResp` messages. Currently falls through to error. v1.5 adds `USPServices.Trust` data model for access control on registrations.

**Action Plan**:

1. **Add Python wrapper classes** in `message/request.py`:
   - `RegisterRequest`: wraps `Register` — `allow_partial` + list of `RegistrationPath` (path strings)
   - `DeregisterRequest`: wraps `Deregister` — list of path strings

2. **Add response wrapper classes** in `message/response.py`:
   - `RegisterResponse`: exposes `registered_path_results` (success/failure per path)
   - `DeregisterResponse`: exposes `deregistered_path_results`

3. **Implement `on_register_request()` in `agent/base_agent.py`**:
   - Validate each path is a valid data model path (not already registered by another USP Service)
   - Store registered paths in a runtime table (e.g., `database/runtime/usp-services.json`)
   - Check `USPServices.Trust` table for access control (v1.5 requirement — see TODO-031)
   - Return `RegisterResp` with per-path success/failure (USP error 7800–7804 for registration errors)

4. **Implement `on_deregister_request()` in `agent/base_agent.py`**:
   - Remove paths from the runtime registration table
   - Return `DeregisterResp`

5. **Add `USPServices.Trust` data model stub** to `database/` (v1.5 requirement):
   ```json
   {
     "Device.USPServices.USPService.{i}.": {},
     "Device.USPServices.Trust.{i}.": {}
   }
   ```

6. **Update dispatch** in `agent/request_handler.py`.

7. **Write tests**:
   - `tests/test_register_deregister.py`: happy path, duplicate path conflict, deregister non-existent path, access control denial

**Estimated Effort**: 12–16 hours  
**Dependencies**: TODO-024 (agent_db patterns), TODO-028 (v1.5 version context)  
**Risk**: Medium — registration state touches authorization model

---

## USP v1.5 Upgrade Path

USP v1.5 (TR-369 Amendment 5) was published January 2026. The codebase was just upgraded to v1.4.2; v1.5 is a focused amendment with one proto-level schema change and several behavioral requirements. See the full analysis from the upgrade evaluation session.

---

### 🔴 TODO-028: Upgrade Proto Schema to v1.5 + Fix Version Strings
**Priority**: CRITICAL  
**Location**: `schema/`, `message/usp_record_pb2.py`, `message/usp_msg_pb2.py`, 9 source files  
**Spec Reference**: TR-369a5 (January 2026)

**Schema change** — `usp-record-1-5.proto` adds two new fields to `Record`:
```proto
// New in v1.5:
string originator_id = 14;   // R-MTP.4c/4d: original sender in forwarded messages
string destination_id = 15;  // R-MTP.4e: target endpoint for Notify messages
```
`usp-msg-1-5.proto` is **identical** to v1.4 — no message body changes. Both new fields are optional in proto3 (default empty string), so the change is fully backward-compatible.

**Action Plan**:

1. **Download updated proto files**:
   ```bash
   # From BroadbandForum/usp GitHub, tag v1.5 (or master)
   curl -o schema/usp-msg-1-5.proto \
     https://raw.githubusercontent.com/BroadbandForum/usp/master/specification/usp-msg-1-5.proto
   curl -o schema/usp-record-1-5.proto \
     https://raw.githubusercontent.com/BroadbandForum/usp/master/specification/usp-record-1-5.proto
   ```

2. **Regenerate protobuf Python files**:
   ```bash
   python -m grpc_tools.protoc -I schema/ \
     --python_out=message/ schema/usp-msg-1-5.proto schema/usp-record-1-5.proto
   # Rename output to usp_msg_pb2.py / usp_record_pb2.py
   # OR keep both versions and alias the v1.5 names
   ```

3. **Fix `record.version` in all 9 files** (currently `"1.0"` or `"1.4"`):

   | File | Fix |
   |---|---|
   | `mtp/usp_binding.py` | `"1.4"` → `"1.5"` |
   | `agent/request_handler.py` | `"1.0"` → `"1.5"` |
   | `agent/notify.py` | `"1.0"` → `"1.5"` |
   | `controller/controller.py` | `"1.0"` → `"1.5"` |
   | `controller/response_handler.py` | `"1.0"` → `"1.5"` |
   | `message/message.py` | `"1.0"` → `"1.5"` |
   | `message/__init__.py` | `"1.0"` → `"1.5"` |
   | `agent/uds_agent_old.py` | `"1.0"` → `"1.5"` |
   | `test_websocket_usp.py` | `"1.3"` → `"1.5"` |
   | `test_reboot.py` | `"1.0"` → `"1.5"` |

   Ideally centralise this in a single constant:
   ```python
   # message/version.py
   USP_VERSION = "1.5"
   ```
   Then all Record construction imports and uses `USP_VERSION`.

4. **Update `GetSupportedProtocol` version string** (TODO-026) to advertise `"1.5"`.

5. **Run full test suite** — proto3 backward compatibility means existing tests should pass.

**Estimated Effort**: 2–3 hours  
**Dependencies**: None — proto3 backward compatible  
**Risk**: Low

---

### 🔴 TODO-029: Implement originator_id / destination_id on Record
**Priority**: HIGH  
**Location**: `agent/notify.py`, `mtp/usp_binding.py`, `agent/bridge_agent.py`, `uspbridge/`  
**Spec Reference**: TR-369a5 R-MTP.4c, R-MTP.4d, R-MTP.4e

**What the spec requires**:
- **R-MTP.4c/4d** (`originator_id`): When a broker, proxy, or trusted broker **forwards** a USP Record, it MUST copy the original `from_id` into `originator_id` before replacing `from_id` with its own endpoint ID. For direct agent↔controller links (no proxy), the field is optional/empty.
- **R-MTP.4e** (`destination_id`): On **Notify** messages directed at a specific controller (subscription-based — not broadcast), the sender MUST populate `destination_id` with the target controller's endpoint ID.

**Action Plan**:

1. **`destination_id` on outbound Notify records** (`agent/notify.py`):
   - `BootNotification`, `ValueChangeNotification`, `PeriodicNotification` all construct a `Record` directly
   - Each already knows the target controller's endpoint ID (from the subscription or controller config)
   - Add: `record.destination_id = controller_endpoint_id` before sending
   - `mtp/usp_binding.py` `serialize_message()` should accept an optional `destination_id` kwarg

2. **`originator_id` in bridge/proxy forwarding** (`agent/bridge_agent.py`, `uspbridge/`):
   - When forwarding, before overwriting `record.from_id`, save it to `record.originator_id`
   - Audit `uspbridge/` for all forwarding code paths

3. **Receiver-side validation** (`mtp/usp_binding.py` `deserialize_bytes()`):
   - Log `originator_id` if present (for debugging proxy chains)
   - Do not reject records with empty `originator_id` (optional field)

4. **Write tests**:
   - `tests/test_v15_record_fields.py`: verify `destination_id` is set on notify records; verify `originator_id` is preserved through bridge forwarding

**Estimated Effort**: 4–6 hours  
**Dependencies**: TODO-028 (need v1.5 proto with new fields regenerated first)  
**Risk**: Low for direct peers; Medium for bridge paths (need to audit all forwarding)

---

### 🟡 TODO-030: UDS Password Authentication Frame (v1.5)
**Priority**: MEDIUM  
**Location**: `mtp/uds.py`, `mtp/uds_binding.py`, `cfg/agent.json`  
**Spec Reference**: TR-369a5 §4.6 (UDS MTP — new auth frame type)

**What changed**: v1.5 defines a new UDS **handshake frame variant** that carries a password for mutual authentication. The current implementation (`mtp/uds.py`) only supports the v1.4 4-byte length-prefix framing. Agents that don't configure a password can still operate (password is optional), but the framing parser must not reject the new frame type.

**Action Plan**:

1. **Extend `UdsTransport` framing in `mtp/uds.py`**:
   - During the UDS handshake, detect whether the peer sends the v1.4 connect record or the v1.5 auth frame
   - If the auth frame is received, extract the password field and validate against configured value
   - If no password is configured, accept any (or no) password

2. **Add password support to `mtp/uds_binding.py`**:
   ```python
   class UdsUspBinding(UspBinding):
       def __init__(self, endpoint_id, socket_path, mode='listen',
                    *, framing='length-prefix', password=None):
           ...
           self._password = password
   ```

3. **Add UDS password to agent config**:
   ```json
   // cfg/agent.json  (new optional field)
   {
     "uds.password": null
   }
   ```

4. **Write tests**: verify handshake with and without password, verify wrong password is rejected.

**Estimated Effort**: 4–8 hours  
**Dependencies**: TODO-028  
**Risk**: Low (backward compatible; password is optional)

---

### 🟡 TODO-031: SET allow_partial + Search Path Behavior (v1.5)
**Priority**: MEDIUM  
**Location**: `agent/request_handler.py`, `agent/base_agent.py`  
**Spec Reference**: TR-369a5 R-SET.2a

**What changed**: v1.5 explicitly clarifies that when a SET targets a **Search Path** (e.g., `Device.WiFi.Radio.[Enable==true].Channel`), `allow_partial` governs failure handling **per matched instance**, not per the whole request:
- `allow_partial=true`: update all instances that succeed; return `OperationFailure` only for those that fail
- `allow_partial=false`: if **any** instance fails, the entire search path update fails (but other unrelated `update_objs` in the same Set message still follow their own `allow_partial` logic)

**Action Plan**:

1. **Audit `on_set_request()` in `agent/base_agent.py`** and the legacy `agent/request_handler.py`:
   - Confirm Search Path resolution currently works (`agent_db.find_params()` regex matching)
   - Check whether `allow_partial` is honored when the resolved path is a Search Path (wildcard or expression)

2. **Fix set handler** if it doesn't correctly distinguish between:
   - A direct path (one instance): any failure is a simple per-param error
   - A Search Path (multiple instances): failures per instance, governed by `allow_partial`

3. **Write tests** in `tests/test_set_search_path.py`:
   - `test_set_search_path_allow_partial_true()`: some instances fail, others succeed
   - `test_set_search_path_allow_partial_false()`: one failure causes all to fail
   - `test_set_direct_path_unaffected()`: direct path still works as before

**Estimated Effort**: 3–6 hours  
**Dependencies**: TODO-028  
**Risk**: Low

---

## Testing & Quality

### 🟡 TODO-015: Expand Test Coverage
**Priority**: MEDIUM  
**Current**: Unknown coverage, limited tests  
**Goal**: >80% coverage

**Action Plan**:

1. **Measure Current Coverage**:
   ```bash
   make test-verbose
   coverage report
   coverage html
   open htmlcov/index.html
   ```

2. **Add Missing Tests**:
   ```python
   # tests/test_stomp_binding.py (NEW)
   def test_stomp_connection():
   def test_stomp_send():
   def test_stomp_receive():
   def test_stomp_error_handling():
   
   # tests/test_coap_binding.py (NEW)
   def test_coap_server_start():
   def test_coap_resource_registration():
   def test_coap_request_handling():
   
   # tests/test_notifications.py (NEW)
   def test_value_change_notification():
   def test_boot_notification():
   def test_periodic_notification():
   
   # tests/test_subscriptions.py (NEW)
   def test_add_subscription():
   def test_remove_subscription():
   def test_subscription_persistence():
   ```

3. **Integration Tests**:
   ```python
   # tests/integration/test_end_to_end.py (NEW)
   def test_get_request_flow():
       # Start agent
       # Send USP Get request
       # Verify response
   
   def test_set_request_flow():
       # Start agent
       # Send USP Set request
       # Verify database updated
   ```

4. **Setup CI/CD**:
   ```yaml
   # .github/workflows/test.yml
   name: Tests
   on: [push, pull_request]
   jobs:
     test:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v3
         - uses: actions/setup-python@v4
           with:
             python-version: '3.11'
         - run: make init
         - run: make test
         - run: coverage report --fail-under=80
   ```

**Estimated Effort**: 30-40 hours  
**Dependencies**: TODO-002  
**Risk**: Low

---

### 🟢 TODO-016: Add Linting & Formatting
**Priority**: LOW  
**Current**: Uses pylint, no formatter

**Action Plan**:

1. **Add Black (formatter)**:
   ```bash
   pip install black
   black --line-length 100 agent/ mtp/ message/ controller/
   ```

2. **Add isort (import sorting)**:
   ```bash
   pip install isort
   isort agent/ mtp/ message/ controller/
   ```

3. **Add mypy (type checking)**:
   ```bash
   pip install mypy
   mypy --strict agent/
   ```

4. **Pre-commit Hooks**:
   ```yaml
   # .pre-commit-config.yaml
   repos:
     - repo: https://github.com/psf/black
       rev: 23.12.1
       hooks:
         - id: black
     - repo: https://github.com/pycqa/isort
       rev: 5.13.2
       hooks:
         - id: isort
     - repo: https://github.com/pre-commit/mirrors-mypy
       rev: v1.8.0
       hooks:
         - id: mypy
   ```

**Estimated Effort**: 4-6 hours  
**Dependencies**: None  
**Risk**: Very Low

---

## Documentation

### 🟢 TODO-017: API Documentation
**Priority**: LOW  
**Goal**: Complete API docs using Sphinx

**Action Plan**:

1. **Setup Sphinx**:
   ```bash
   pip install sphinx sphinx-rtd-theme
   mkdir docs
   cd docs
   sphinx-quickstart
   ```

2. **Add Docstrings**:
   ```python
   def handle_get_request(self, msg: Message) -> GetResp:
       """
       Handle USP Get request.
       
       Args:
           msg: USP message containing Get request
           
       Returns:
           GetResp: Response message with requested parameter values
           
       Raises:
           ValueError: If message format is invalid
           
       Example:
           >>> handler.handle_get_request(get_msg)
           <GetResp with 5 parameters>
       """
   ```

3. **Generate Docs**:
   ```bash
   cd docs
   sphinx-apidoc -o source/ ../agent
   make html
   ```

**Estimated Effort**: 16-20 hours  
**Dependencies**: None  
**Risk**: Very Low

---

### 🟢 TODO-018: Architecture Documentation
**Priority**: LOW  
**Goal**: Comprehensive architecture docs

**Action Plan**:

1. **Create Diagrams**:
   - Component diagram (agents, controllers, MTP)
   - Sequence diagram (request/response flow)
   - Class diagram (main classes)
   - Deployment diagram (Docker, network)

2. **Documentation Sections**:
   - Architecture Overview
   - Protocol Flow
   - Data Model Structure
   - Extension Guide
   - Deployment Guide
   - Troubleshooting Guide

**Estimated Effort**: 12-16 hours  
**Dependencies**: None  
**Risk**: Very Low

---

## Long-term Improvements

### ~~🟢 TODO-019: Evaluate Modern USP Specs~~ ✅ COMPLETED
**Priority**: ~~LOW~~ DONE  
**Current**: ~~Based on WT-369 draft from June 2017~~ Updated to TR-369 v1.4.2  
**Goal**: ~~Update to latest TR-369 specification~~ ACHIEVED

**Action Plan**:

1. **Review Spec Changes**:
   - Download latest TR-369 from Broadband Forum
   - Identify protocol changes
   - List new features (MQTT MTP, WebSocket, etc.)

2. **Update Protocol Buffers**:
   - Get latest .proto files
   - Regenerate Python code
   - Update message handlers

3. **Add New Features**:
   - MQTT MTP support
   - WebSocket MTP support
   - Bulk data collection
   - Software module management

**Estimated Effort**: 80-120 hours  
**Dependencies**: All other TODOs  
**Risk**: High (major version upgrade)

---

### � TODO-022: Modernize CoAP and STOMP Agents
**Priority**: MEDIUM  
**Status**: Planned  
**Goal**: Refactor CoAP and STOMP agents to use modern async BaseAgent architecture

**Background**:
- Current `coap_agent.py` and `stomp_agent.py` use old threading-based `AbstractAgent`
- New `uds_agent.py` uses modern async/await `BaseAgent` with:
  - `_periodic_tasks` list for tracking background asyncio tasks
  - `_subscription_handlers` dict for managing active subscriptions
  - `_init_subscriptions()` async method for subscription initialization
  - `_perform_reboot()` method that cleanly restarts agent state
- CoAP/STOMP agents lack these standardized patterns, making Device.Reboot() and other lifecycle operations inconsistent

**Current State**:
- **CoAP Agent** (`agent/coap_agent.py`):
  - Extends `abstract_agent.AbstractAgent` (threading-based)
  - Uses `CoapPeriodicNotifHandler(threading.Thread)`
  - Uses `CoapValueChangeNotifPoller(threading.Thread)`
  - Calls `init_subscriptions()` (old API, not async)
  - No `_periodic_tasks`, `_subscription_handlers`, or `_init_subscriptions()`

- **STOMP Agent** (`agent/stomp_agent.py`):
  - Extends `abstract_agent.AbstractAgent` (threading-based)
  - Uses `StompPeriodicNotifHandler(threading.Thread)`
  - Uses `StompValueChangeNotifPoller(threading.Thread)`
  - Multiple bindings via `_binding_dict`
  - Calls `init_subscriptions()` (old API, not async)
  - No modern async patterns

**Action Plan**:

1. **Create New Async Implementations**:
   - Create `agent/coap_agent_async.py` extending `BaseAgent`
   - Create `agent/stomp_agent_async.py` extending `BaseAgent`
   - Follow UdsAgent pattern as reference implementation

2. **Implement Required Methods**:
   ```python
   # Both agents must implement:
   async def on_get_request(self, request)
   async def on_set_request(self, request)
   async def on_operate_request(self, request)
   async def on_get_supported_dm_request(self, request)
   async def on_get_instances_request(self, request)
   async def _send_bytes(self, data, writer)
   async def _send_notification_bytes(self, data, dest_info)
   async def _init_subscriptions(self)
   ```

3. **Add Standard Attributes**:
   ```python
   self._periodic_tasks = []  # List of asyncio.Task objects
   self._subscription_handlers = {}  # Dict tracking subscriptions
   ```

4. **Convert Threading to Asyncio**:
   - Replace `threading.Thread` with `asyncio.Task`
   - Replace `threading.Lock` with `asyncio.Lock`
   - Convert blocking I/O to async/await
   - Use `asyncio.create_task()` for background tasks
   - Use `asyncio.gather()` for concurrent operations

5. **Implement Device.Reboot()**:
   ```python
   async def _perform_reboot(self):
       """Restart agent with fresh subscription handlers"""
       # Cancel all periodic tasks
       for task in self._periodic_tasks:
           task.cancel()
       await asyncio.gather(*self._periodic_tasks, return_exceptions=True)
       
       # Clear handlers
       self._periodic_tasks.clear()
       self._subscription_handlers.clear()
       
       # Re-initialize subscriptions
       await self._init_subscriptions()
   ```

6. **Update Bindings**:
   - Modify `mtp/coap_usp_binding.py` for async operation
   - Modify `mtp/stomp_usp_binding.py` for async operation
   - Ensure compatibility with asyncio event loop

7. **Testing**:
   - Port existing tests to async equivalents
   - Add Device.Reboot() tests (similar to test_reboot.py)
   - Verify Boot! and Periodic! notifications work
   - Test subscription lifecycle management

8. **Migration Strategy**:
   - Keep old agents for backward compatibility initially
   - Add `--async` flag to `agent/main.py` for opt-in
   - Document migration path for users
   - Deprecate old agents in future release

**Dependencies**:
- Modern BaseAgent architecture (✅ exists in base_agent.py)
- UdsAgent reference implementation (✅ complete)
- Async MTP bindings (⬜ need updates)

**Benefits**:
- Consistent agent architecture across all MTPs
- Standard Device.Reboot() implementation
- Better resource management (asyncio vs threading)
- Easier to add new lifecycle operations
- Simplified subscription management

**Estimated Effort**: 40-60 hours  
- CoAP async implementation: 20-30 hours
- STOMP async implementation: 20-30 hours
- Testing and validation: 10-15 hours

**Risk**: Medium (significant refactoring, backward compatibility concerns)

---

### 🟢 TODO-023: Performance Optimization
**Priority**: LOW  
**Goal**: Improve throughput and latency

**Action Plan**:

1. **Profile Application**:
   ```bash
   python -m cProfile -o profile.stats agent/main.py
   python -m pstats profile.stats
   ```

2. **Optimize Hot Paths**:
   - Message parsing/serialization
   - Database lookups
   - Path resolution

3. **Add Caching**:
   - Parameter value cache
   - Path resolution cache
   - Data model cache

4. **Async Improvements**:
   - Convert blocking I/O to async
   - Use asyncio event loop
   - Concurrent request processing

**Estimated Effort**: 40-60 hours  
**Dependencies**: TODO-013, TODO-022  
**Risk**: Medium

---

## Summary & Priorities

### Sprint 1 — USP Protocol Foundation (Now)
1. ⬜ **TODO-028**: Upgrade proto schema to v1.5 + fix all version strings *(2–3 hrs)*
2. ⬜ **TODO-024**: Implement Add & Delete message handlers *(12–16 hrs)*
3. ⬜ **TODO-025**: Implement Notify (inbound) & NotifyResp handlers *(6–8 hrs)*
4. ⬜ **TODO-026**: Implement GetSupportedProtocol handler *(2–4 hrs)*

### Sprint 2 — USP v1.5 Behavioral + Register/Deregister (Next 2 Weeks)
5. ⬜ **TODO-029**: Implement originator_id / destination_id on Record *(4–6 hrs)*
6. ⬜ **TODO-027**: Implement Register & Deregister handlers + USPServices.Trust stub *(12–16 hrs)*
7. ⬜ **TODO-031**: SET allow_partial + Search Path behavior fix *(3–6 hrs)*
8. ✅ **TODO-022**: Fix CoAP `asyncio.coroutine` — **COMPLETED** *(March 19, 2026)*

### Sprint 3 — Security & Infrastructure (Next Month)
9. ⬜ **TODO-030**: UDS password authentication frame (v1.5) *(4–8 hrs)*
11. ⬜ **TODO-003**: CoAP payload validation *(8–12 hrs)*
12. ⬜ **TODO-004**: STOMP payload validation *(6–8 hrs)*
13. ⬜ **TODO-007**: Immutable parameter protection *(6–8 hrs)*

### Medium-term (Next Quarter)
14. ⬜ **TODO-001**: Docker base image upgrade *(4–8 hrs)*
15. ⬜ **TODO-005**: Thread shutdown *(4–6 hrs)*
16. ⬜ **TODO-006**: Shutdown coordination *(4–6 hrs)*
17. ⬜ **TODO-022-async**: CoAP and STOMP async modernization *(40–60 hrs)*
18. ⬜ **TODO-014**: Container improvements *(6–8 hrs)*
18. ⬜ **TODO-008**: Plugin architecture *(12–16 hrs)*
19. ⬜ **TODO-013**: Python 3 type annotation modernization *(20–30 hrs)*
20. ⬜ **TODO-015**: Test coverage expansion *(30–40 hrs)*
21. ⬜ **TODO-017**: API documentation *(16–20 hrs)*

### Long-term (6+ Months)
22. ✅ **TODO-019**: USP spec update — **COMPLETED (TR-369 v1.4.2)**
23. ⬜ **TODO-023**: Performance optimization *(40–60 hrs)*

### Low Priority (As Needed)
24. ⬜ **TODO-009**: File cleanup *(3–4 hrs)*
25. ⬜ **TODO-010**: Better ID handling *(4–6 hrs)*
26. ✅ **TODO-011**: Notification list — **COMPLETED**
27. ⬜ **TODO-012**: Message binding *(2–4 hrs)*
28. ⬜ **TODO-016**: Linting/formatting *(4–6 hrs)*
29. ⬜ **TODO-018**: Architecture docs *(12–16 hrs)*

---

## Estimated Total Effort

| Category | Items | Estimate |
|---|---|---|
| **USP v1.5 upgrade** (TODO-028–031) | 4 items | 13–23 hours |
| **Missing message handlers** (TODO-024–027) | 4 items | 32–44 hours |
| **Security & Infrastructure** (TODO-001, 003, 004, 007) | 4 items | 24–36 hours |
| **Code quality / async** (TODO-005, 006, 013, 022) | 4 items | 70–100 hours |
| **Testing** (TODO-015) | 1 item | 30–40 hours |
| **Low priority** (TODO-008–012, 014, 016–018, 023) | 9 items | 117–174 hours |

**Total open work**: ~286–417 hours

**Sprint 1+2 focus** (USP v1.5 + missing handlers): **~45–67 hours** of targeted protocol work to achieve full TR-369 v1.5 conformance.

---

## Notes
- Some TODOs can be parallelized
- Testing should accompany all changes
- Consider creating branches per TODO
- Update this document as items are completed
