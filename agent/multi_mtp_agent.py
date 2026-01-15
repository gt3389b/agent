"""
Multi-MTP USP Agent

Connects to multiple controllers via multiple MTPs simultaneously.
Each MTP connection maintains its own RequestContext for proper response routing.
"""

import asyncio
import logging
from agent.base_agent import BaseAgent, RequestContext
from agent import agent_db, notify
from mtp.websocket_binding import WebSocketUspBinding

logger = logging.getLogger(__name__)


class MTPConnectionManager:
    """Manages a single MTP connection to a controller"""
    
    def __init__(self, agent, controller_id, mtp_index, protocol, config):
        self.agent = agent
        self.controller_id = controller_id
        self.mtp_index = mtp_index
        self.protocol = protocol
        self.config = config
        self.binding = None
        self.connection = None  # WebSocket, socket, etc.
        self.connected = False
        self.periodic_task = None
    
    async def connect(self):
        """Establish MTP connection"""
        try:
            if self.protocol == "WebSocket":
                host = self.config.get('host')
                port = self.config.get('port')
                path = self.config.get('path', '/')
                url = f"ws://{host}:{port}{path}"
                
                logger.info(f"Connecting to {self.controller_id} via WebSocket: {url}")
                
                # Create binding
                self.binding = WebSocketUspBinding(self.agent.endpoint_id)
                
                # Set message callback for incoming requests
                self.binding._message_callback = self._handle_incoming_message
                
                # Connect as client (this starts receive loop automatically)
                await self.binding.connect(url)
                self.connection = self.binding.client_websocket
                self.connected = True
                
                # Send Boot! notification
                await self._send_boot()
                
                # Start periodic notifications if configured
                await self._start_periodic()
                
                return True
                
            elif self.protocol == "UDS":
                # TODO: Implement UDS client
                logger.warning(f"UDS client not yet implemented")
                return False
                
            elif self.protocol == "CoAP":
                # TODO: Implement CoAP client
                logger.warning(f"CoAP client not yet implemented")
                return False
                
            else:
                logger.warning(f"Unsupported protocol: {self.protocol}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect {self.protocol} to {self.controller_id}: {e}", exc_info=True)
            return False
    
    async def _handle_incoming_message(self, python_msg, from_id, to_id, writer):
        """
        Handle incoming message (called by MTP binding's receive loop)
        
        Args:
            python_msg: Deserialized Python message object
            from_id (str): Controller endpoint ID
            to_id (str): Agent endpoint ID
            writer: Connection object (websocket) for sending response
        """
        # Forward to agent's request handler with proper context
        await self.agent.handle_incoming_request(python_msg, from_id, to_id, writer)
    
    async def _send_boot(self):
        """Send Boot! notification to controller"""
        try:
            logger.info(f"Sending Boot! to {self.controller_id} via {self.protocol}")
            
            boot_notif = notify.BootNotification(
                self.agent.endpoint_id,
                self.controller_id,
                f"sub-boot-{self.protocol.lower()}-{self.mtp_index}",
                self.agent._db,
                self.agent._data_model
            )
            
            notif_msg = boot_notif.generate_notif_msg()
            
            # Serialize
            data = self.binding.serialize_message(notif_msg, self.controller_id, self.agent.endpoint_id)
            
            # Send
            await self.connection.send(data)
            
            logger.info(f"✓ Boot! sent to {self.controller_id} via {self.protocol}")
            
        except Exception as e:
            logger.error(f"Failed to send Boot!: {e}", exc_info=True)
    
    async def _start_periodic(self):
        """Start periodic notification task"""
        try:
            # Get periodic interval from controller config
            # Extract controller index from endpoint ID or database
            ctrl_num = self.mtp_index  # Simplified - should parse from config
            interval_str = self.agent._db.get(f"Device.LocalAgent.Controller.{ctrl_num}.PeriodicNotifInterval")
            interval = int(interval_str) if interval_str else 0
            
            if interval > 0:
                logger.info(f"Starting periodic notifications to {self.controller_id} every {interval}s via {self.protocol}")
                self.periodic_task = asyncio.create_task(self._periodic_loop(interval))
            
        except Exception as e:
            logger.debug(f"Periodic notifications not configured: {e}")
    
    async def _periodic_loop(self, interval):
        """Send periodic notifications"""
        while self.connected:
            await asyncio.sleep(interval)
            
            try:
                periodic_notif = notify.PeriodicNotification(
                    self.agent.endpoint_id,
                    self.controller_id,
                    f"sub-periodic-{self.protocol.lower()}",
                    self.agent._db,
                    self.agent._data_model
                )
                
                notif_msg = periodic_notif.generate_notif_msg()
                data = self.binding.serialize_message(notif_msg, self.controller_id, self.agent.endpoint_id)
                
                await self.connection.send(data)
                
                logger.debug(f"Sent periodic notification to {self.controller_id} via {self.protocol}")
                
            except Exception as e:
                if self.connected:
                    logger.error(f"Error sending periodic notification: {e}", exc_info=True)
    
    async def send_notification(self, data):
        """Send notification bytes on this MTP"""
        if self.connected and self.connection:
            await self.connection.send(data)
    
    async def disconnect(self):
        """Disconnect this MTP"""
        self.connected = False
        if self.periodic_task:
            self.periodic_task.cancel()


