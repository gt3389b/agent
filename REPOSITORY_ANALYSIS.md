# Repository Analysis: pyagent-old

**Analysis Date**: January 14, 2026  
**Repository**: USP Agent Implementation (Legacy)

---

## Executive Summary

This is a **Python-based USP (User Services Platform) Agent** implementation following the Broadband Forum's TR-369 protocol specification. Originally developed for Comcast/ARRIS, this appears to be a legacy implementation as indicated by the `-old` suffix in the directory name.

The agent supports multiple device types (test, camera, motion) and can communicate via either STOMP or CoAP message transport protocols.

---

## Project Metadata

- **License**: MIT License (Copyright © 2016 John Blackford)
- **Protocol**: Broadband Forum WT-369 (USP - User Services Platform)
- **Primary Language**: Python 3
- **Status**: Legacy/deprecated implementation
- **Container**: Docker-based deployment

---

## Architecture Overview

### Core Modules

#### 1. Agent Module (`agent/`)
The main implementation containing:

| File | Purpose | Lines | Key Features |
|------|---------|-------|--------------|
| `abstract_agent.py` | Base agent class | 545 | Subscription management, threading, metrics |
| `stomp_agent.py` | STOMP binding | - | STOMP MTP implementation |
| `coap_agent.py` | CoAP binding | - | CoAP MTP implementation |
| `request_handler.py` | Request processor | - | Get, Set, Add, Delete, Operate commands |
| `notify.py` | Notification handler | - | Boot, ValueChange, Periodic events |
| `agent_db.py` | Database layer | - | Parameter storage & retrieval |
| `mdns.py` | Service discovery | - | mDNS advertisement |
| `camera.py` | Camera device | - | Image capture & streaming |
| `motion.py` | Motion sensor | - | Motion detection via GPIO |

#### 2. Message Module (`message/`)
Protocol Buffer based messaging:
- `usp_msg_pb2.py` - USP message definitions (generated from proto)
- `usp_record_pb2.py` - USP record definitions (generated from proto)
- `message.py` - Message utilities and helpers
- `utils.py` - Message processing utilities

#### 3. MTP Module (`mtp/`)
Message Transport Protocol abstractions:
- `coap.py` / `coap_usp_binding.py` - CoAP transport
- `uds.py` - **NEW** Unix Domain Socket transport (TR-369 v1.4)
- `generic_usp_binding.py` - Generic binding interface
- `direct.py` - Direct communication (testing)
- `log.py` - MTP logging

#### 4. Controller Module (`controller/`)
Controller/device manager implementation:
- `main.py` - Controller entry point
- `devicemanager.py` - Device management
- `response_handler.py` - Response processing
- `mdns.py` - Service discovery
- `utils.py` - Helper utilities

#### 5. Schema Module (`schema/`)
Protocol Buffer definitions:
- `usp-msg-1-4.proto` - USP message schema (TR-369 v1.4.2)
- `usp-record-1-4.proto` - USP record schema (TR-369 v1.4.2)
- `usp-msg.proto` / `usp-record.proto` - Legacy schemas (WT-369 Draft 1)

---

## Key Features

### Protocol Support
- ✅ **STOMP Binding** - STOMP 1.1/1.2 message transport
- ✅ **CoAP Binding** - Constrained Application Protocol transport
- ✅ **UDS Binding** - **NEW** Unix Domain Socket transport (TR-369 v1.4)
- ✅ **Protocol Buffers** - Efficient message serialization (protobuf v6.33.4)

### Device Types
Configurable via `-t` parameter:
- **test** - Generic test agent
- **camera** - Camera device with web UI
- **motion** - Motion detection sensor
- **uds** - **NEW** Unix Domain Socket-based agent

### USP Operations
- **Get** - Retrieve parameter values
- **Set** - Update parameter values
- **Add** - Create object instances
- **Delete** - Remove object instances
- **Operate** - Execute commands
- **Notify** - Event notifications (Boot, ValueChange, Periodic)

