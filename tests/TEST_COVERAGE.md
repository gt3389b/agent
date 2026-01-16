# USP-WRP Bridge Test Coverage

## Summary

**Total Tests: 40** (all passing ✅)
- **Unit Tests:** 26 tests
- **Integration Tests:** 14 tests

## Unit Tests (`test_usp2wrp_bridge.py`)

### WRP Message Tests (4 tests)
- ✅ Create simple WRP message
- ✅ Encode/decode msgpack roundtrip
- ✅ Encode with all optional fields
- ✅ Handle invalid msgpack data

### Bridge Context Tests (4 tests)
- ✅ Create bridge context
- ✅ Generate structured transaction IDs (`{usp_msg_id}:{seq}:{controller_id}`)
- ✅ Convert context to WRP metadata
- ✅ Metadata generation without path

### USP → WRP Translation Tests (6 tests)
- ✅ **GetRequest** → WRP JSON-RPC `get`
- ✅ **SetRequest** → WRP JSON-RPC `set` (with data type inference)
- ✅ **OperateRequest** → WRP JSON-RPC direct method call
- ✅ **GetSupportedDMRequest** → WRP JSON-RPC `getAttributes`
- ✅ **GetInstancesRequest** → WRP JSON-RPC `getInstances`
- ✅ Transaction ID appears in JSON-RPC payload

### WRP → USP Translation Tests (5 tests)
- ✅ Parse **Get** response (operation type from metadata)
- ✅ Parse **Set** response (differentiated from operate)
- ✅ Parse **Operate** response (differentiated from get/set)
- ✅ Parse error responses
- ✅ Handle missing operation metadata

### Helper Method Tests (7 tests)
- ✅ Infer data type: string
- ✅ Infer data type: integer
- ✅ Infer data type: boolean
- ✅ Generate source endpoint (`mac:{MAC}/usp`)
- ✅ Generate destination endpoint (`mac:{MAC}/usp2wrp`)
- ✅ Extract context from WRP metadata
- ✅ Parse context from transaction ID

## Integration Tests (`test_usp2wrp_integration.py`)

### Mock Parodus Client
Complete simulation of WRP message transport:
- Msgpack encoding/decoding
- JSON-RPC request/response handling
- Transaction ID preservation
- Metadata echo-back
- Custom response handlers

### Get Request-Response Flow (2 tests)
- ✅ Complete Get request-response through Parodus
- ✅ Get with custom response data

### Set Request-Response Flow (2 tests)
- ✅ Complete Set request-response through Parodus
  - **CRITICAL:** Verifies `usp_operation="set"` preserved
- ✅ Set with automatic data type inference

### Operate Request-Response Flow (2 tests)
- ✅ Complete Operate request-response through Parodus
  - **CRITICAL:** Verifies `usp_operation="operate"` preserved
  - **CRITICAL:** Distinguishes from get/set (all use JSON-RPC methods)
- ✅ Operate with different command types

### GetSupportedDM Request-Response Flow (1 test)
- ✅ Complete GetSupportedDM request-response through Parodus

### GetInstances Request-Response Flow (1 test)
- ✅ Complete GetInstances request-response through Parodus

### Error Handling (2 tests)
- ✅ Handle WRP error responses
- ✅ Handle invalid WRP messages

### Context Preservation (3 tests)
- ✅ Transaction ID roundtrip preservation
- ✅ Metadata preservation through request-response
- ✅ Multiple sequential requests (sequence increment)

### Operation Type Differentiation (1 test)
- ✅ **CRITICAL TEST:** Verify get, set, and operate are correctly distinguished
  - All use JSON-RPC methods but have different `usp_operation` metadata
  - Metadata preserved through Parodus roundtrip
  - Correct operation type identified on response

## Critical Test Coverage

### Operation Type Differentiation ⚠️
The most critical aspect of the bridge is distinguishing between USP operations when they all translate to JSON-RPC methods:

| USP Operation | JSON-RPC Method | Metadata Field |
|---------------|----------------|----------------|
| GetRequest | `get` | `usp_operation="get"` |
| SetRequest | `set` | `usp_operation="set"` |
| OperateRequest | `Device.Reboot` (direct) | `usp_operation="operate"` + `usp_command` |
| GetSupportedDMRequest | `getAttributes` | `usp_operation="get_supported_dm"` |
| GetInstancesRequest | `getInstances` | `usp_operation="get_instances"` |

**Tests verify:**
- ✅ Metadata contains correct `usp_operation` for each request type
- ✅ Parodus client echoes metadata back in response
- ✅ Bridge correctly extracts operation type from response metadata
- ✅ Response parsing uses operation type to build correct USP response

### Primary USP Operations Covered
- ✅ **Get** - Query parameter values
- ✅ **Set** - Set parameter values (with data type inference)
- ✅ **Operate** - Execute commands (preserves full TR-181 path)
- ✅ **GetSupportedDM** - Query data model metadata
- ✅ **GetInstances** - Query object instances

### Context Preservation
- ✅ Structured transaction IDs: `{usp_msg_id}:{sequence}:{controller_id}`
- ✅ Metadata fields: `usp_msg_id`, `usp_operation`, `controller_endpoint`, `mtp_id`, `timestamp`
- ✅ Transaction ID roundtrip through Parodus
- ✅ Full metadata preservation

### Message Encoding
- ✅ WRP msgpack encoding/decoding
- ✅ JSON-RPC payload generation
- ✅ All required WRP fields
- ✅ All optional WRP fields
- ✅ Headers and metadata as `key=value` arrays

## Test Execution

Run all tests:
```bash
pytest tests/test_usp2wrp_bridge.py tests/test_usp2wrp_integration.py -v
```

Run unit tests only:
```bash
pytest tests/test_usp2wrp_bridge.py -v
```

Run integration tests only:
```bash
pytest tests/test_usp2wrp_integration.py -v
```

Run specific test:
```bash
pytest tests/test_usp2wrp_integration.py::test_operation_type_differentiation -v
```

## Next Steps

### TODO: Response Object Builders
- [ ] Update `from_wrp()` to return UspMessage response objects
- [ ] Implement `_build_get_response()` → GetResponse
- [ ] Implement `_build_set_response()` → SetResponse
- [ ] Implement `_build_operate_response()` → OperateResponse
- [ ] Implement `_build_get_supported_dm_response()` → GetSupportedDMResponse
- [ ] Implement `_build_get_instances_response()` → GetInstancesResponse

### TODO: Event Translation
- [ ] WRP SIMPLE_EVENT → USP Notify
- [ ] Handle `Boot!`, `ValueChange!`, `Periodic!` events
- [ ] Add event translation tests

### TODO: Transport Layer
- [ ] WRP nanomsg/UDS transport wrapper
- [ ] Parodus client integration
- [ ] Connection management tests

### TODO: WRPAgent Implementation
- [ ] Extend MultiMTPAgent for WRP transport
- [ ] Request routing and response handling
- [ ] End-to-end agent tests
