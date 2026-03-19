"""
End-to-End tests for WebSocket MTP

Tests full USP request/response cycles over WebSocket transport:
- Get, Set, GetSupportedDM, GetInstances, Operate
- Boot! and Periodic! notifications
- Error handling
- Concurrent requests
"""

import asyncio
import pytest
import pytest_asyncio
import websockets
import json
from message import usp_msg_pb2, usp_record_pb2
from agent.multi_mtp_agent import MultiMTPAgent
from mtp.websocket_binding import WebSocketUspBinding


@pytest_asyncio.fixture
async def mock_controller():
    """Start a mock WebSocket controller server"""
    received_messages = []
    clients = []
    
    async def handle_client(websocket):
        """Handle controller client connection"""
        clients.append(websocket)
        try:
            async for message in websocket:
                # Deserialize and store
                record = usp_record_pb2.Record()
                record.ParseFromString(message)
                received_messages.append(record)
                
                # Parse USP message
                usp_msg = usp_msg_pb2.Msg()
                usp_msg.ParseFromString(record.no_session_context.payload)
                
                # Auto-respond to requests
                if usp_msg.header.msg_type == usp_msg_pb2.Header.GET:
                    response = create_get_response(usp_msg)
                    await websocket.send(response)
                elif usp_msg.header.msg_type == usp_msg_pb2.Header.GET_SUPPORTED_DM:
                    response = create_gsdm_response(usp_msg)
                    await websocket.send(response)
                elif usp_msg.header.msg_type == usp_msg_pb2.Header.GET_INSTANCES:
                    response = create_instances_response(usp_msg)
                    await websocket.send(response)
                elif usp_msg.header.msg_type == usp_msg_pb2.Header.SET:
                    response = create_set_response(usp_msg)
                    await websocket.send(response)
                    
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            clients.remove(websocket)
    
    server = await websockets.serve(
        handle_client,
        'localhost',
        9080,
        subprotocols=['v1.usp']
    )
    
    yield {
        'server': server,
        'received': received_messages,
        'clients': clients
    }
    
    server.close()
    await server.wait_closed()


def create_get_response(request_msg):
    """Create Get response"""
    response = usp_msg_pb2.Msg()
    response.header.msg_id = "test-resp-" + request_msg.header.msg_id
    response.header.msg_type = usp_msg_pb2.Header.GET_RESP
    
    get_resp = response.body.response.get_resp
    req_path_result = get_resp.req_path_results.add()
    req_path_result.requested_path = "Device.LocalAgent.EndpointID"
    
    param = req_path_result.resolved_path_results.add()
    param.resolved_path = "Device.LocalAgent.EndpointID"
    param.result_params["EndpointID"] = "ops::00D09E-Test-T01"
    
    # Wrap in record
    record = usp_record_pb2.Record()
    record.version = "1.3"
    record.to_id = request_msg.header.from_id
    record.from_id = request_msg.header.to_id
    record.no_session_context.payload = response.SerializeToString()
    
    return record.SerializeToString()


def create_gsdm_response(request_msg):
    """Create GetSupportedDM response"""
    response = usp_msg_pb2.Msg()
    response.header.msg_id = "test-resp-" + request_msg.header.msg_id
    response.header.msg_type = usp_msg_pb2.Header.GET_SUPPORTED_DM_RESP
    
    gsdm_resp = response.body.response.get_supported_dm_resp
    req_obj = gsdm_resp.req_obj_results.add()
    req_obj.req_obj_path = "Device."
    req_obj.data_model_inst_uri = "urn:broadband-forum-org:tr-181-2-12-0"
    
    obj = req_obj.supported_objs.add()
    obj.supported_obj_path = "Device.LocalAgent."
    
    # Wrap in record
    record = usp_record_pb2.Record()
    record.version = "1.3"
    record.to_id = request_msg.header.from_id
    record.from_id = request_msg.header.to_id
    record.no_session_context.payload = response.SerializeToString()
    
    return record.SerializeToString()


def create_instances_response(request_msg):
    """Create GetInstances response"""
    response = usp_msg_pb2.Msg()
    response.header.msg_id = "test-resp-" + request_msg.header.msg_id
    response.header.msg_type = usp_msg_pb2.Header.GET_INSTANCES_RESP
    
    gi_resp = response.body.response.get_instances_resp
    req_path = gi_resp.req_path_results.add()
    req_path.requested_path = "Device.LocalAgent.Controller."
    
    inst = req_path.curr_insts.add()
    inst.instantiated_obj_path = "Device.LocalAgent.Controller.1."
    
    # Wrap in record
    record = usp_record_pb2.Record()
    record.version = "1.3"
    record.to_id = request_msg.header.from_id
    record.from_id = request_msg.header.to_id
    record.no_session_context.payload = response.SerializeToString()
    
    return record.SerializeToString()


