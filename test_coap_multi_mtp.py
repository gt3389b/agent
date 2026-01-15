#!/usr/bin/env python3
"""
Test script for CoAP agent with Multi-MTP controller
"""

import asyncio
import logging
import signal
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(name)-25s] %(levelname)-8s: %(message)s'
)

# Separate loggers for better visibility
ctrl_logger = logging.getLogger('CONTROLLER')
agent_logger = logging.getLogger('AGENT')

async def run_controller():
    """Run the multi-MTP controller"""
    from controller.multi_mtp_controller import MultiMtpController
    
    ctrl_logger.info("Starting Multi-MTP Controller...")
    controller = MultiMtpController('cfg/multi-controller.json')
    
    try:
        await controller.start()
    except asyncio.CancelledError:
        ctrl_logger.info("Controller stopped")
    finally:
        await controller.stop()

async def run_agent():
    """Run the CoAP agent"""
    from agent.coap_agent_async import CoapAgent
    
    # Wait a moment for controller to start
    await asyncio.sleep(2)
    
    agent_logger.info("Starting CoAP Agent...")
    agent = CoapAgent('database/coap-dm.json', 'database/coap-db.json')
    
    try:
        await agent.start()
    except asyncio.CancelledError:
        agent_logger.info("Agent stopped")

async def main():
    """Run both controller and agent"""
    print("=" * 80)
    print("Testing CoAP Agent with Multi-MTP Controller")
    print("=" * 80)
    
    # Run both concurrently
    tasks = [
        asyncio.create_task(run_controller(), name='controller'),
        asyncio.create_task(run_agent(), name='agent')
    ]
    
    # Wait for both to complete (or be interrupted)
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print("\n" + "=" * 80)
        print("Shutting down...")
        print("=" * 80)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest completed")
