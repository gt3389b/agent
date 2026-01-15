#!/usr/bin/env python3
"""
USP Simulator - Unified async runner for Controller and Agent
Starts controller first, then agent, and manages both concurrently using asyncio
"""

import sys
import os
import asyncio
import logging
import signal
import argparse

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controller.controller import Controller
from controller.northbound import ControllerNorthbound
from agent.uds_agent import UdsAgent


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)-25s] %(levelname)-8s %(message)s'
)
logger = logging.getLogger("Simulator")


class UspSimulator:
    """Async USP Simulator running both Controller and Agent"""
    
    def __init__(self, config_file='cfg/controller.json'):
        self.config_file = config_file
        self.controller = None
        self.northbound = None
        self.agent = None
        self.controller_task = None
        self.agent_task = None
        
    async def run_controller(self):
        """Run the controller"""
        try:
            logger.info("="*60)
            logger.info("Starting USP Controller...")
            logger.info("="*60)
            
            self.controller = Controller(self.config_file)
            self.northbound = ControllerNorthbound(self.controller)
            
            # Run both controller and northbound API concurrently
            await asyncio.gather(
                self.controller.start(),
                self.northbound.start()
            )
            
        except asyncio.CancelledError:
            logger.info("Controller task cancelled")
        except Exception as e:
            logger.error(f"Controller error: {e}", exc_info=True)
        finally:
            if self.controller:
                await self.controller.stop()
                
    async def run_agent(self):
        """Run the agent"""
        try:
            # Give controller time to start
            await asyncio.sleep(1)
            
            logger.info("="*60)
            logger.info("Starting USP Agent...")
            logger.info("="*60)
            
            # Use default UDS agent for now
            dm_file = "database/uds-dm.json"
            db_file = "database/uds-db.json"
            
            self.agent = UdsAgent(
                dm_file=dm_file,
                db_file=db_file,
                cfg_file="cfg/agent.json"
            )
            
            await self.agent.start()
            
        except asyncio.CancelledError:
            logger.info("Agent task cancelled")
        except Exception as e:
            logger.error(f"Agent error: {e}", exc_info=True)
        finally:
            if self.agent:
                await self.agent.stop()
                
    async def start(self):
        """Start both controller and agent"""
        logger.info("="*60)
        logger.info(f"USP Simulator Starting - Transport: {self.transport_type.upper()}")
        logger.info("Press Ctrl+C to stop")
        logger.info("="*60)
        
        # Create tasks for controller and agent
        self.controller_task = asyncio.create_task(self.run_controller())
        self.agent_task = asyncio.create_task(self.run_agent())
        
        # Wait for both tasks
        try:
            await asyncio.gather(self.controller_task, self.agent_task)
        except asyncio.CancelledError:
            logger.info("Simulator cancelled")
            
    async def stop(self):
        """Stop both controller and agent"""
        logger.info("\nShutting down simulator...")
        
        # Cancel tasks
        if self.agent_task:
            self.agent_task.cancel()
        if self.controller_task:
            self.controller_task.cancel()
        
        # Wait for cleanup
        tasks = []
        if self.agent_task:
            tasks.append(self.agent_task)
        if self.controller_task:
            tasks.append(self.controller_task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info("Simulator stopped")


async def main(config_file):
    """Main entry point"""
    simulator = UspSimulator(config_file)
    
    # Setup signal handler for graceful shutdown
    loop = asyncio.get_running_loop()
    
    def signal_handler():
        logger.info("\nReceived interrupt signal")
        asyncio.create_task(simulator.stop())
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        await simulator.start()
    except KeyboardInterrupt:
        await simulator.stop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='USP Simulator - Unified Controller and Agent')
    parser.add_argument('-c', '--config',
                        default='cfg/controller.json',
                        help='Controller configuration file (default: cfg/controller.json)')
    
    args = parser.parse_args()
    
    try:
        asyncio.run(main(args.config))
    except KeyboardInterrupt:
        pass
