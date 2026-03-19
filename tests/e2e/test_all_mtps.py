"""
Parameterized E2E tests across all MTP types

Tests the same operations across WebSocket, CoAP, and UDS transports
to ensure consistent behavior regardless of MTP.
"""

import asyncio
import pytest
import pytest_asyncio
import websockets
from message import usp_msg_pb2, usp_record_pb2
from mtp.websocket_binding import WebSocketUspBinding
from mtp.uds_binding import UdsUspBinding
from mtp.uds import UdsTransport


# MTP configurations for testing
MTP_CONFIGS = [
    {
        'name': 'websocket',
        'port': 9090,
        'binding_class': WebSocketUspBinding,
        'enabled': True
    },
    {
        'name': 'uds',
        'socket_subpath': 'usp-test-mtp-all.sock',
        'binding_class': UdsUspBinding,
        'enabled': True
    },
    # TODO: Add CoAP once implemented
    # {
    #     'name': 'coap',
    #     'port': 5683,
    #     'binding_class': CoAPUspBinding,
    #     'enabled': False
    # },
]

# Filter to only enabled MTPs
ENABLED_MTPS = [m for m in MTP_CONFIGS if m.get('enabled', False)]


@pytest_asyncio.fixture(params=ENABLED_MTPS, ids=lambda m: m['name'])
async def mtp_server(request):
    """
    Parameterized fixture that creates a server for each MTP type
    
    Tests using this fixture will run once for each enabled MTP
    """
    mtp_config = request.param

    if mtp_config['name'] == 'websocket':
        # WebSocket server setup
        received = []

        async def handler(websocket):
            async for message in websocket:
                received.append(message)
                await websocket.send(message)  # Echo

        server = await websockets.serve(handler, 'localhost', mtp_config['port'])

        yield {
            'name': 'websocket',
            'config': mtp_config,
            'server': server,
            'received': received,
            'url': f"ws://localhost:{mtp_config['port']}/usp"
        }

        server.close()
        await server.wait_closed()

    elif mtp_config['name'] == 'uds':
        import tempfile, os
        received = []
        import uuid
        socket_path = f"/tmp/usp-mtp-all-{uuid.uuid4().hex[:8]}.sock"

        async def uds_echo_callback(data, writer):
            received.append(data)
            transport_ref['transport'].writer = writer
            await transport_ref['transport'].send_message(data, writer)

        transport_ref = {}
        server_transport = UdsTransport(socket_path, 'listen')
        transport_ref['transport'] = server_transport
        await server_transport.start_server(uds_echo_callback)

        yield {
            'name': 'uds',
            'config': mtp_config,
            'server': server_transport.server,
            'received': received,
            'socket_path': socket_path,
        }

        await server_transport.close()

    elif mtp_config['name'] == 'coap':
        # TODO: CoAP server setup
        pytest.skip("CoAP not yet implemented")


@pytest.mark.asyncio
async def test_mtp_client_connect(mtp_server):
    """Test: Client can connect to server (all MTPs)"""
    if mtp_server['name'] == 'websocket':
        config = mtp_server['config']
        binding = config['binding_class']('ops::test-agent')
        await binding.connect(mtp_server['url'])
        assert binding.client_websocket is not None
        await binding.client_websocket.close()

    elif mtp_server['name'] == 'uds':
        transport = UdsTransport(mtp_server['socket_path'], 'connect', endpoint_id='ops::test-agent')
        await transport.connect()
        assert transport.writer is not None
        await transport.close()


@pytest.mark.asyncio
async def test_mtp_send_receive(mtp_server):
    """Test: Can send and receive USP messages (all MTPs)"""
    if mtp_server['name'] == 'websocket':
        config = mtp_server['config']
        binding = config['binding_class']('ops::test-agent')
        await binding.connect(mtp_server['url'])

        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = "test-123"
        msg.header.msg_type = usp_msg_pb2.Header.GET
        msg.body.request.get.param_paths.append("Device.LocalAgent.EndpointID")

        record = usp_record_pb2.Record()
        record.version = "1.3"
        record.to_id = "proto::controller"
        record.from_id = "ops::test-agent"
        record.no_session_context.payload = msg.SerializeToString()

        await binding.client_websocket.send(record.SerializeToString())
        await asyncio.sleep(0.2)
        assert len(mtp_server['received']) > 0
        await binding.client_websocket.close()

    elif mtp_server['name'] == 'uds':
        transport = UdsTransport(mtp_server['socket_path'], 'connect', endpoint_id='ops::test-agent')
        await transport.connect()

        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = "test-uds-123"
        msg.header.msg_type = usp_msg_pb2.Header.GET
        msg.body.request.get.param_paths.append("Device.LocalAgent.EndpointID")

        record = usp_record_pb2.Record()
        record.version = "1.3"
        record.to_id = "proto::controller"
        record.from_id = "ops::test-agent"
        record.no_session_context.payload = msg.SerializeToString()

        await transport.send_message(record.SerializeToString())
        echo = await asyncio.wait_for(transport.receive_message(), timeout=2.0)
        assert echo is not None
        assert len(mtp_server['received']) > 0
        await transport.close()


