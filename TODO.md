# TODO List & Action Plan
**Project**: pyagent-old (USP Agent Implementation)  
**Last Updated**: January 14, 2026

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
4. [Testing & Quality](#testing--quality)
5. [Documentation](#documentation)
6. [Long-term Improvements](#long-term-improvements)

---

## Critical Security & Infrastructure

### 🔴 TODO-001: Upgrade Docker Base Image
**Priority**: CRITICAL  
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

### 🟢 TODO-011: Replace Hard-coded List (Notifications)
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

### 🟢 TODO-020: Performance Optimization
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
**Dependencies**: TODO-013  
**Risk**: Medium

---

## Summary & Priorities

### Immediate (Next 2 Weeks)
1. ⬜ TODO-001: Docker base image upgrade
2. ⬜ TODO-003: CoAP payload validation
3. ⬜ TODO-004: STOMP payload validation
4. ✅ TODO-002: Dependency updates - **COMPLETED**

### Short-term (Next Month)
5. ⬜ TODO-007: Immutable parameter protection
6. ⬜ TODO-005: Thread shutdown
7. ⬜ TODO-006: Shutdown coordination
8. ⬜ TODO-014: Container improvements

### Medium-term (Next Quarter)
9. ⬜ TODO-008: Plugin architecture
10. ⬜ TODO-013: Python 3 migration
11. ⬜ TODO-015: Test coverage expansion
12. ⬜ TODO-017: API documentation

### Long-term (6+ Months)
13. ✅ TODO-019: USP spec update - **COMPLETED (TR-369 v1.4.2)**
14. ⬜ TODO-020: Performance optimization

### Low Priority (As Needed)
15. ⬜ TODO-009: File cleanup
16. ⬜ TODO-010: Better ID handling
17. ⬜ TODO-011: Notification list
18. ⬜ TODO-012: Message binding
19. ⬜ TODO-016: Linting/formatting
20. ⬜ TODO-018: Architecture docs

---

## Estimated Total Effort
- **Critical**: 28-40 hours
- **High**: 14-20 hours  
- **Medium**: 76-104 hours
- **Low**: 45-62 hours
- **Long-term**: 120-180 hours

**Total**: 283-406 hours (~3-5 months of full-time work)

---

## Notes
- Some TODOs can be parallelized
- Testing should accompany all changes
- Consider creating branches per TODO
- Update this document as items are completed
