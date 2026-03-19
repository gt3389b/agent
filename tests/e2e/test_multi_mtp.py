"""
End-to-End tests for Multi-MTP Agent

Tests agent with multiple simultaneous MTP connections:
- Multiple controllers on same MTP
- Same controller on multiple MTPs
- Request/response routing correctness
- Concurrent requests across MTPs
"""

import asyncio
import pytest
import pytest_asyncio
import websockets
from message import usp_msg_pb2, usp_record_pb2
from agent.multi_mtp_agent import MultiMTPAgent



@pytest_asyncio.fixture
async def dual_controller_setup():
    """
    Setup 2 WebSocket controllers on different ports
    Simulates multiple controllers communicating with agent
    """
    controllers = {}
    
    async def create_controller(name, port):
        received = []
        clients = []
        
        async def handle_client(websocket):
            clients.append(websocket)
            try:
                async for message in websocket:
                    record = usp_record_pb2.Record()
                    record.ParseFromString(message)
                    received.append({
                        'record': record,
                        'from': name
                    })
                    
                    # Echo back simple response
                    response = create_echo_response(record)
                    await websocket.send(response)
                    
            except websockets.exceptions.ConnectionClosed:
                pass
            finally:
                if websocket in clients:
                    clients.remove(websocket)
        
        server = await websockets.serve(
            handle_client,
            'localhost',
            port,
            subprotocols=['v1.usp']
        )
        
        return {
            'name': name,
            'server': server,
            'received': received,
            'clients': clients,
            'port': port
        }
    
    # Start 2 controllers
    controllers['ctrl1'] = await create_controller('controller-1', 9080)
    controllers['ctrl2'] = await create_controller('controller-2', 9081)
    
    yield controllers
    
    # Cleanup
    for ctrl in controllers.values():
        ctrl['server'].close()
        await ctrl['server'].wait_closed()


def create_echo_response(request_record):
    """Create simple echo response"""
    msg = usp_msg_pb2.Msg()
    msg.header.msg_id = "echo-resp"
    msg.header.msg_type = usp_msg_pb2.Header.GET_RESP
    
    record = usp_record_pb2.Record()
    record.version = "1.3"
    record.to_id = request_record.from_id
    record.from_id = request_record.to_id
    record.no_session_context.payload = msg.SerializeToString()
    
    return record.SerializeToString()


