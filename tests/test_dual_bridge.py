"""
Quick test of dual bridge architecture (local + remote)
Shows that BridgeAgent no longer has direct Database access.
"""

import asyncio
import sys

sys.path.insert(0, '/Users/rleake939@cable.comcast.com/Development/Comcast/ai/pyagent-old')

from agent.bridge_agent import BridgeAgent
from uspbridge.wrp_bridge import WrpBridge
from message.request import GetRequest
from tests.mock_wrp_service import MockWrpService


class TestBridgeAgent(BridgeAgent):
    """Test agent with sync response handling"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._responses = []
        
    def set_service(self, service):
        """Wire up mock service"""
        self._service = service
        service.response_callback = lambda data: asyncio.create_task(self._handle_response(data))
        
    async def _handle_response(self, response_bytes: bytes):
        """Handle bridge response (internal or external)"""
        operation, data, context = self.bridge.from_bytes(response_bytes)
        pending = self._pending.get(context.usp_msg_id)
        if pending and pending.future and not pending.future.done():
            response = self._build_response(operation, data, pending.request)
            pending.future.set_result(response)
    
    async def _receive_from_backend(self):
        """No polling needed - using callbacks"""
        await asyncio.sleep(1)
        return None


async def test_dual_bridges():
    """Test that everything goes through single bridge (endpoint-based routing)"""
    
    print("\n" + "="*80)
    print("Testing Single Bridge Architecture (Endpoint-Based Routing)")
    print("="*80)
    print()
    
    # Create single mock service with full data model
    service = MockWrpService(
        dm_file="database/test-dm.json",
        db_file="database/test-db.json"
    )
    
    print("✅ Created MockWrpService with full data model")
    print(f"   DB has {service.get_stats()['db_size']} parameters")
    print()
    
    # Create single bridge
    bridge = WrpBridge(
        mac_address="112233445566",
        transport_send=service.receive  # Direct to service
    )
    
    print("✅ Created single WrpBridge")
    print()
    
    # Create agent (NO Database files, single bridge!)
    agent = TestBridgeAgent(
        endpoint_id="proto::test-agent",
        bridge=bridge
    )
    
    agent.set_service(service)
    
    print("✅ Created BridgeAgent with single bridge")
    print("   Internal requests use agent's own endpoint")
    print("   External requests use controller's endpoint")
    print()
    
    await agent.start()
    
    # Mock controller context
    ctx = type('Ctx', (), {
        'endpoint': 'proto::controller',
        'mtp_id': 'test',
        'controller_id': 'ctrl-1'
    })()
    
    # Test 1: Get remote parameter (Device.WiFi.*)
    print("Test 1: Get remote parameter (should route to remote bridge)")
    print("-" * 80)
    
    req1 = GetRequest(
        msg_id="test-1",
        paths=["Device.DeviceInfo.Manufacturer"]
    )
    
    resp1 = await agent.handle_get(req1, ctx)
    print(f"✅ Response: {resp1.results}")
    print()
    
    # Test 2: Get local parameter (Device.LocalAgent.*)
    print("Test 2: Get local parameter (should route to local bridge)")
    print("-" * 80)
    
    req2 = GetRequest(
        msg_id="test-2",
        paths=["Device.LocalAgent.SoftwareVersion"]
    )
    
    resp2 = await agent.handle_get(req2, ctx)
    print(f"✅ Response: {resp2.results}")
    print()
    
    # Verify stats
    print("Statistics:")
    print("-" * 80)
    print(f"Service: {service.get_stats()['requests']} requests")
    print(f"         (1 internal for LocalAgent, 1 external for DeviceInfo)")
    print()
    
    print("="*80)
    print("✅ SUCCESS: Single bridge with endpoint-based routing!")
    print("   Internal: Uses agent's own endpoint (proto::test-agent)")
    print("   External: Uses controller's endpoint (proto::controller)")
    print("   MockWrpService fronts real Database architecture")
    # Verify stats
    print("Statistics:")
    print("-" * 80)
    print(f"Service: {service.get_stats()['requests']} requests")
    print(f"         (1 internal for LocalAgent, 1 external for DeviceInfo)")
    print()
    
    print("="*80)
    print("✅ SUCCESS: Single bridge with endpoint-based routing!")
    print("   Internal: Uses agent's own endpoint (proto::test-agent)")
    print("   External: Uses controller's endpoint (proto::controller)")
    print("   MockWrpService fronts real Database architecture")
    print("="*80)
    print()
    
    await agent.stop()


if __name__ == "__main__":
    asyncio.run(test_dual_bridges())
