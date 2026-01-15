# STOMP Support in Multi-MTP Controller

## Overview

The Multi-MTP Controller now supports three transport protocols:
- **UDS** (Unix Domain Sockets) - for local IPC
- **CoAP** (Constrained Application Protocol) - for UDP-based peer-to-peer
- **STOMP** (Simple Text Oriented Messaging Protocol) - for message broker-based communication

## Architecture

### STOMP Message Flow

1. **Controller Connection**: Controller connects to STOMP broker and subscribes to controller queue
2. **Agent Connection**: Agent connects to same broker and subscribes to agent queue
3. **Agent → Controller**: Agent sends messages (Boot!, Periodic!, etc.) to controller queue
4. **Controller → Agent**: Controller sends requests (GetSupportedDM, Set, etc.) to agent queue
5. **Async Responses**: Agent sends responses back to controller queue

### Key Differences from UDS/CoAP

- **Asynchronous**: STOMP is message-based, not request/response
- **Broker Required**: Needs RabbitMQ, ActiveMQ, or similar STOMP broker running
- **Queue-Based**: Messages routed via queues, not direct connections
- **Reply-To Pattern**: Messages include reply-to header for routing responses

## Configuration

### Enable STOMP in Controller

Edit `cfg/multi-controller.json`:

```json
{
  "endpoint_id": "proto::controller-01",
  "uds_socket_path": "/tmp/usp-controller.sock",
  "uds_mode": "listen",
  "coap_host": "localhost",
  "coap_port": 5683,
  "coap_path": "usp",
  "stomp_enabled": true,
  "stomp_host": "localhost",
  "stomp_port": 61613,
  "stomp_controller_queue": "/queue/usp-controller",
  "stomp_agent_queue": "/queue/usp-agent"
}
```

### STOMP Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `stomp_enabled` | `false` | Enable/disable STOMP transport |
| `stomp_host` | `localhost` | STOMP broker hostname |
| `stomp_port` | `61613` | STOMP broker port (default for STOMP 1.0) |
| `stomp_controller_queue` | `/queue/usp-controller` | Queue for controller to receive messages |
| `stomp_agent_queue` | `/queue/usp-agent` | Queue for agents to receive messages |

## Running with STOMP

### 1. Install STOMP Broker

Choose one:

**RabbitMQ** (recommended):
```bash
# macOS
brew install rabbitmq
rabbitmq-plugins enable rabbitmq_stomp
rabbitmq-server

# Linux
sudo apt-get install rabbitmq-server
sudo rabbitmq-plugins enable rabbitmq_stomp
sudo service rabbitmq-server start
```

**ActiveMQ**:
```bash
# macOS
brew install activemq
activemq start

# Linux - download from https://activemq.apache.org/
./bin/activemq start
```

### 2. Start Controller

```bash
python bin/controller.py -t multi -c cfg/multi-controller.json
```

Expected output:
```
============================================================
Multi-MTP Controller Initialized
  Endpoint ID: proto::controller-01
  UDS Socket: /tmp/usp-controller.sock (mode=listen)
  CoAP: localhost:5683/usp
  STOMP: localhost:61613
    Controller Queue: /queue/usp-controller
    Agent Queue: /queue/usp-agent
============================================================
Starting UDS listener on /tmp/usp-controller.sock
Starting CoAP listener on localhost:5683/usp
Starting STOMP listener on localhost:61613
✓ STOMP connected to localhost:61613
✓ STOMP subscribed to /queue/usp-controller
Controller waiting for agent messages on multiple MTPs...
```

### 3. Start STOMP Agent

When the async STOMP agent is created, it will:
1. Connect to STOMP broker
2. Subscribe to agent queue
3. Send Boot! notification to controller queue
4. Process requests from controller queue

## Implementation Details

### Controller Components

#### StompMessageListener
- Implements `stomp.ConnectionListener`
- Receives messages in sync context
- Queues messages for async processing via `asyncio.Queue`

#### _run_stomp_server()
- Connects to STOMP broker
- Subscribes to controller queue
- Processes messages from async queue

#### _handle_stomp_message()
- Parses USP Record from message body
- Tracks agent MTP type as 'stomp'
- Stores reply-to queue in agent tracking

#### _send_request_stomp()
- Sends requests to agent queue
- Includes reply-to header for responses
- Returns immediately (async messaging)

### Agent Tracking

Agents using STOMP are tracked with:
```python
{
    'mtp_type': 'stomp',
    'mtp_info': '/queue/agent-reply-queue',  # Reply-to queue
    'last_heartbeat': '2026-01-15T10:30:00',
    'metadata': {}
}
```

### Message Routing

Controller automatically routes requests to correct transport:
```python
if mtp_type == 'uds':
    await self._send_request_uds(...)
elif mtp_type == 'coap':
    await self._send_request_coap(...)
elif mtp_type == 'stomp':
    await self._send_request_stomp(...)  # New!
```

## Next Steps

### TODO: Create Async STOMP Agent

Following the same pattern as `coap_agent_async.py`:
- Inherit from `BaseAgent`
- Use `_periodic_tasks`, `_subscription_handlers`, `_init_subscriptions()`
- Connect to STOMP broker in `start()`
- Send notifications via STOMP queue

### Testing Checklist

- [ ] Install and start STOMP broker (RabbitMQ/ActiveMQ)
- [ ] Enable STOMP in controller config
- [ ] Create async STOMP agent
- [ ] Test Boot! notification
- [ ] Test GetSupportedDM request/response
- [ ] Test Set request/response
- [ ] Test Periodic! notifications
- [ ] Test Device.Reboot() with STOMP agent

## Troubleshooting

### Connection Refused
- Ensure STOMP broker is running: `telnet localhost 61613`
- Check broker logs for errors
- Verify broker has STOMP plugin enabled (RabbitMQ)

### Messages Not Received
- Check queue names match between agent and controller
- Verify broker has created queues (use broker admin UI)
- Enable debug logging: `logger.setLevel(logging.DEBUG)`

### Async Issues
- STOMP uses threads internally (stomp.py library)
- Messages queued via `asyncio.Queue` for async processing
- Use `call_soon_threadsafe()` to bridge sync/async contexts

## References

- [STOMP Protocol](https://stomp.github.io/)
- [stomp.py Documentation](https://github.com/jasonrbriggs/stomp.py)
- [RabbitMQ STOMP Plugin](https://www.rabbitmq.com/stomp.html)
- [ActiveMQ STOMP](https://activemq.apache.org/stomp)
