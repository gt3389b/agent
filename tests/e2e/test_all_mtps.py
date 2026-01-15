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


# MTP configurations for testing
MTP_CONFIGS = [
    {
        'name': 'websocket',
        'port': 9090,
        'binding_class': WebSocketUspBinding,
        'enabled': True
    },
    # TODO: Add CoAP once implemented
    # {
    #     'name': 'coap',
    #     'port': 5683,
    #     'binding_class': CoAPUspBinding,
    #     'enabled': False
    # },
    # TODO: Add UDS once implemented
    # {
    #     'name': 'uds',
    #     'socket_path': '/tmp/usp-agent.sock',
    #     'binding_class': UDSUspBinding,
    #     'enabled': False
    # }
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
        
    elif mtp_config['name'] == 'coap':
        # TODO: CoAP server setup
        pytest.skip("CoAP not yet implemented")
        
    elif mtp_config['name'] == 'uds':
        # TODO: UDS server setup
        pytest.skip("UDS not yet implemented")


@pytest.mark.asyncio
async def test_mtp_client_connect(mtp_server):
    """Test: Client can connect to server (all MTPs)"""
    config = mtp_server['config']
    binding = config['binding_class']('ops::test-agent')
    
    if mtp_server['name'] == 'websocket':
        await binding.connect(mtp_server['url'])
        assert binding.client_websocket is not None
        await binding.client_websocket.close()
    # Add elif for other MTPs when implemented


@pytest.mark.asyncio
async def test_mtp_send_receive(mtp_server):
    """Test: Can send and receive USP messages (all MTPs)"""
    config = mtp_server['config']
    binding = config['binding_class']('ops::test-agent')
    
    if mtp_server['name'] == 'websocket':
        await binding.connect(mtp_server['url'])
        
        # Create Get request
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = "test-123"
        msg.header.msg_type = usp_msg_pb2.Header.GET
        
        get_req = msg.body.request.get
        get_req.param_paths.append("Device.LocalAgent.EndpointID")
        
        record = usp_record_pb2.Record()
        record.version = "1.3"
        record.to_id = "proto::controller"
        record.from_id = "ops::test-agent"
        record.no_session_context.payload = msg.SerializeToString()
        
        # Send
        await binding.client_websocket.send(record.SerializeToString())
        await asyncio.sleep(0.2)
        
        # Verify received
        assert len(mtp_server['received']) > 0
        
        await binding.client_websocket.close()


@pytest.mark.asyncio
async def test_mtp_serialization(mtp_server):
    """Test: Message serialization works (all MTPs)"""
    from message.response import GetResponse
    
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
    config = mtp_server['config']
    binding = config['binding_class']('ops::test-agent')
    
    if mtp_server['name'] == 'websocket':
        await binding.connect(mtp_server['url'])
        
        # Send 5 concurrent messages
        async def send_message(i):
            msg = usp_msg_pb2.Msg()
            msg.header.msg_id = f"test-{i}"
            msg.header.msg_type = usp_msg_pb2.Header.GET
            
            get_req = msg.body.request.get
            get_req.param_paths.append("Device.LocalAgent.EndpointID")
            
            record = usp_record_pb2.Record()
            record.version = "1.3"
            record.to_id = "proto::controller"
            record.from_id = "ops::test-agent"
            record.no_session_context.payload = msg.SerializeToString()
            
            await binding.client_websocket.send(record.SerializeToString())
        
        # Send all concurrently
        await asyncio.gather(*[send_message(i) for i in range(5)])
        await asyncio.sleep(0.3)
        
        # Should have received all 5
        assert len(mtp_server['received']) >= 5
        
        await binding.client_websocket.close()


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
