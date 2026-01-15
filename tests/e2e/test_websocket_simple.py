"""
Simplified E2E tests for WebSocket MTP

Tests basic WebSocket communication without full agent startup
"""

import asyncio
import pytest
import pytest_asyncio
import websockets
from message import usp_msg_pb2, usp_record_pb2
from mtp.websocket_binding import WebSocketUspBinding


@pytest_asyncio.fixture
async def ws_server():
    """Start a simple WebSocket server"""
    received = []
    
    async def handler(websocket):
        async for message in websocket:
            received.append(message)
            # Echo back
            await websocket.send(message)
    
    server = await websockets.serve(handler, 'localhost', 9090)
    
    yield {
        'server': server,
        'received': received,
        'url': 'ws://localhost:9090/usp'
    }
    
    server.close()
    await server.wait_closed()


@pytest.mark.asyncio
async def test_websocket_client_connect(ws_server):
    """Test: WebSocket client can connect to server"""
    binding = WebSocketUspBinding('ops::test-agent')
    
    # Connect as client
    await binding.connect('ws://localhost:9090/usp')
    
    assert binding.client_websocket is not None
    
    # Close websocket
    await binding.client_websocket.close()


@pytest.mark.asyncio  
async def test_websocket_send_receive(ws_server):
    """Test: Can send and receive USP messages"""
    binding = WebSocketUspBinding('ops::test-agent')
    await binding.connect('ws://localhost:9090/usp')
    
    # Create simple USP message with proper Get body
    msg = usp_msg_pb2.Msg()
    msg.header.msg_id = "test-123"
    msg.header.msg_type = usp_msg_pb2.Header.GET
    
    # Add Get request body
    get_req = msg.body.request.get
    get_req.param_paths.append("Device.LocalAgent.EndpointID")
    
    record = usp_record_pb2.Record()
    record.version = "1.3"
    record.to_id = "proto::controller"
    record.from_id = "ops::test-agent"
    record.no_session_context.payload = msg.SerializeToString()
    
    # Send
    await binding.client_websocket.send(record.SerializeToString())
    
    # Wait a bit
    await asyncio.sleep(0.2)
    
    # Check server received it
    assert len(ws_server['received']) > 0
    
    # Close
    await binding.client_websocket.close()


@pytest.mark.asyncio
async def test_websocket_binding_serialize():
    """Test: WebSocketUspBinding serializes messages correctly"""
    from message.response import GetResponse
    
    binding = WebSocketUspBinding('ops::test-agent')
    
    response = GetResponse(
        msg_id='test-resp',
        results={'Device.LocalAgent.EndpointID': 'ops::test-agent'}
    )
    response.from_id = 'ops::test-agent'
    response.to_id = 'proto::controller'
    
    # Serialize
    data = binding.serialize_message(response, 'proto::controller')
    
    # Should be valid bytes
    assert isinstance(data, bytes)
    assert len(data) > 0
    
    # Should be valid Record
    record = usp_record_pb2.Record()
    record.ParseFromString(data)
    
    assert record.from_id == 'ops::test-agent'
    assert record.to_id == 'proto::controller'


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