### Data Model (TR-369)
Hierarchical parameter structure:
```
Device.
├── DeviceInfo.
│   ├── Manufacturer
│   ├── SerialNumber
│   ├── ModelName
│   └── ...
└── LocalAgent.
    ├── EndpointID
    ├── SoftwareVersion
    ├── MTP.{i}.
    │   ├── Protocol
    │   ├── CoAP.Host
    │   ├── CoAP.Port
    │   └── STOMP.Destination
    ├── Controller.{i}.
    │   ├── EndpointID
    │   └── PeriodicNotifInterval
    └── Subscription.{i}.
        ├── ID
        └── ReferenceList
```

### Monitoring & Metrics
- **Prometheus Integration** (port 9001)
- Metrics tracked:
  - `incoming_request_processing_seconds` - Request latency
  - `number_of_proto_violations` - Protocol errors
  - `number_of_value_change_params` - Monitored parameters
  - `number_of_value_change_notifs` - Notifications sent

### Service Discovery
- **mDNS/Zeroconf** - Automatic service advertisement
- Service type broadcasting for agent discovery

---

## Dependencies

### Python Packages
```
asyncio                    # Async I/O
aiocoap==0.3              # CoAP implementation
bottle==0.12.9            # Web framework (camera UI)
stomp.py==4.1.11          # STOMP client
zeroconf==0.18.0          # mDNS/service discovery
protobuf                   # Protocol Buffers
prometheus-client==0.3.1   # Metrics
netifaces==0.10.5         # Network interface info
```

### Test Framework
```
nose2==0.6.5              # Test runner
nose2-cov==1.0a4          # Coverage plugin
coverage==4.2             # Code coverage
```

---

## Usage

### Running the Agent

**STOMP Binding (default):**
```bash
python3 -m agent.main -t test
```

**CoAP Binding:**
```bash
python3 -m agent.main -t test -c --coap-port 15683
```

**Camera Agent:**
```bash
python3 -m agent.main -t camera -c --coap-port 15683
```

**Command Line Options:**
```
-c, --coap              Use CoAP binding (default: STOMP)
--coap-port PORT        CoAP port (default: 5683)
--intf INTERFACE        Network interface to use
-t, --client-type TYPE  Device type: test, camera, motion
```

### Docker Deployment

**Build:**
```bash
docker build -t coap-usp-agent .
```

**Run:**
```bash
docker run -p 15683:15683/udp -itd coap-usp-agent
```

**Test:**
```bash
coap coap://localhost:15683/.well-known/core
```

### Development Commands

```bash
make init          # Install dependencies
make schema        # Generate protobuf files
make test          # Run tests with coverage
make test-verbose  # Verbose test output
make lint          # Run pylint
make run           # Run test agent (STOMP)
make runcoap       # Run test agent (CoAP)
make controller    # Run controller
```

---

## Configuration

### Agent Configuration (`cfg/agent.json`)
```json
{
  "gpio.pin": "4",
  "camera.image.dir": "pictures"
}
```

### Database Files (`database/`)
Each device type has two files:
- `{type}-dm.json` - Data model definition (parameters & permissions)
- `{type}-db.json` - Current parameter values

Example: `test-dm.json`, `test-db.json`

---

## Technical Debt & Issues

### High Priority

1. **Outdated Base Image**
   - Using Ubuntu 16.04 (EOL April 2021)
   - Security vulnerabilities likely present
   - **Recommendation**: Upgrade to Ubuntu 22.04 or Alpine

2. **Deprecated Dependencies**
   - Python 2/3 compatibility libraries still included
   - Old package versions (aiocoap 0.3, bottle 0.12.9)
   - **Recommendation**: Update to current versions

3. **Missing Payload Validation**
   - TODO in `coap_usp_binding.py:255`
   - Security risk for malformed messages
   - **Recommendation**: Implement schema validation

### Medium Priority

