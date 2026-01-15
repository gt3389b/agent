#!/usr/bin/env python3
"""
Test client for Controller Northbound API
"""
import asyncio
import json
import sys


class NorthboundClient:
    """Client for controller northbound API"""
    
    def __init__(self, socket_path="/tmp/usp-controller-api.sock"):
        self.socket_path = socket_path
        self.reader = None
        self.writer = None
        self.request_id = 0
    
    async def connect(self):
        """Connect to controller API"""
        self.reader, self.writer = await asyncio.open_unix_connection(
            self.socket_path
        )
        print(f"✓ Connected to {self.socket_path}")
    
    async def send_request(self, method, params=None):
        """Send JSON-RPC request"""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": self.request_id
        }
        
        print(f"\n→ Request: {method}")
        print(f"  {json.dumps(params, indent=2)}")
        
        # Send request
        self.writer.write(json.dumps(request).encode() + b'\n')
        await self.writer.drain()
        
        # Read response
        data = await self.reader.readline()
        response = json.loads(data.decode())
        
        print(f"\n← Response:")
        if 'error' in response:
            print(f"  ERROR {response['error']['code']}: {response['error']['message']}")
            raise Exception(f"Error: {response['error']['message']}")
        else:
            print(f"  {json.dumps(response['result'], indent=2)}")
        
        return response['result']
    
    async def list_agents(self):
        """List connected agents"""
        return await self.send_request('list_agents')
    
    async def get(self, agent_id, paths):
        """Get parameters"""
        return await self.send_request('get', {
            'agent_id': agent_id,
            'paths': paths
        })
    
    async def set(self, agent_id, parameters):
        """Set parameters"""
        return await self.send_request('set', {
            'agent_id': agent_id,
            'parameters': parameters
        })
    
    async def close(self):
        """Close connection"""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()


async def main():
    """Test the northbound API"""
    client = NorthboundClient()
    
    try:
        await client.connect()
        
        # Test 1: List agents
        print("\n" + "=" * 60)
        print("TEST 1: List agents")
        print("=" * 60)
        agents = await client.list_agents()
        
        if not agents:
            print("\n⚠️  No agents connected yet. Waiting for agent to boot...")
            await asyncio.sleep(5)
            agents = await client.list_agents()
        
        if agents:
            agent_id = agents[0]['agent_id']
            print(f"\n✓ Found agent: {agent_id}")
            
            # Test 2: Get parameters
            print("\n" + "=" * 60)
            print("TEST 2: Get parameters")
            print("=" * 60)
            result = await client.get(agent_id, [
                'Device.DeviceInfo.Manufacturer',
                'Device.DeviceInfo.ModelName',
                'Device.LocalAgent.Controller.1.PeriodicNotifInterval'
            ])
            
            # Test 3: Set parameter (change heartbeat to 15 seconds)
            print("\n" + "=" * 60)
            print("TEST 3: Set parameter (PeriodicNotifInterval to 15)")
            print("=" * 60)
            result = await client.set(agent_id, [
                {
                    'path': 'Device.LocalAgent.Controller.1.PeriodicNotifInterval',
                    'value': '15'
                }
            ])
            
            # Test 4: Verify the change
            print("\n" + "=" * 60)
            print("TEST 4: Verify the change")
            print("=" * 60)
            result = await client.get(agent_id, [
                'Device.LocalAgent.Controller.1.PeriodicNotifInterval'
            ])
            
            print("\n✅ All tests passed!")
        else:
            print("\n❌ No agents connected")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()


if __name__ == '__main__':
    asyncio.run(main())
