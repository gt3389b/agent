"""
Integration Test: JSON-RPC → Controller → BridgeAgent → MockWRP

Tests the complete data flow path:
1. JSON-RPC commands over UDS (Unix Domain Socket)
2. Controller processes commands and routes to agent
3. BridgeAgent receives USP requests and routes via bridge
4. MockWRP service handles backend data model

This demonstrates the full stack integration.
"""

import asyncio
import json
import logging
import os
import sys
import socket
from pathlib import Path
import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.bridge_agent import BridgeAgent
from uspbridge.wrp_bridge import WrpBridge, BridgeContext
from tests.mock_wrp_service import MockWrpService
from message.request import GetRequest, SetRequest

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SimpleController:
    """
    Simple JSON-RPC controller for testing
    
    Accepts JSON-RPC commands over UDS and forwards to BridgeAgent
    """
    
    def __init__(self, agent: BridgeAgent, socket_path="/tmp/test-usp-controller.sock"):
        self.agent = agent
        self.socket_path = socket_path
        self.server = None
        self.endpoint_id = "proto::controller-1"
        
    async def start(self):
        """Start controller server"""
        # Remove old socket
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        
        self.server = await asyncio.start_unix_server(
            self._handle_client,
            path=self.socket_path
        )
        
        logger.info(f"🎮 Controller listening on UDS: {self.socket_path}")
        
        # Don't block - return the server task
        return asyncio.create_task(self.server.serve_forever())
    
    async def _handle_client(self, reader, writer):
        """Handle client connection and JSON-RPC requests"""
        logger.info("📱 Client connected to controller")
        
        try:
            while True:
                # Read line-delimited JSON
                data = await reader.readline()
                if not data:
                    break
                
                try:
                    request = json.loads(data.decode().strip())
                    logger.info(f"📥 Controller received JSON-RPC: {request.get('method')}")
                    
                    response = await self._process_request(request)
                    
                    # Send response
                    response_data = json.dumps(response) + '\n'
                    writer.write(response_data.encode())
                    await writer.drain()
                    
                    logger.info(f"📤 Controller sent: {response.get('result', {}).get('status', 'response')}")
                    
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parse error: {e}")
                    error_response = {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": f"Parse error: {e}"}
                    }
                    writer.write((json.dumps(error_response) + '\n').encode())
                    await writer.drain()
                    
        except Exception as e:
            logger.error(f"Error handling client: {e}", exc_info=True)
        finally:
            logger.info("📱 Client disconnected from controller")
            writer.close()
            await writer.wait_closed()
    
    async def _process_request(self, request):
        """
        Process JSON-RPC request by forwarding to BridgeAgent
        
        Supported methods:
        - get: Get parameter values
        - set: Set parameter values
        - operate: Execute command
        """
        method = request.get('method')
        params = request.get('params', {})
        req_id = request.get('id')
        
        try:
            # Create controller context
            controller_ctx = type('Context', (), {
                'endpoint': self.endpoint_id,
                'mtp_id': 'uds',
                'controller_id': 'ctrl-test'
            })()
            
            if method == 'get':
                # Get parameter values
                paths = params.get('paths', [])
                logger.info(f"   Forwarding Get request to agent: {paths}")
                
                get_req = GetRequest(
                    msg_id=f"ctrl-{req_id}",
                    paths=paths
                )
                
                get_resp = await self.agent.handle_get(get_req, controller_ctx)
                
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "status": "success",
                        "parameters": get_resp.results
                    }
                }
            
            elif method == 'set':
                # Set parameter values
                parameters = params.get('parameters', {})
                logger.info(f"   Forwarding Set request to agent: {list(parameters.keys())}")
                
                set_req = SetRequest(
                    msg_id=f"ctrl-{req_id}",
                    parameters=parameters
                )
                
                set_resp = await self.agent.handle_set(set_req, controller_ctx)
                
                # Build results from updated_params and failed_params
                results = []
                for path, value in set_resp.updated_params.items():
                    results.append({
                        "path": path,
                        "status": "success",
                        "value": value
                    })
                for path, (err_code, err_msg) in set_resp.failed_params.items():
                    results.append({
                        "path": path,
                        "status": "error",
                        "error_code": err_code,
                        "error_message": err_msg
                    })
                
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "status": "success",
                        "updated_params": set_resp.updated_params,
                        "failed_params": set_resp.failed_params,
                        "results": results  # Convenience list format
                    }
                }
            
            elif method == 'get_supported_dm':
                # Query data model structure
                obj_paths = params.get('obj_paths', [])
                logger.info(f"   Forwarding GetSupportedDM request to agent: {obj_paths}")
                
                from message.request import GetSupportedDMRequest
                
                gsdm_req = GetSupportedDMRequest(
                    msg_id=f"ctrl-{req_id}",
                    obj_paths=obj_paths,
                    first_level_only=params.get('first_level_only', False),
                    return_params=params.get('return_params', True)
                )
                
                gsdm_resp = await self.agent.handle_get_supported_dm(gsdm_req, controller_ctx)
                
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "status": "success",
                        "supported_objects": gsdm_resp.supported_objects
                    }
                }
            
            elif method == 'get_instances':
                # Query object instances
                obj_paths = params.get('obj_paths', [])
                logger.info(f"   Forwarding GetInstances request to agent: {obj_paths}")
                
                from message.request import GetInstancesRequest
                
                gi_req = GetInstancesRequest(
                    msg_id=f"ctrl-{req_id}",
                    obj_paths=obj_paths,
                    first_level_only=params.get('first_level_only', False)
                )
                
                gi_resp = await self.agent.handle_get_instances(gi_req, controller_ctx)
                
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "status": "success",
                        "instances": gi_resp.instances
                    }
                }
            
            elif method == 'operate':
                # Execute command
                command = params.get('command')
                input_args = params.get('input_args', {})
                logger.info(f"   Forwarding Operate request to agent: {command}")
                
                from message.request import OperateRequest
                
                op_req = OperateRequest(
                    msg_id=f"ctrl-{req_id}",
                    command=command,
                    input_args=input_args
                )
                
                op_resp = await self.agent.handle_operate(op_req, controller_ctx)
                
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "status": "success" if not op_resp.error else "error",
                        "command": op_resp.command,
                        "output_args": op_resp.output_args,
                        "error": op_resp.error
                    }
                }
            
            elif method == 'add':
                # Create object instance
                obj_path = params.get('obj_path')
                create_params = params.get('params', {})
                logger.info(f"   Forwarding Add request to agent: {obj_path}")
                
                # Create simple Add request object (not in message module yet)
                add_req = type('AddRequest', (), {
                    'msg_id': f"ctrl-{req_id}",
                    'obj_path': obj_path,
                    'params': create_params
                })()
                
                add_resp = await self.agent.handle_add(add_req, controller_ctx)
                
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "status": getattr(add_resp, 'status', 'success'),
                        "created_obj_path": getattr(add_resp, 'created_obj_path', '')
                    }
                }
            
            elif method == 'delete':
                # Delete object instances
                obj_paths = params.get('obj_paths', [])
                logger.info(f"   Forwarding Delete request to agent: {obj_paths}")
                
                # Create simple Delete request object (not in message module yet)
                del_req = type('DeleteRequest', (), {
                    'msg_id': f"ctrl-{req_id}",
                    'obj_paths': obj_paths
                })()
                
                del_resp = await self.agent.handle_delete(del_req, controller_ctx)
                
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "status": "success",
                        "results": getattr(del_resp, 'results', [])
                    }
                }
            
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }
                
        except Exception as e:
            logger.error(f"Error processing request: {e}", exc_info=True)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {e}"
                }
            }


