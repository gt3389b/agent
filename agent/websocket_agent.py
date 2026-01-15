"""
Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

# File Name: websocket_agent.py
#
# Description: Async WebSocket USP Agent
#
"""

import logging
import asyncio
import json

from agent.base_agent import BaseAgent
from agent import agent_db
from agent import notify
from mtp.websocket_binding import WebSocketUspBinding
from message.request import GetRequest, SetRequest, OperateRequest, GetSupportedDMRequest, GetInstancesRequest
from message.response import GetResponse, SetResponse, OperateResponse, GetSupportedDMResponse, GetInstancesResponse
from message import usp_msg_pb2

logger = logging.getLogger(__name__)


class WebSocketAgent(BaseAgent):
    """Async WebSocket-based USP Agent"""
    
    def __init__(self, dm_file, db_file, cfg_file='cfg/agent.json'):
        """
        Initialize Async WebSocket Agent
        
        Args:
            dm_file (str): Data model file path
            db_file (str): Database file path
            cfg_file (str): Config file path
        """
        # Initialize database
        self._db = agent_db.Database(dm_file, db_file, "")
        
        # Get agent endpoint ID
        agent_id = self._db.get("Device.LocalAgent.EndpointID")
        
        # Initialize base agent
        super().__init__(agent_id)
        
        # Find WebSocket MTP configuration
        mtp_path, listen_host, listen_port, resource_path = self._find_websocket_mtp()
        
        # Create WebSocket binding
        self._mtp_binding = WebSocketUspBinding(
            agent_id, 
            listen_host=listen_host,
            listen_port=listen_port,
            resource_path=resource_path
        )
        
        logger.info(f"Async WebSocket Agent initialized: {agent_id}")
        logger.info(f"  Listen: {listen_host}:{listen_port}{resource_path}")
        
        self._listen_host = listen_host
        self._listen_port = listen_port
        self._resource_path = resource_path
        self._periodic_tasks = []  # List of periodic notification tasks
        self._subscription_handlers = {}  # Track active subscription handlers
        
        # Load data model for GetSupportedDM responses
        self._dm_file = dm_file
        self._data_model = self._load_data_model(dm_file)
        
    def _find_websocket_mtp(self):
        """Find WebSocket MTP configuration"""
        num_mtps = int(self._db.get("Device.LocalAgent.MTPNumberOfEntries"))
        
        for i in range(1, num_mtps + 1):
            mtp_path = f"Device.LocalAgent.MTP.{i}."
            protocol = self._db.get(mtp_path + "Protocol")
            
            if protocol == "WebSocket":
                listen_host = self._db.get(mtp_path + "WebSocket.Host", default="localhost")
                listen_port = int(self._db.get(mtp_path + "WebSocket.Port", default=8080))
                resource_path = self._db.get(mtp_path + "WebSocket.Path", default="/usp")
                
                logger.info(f"Found WebSocket MTP: ws://{listen_host}:{listen_port}{resource_path}")
                return mtp_path, listen_host, listen_port, resource_path
        
        raise ValueError("No WebSocket MTP found in database")
    
    async def start(self):
        """Start the async WebSocket agent"""
        logger.info(f"Agent starting on ws://{self._listen_host}:{self._listen_port}{self._resource_path}")
        
        # Initialize subscriptions and start handlers
        await self._init_subscriptions()
        
        # Start listening for controller messages
        await self._mtp_binding.start_server(self.handle_incoming_request)
        
        logger.info("Agent listening for controller messages...")
        
        # Keep server running forever
        await asyncio.Future()
    
    async def send_boot_notification(self):
        """Send Boot! notification to controller"""
        try:
            # Find controller WebSocket URL
            controller_url = self._find_controller_url()
            
            logger.info(f"Sending Boot! notification to {controller_url}")
            
            # Create Boot notification
            boot_notif = notify.BootNotification(
                self.endpoint_id,
                self._controller_id,
                "sub-boot-websocket-ctrl-1",
                self._db,
                self._data_model
            )
            
            # Generate notification message
            notif_msg = boot_notif.generate_notif_msg()
            
            # Connect to controller
            await self._mtp_binding.connect(controller_url)
            
            # Send via binding
            await self.notify(notif_msg, self._controller_id, controller_url)
            
            logger.info("✓ Boot! notification sent successfully")
            
        except Exception as e:
            logger.error(f"Failed to send Boot! notification: {e}", exc_info=True)
    
    def _find_controller_url(self):
        """Find controller WebSocket URL from database"""
        try:
            num_controllers = int(self._db.get("Device.LocalAgent.ControllerNumberOfEntries"))
            
            for i in range(1, num_controllers + 1):
                ctrl_path = f"Device.LocalAgent.Controller.{i}."
                self._controller_id = self._db.get(ctrl_path + "EndpointID")
                
                # Find MTP for this controller
                num_mtps = int(self._db.get(ctrl_path + "MTPNumberOfEntries"))
                
                for j in range(1, num_mtps + 1):
                    mtp_path = f"{ctrl_path}MTP.{j}."
                    protocol = self._db.get(mtp_path + "Protocol")
                    
                    if protocol == "WebSocket":
                        host = self._db.get(mtp_path + "WebSocket.Host")
                        port = int(self._db.get(mtp_path + "WebSocket.Port"))
                        path = self._db.get(mtp_path + "WebSocket.Path")
                        
                        return f"ws://{host}:{port}{path}"
            
            raise ValueError("No WebSocket MTP found for any controller")
            
        except Exception as e:
            logger.error(f"Error finding controller WebSocket URL: {e}", exc_info=True)
            raise
    
    async def _init_subscriptions(self):
        """Initialize subscriptions from database"""
        try:
            num_subscriptions = int(self._db.get("Device.LocalAgent.SubscriptionNumberOfEntries", default=0))
            
            logger.info(f"Initializing {num_subscriptions} subscriptions...")
            
            for i in range(1, num_subscriptions + 1):
                sub_path = f"Device.LocalAgent.Subscription.{i}."
                
                # Check if subscription is enabled
                enable = self._db.get(sub_path + "Enable", default="false").lower() == "true"
                
                if not enable:
                    continue
                
                subscription_id = self._db.get(sub_path + "ID")
                notification_type = self._db.get(sub_path + "NotifType")
                recipient = self._db.get(sub_path + "Recipient")
                
                logger.info(f"  Subscription {subscription_id}: {notification_type} → {recipient}")
                
                # Handle different notification types
                if notification_type == "ValueChange":
                    # ValueChange subscriptions are handled by polling
                    await self._init_value_change_subscription(sub_path, subscription_id, recipient)
                    
                elif notification_type == "Event":
                    # Event subscriptions listen for events
                    await self._init_event_subscription(sub_path, subscription_id, recipient)
                    
        except Exception as e:
            logger.warning(f"Error initializing subscriptions: {e}", exc_info=True)
    
    async def _init_value_change_subscription(self, sub_path, subscription_id, recipient):
        """Initialize a ValueChange subscription"""
        try:
            # Get reference list
            num_refs = int(self._db.get(sub_path + "ReferenceListNumberOfEntries", default=0))
            
            for i in range(1, num_refs + 1):
                param_path = self._db.get(f"{sub_path}ReferenceList.{i}.Parameter")
                
                logger.info(f"    Monitoring: {param_path}")
                
                # Start periodic polling task
                task = asyncio.create_task(
                    self._poll_value_change(param_path, subscription_id, recipient)
                )
                self._periodic_tasks.append(task)
                
        except Exception as e:
            logger.error(f"Error initializing ValueChange subscription: {e}", exc_info=True)
    
    async def _init_event_subscription(self, sub_path, subscription_id, recipient):
        """Initialize an Event subscription"""
        try:
            # Get reference list
            num_refs = int(self._db.get(sub_path + "ReferenceListNumberOfEntries", default=0))
            
            for i in range(1, num_refs + 1):
                obj_path = self._db.get(f"{sub_path}ReferenceList.{i}.Parameter")
                
                logger.info(f"    Listening for events on: {obj_path}")
                
        except Exception as e:
            logger.error(f"Error initializing Event subscription: {e}", exc_info=True)
    
    async def _poll_value_change(self, param_path, subscription_id, recipient):
        """Poll for parameter value changes"""
        last_value = None
        
        while True:
            try:
                await asyncio.sleep(5)  # Poll every 5 seconds
                
                current_value = self._db.get(param_path)
                
                if last_value is not None and current_value != last_value:
                    logger.info(f"Value changed: {param_path} = {current_value}")
                    
                    # Send ValueChange notification
                    await self._send_value_change_notification(
                        param_path, current_value, subscription_id, recipient
                    )
                
                last_value = current_value
                
            except Exception as e:
                logger.error(f"Error polling {param_path}: {e}", exc_info=True)
    
    async def _send_value_change_notification(self, param_path, value, subscription_id, recipient):
        """Send ValueChange notification"""
        try:
            # Create ValueChange notification
            value_change_notif = notify.ValueChangeNotification(
                self.endpoint_id,
                recipient,
                subscription_id,
                param_path,
                value
            )
            
            # Generate notification message
            notif_msg = value_change_notif.generate_notif_msg()
            
            # Get controller WebSocket URL
            controller_url = self._find_controller_url()
            
            # Send via binding
            await self.notify(notif_msg, recipient, controller_url)
            
        except Exception as e:
            logger.error(f"Error sending ValueChange notification: {e}", exc_info=True)
    
    def _load_data_model(self, dm_file):
        """Load data model from JSON file"""
        try:
            with open(dm_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading data model: {e}", exc_info=True)
            return {}


async def main():
    """Main entry point"""
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python websocket_agent.py <dm_file> <db_file> [cfg_file]")
        sys.exit(1)
    
    dm_file = sys.argv[1]
    db_file = sys.argv[2]
    cfg_file = sys.argv[3] if len(sys.argv) > 3 else 'cfg/agent.json'
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and start agent
    agent = WebSocketAgent(dm_file, db_file, cfg_file)
    
    # Send boot notification
    await agent.send_boot_notification()
    
    # Start agent
    await agent.start()


if __name__ == '__main__':
    asyncio.run(main())