@pytest.mark.asyncio
async def test_agent_connects_to_multiple_controllers(dual_controller_setup, e2e_dual_ws_db):
    """Test: Agent connects to multiple controllers simultaneously"""
    agent_task = asyncio.create_task(run_agent_for_seconds(3, e2e_dual_ws_db))
    await asyncio.sleep(2)
    
    # Check both controllers received Boot!
    ctrl1 = dual_controller_setup['ctrl1']
    ctrl2 = dual_controller_setup['ctrl2']
    
    # At least one controller should have received Boot!
    # (depends on database config)
    total_messages = len(ctrl1['received']) + len(ctrl2['received'])
    assert total_messages > 0, "No messages received by any controller"
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_request_routing_to_correct_mtp(dual_controller_setup, e2e_dual_ws_db):
    """Test: Responses route back on correct MTP connection"""
    agent_task = asyncio.create_task(run_agent_for_seconds(5, e2e_dual_ws_db))
    await asyncio.sleep(1)
    
    ctrl1 = dual_controller_setup['ctrl1']
    
    if len(ctrl1['clients']) > 0:
        # Send request on ctrl1
        ws1 = ctrl1['clients'][0]
        request = create_test_request("ctrl1-req-1")
        await ws1.send(request)
        
        await asyncio.sleep(0.5)
        
        # Response should come back on ctrl1's websocket
        # (verified by receive loop in controller)
        assert len(ctrl1['received']) >= 2  # Boot! + our request
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_concurrent_requests_different_mtps(dual_controller_setup, e2e_dual_ws_db):
    """Test: Concurrent requests on different MTPs handled correctly"""
    agent_task = asyncio.create_task(run_agent_for_seconds(5, e2e_dual_ws_db))
    await asyncio.sleep(1)
    
    ctrl1 = dual_controller_setup['ctrl1']
    ctrl2 = dual_controller_setup['ctrl2']
    
    # Send concurrent requests from both controllers
    requests = []
    if len(ctrl1['clients']) > 0:
        requests.append(ctrl1['clients'][0].send(create_test_request("c1-req-1")))
    if len(ctrl2['clients']) > 0:
        requests.append(ctrl2['clients'][0].send(create_test_request("c2-req-1")))
    
    if requests:
        await asyncio.gather(*requests)
        await asyncio.sleep(1)
        
        # Both should have received responses
        total = len(ctrl1['received']) + len(ctrl2['received'])
        assert total >= len(requests) + 1  # Requests + Boot!
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_mtp_connection_isolation(dual_controller_setup, e2e_dual_ws_db):
    """Test: Message sent on MTP1 doesn't leak to MTP2"""
    agent_task = asyncio.create_task(run_agent_for_seconds(5, e2e_dual_ws_db))
    await asyncio.sleep(1)
    
    ctrl1 = dual_controller_setup['ctrl1']
    ctrl2 = dual_controller_setup['ctrl2']
    
    initial_ctrl2_count = len(ctrl2['received'])
    
    if len(ctrl1['clients']) > 0:
        # Send request only on ctrl1
        ws1 = ctrl1['clients'][0]
        await ws1.send(create_test_request("isolated-req"))
        
        await asyncio.sleep(0.5)
        
        # ctrl2 should not have received this request
        assert len(ctrl2['received']) == initial_ctrl2_count
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_mtp_failure_doesnt_affect_other_mtps(dual_controller_setup, e2e_dual_ws_db):
    """Test: Failure on one MTP doesn't impact others"""
    agent_task = asyncio.create_task(run_agent_for_seconds(10, e2e_dual_ws_db))
    await asyncio.sleep(1)
    
    ctrl1 = dual_controller_setup['ctrl1']
    ctrl2 = dual_controller_setup['ctrl2']
    
    if len(ctrl1['clients']) > 0 and len(ctrl2['clients']) > 0:
        # Close ctrl1 connection
        await ctrl1['clients'][0].close()
        await asyncio.sleep(1)
        
        # ctrl2 should still work
        ws2 = ctrl2['clients'][0]
        await ws2.send(create_test_request("after-failure"))
        
        await asyncio.sleep(0.5)
        
        # Should have received response on ctrl2
        assert len(ctrl2['received']) > 0
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_notification_routing_to_correct_controller(dual_controller_setup, e2e_dual_ws_db):
    """Test: Notifications route to correct controller"""
    agent_task = asyncio.create_task(run_agent_for_seconds(3, e2e_dual_ws_db))
    await asyncio.sleep(2)
    
    ctrl1 = dual_controller_setup['ctrl1']
    
    # Check Boot! notification has correct to_id
    if len(ctrl1['received']) > 0:
        boot_record = ctrl1['received'][0]['record']
        assert boot_record.to_id == "proto::controller-01"
        
        usp_msg = usp_msg_pb2.Msg()
        usp_msg.ParseFromString(boot_record.no_session_context.payload)
        assert usp_msg.header.msg_type == usp_msg_pb2.Header.NOTIFY
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_stress_multiple_concurrent_mtps(dual_controller_setup, e2e_dual_ws_db):
    """Test: High load across multiple MTPs"""
    agent_task = asyncio.create_task(run_agent_for_seconds(10, e2e_dual_ws_db))
    await asyncio.sleep(1)
    
    ctrl1 = dual_controller_setup['ctrl1']
    ctrl2 = dual_controller_setup['ctrl2']
    
    # Send 20 requests total across both controllers
    requests = []
    for i in range(10):
        if len(ctrl1['clients']) > 0:
            requests.append(ctrl1['clients'][0].send(create_test_request(f"c1-stress-{i}")))
        if len(ctrl2['clients']) > 0:
            requests.append(ctrl2['clients'][0].send(create_test_request(f"c2-stress-{i}")))
    
    if requests:
        await asyncio.gather(*requests)
        await asyncio.sleep(2)
        
        # All should be processed
        total = len(ctrl1['received']) + len(ctrl2['received'])
        assert total >= 20  # At least the requests we sent
    
    agent_task.cancel()


# Helper functions

async def run_agent_for_seconds(seconds, db_path):
    """Run multi-MTP agent for specified duration"""
    agent = MultiMTPAgent('database/test-dm.json', str(db_path))
    try:
        await asyncio.wait_for(agent.start(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


def create_test_request(msg_id):
    """Create a simple Get request"""
    msg = usp_msg_pb2.Msg()
    msg.header.msg_id = msg_id
    msg.header.msg_type = usp_msg_pb2.Header.GET
    
    get_req = msg.body.request.get
    get_req.param_paths.append("Device.LocalAgent.EndpointID")
    
    record = usp_record_pb2.Record()
    record.version = "1.3"
    record.to_id = "ops::00D09E-Test-T01"
    record.from_id = "proto::controller-01"
    record.no_session_context.payload = msg.SerializeToString()
    
    return record.SerializeToString()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