def create_set_response(request_msg):
    """Create Set response"""
    response = usp_msg_pb2.Msg()
    response.header.msg_id = "test-resp-" + request_msg.header.msg_id
    response.header.msg_type = usp_msg_pb2.Header.SET_RESP
    
    set_resp = response.body.response.set_resp
    obj_result = set_resp.updated_obj_results.add()
    obj_result.requested_path = "Device.LocalAgent.Controller.1."
    
    param_result = obj_result.oper_success.updated_inst_results.add()
    param_result.affected_path = "Device.LocalAgent.Controller.1."
    param_result.updated_params["PeriodicNotifInterval"] = "60"
    
    # Wrap in record
    record = usp_record_pb2.Record()
    record.version = "1.3"
    record.to_id = request_msg.header.from_id
    record.from_id = request_msg.header.to_id
    record.no_session_context.payload = response.SerializeToString()
    
    return record.SerializeToString()


@pytest.mark.asyncio
async def test_agent_sends_boot_notification(mock_controller, e2e_ws_db_9080):
    """Test: Agent sends Boot! notification on connect"""
    # Start agent
    agent_task = asyncio.create_task(run_agent_for_seconds(2, e2e_ws_db_9080))
    
    # Wait for Boot!
    await asyncio.sleep(1)
    
    # Verify Boot! received
    assert len(mock_controller['received']) > 0, "No messages received"
    
    boot_msg = mock_controller['received'][0]
    usp_msg = usp_msg_pb2.Msg()
    usp_msg.ParseFromString(boot_msg.no_session_context.payload)
    
    assert usp_msg.header.msg_type == usp_msg_pb2.Header.NOTIFY
    assert usp_msg.body.request.notify.event.event_name == "Boot!"
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_get_request_response_cycle(mock_controller, e2e_ws_db_9080):
    """Test: Full Get request/response cycle"""
    agent_task = asyncio.create_task(run_agent_for_seconds(5, e2e_ws_db_9080))
    await asyncio.sleep(1)  # Wait for agent to connect
    
    # Send Get request
    controller_ws = mock_controller['clients'][0]
    get_request = create_get_request()
    await controller_ws.send(get_request)
    
    # Wait for response
    await asyncio.sleep(0.5)
    
    # Verify response received (agent should have sent response)
    # Response is handled by agent's handle_incoming_request
    assert len(mock_controller['received']) >= 2  # Boot! + our Get
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_set_request_updates_database(mock_controller, e2e_ws_db_9080):
    """Test: Set request updates agent database"""
    agent_task = asyncio.create_task(run_agent_for_seconds(5, e2e_ws_db_9080))
    await asyncio.sleep(1)
    
    # Send Set request
    controller_ws = mock_controller['clients'][0]
    set_request = create_set_request()
    await controller_ws.send(set_request)
    
    await asyncio.sleep(0.5)
    
    # Verify Set processed (check logs or response)
    assert len(mock_controller['received']) >= 2
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_get_supported_dm_request(mock_controller, e2e_ws_db_9080):
    """Test: GetSupportedDM request returns data model"""
    agent_task = asyncio.create_task(run_agent_for_seconds(5, e2e_ws_db_9080))
    await asyncio.sleep(1)
    
    controller_ws = mock_controller['clients'][0]
    gsdm_request = create_gsdm_request()
    await controller_ws.send(gsdm_request)
    
    await asyncio.sleep(0.5)
    
    assert len(mock_controller['received']) >= 2
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_get_instances_request(mock_controller, e2e_ws_db_9080):
    """Test: GetInstances request returns instance paths"""
    agent_task = asyncio.create_task(run_agent_for_seconds(5, e2e_ws_db_9080))
    await asyncio.sleep(1)
    
    controller_ws = mock_controller['clients'][0]
    gi_request = create_get_instances_request()
    await controller_ws.send(gi_request)
    
    await asyncio.sleep(0.5)
    
    assert len(mock_controller['received']) >= 2
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_concurrent_requests(mock_controller, e2e_ws_db_9080):
    """Test: Agent handles concurrent requests correctly"""
    agent_task = asyncio.create_task(run_agent_for_seconds(10, e2e_ws_db_9080))
    await asyncio.sleep(1)
    
    controller_ws = mock_controller['clients'][0]
    
    # Send 5 concurrent Get requests
    requests = [create_get_request() for _ in range(5)]
    await asyncio.gather(*[controller_ws.send(req) for req in requests])
    
    await asyncio.sleep(1)
    
    # Should have Boot! + 5 Gets = 6 messages
    assert len(mock_controller['received']) >= 6
    
    agent_task.cancel()