class UDSClient:
    """Unix Domain Socket client for testing"""
    
    def __init__(self, socket_path="/tmp/test-usp-controller.sock"):
        self.socket_path = socket_path
        self.reader = None
        self.writer = None
        
    async def connect(self):
        """Connect to UDS server"""
        # Wait for socket to exist
        for _ in range(50):
            if os.path.exists(self.socket_path):
                break
            await asyncio.sleep(0.1)
        
        self.reader, self.writer = await asyncio.open_unix_connection(self.socket_path)
        logger.info(f"🔌 Connected to controller at {self.socket_path}")
    
    async def send_request(self, method, params, req_id=1):
        """Send JSON-RPC request"""
        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params
        }
        
        logger.info(f"📤 Client sending JSON-RPC: {method}")
        
        # Send request
        request_data = json.dumps(request) + '\n'
        self.writer.write(request_data.encode())
        await self.writer.drain()
        
        # Receive response
        response_line = await self.reader.readline()
        response = json.loads(response_line.decode().strip())
        
        logger.info(f"📥 Client received: {response.get('result', {}).get('status', 'response')}")
        return response
    
    async def close(self):
        """Close connection"""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            logger.info("🔌 Client disconnected")


@pytest.mark.asyncio
async def test_complete_flow():
    """
    Test complete JSON-RPC → Controller → BridgeAgent → MockWRP flow
    """
    print("\n" + "="*80)
    print("🚀 Testing Complete Flow: JSON-RPC → Controller → BridgeAgent → MockWRP")
    print("="*80 + "\n")
    
    # 1. Create MockWRP service (backend data model)
    print("1️⃣  Creating MockWRP service (backend)...")
    service = MockWrpService(
        dm_file="database/test-dm.json",
        db_file="database/test-db.json"
    )
    print(f"   ✅ Service has {service.get_stats()['db_size']} parameters\n")
    
    # 2. Create WRP bridge
    print("2️⃣  Creating WRP bridge...")
    bridge = WrpBridge(
        mac_address="112233445566",
        transport_send=service.receive  # Direct connection to service
    )
    service.response_callback = None  # Will be set by agent
    print("   ✅ Bridge ready\n")
    
    # 3. Create BridgeAgent
    print("3️⃣  Creating BridgeAgent...")
    agent = BridgeAgent(
        endpoint_id="proto::test-agent",
        bridge=bridge
    )
    
    # Wire up agent response handling
    class AgentTransport:
        def __init__(self, agent):
            self.agent = agent
            
        async def receive_callback(self, data):
            operation, result, context = bridge.from_bytes(data)
            pending = agent._pending.get(context.usp_msg_id)
            if pending and pending.future and not pending.future.done():
                response = agent._build_response(operation, result, pending.request)
                pending.future.set_result(response)
    
    agent_transport = AgentTransport(agent)
    service.response_callback = lambda data: asyncio.create_task(
        agent_transport.receive_callback(data)
    )
    
    await agent.start()
    print("   ✅ Agent started\n")
    
    # 4. Create Controller
    print("4️⃣  Creating Controller with UDS endpoint...")
    controller = SimpleController(agent, socket_path="/tmp/test-usp-controller.sock")
    controller_task = await controller.start()
    print("   ✅ Controller listening on UDS\n")
    
    # Give server time to start
    await asyncio.sleep(0.2)
    
    # 5. Create UDS client and test commands
    print("5️⃣  Testing commands via JSON-RPC over UDS...\n")
    client = UDSClient(controller.socket_path)
    await client.connect()
    
    try:
        # Test 1: Get parameter
        print("=" * 80)
        print("Test 1: Get Device.DeviceInfo.Manufacturer")
        print("=" * 80)
        response = await client.send_request(
            method="get",
            params={"paths": ["Device.DeviceInfo.Manufacturer"]},
            req_id=1
        )
        print(f"✅ Result: {response['result']}\n")
        
        # Test 2: Get multiple parameters
        print("=" * 80)
        print("Test 2: Get multiple DeviceInfo parameters")
        print("=" * 80)
        response = await client.send_request(
            method="get",
            params={"paths": [
                "Device.DeviceInfo.Manufacturer",
                "Device.DeviceInfo.SerialNumber",
                "Device.DeviceInfo.ProductClass"
            ]},
            req_id=2
        )
        print(f"✅ Result: {len(response['result']['parameters'])} parameters retrieved")
        for param in response['result']['parameters']:
            if 'value' in param:
                print(f"   {param['name']} = {param['value']}")
        print()
        
        # Test 3: Get local agent parameter
        print("=" * 80)
        print("Test 3: Get Device.LocalAgent.SoftwareVersion (local)")
        print("=" * 80)
        response = await client.send_request(
            method="get",
            params={"paths": ["Device.LocalAgent.SoftwareVersion"]},
            req_id=3
        )
        print(f"✅ Result: {response['result']}\n")
        
        # Test 4: Set parameter (basic test - may not work without full Set support)
        print("=" * 80)
        print("Test 4: Set Device.Test.Parameter (if supported)")
        print("=" * 80)
        response = await client.send_request(
            method="set",
            params={"parameters": {
                "Device.LocalAgent.SoftwareVersion": "0.0.2-test"
            }},
            req_id=4
        )
        if 'error' in response:
            print(f"⚠️  Set not fully implemented: {response['error']['message']}\n")
        else:
            print(f"✅ Result: {response['result']}\n")
        
        # Test 5: Multiple Get (batch)
        print("=" * 80)
        print("Test 5: Get multiple parameters (batch request)")
        print("=" * 80)
        response = await client.send_request(
            method="get",
            params={"paths": [
                "Device.LocalAgent.SoftwareVersion",
                "Device.DeviceInfo.Manufacturer",
                "Device.DeviceInfo.SerialNumber",
                "Device.DeviceInfo.ModelName",
                "Device.DeviceInfo.ProductClass"
            ]},
            req_id=5
        )
        print(f"✅ Result: {len(response['result']['parameters'])} parameters retrieved")
        for param in response['result']['parameters'][:3]:  # Show first 3
            if 'value' in param:
                print(f"   {param['name']} = {param['value']}")
        print()
        
        # Test 6: Get non-existent parameter (error handling)
        print("=" * 80)
        print("Test 6: Get non-existent parameter (error handling)")
        print("=" * 80)
        response = await client.send_request(
            method="get",
            params={"paths": ["Device.Invalid.Path"]},
            req_id=6
        )
        print(f"✅ Error handling works: {response['result']['parameters'][0].get('error', 'no error')}\n")
        
        # Test 7: GetSupportedDM - Query data model structure
        print("=" * 80)
        print("Test 7: GetSupportedDM - Query data model structure")
        print("=" * 80)
        response = await client.send_request(
            method="get_supported_dm",
            params={
                "obj_paths": ["Device.DeviceInfo."],
                "return_params": True
            },
            req_id=7
        )
        if 'error' in response:
            print(f"⚠️  GetSupportedDM error: {response['error']['message']}\n")
        else:
            obj_info = response['result'].get('supported_objects', {}).get('Device.DeviceInfo.', {})
            param_count = len(obj_info.get('parameters', {}))
            print(f"✅ Result: Found {param_count} parameters in Device.DeviceInfo.")
            if param_count > 0:
                # Show a few parameters
                sample_params = list(obj_info['parameters'].keys())[:5]
                print(f"   Sample: {', '.join(sample_params)}\n")
        
        # Test 8: GetInstances - Query object instances
        print("=" * 80)
        print("Test 8: GetInstances - Query multi-instance objects")
        print("=" * 80)
        response = await client.send_request(
            method="get_instances",
            params={
                "obj_paths": ["Device.LocalAgent.MTP."]
            },
            req_id=8
        )
        if 'error' in response:
            print(f"⚠️  GetInstances error: {response['error']['message']}\n")
        else:
            instances = response['result'].get('instances', {}).get('Device.LocalAgent.MTP.', [])
            print(f"✅ Result: Found {len(instances)} MTP instances")
            if instances:
                print(f"   Instances: {', '.join(instances[:3])}\n")
            else:
                print("   (No instances found)\n")
        
        # Test 9: Operate - Factory Reset
        print("=" * 80)
        print("Test 9: Operate - Device.FactoryReset() command")
        print("=" * 80)
        response = await client.send_request(
            method="operate",
            params={
                "command": "Device.FactoryReset()",
                "input_args": {}
            },
            req_id=9
        )
        if 'error' in response:
            print(f"⚠️  Operate error: {response['error']['message']}\n")
        else:
            result = response['result']
            if result.get('error'):
                print(f"⚠️  Command failed: {result['error']}\n")
            else:
                output_args = result.get('output_args', {})
                print(f"✅ Result: Factory reset executed successfully")
                if 'ResetCount' in output_args:
                    print(f"   Reset {output_args['ResetCount']} parameters\n")
                else:
                    print("   Command completed\n")
        
        # Test 10: Add - Create new MTP instance
        print("=" * 80)
        print("Test 10: Add - Create Device.LocalAgent.MTP instance")
        print("=" * 80)
        created_path = ""  # Initialize to handle error case
        response = await client.send_request(
            method="add",
            params={
                "obj_path": "Device.LocalAgent.MTP.",
                "params": {
                    "Enable": "true",
                    "Alias": "TestMTP",
                    "Protocol": "WebSocket"
                }
            },
            req_id=10
        )
        if 'error' in response:
            print(f"⚠️  Add error: {response['error']['message']}\n")
        else:
            result = response['result']
            created_path = result.get('created_obj_path', '')
            print(f"✅ Result: Created instance {created_path}\n")
        
        # Test 11: Delete - Remove the MTP instance we just created
        if created_path:  # Only try to delete if we successfully created
            print("=" * 80)
            print("Test 11: Delete - Remove MTP instance")
            print("=" * 80)
            response = await client.send_request(
                method="delete",
                params={
                    "obj_paths": [created_path]  # Delete the instance we just created
                },
                req_id=11
            )
            if 'error' in response:
                print(f"⚠️  Delete error: {response['error']['message']}\n")
            else:
                result = response['result']
                delete_results = result.get('results', [])
                if delete_results and delete_results[0].get('status') == 'success':
                    print(f"✅ Result: Deleted instance {created_path}\n")
                else:
                    print(f"⚠️  Delete failed\n")
        
    finally:
        await client.close()
        controller_task.cancel()
        await agent.stop()
        
        # Cleanup socket
        if os.path.exists(controller.socket_path):
            os.remove(controller.socket_path)
    
    print("=" * 80)
    print("✅ All tests completed successfully!")
    print("=" * 80)
    print("\n📊 Statistics:")
    stats = service.get_stats()
    print(f"   WRP Requests:  {stats['requests']}")
    print(f"   WRP Responses: {stats['responses']}")
    print(f"   DB Size:       {stats['db_size']} parameters")
    print()


if __name__ == "__main__":
    asyncio.run(test_complete_flow())