@pytest.mark.asyncio
async def test_mtp_serialization(mtp_server):
    """Test: Message serialization works (all MTPs)"""
    from message.response import GetResponse

    # Serialization is MTP-independent; test via WebSocket binding only
    if mtp_server['name'] != 'websocket':
        pytest.skip("Serialization tested via WebSocket only")

    config = mtp_server['config']
    binding = config['binding_class']('ops::test-agent')

    response = GetResponse(
        msg_id='test-resp',
        results={'Device.LocalAgent.EndpointID': 'ops::test-agent'}
    )
    response.from_id = 'ops::test-agent'
    response.to_id = 'proto::controller'
    
    # Serialize
    data = binding.serialize_message(response, 'proto::controller')
    
    # Validate
    assert isinstance(data, bytes)
    assert len(data) > 0
    
    # Parse back
    record = usp_record_pb2.Record()
    record.ParseFromString(data)
    
    assert record.from_id == 'ops::test-agent'
    assert record.to_id == 'proto::controller'


@pytest.mark.asyncio
async def test_mtp_concurrent_messages(mtp_server):
    """Test: Can handle concurrent messages (all MTPs)"""
    if mtp_server['name'] == 'websocket':
        config = mtp_server['config']
        binding = config['binding_class']('ops::test-agent')
        await binding.connect(mtp_server['url'])

        async def send_message(i):
            msg = usp_msg_pb2.Msg()
            msg.header.msg_id = f"test-{i}"
            msg.header.msg_type = usp_msg_pb2.Header.GET
            msg.body.request.get.param_paths.append("Device.LocalAgent.EndpointID")
            record = usp_record_pb2.Record()
            record.version = "1.3"
            record.to_id = "proto::controller"
            record.from_id = "ops::test-agent"
            record.no_session_context.payload = msg.SerializeToString()
            await binding.client_websocket.send(record.SerializeToString())

        await asyncio.gather(*[send_message(i) for i in range(5)])
        await asyncio.sleep(0.3)
        assert len(mtp_server['received']) >= 5
        await binding.client_websocket.close()

    elif mtp_server['name'] == 'uds':
        # UDS requires sequential send-receive (half-duplex per standard)
        transport = UdsTransport(mtp_server['socket_path'], 'connect', endpoint_id='ops::test-agent')
        await transport.connect()

        n = 5
        for i in range(n):
            msg = usp_msg_pb2.Msg()
            msg.header.msg_id = f"uds-test-{i}"
            msg.header.msg_type = usp_msg_pb2.Header.GET
            msg.body.request.get.param_paths.append("Device.LocalAgent.EndpointID")
            record = usp_record_pb2.Record()
            record.version = "1.3"
            record.to_id = "proto::controller"
            record.from_id = "ops::test-agent"
            record.no_session_context.payload = msg.SerializeToString()
            await transport.send_message(record.SerializeToString())
            echo = await asyncio.wait_for(transport.receive_message(), timeout=2.0)
            assert echo is not None

        assert len(mtp_server['received']) >= n
        await transport.close()


# Summary test to show which MTPs are tested
def test_mtp_coverage_report():
    """Display which MTPs are being tested"""
    enabled = [m['name'] for m in ENABLED_MTPS]
    disabled = [m['name'] for m in MTP_CONFIGS if not m.get('enabled', False)]
    
    print(f"\n✅ Testing MTPs: {', '.join(enabled) if enabled else 'None'}")
    if disabled:
        print(f"⏸️  Disabled MTPs: {', '.join(disabled)}")
    
    assert len(enabled) > 0, "At least one MTP must be enabled for testing"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