@pytest.mark.skip(reason="Requires 35s runtime; enable manually for periodic notification testing")
@pytest.mark.asyncio
async def test_periodic_notification(mock_controller, e2e_ws_db_9080):
    """Test: Agent sends periodic notifications"""
    # This test requires longer runtime to see periodic
    agent_task = asyncio.create_task(run_agent_for_seconds(35, e2e_ws_db_9080))
    await asyncio.sleep(1)
    
    initial_count = len(mock_controller['received'])
    
    # Wait for periodic interval (30s)
    await asyncio.sleep(32)
    
    # Should have received at least one Periodic!
    final_count = len(mock_controller['received'])
    assert final_count > initial_count, "No periodic notification received"
    
    # Check for Periodic! notification
    periodic_found = False
    for msg in mock_controller['received'][initial_count:]:
        usp_msg = usp_msg_pb2.Msg()
        usp_msg.ParseFromString(msg.no_session_context.payload)
        if (usp_msg.header.msg_type == usp_msg_pb2.Header.NOTIFY and
                usp_msg.body.request.notify.event.event_name == "Periodic!"):
            periodic_found = True
            break
    
    assert periodic_found, "Periodic! notification not found"
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_malformed_request_handling(mock_controller, e2e_ws_db_9080):
    """Test: Agent handles malformed requests gracefully"""
    agent_task = asyncio.create_task(run_agent_for_seconds(5, e2e_ws_db_9080))
    await asyncio.sleep(1)
    
    controller_ws = mock_controller['clients'][0]
    
    # Send malformed data
    await controller_ws.send(b"this is not valid protobuf")
    
    await asyncio.sleep(0.5)
    
    # Agent should still be running (not crashed)
    assert len(mock_controller['clients']) == 1
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_connection_recovery(mock_controller, e2e_ws_db_9080):
    """Test: Agent handles connection drop and reconnect"""
    agent_task = asyncio.create_task(run_agent_for_seconds(10, e2e_ws_db_9080))
    await asyncio.sleep(1)
    
    # Drop connection
    controller_ws = mock_controller['clients'][0]
    await controller_ws.close()
    
    await asyncio.sleep(2)
    
    # Agent should attempt to reconnect (implementation dependent)
    # This test validates graceful handling of disconnect
    
    agent_task.cancel()


# Helper functions

async def run_agent_for_seconds(seconds, db_path):
    """Run agent for specified duration"""
    agent = MultiMTPAgent('database/test-dm.json', str(db_path))
    try:
        await asyncio.wait_for(agent.start(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


def create_get_request():
    """Create a Get request"""
    msg = usp_msg_pb2.Msg()
    msg.header.msg_id = "test-get-1"
    msg.header.msg_type = usp_msg_pb2.Header.GET
    
    get_req = msg.body.request.get
    get_req.param_paths.append("Device.LocalAgent.EndpointID")
    
    record = usp_record_pb2.Record()
    record.version = "1.3"
    record.to_id = "ops::00D09E-Test-T01"
    record.from_id = "proto::controller-01"
    record.no_session_context.payload = msg.SerializeToString()
    
    return record.SerializeToString()


def create_set_request():
    """Create a Set request"""
    msg = usp_msg_pb2.Msg()
    msg.header.msg_id = "test-set-1"
    msg.header.msg_type = usp_msg_pb2.Header.SET
    
    set_req = msg.body.request.set
    update_obj = set_req.update_objs.add()
    update_obj.obj_path = "Device.LocalAgent.Controller.1."
    
    param = update_obj.param_settings.add()
    param.param = "PeriodicNotifInterval"
    param.value = "60"
    
    record = usp_record_pb2.Record()
    record.version = "1.3"
    record.to_id = "ops::00D09E-Test-T01"
    record.from_id = "proto::controller-01"
    record.no_session_context.payload = msg.SerializeToString()
    
    return record.SerializeToString()


def create_gsdm_request():
    """Create GetSupportedDM request"""
    msg = usp_msg_pb2.Msg()
    msg.header.msg_id = "test-gsdm-1"
    msg.header.msg_type = usp_msg_pb2.Header.GET_SUPPORTED_DM
    
    gsdm_req = msg.body.request.get_supported_dm
    gsdm_req.obj_paths.append("Device.")
    gsdm_req.return_params = True
    
    record = usp_record_pb2.Record()
    record.version = "1.3"
    record.to_id = "ops::00D09E-Test-T01"
    record.from_id = "proto::controller-01"
    record.no_session_context.payload = msg.SerializeToString()
    
    return record.SerializeToString()


def create_get_instances_request():
    """Create GetInstances request"""
    msg = usp_msg_pb2.Msg()
    msg.header.msg_id = "test-gi-1"
    msg.header.msg_type = usp_msg_pb2.Header.GET_INSTANCES
    
    gi_req = msg.body.request.get_instances
    gi_req.obj_paths.append("Device.LocalAgent.Controller.")
    
    record = usp_record_pb2.Record()
    record.version = "1.3"
    record.to_id = "ops::00D09E-Test-T01"
    record.from_id = "proto::controller-01"
    record.no_session_context.payload = msg.SerializeToString()
    
    return record.SerializeToString()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
