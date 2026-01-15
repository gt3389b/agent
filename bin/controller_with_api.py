#!/usr/bin/env python3
"""
Controller with Northbound API
Auto-starts agent, controller, and northbound API using async tasks
"""
import asyncio
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controller.uds_controller import UdsController
from controller.northbound import ControllerNorthbound
from agent.uds_agent import UdsAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


async def run_controller(controller):
    """Run the controller"""
    try:
        await controller.start()
    except asyncio.CancelledError:
        logger.info("Controller task cancelled")
    except Exception as e:
        logger.error(f"Controller error: {e}", exc_info=True)
    finally:
        await controller.stop()


async def run_northbound(northbound):
    """Run the northbound API"""
    try:
        await northbound.start()
    except asyncio.CancelledError:
        logger.info("Northbound task cancelled")
    except Exception as e:
        logger.error(f"Northbound error: {e}", exc_info=True)
    finally:
        await northbound.stop()


async def run_agent(agent):
    """Run the agent"""
    try:
        # Give controller time to start
        await asyncio.sleep(1)
        
        logger.info("="*60)
        logger.info("Starting UDS Agent...")
        logger.info("="*60)
        
        await agent.start()
        
    except asyncio.CancelledError:
        logger.info("Agent task cancelled")
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)


async def main():
    """Run controller with northbound API and agent"""
    
    logger.info("="*60)
    logger.info("Starting Controller + Northbound API + Agent")
    logger.info("Press Ctrl+C to stop")
    logger.info("="*60)
    
    # Initialize components
    controller = UdsController('cfg/controller.json')
    northbound = ControllerNorthbound(controller)
    agent = UdsAgent(
        dm_file='database/uds-dm.json',
        db_file='database/uds-db.json',
        cfg_file='cfg/agent.json'
    )
    
    # Create tasks for all three components
    controller_task = asyncio.create_task(run_controller(controller))
    northbound_task = asyncio.create_task(run_northbound(northbound))
    agent_task = asyncio.create_task(run_agent(agent))
    
    try:
        # Wait for all tasks
        await asyncio.gather(controller_task, northbound_task, agent_task)
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
        # Cancel all tasks
        agent_task.cancel()
        northbound_task.cancel()
        controller_task.cancel()
        # Wait for cleanup
        await asyncio.gather(agent_task, northbound_task, controller_task, return_exceptions=True)


if __name__ == '__main__':
    asyncio.run(main())
