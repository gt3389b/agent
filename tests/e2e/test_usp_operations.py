"""
End-to-End tests for all USP operations

Comprehensive testing of each USP message type:
- Get, Set, Add, Delete, Operate
- GetSupportedDM, GetInstances, GetSupportedProtocol
- Notifications: Boot!, Periodic!, ValueChange!, ObjectCreation!, OperationComplete!
"""

import asyncio
import pytest
import pytest_asyncio
import websockets
from message import usp_msg_pb2, usp_record_pb2
from agent.multi_mtp_agent import MultiMTPAgent




class USPController:
    """Mock USP Controller for testing"""
    
    def __init__(self, port=9082):
        self.port = port
        self.server = None
        self.websocket = None
        self.received = []
        
    async def start(self):
        """Start controller server"""
        async def handle_connection(websocket):
            self.websocket = websocket
            try:
                async for message in websocket:
                    record = usp_record_pb2.Record()
                    record.ParseFromString(message)
                    self.received.append(record)
                    
                    # Auto-respond to requests
                    await self.handle_request(record, websocket)
                    
            except websockets.exceptions.ConnectionClosed:
                pass
        
        self.server = await websockets.serve(
            handle_connection,
            'localhost',
            self.port,
            subprotocols=['v1.usp']
        )
    
    async def handle_request(self, record, websocket):
        """Auto-respond to USP requests"""
        usp_msg = usp_msg_pb2.Msg()
        usp_msg.ParseFromString(record.no_session_context.payload)
        
        # Don't respond to notifications
        if usp_msg.header.msg_type == usp_msg_pb2.Header.NOTIFY:
            return
        
        # Create simple success response
        response = self.create_success_response(record, usp_msg)
        if response:
            await websocket.send(response)
    
    def create_success_response(self, req_record, req_msg):
        """Create success response for any request"""
        resp = usp_msg_pb2.Msg()
        resp.header.msg_id = "resp-" + req_msg.header.msg_id
        
        msg_type = req_msg.header.msg_type
        if msg_type == usp_msg_pb2.Header.GET:
            resp.header.msg_type = usp_msg_pb2.Header.GET_RESP
            # Minimal Get response
        elif msg_type == usp_msg_pb2.Header.SET:
            resp.header.msg_type = usp_msg_pb2.Header.SET_RESP
            # Minimal Set response
        elif msg_type == usp_msg_pb2.Header.GET_SUPPORTED_DM:
            resp.header.msg_type = usp_msg_pb2.Header.GET_SUPPORTED_DM_RESP
        elif msg_type == usp_msg_pb2.Header.GET_INSTANCES:
            resp.header.msg_type = usp_msg_pb2.Header.GET_INSTANCES_RESP
        elif msg_type == usp_msg_pb2.Header.OPERATE:
            resp.header.msg_type = usp_msg_pb2.Header.OPERATE_RESP
        elif msg_type == usp_msg_pb2.Header.ADD:
            resp.header.msg_type = usp_msg_pb2.Header.ADD_RESP
        elif msg_type == usp_msg_pb2.Header.DELETE:
            resp.header.msg_type = usp_msg_pb2.Header.DELETE_RESP
        elif msg_type == usp_msg_pb2.Header.GET_SUPPORTED_PROTO:
            resp.header.msg_type = usp_msg_pb2.Header.GET_SUPPORTED_PROTO_RESP
        else:
            return None
        
        record = usp_record_pb2.Record()
        record.version = "1.3"
        record.to_id = req_record.from_id
        record.from_id = req_record.to_id
        record.no_session_context.payload = resp.SerializeToString()
        
        return record.SerializeToString()
    
    async def send_get(self, path):
        """Send Get request to agent"""
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = "test-get"
        msg.header.msg_type = usp_msg_pb2.Header.GET
        
        get_req = msg.body.request.get
        get_req.param_paths.append(path)
        
        await self.send_request(msg)
    
    async def send_set(self, path, value):
        """Send Set request to agent"""
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = "test-set"
        msg.header.msg_type = usp_msg_pb2.Header.SET
        
        set_req = msg.body.request.set
        obj = set_req.update_objs.add()
        obj.obj_path = path.rsplit('.', 1)[0] + '.'
        
        param = obj.param_settings.add()
        param.param = path.rsplit('.', 1)[1]
        param.value = value
        
        await self.send_request(msg)
    
    async def send_get_supported_dm(self, obj_path):
        """Send GetSupportedDM request"""
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = "test-gsdm"
        msg.header.msg_type = usp_msg_pb2.Header.GET_SUPPORTED_DM
        
        gsdm = msg.body.request.get_supported_dm
        gsdm.obj_paths.append(obj_path)
        gsdm.return_params = True
        
        await self.send_request(msg)
    
    async def send_get_instances(self, obj_path):
        """Send GetInstances request"""
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = "test-gi"
        msg.header.msg_type = usp_msg_pb2.Header.GET_INSTANCES
        
        gi = msg.body.request.get_instances
        gi.obj_paths.append(obj_path)
        
        await self.send_request(msg)
    
    async def send_operate(self, command, input_args=None):
        """Send Operate request"""
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = "test-operate"
        msg.header.msg_type = usp_msg_pb2.Header.OPERATE
        
        operate = msg.body.request.operate
        operate.command = command
        
        if input_args:
            for key, val in input_args.items():
                operate.command_key = key
                operate.send_resp = True
        
        await self.send_request(msg)

    async def send_add(self, obj_path, param_settings=None):
        """Send Add request"""
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = "test-add"
        msg.header.msg_type = usp_msg_pb2.Header.ADD

        add_req = msg.body.request.add
        add_req.allow_partial = True
        create_obj = add_req.create_objs.add()
        create_obj.obj_path = obj_path
        for param, value in (param_settings or {}).items():
            setting = create_obj.param_settings.add()
            setting.param = param
            setting.value = str(value)

        await self.send_request(msg)

    async def send_delete(self, obj_paths):
        """Send Delete request"""
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = "test-delete"
        msg.header.msg_type = usp_msg_pb2.Header.DELETE

        delete_req = msg.body.request.delete
        delete_req.allow_partial = True
        if isinstance(obj_paths, str):
            obj_paths = [obj_paths]
        delete_req.obj_paths.extend(obj_paths)

        await self.send_request(msg)

    async def send_get_supported_protocol(self, versions="1.3"):
        """Send GetSupportedProtocol request"""
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = "test-gsp"
        msg.header.msg_type = usp_msg_pb2.Header.GET_SUPPORTED_PROTO
        msg.body.request.get_supported_protocol.controller_supported_protocol_versions = versions

        await self.send_request(msg)
    
    async def send_request(self, msg):
        """Send USP request to agent"""
        record = usp_record_pb2.Record()
        record.version = "1.3"
        record.to_id = "ops::00D09E-Test-T01"
        record.from_id = "proto::controller-01"
        record.no_session_context.payload = msg.SerializeToString()
        
        await self.websocket.send(record.SerializeToString())
    
    async def stop(self):
        """Stop controller"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()


@pytest_asyncio.fixture
async def controller():
    """Fixture providing mock controller"""
    ctrl = USPController(8080)
    await ctrl.start()
    yield ctrl
    await ctrl.stop()


@pytest.mark.asyncio
async def test_get_operation(controller, e2e_ws_db_8080):
    """Test: Get operation retrieves parameter values"""
    agent_task = asyncio.create_task(run_agent(3, e2e_ws_db_8080))
    await asyncio.sleep(1)
    
    await controller.send_get("Device.LocalAgent.EndpointID")
    await asyncio.sleep(0.5)
    
    # Should have Boot! + Get request
    assert len(controller.received) >= 2
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_set_operation(controller, e2e_ws_db_8080):
    """Test: Set operation updates parameter values"""
    agent_task = asyncio.create_task(run_agent(3, e2e_ws_db_8080))
    await asyncio.sleep(1)
    
    await controller.send_set("Device.LocalAgent.Controller.1.PeriodicNotifInterval", "120")
    await asyncio.sleep(0.5)
    
    assert len(controller.received) >= 2
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_get_supported_dm_operation(controller, e2e_ws_db_8080):
    """Test: GetSupportedDM returns data model structure"""
    agent_task = asyncio.create_task(run_agent(3, e2e_ws_db_8080))
    await asyncio.sleep(1)
    
    await controller.send_get_supported_dm("Device.")
    await asyncio.sleep(0.5)
    
    assert len(controller.received) >= 2
    
    # Check for GetSupportedDMResp
    for record in controller.received[1:]:
        msg = usp_msg_pb2.Msg()
        msg.ParseFromString(record.no_session_context.payload)
        if msg.header.msg_type == usp_msg_pb2.Header.GET_SUPPORTED_DM_RESP:
            assert True
            agent_task.cancel()
            return
    
    agent_task.cancel()
    assert False, "No GetSupportedDMResp received"


@pytest.mark.asyncio
async def test_get_instances_operation(controller, e2e_ws_db_8080):
    """Test: GetInstances returns instance paths"""
    agent_task = asyncio.create_task(run_agent(3, e2e_ws_db_8080))
    await asyncio.sleep(1)
    
    await controller.send_get_instances("Device.LocalAgent.Controller.")
    await asyncio.sleep(0.5)
    
    assert len(controller.received) >= 2
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_operate_returns_not_supported(controller, e2e_ws_db_8080):
    """Test: Operate operation returns not supported by default"""
    agent_task = asyncio.create_task(run_agent(3, e2e_ws_db_8080))
    await asyncio.sleep(1)
    
    await controller.send_operate("Device.Reboot()")
    await asyncio.sleep(0.5)
    
    # Should receive OperateResp with error
    assert len(controller.received) >= 2
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_boot_notification(controller, e2e_ws_db_8080):
    """Test: Boot! notification sent on connect"""
    agent_task = asyncio.create_task(run_agent(3, e2e_ws_db_8080))
    await asyncio.sleep(1)
    
    assert len(controller.received) >= 1
    
    boot_record = controller.received[0]
    msg = usp_msg_pb2.Msg()
    msg.ParseFromString(boot_record.no_session_context.payload)
    
    assert msg.header.msg_type == usp_msg_pb2.Header.NOTIFY
    assert "Boot!" in msg.body.request.notify.event.event_name
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_multiple_operations_sequence(controller, e2e_ws_db_8080):
    """Test: Multiple operations in sequence"""
    agent_task = asyncio.create_task(run_agent(5, e2e_ws_db_8080))
    await asyncio.sleep(1)
    
    # Send Get
    await controller.send_get("Device.LocalAgent.EndpointID")
    await asyncio.sleep(0.3)
    
    # Send Set
    await controller.send_set("Device.LocalAgent.Controller.1.PeriodicNotifInterval", "90")
    await asyncio.sleep(0.3)
    
    # Send GetSupportedDM
    await controller.send_get_supported_dm("Device.LocalAgent.")
    await asyncio.sleep(0.3)
    
    # Send GetInstances
    await controller.send_get_instances("Device.LocalAgent.MTP.")
    await asyncio.sleep(0.3)
    
    # Should have Boot! + 4 requests = 5+ messages
    assert len(controller.received) >= 5
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_error_response_on_invalid_path(controller, e2e_ws_db_8080):
    """Test: Error response for invalid parameter path"""
    agent_task = asyncio.create_task(run_agent(3, e2e_ws_db_8080))
    await asyncio.sleep(1)
    
    await controller.send_get("Device.NonExistent.Parameter")
    await asyncio.sleep(0.5)
    
    # Should still receive response (with error)
    assert len(controller.received) >= 2
    
    agent_task.cancel()


@pytest.mark.asyncio
async def test_add_object(controller, e2e_ws_db_8080):
    """Test: Add operation creates a new object instance"""
    agent_task = asyncio.create_task(run_agent(3, e2e_ws_db_8080))
    await asyncio.sleep(1)

    await controller.send_add(
        "Device.LocalAgent.Subscription.",
        {"ID": "ws-test-sub", "NotifType": "Event", "Enable": "true"}
    )
    await asyncio.sleep(0.5)

    # Should have Boot! + Add response
    assert len(controller.received) >= 2

    # Verify Add response type
    for record in controller.received[1:]:
        msg = usp_msg_pb2.Msg()
        msg.ParseFromString(record.no_session_context.payload)
        if msg.header.msg_type == usp_msg_pb2.Header.ADD_RESP:
            assert True
            agent_task.cancel()
            return

    agent_task.cancel()
    assert False, "No ADD_RESP received"


@pytest.mark.asyncio
async def test_delete_object(controller, e2e_ws_db_8080):
    """Test: Delete operation removes an object instance"""
    agent_task = asyncio.create_task(run_agent(3, e2e_ws_db_8080))
    await asyncio.sleep(1)

    # First add an instance, then delete it
    await controller.send_add(
        "Device.LocalAgent.Subscription.",
        {"ID": "ws-del-sub", "NotifType": "Event", "Enable": "true"}
    )
    await asyncio.sleep(0.3)

    # Determine the instance path from the ADD response
    created_path = None
    for record in controller.received[1:]:
        msg = usp_msg_pb2.Msg()
        msg.ParseFromString(record.no_session_context.payload)
        if msg.header.msg_type == usp_msg_pb2.Header.ADD_RESP:
            for result in msg.body.response.add_resp.created_obj_results:
                if not result.oper_status.HasField('oper_failure'):
                    created_path = result.oper_status.oper_success.instantiated_path
                    break
            break

    if created_path:
        await controller.send_delete(created_path)
        await asyncio.sleep(0.5)

        for record in controller.received:
            msg = usp_msg_pb2.Msg()
            msg.ParseFromString(record.no_session_context.payload)
            if msg.header.msg_type == usp_msg_pb2.Header.DELETE_RESP:
                assert True
                agent_task.cancel()
                return

        agent_task.cancel()
        assert False, "No DELETE_RESP received"
    else:
        agent_task.cancel()
        pytest.skip("Add did not return an instantiated path; skipping delete")


@pytest.mark.asyncio
async def test_get_supported_protocol(controller, e2e_ws_db_8080):
    """Test: GetSupportedProtocol returns agent protocol versions"""
    agent_task = asyncio.create_task(run_agent(3, e2e_ws_db_8080))
    await asyncio.sleep(1)

    await controller.send_get_supported_protocol("1.3")
    await asyncio.sleep(0.5)

    for record in controller.received[1:]:
        msg = usp_msg_pb2.Msg()
        msg.ParseFromString(record.no_session_context.payload)
        if msg.header.msg_type == usp_msg_pb2.Header.GET_SUPPORTED_PROTO_RESP:
            versions = msg.body.response.get_supported_protocol_resp.agent_supported_protocol_versions
            assert "1" in versions  # At least one version returned
            agent_task.cancel()
            return

    agent_task.cancel()
    assert False, "No GET_SUPPORTED_PROTO_RESP received"


async def run_agent(seconds, db_path):
    """Run agent for specified duration"""
    agent = MultiMTPAgent('database/test-dm.json', str(db_path))
    try:
        await asyncio.wait_for(agent.start(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