4. **Hard-coded Logic**
   - Camera logic hard-coded in `request_handler.py:430`
   - TODO: Make dynamic/pluggable
   - **Recommendation**: Use plugin architecture

5. **ID Handling**
   - TODO in `stomp_usp_binding.py:143`
   - Needs better message ID management
   - **Recommendation**: Use UUID or similar

6. **Thread Management**
   - TODO in `coap_usp_binding.py:282`
   - Cleanup of listening threads unclear
   - **Recommendation**: Proper shutdown handling

### Low Priority

7. **Test Coverage**
   - Tests exist but coverage unknown
   - Limited test files in `tests/`
   - **Recommendation**: Expand test suite

8. **Documentation**
   - Minimal README
   - No API documentation
   - **Recommendation**: Add comprehensive docs

---

## TODO Items Found

| Location | Issue | Priority |
|----------|-------|----------|
| `mtp/coap_usp_binding.py:255` | Implement payload validation | High |
| `mtp/coap_usp_binding.py:282` | Terminate listening thread | Medium |
| `agent/coap_usp_binding.py:255` | Implement payload validation | High |
| `agent/coap_usp_binding.py:282` | Terminate listening thread | Medium |
| `agent/abstract_agent.py:373` | Check shutdown with msg_handler | Medium |
| `agent/request_handler.py:335` | Prevent sets on immutable params | Medium |
| `agent/request_handler.py:430` | Make camera logic dynamic | Medium |
| `agent/camera.py:122` | File cleanup on deletion | Low |
| `agent/stomp_usp_binding.py:143` | Better ID handling | Medium |
| `agent/notify.py:94` | Replace hard-coded list | Low |
| `message/message.py:120` | Binding needed | Medium |

---

## Testing

### Test Structure
Located in `tests/`:
- `test_agent_db.py` - Database layer tests
- `test_config_mgr.py` - Configuration management tests
- `test_generic_usp_binding.py` - Generic binding tests
- `test_path_helper.py` - Path parsing tests
- `test_request_handler.py` - Request handler tests

### Running Tests
```bash
# Standard
make test

# Verbose
make test-verbose

# Manual
nose2 --with-coverage
```

---

## Project Structure Summary

```
pyagent-old/
├── agent/              # Main agent implementation
├── controller/         # Controller/device manager
├── message/           # Protocol Buffer messaging
├── mtp/               # Message transport protocols
├── database/          # Data model & parameter storage
├── schema/            # Protocol Buffer definitions
├── static/            # Web UI assets
├── views/             # Web UI templates
├── tests/             # Unit tests
├── bin/               # Entry point scripts
├── cfg/               # Configuration files
├── Dockerfile         # Container definition
├── Makefile          # Build automation
└── requirements.txt   # Python dependencies
```

---

## Recommendations

### Immediate Actions
1. ✅ **Document current state** (this document)
2. 🔴 **Upgrade Docker base image** to modern Ubuntu/Alpine
3. 🔴 **Update dependencies** to current versions
4. 🔴 **Implement payload validation** for security

### Short-term
5. 🟡 **Expand test coverage** to >80%
6. 🟡 **Refactor hard-coded logic** to be pluggable
7. 🟡 **Add API documentation** using Sphinx

### Long-term
8. 🟢 **Modernize to Python 3.10+** only
9. 🟢 **Evaluate newer USP specs** (post-2017)
10. 🟢 **Consider migration strategy** from legacy codebase

---

## Related Specifications

- **TR-369**: USP (User Services Platform) - Broadband Forum
- **WT-369**: Original working text for USP specification
- **STOMP**: Simple Text Oriented Messaging Protocol
- **CoAP**: RFC 7252 - Constrained Application Protocol
- **Protocol Buffers**: Google's serialization format

---

## Contact & Maintenance

This appears to be a legacy implementation that may have been superseded. The `-old` suffix suggests a newer version exists elsewhere in the codebase or organization.

**Original Author**: John Blackford  
**Copyright**: 2016  
**Organization**: ARRIS Enterprises / Comcast