class MultiMTPAgent(BaseAgent):
    """
    USP Agent supporting multiple simultaneous MTP connections
    
    - Reads controller MTP configurations from database
    - Connects to all enabled controller MTPs
    - Maintains RequestContext for proper response routing
    - Routes notifications to appropriate MTPs
    """
    
    def __init__(self, dm_file, db_file):
        """
        Initialize multi-MTP agent
        
        Args:
            dm_file (str): Data model file path
            db_file (str): Database file path
        """
        # Load database
        self._db = agent_db.Database(dm_file, db_file, "eth0")
        endpoint_id = self._db.get("Device.LocalAgent.EndpointID")
        
        # Initialize base agent
        super().__init__(endpoint_id)
        
        # Load data model
        self._data_model = self._load_data_model(dm_file)
        
        # MTP connection registry
        self.mtp_connections = []  # List of all MTP connections
        self.controller_mtps = {}  # controller_id -> list of MTPs
        
        self._logger.info(f"Multi-MTP Agent initialized: {endpoint_id}")
    
    async def start(self):
        """Start agent and connect to all controller MTPs"""
        try:
            # Discover and connect to all controller MTPs
            await self._discover_and_connect_mtps()
            
            # Keep running
            self._logger.info("Agent running, listening on all MTPs...")
            while True:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            self._logger.info("Shutting down...")
            await self._shutdown()
    
    async def _discover_and_connect_mtps(self):
        """Discover all controller MTPs from database and connect"""
        try:
            num_controllers = int(self._db.get("Device.LocalAgent.ControllerNumberOfEntries"))
            
            for ctrl_idx in range(1, num_controllers + 1):
                ctrl_path = f"Device.LocalAgent.Controller.{ctrl_idx}."
                
                # Check if controller is enabled
                enabled = self._db.get(ctrl_path + "Enable")
                if isinstance(enabled, str):
                    enabled = enabled.lower() == "true"
                
                if not enabled:
                    continue
                
                controller_id = self._db.get(ctrl_path + "EndpointID")
                
                # Get controller's MTPs
                num_mtps = int(self._db.get(ctrl_path + "MTPNumberOfEntries"))
                
                for mtp_idx in range(1, num_mtps + 1):
                    mtp_path = f"{ctrl_path}MTP.{mtp_idx}."
                    
                    # Check if MTP is enabled
                    mtp_enabled = self._db.get(mtp_path + "Enable")
                    if isinstance(mtp_enabled, str):
                        mtp_enabled = mtp_enabled.lower() == "true"
                    
                    if not mtp_enabled:
                        continue
                    
                    protocol = self._db.get(mtp_path + "Protocol")
                    
                    # Extract MTP config
                    config = {}
                    if protocol == "WebSocket":
                        config['host'] = self._db.get(mtp_path + "WebSocket.Host")
                        config['port'] = int(self._db.get(mtp_path + "WebSocket.Port"))
                        config['path'] = self._db.get(mtp_path + "WebSocket.Path")
                    elif protocol == "CoAP":
                        config['host'] = self._db.get(mtp_path + "CoAP.Host")
                        config['port'] = int(self._db.get(mtp_path + "CoAP.Port"))
                        config['path'] = self._db.get(mtp_path + "CoAP.Path")
                    elif protocol == "UDS":
                        config['socket_path'] = self._db.get(mtp_path + "UDS.UnixSocketPath")
                    
                    # Create and connect MTP
                    mtp_mgr = MTPConnectionManager(
                        self,
                        controller_id,
                        ctrl_idx,  # Pass controller index for DB lookups
                        protocol,
                        config
                    )
                    
                    if await mtp_mgr.connect():
                        self.mtp_connections.append(mtp_mgr)
                        
                        # Register in controller MTP registry
                        if controller_id not in self.controller_mtps:
                            self.controller_mtps[controller_id] = []
                        self.controller_mtps[controller_id].append(mtp_mgr)
                        
                        self._logger.info(f"✓ Connected to {controller_id} via {protocol}")
                    else:
                        self._logger.warning(f"✗ Failed to connect to {controller_id} via {protocol}")
        
        except Exception as e:
            self._logger.error(f"Error discovering MTPs: {e}", exc_info=True)
    
    async def _shutdown(self):
        """Shutdown all MTP connections"""
        for mtp_mgr in self.mtp_connections:
            await mtp_mgr.disconnect()
    
    # Override respond() to use correct MTP binding from context
    
    async def respond(self, response, context):
        """
        Send response - finds correct MTP binding based on context
        
        Args:
            response: Python response object
            context (RequestContext): Contains writer (MTP connection)
        """
        # Find MTP manager that owns this connection
        mtp_mgr = None
        for mgr in self.mtp_connections:
            if mgr.connection == context.writer:
                mtp_mgr = mgr
                break
        
        if not mtp_mgr:
            self._logger.error(f"No MTP found for response context")
            return
        
        # Set response IDs
        response.from_id = self.endpoint_id
        response.to_id = context.from_id
        
        # Serialize using the MTP's binding
        data = mtp_mgr.binding.serialize_message(response, context.from_id)
        
        # Send on the writer from context (ensures response goes back on correct MTP)
        await self._send_bytes(data, context.writer)
    
    # Implement abstract methods
    
    async def _send_bytes(self, data, writer):
        """
        Send bytes on connection
        
        Args:
            data (bytes): Serialized message
            writer: MTP connection object (websocket, socket, etc.)
        """
        if hasattr(writer, 'send'):
            # WebSocket
            await writer.send(data)
        elif hasattr(writer, 'write'):
            # Stream writer (UDS)
            writer.write(data)
            await writer.drain()
        else:
            self._logger.warning(f"Unknown writer type: {type(writer)}")
    
    async def _send_notification_bytes(self, data, to_id):
        """
        Send notification bytes - route to appropriate MTP
        
        Args:
            data (bytes): Serialized notification
            to_id (str): Controller endpoint ID
        """
        # Find an MTP connection for this controller
        mtps = self.controller_mtps.get(to_id, [])
        
        for mtp_mgr in mtps:
            if mtp_mgr.connected:
                await mtp_mgr.send_notification(data)
                return
        
        self._logger.warning(f"No connected MTP found for controller {to_id}")


async def main():
    """Main entry point"""
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python -m agent.multi_mtp_agent <dm_file> <db_file>")
        sys.exit(1)
    
    dm_file = sys.argv[1]
    db_file = sys.argv[2]
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and start agent
    agent = MultiMTPAgent(dm_file, db_file)
    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
