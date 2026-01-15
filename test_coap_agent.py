#!/usr/bin/env python3
"""
Simple test to verify CoAP agent registers correctly with multi-MTP controller
"""

import asyncio
import logging

# Setup clean logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

async def test_coap_registration():
    """Test that CoAP agent registers with Boot! notification"""
    from controller.multi_mtp_controller import MultiMtpController
    from agent.coap_agent_async import CoapAgent
    
    print("=" * 80)
    print("Testing CoAP Agent Registration with Multi-MTP Controller")
    print("=" * 80)
    
    # Start controller
    controller = MultiMtpController('cfg/multi-controller.json')
    controller_task = asyncio.create_task(controller.start())
    
    # Wait for controller to be ready
    await asyncio.sleep(1)
    
    # Start agent
    agent = CoapAgent('database/coap-dm.json', 'database/coap-db.json')
    agent_task = asyncio.create_task(agent.start())
    
    # Wait for agent to send Boot! and process requests
    await asyncio.sleep(3)
    
    # Check registered agents
    agents = controller.get_connected_agents()
    
    print("\n" + "=" * 80)
    print("RESULTS:")
    print("=" * 80)
    
    if agents:
        for agent_info in agents:
            print(f"✓ Agent Registered:")
            print(f"  - Agent ID: {agent_info['agent_id']}")
            print(f"  - MTP Type: {agent_info['mtp_type'].upper()}")
            print(f"  - MTP Info: {agent_info['mtp_info']}")
            print(f"  - OUI: {agent_info.get('manufacturer_oui', 'N/A')}")
            print(f"  - Product: {agent_info.get('product_class', 'N/A')}")
            print(f"  - Serial: {agent_info.get('serial_number', 'N/A')}")
            print(f"  - Last Boot: {agent_info.get('last_boot', 'N/A')}")
    else:
        print("✗ No agents registered")
    
    print("=" * 80)
    
    # Cleanup
    controller_task.cancel()
    agent_task.cancel()
    await asyncio.gather(controller_task, agent_task, return_exceptions=True)
    await controller.stop()

if __name__ == "__main__":
    try:
        asyncio.run(test_coap_registration())
        print("\n✓ Test completed successfully!")
    except KeyboardInterrupt:
        print("\nTest interrupted")
