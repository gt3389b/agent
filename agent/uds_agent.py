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

# File Name: uds_agent_new.py
#
# Description: Refactored Async UDS USP Agent using new 3-layer architecture
#
"""

import logging
import asyncio
import json

from agent.base_agent import BaseAgent
from agent import agent_db
from agent import notify
from mtp.uds_binding import UdsUspBinding
from mtp.uds import UdsTransport
from message.request import GetRequest, SetRequest, OperateRequest, GetSupportedDMRequest, GetInstancesRequest
from message.response import GetResponse, SetResponse, OperateResponse, GetSupportedDMResponse, GetInstancesResponse
from message import usp_msg_pb2

logger = logging.getLogger(__name__)


class UdsAgent(BaseAgent):
    """Async UDS-based USP Agent using new architecture"""
    
    def __init__(self, dm_file, db_file, cfg_file='cfg/agent.json'):
        """
        Initialize Async UDS Agent
        
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
        
        # Find UDS MTP configuration
        mtp_path, socket_path, mode = self._find_uds_mtp()
        
        # Create UDS binding
        self._mtp_binding = UdsUspBinding(agent_id, socket_path, mode)
        
        logger.info(f"Async UDS Agent initialized: {agent_id}")
        logger.info(f"  Socket: {socket_path} (mode={mode})")
        
        self._socket_path = socket_path
        self._mode = mode
        self._periodic_tasks = []  # List of periodic notification tasks
        self._subscription_handlers = {}  # Track active subscription handlers
        
        # Load data model for GetSupportedDM responses
        self._dm_file = dm_file
        self._data_model = self._load_data_model(dm_file)
        
    def _find_uds_mtp(self):
        """Find UDS MTP configuration"""
        num_mtps = int(self._db.get("Device.LocalAgent.MTPNumberOfEntries"))
        
        for i in range(1, num_mtps + 1):
            mtp_path = f"Device.LocalAgent.MTP.{i}."
            protocol = self._db.get(mtp_path + "Protocol")
            
            if protocol == "UDS":
                socket_path = self._db.get(mtp_path + "UDS.UnixSocketPath")
                
                # Get mode from Device.UDS.UnixSocket table (optional)
                mode = "listen"  # Default
                try:
                    num_sockets = int(self._db.get("Device.UDS.UnixSocketNumberOfEntries"))
                    for j in range(1, num_sockets + 1):
                        sock_path = self._db.get(f"Device.UDS.UnixSocket.{j}.Path")
                        if sock_path == socket_path:
                            mode = self._db.get(f"Device.UDS.UnixSocket.{j}.Mode")
                            if mode:
                                mode = mode.lower()
                            break
                except:
                    pass
                
                logger.info(f"Found UDS MTP: socket={socket_path}")
                return mtp_path, socket_path, mode
        
        raise ValueError("No UDS MTP found in database")
    
    def _load_data_model(self, dm_file):
        """Load data model from JSON file"""
        try:
            with open(dm_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load data model from {dm_file}: {e}")
            return {}
    
    async def start(self):
        """Start the async UDS agent"""
        logger.info(f"Agent starting on {self._socket_path}")
        
        # Initialize subscriptions and start handlers
        await self._init_subscriptions()
        
        # Start listening for controller messages
        await self._mtp_binding.start_server(self.handle_incoming_request)
        
        logger.info("Agent listening for controller messages...")
        
        # Keep server running
        async with self._mtp_binding.transport.server:
            await self._mtp_binding.transport.server.serve_forever()
    
    async def send_boot_notification(self):
        """Send Boot! notification to controller"""
        try:
            logger.info(f"Sending Boot! notification to {self._controller_socket}")
            
            # Create Boot notification
            boot_notif = notify.BootNotification(
                self.endpoint_id,
                self._controller_id,
                "sub-boot-uds-ctrl-1",
                self._db
            )
            
            # Generate notification message
            notif_msg = boot_notif.generate_notif_msg()
            
            # Send via binding
            await self.notify(notif_msg, self._controller_id, self._controller_socket)
            
            logger.info("✓ Boot! notification sent successfully")
            
        except Exception as e:
            logger.error(f"Failed to send Boot notification: {e}", exc_info=True)
    
    # ===== BaseAgent callback implementations =====
    
    async def on_get_request(self, request):
        """
        Handle Get request - query parameter values
        
        Args:
            request (GetRequest): Request with .paths list
            
        Returns:
            GetResponse: Response with .results dict
        """
        logger.info(f"Processing Get request for {len(request.paths)} paths")
        
        results = {}
        
        for path in request.paths:
            try:
                # Simple path lookup - could be enhanced with wildcard/partial path support
                value = self._db.get(path)
                results[path] = value
                logger.debug(f"  {path} = {value}")
            except Exception as e:
                logger.warning(f"  {path} - error: {e}")
                results[path] = {'error': (7004, f"Invalid parameter: {path}")}
        
        return GetResponse(
            msg_id=request.msg_id,
            results=results
        )
    
    async def on_set_request(self, request):
        """
        Handle Set request - update parameter values
        
        Args:
            request (SetRequest): Request with .parameters dict
            
        Returns:
            SetResponse: Response with .updated_params and .failed_params
        """
        logger.info(f"Processing Set request for {len(request.parameters)} parameters")
        
        updated_params = {}
        failed_params = {}
        
        for path, value in request.parameters.items():
            try:
                # Update in database
                self._db.update(path, value)
                updated_params[path] = value
                logger.info(f"  ✓ {path} = {value}")
            except Exception as e:
                logger.warning(f"  ✗ {path} - error: {e}")
                failed_params[path] = (7004, f"Failed to set {path}: {str(e)}")
        
        return SetResponse(
            msg_id=request.msg_id,
            updated_params=updated_params,
            failed_params=failed_params
        )
    
    async def on_operate_request(self, request):
        """
        Handle Operate request - invoke command
        
        Args:
            request (OperateRequest): Request with .command and .input_args
            
        Returns:
            OperateResponse: Response with .output_args or .error
        """
        logger.info(f"Processing Operate request: {request.command}")
        
        # Stub - command execution not implemented yet
        return OperateResponse(
            msg_id=request.msg_id,
            command=request.command,
            error=(7004, "Command execution not implemented")
        )
    
    async def on_get_supported_dm_request(self, request):
        """
        Handle GetSupportedDM request - query data model structure
        
        Args:
            request (GetSupportedDMRequest): Request with .obj_paths
            
        Returns:
            GetSupportedDMResponse: Response with .supported_objects dict
        """
        logger.info(f"Processing GetSupportedDM request for {request.obj_paths}")
        logger.info(f"  first_level_only={request.first_level_only}, return_params={request.return_params}")
        
        # Build data model tree
        objects = self._build_data_model_tree()
        
        supported_objects = {}
        
        for req_path in request.obj_paths:
            # Normalize path
            if not req_path.endswith('.'):
                req_path += '.'
            
            # Get objects to return
            if request.first_level_only:
                obj_paths = self._get_first_level_children(req_path, objects)
            else:
                obj_paths = [p for p in objects.keys() if p.startswith(req_path)]
            
            logger.info(f"  Returning {len(obj_paths)} objects for {req_path}")
            
            # Build supported objects
            for obj_path in obj_paths:
                obj_data = objects.get(obj_path, {})
                
                # Convert parameters to response format
                parameters = {}
                if request.return_params:
                    for param_name, access in obj_data.get('params', {}).items():
                        parameters[param_name] = {
                            'access': 'read-write' if access == 'readWrite' else 'read-only',
                            'type': 'string'
                        }
                
                supported_objects[obj_path] = {
                    'access': 'read-only',  # Simplified - no add/delete support yet
                    'is_multi_instance': obj_data.get('is_multi_instance', False),
                    'parameters': parameters
                }
        
        return GetSupportedDMResponse(
            msg_id=request.msg_id,
            supported_objects=supported_objects
        )
    
    async def on_get_instances_request(self, request):
        """
        Handle GetInstances request - query object instances
        
        Args:
            request (GetInstancesRequest): Request with .obj_paths
            
        Returns:
            GetInstancesResponse: Response with .instances dict
        """
        logger.info(f"Processing GetInstances request for {request.obj_paths}")
        
        instances = {}
        
        for obj_path in request.obj_paths:
            try:
                # Query database for instances
                instance_paths = self._db.find_instances(obj_path)
                instances[obj_path] = instance_paths
                logger.info(f"  {obj_path}: {len(instance_paths)} instances")
            except Exception as e:
                logger.warning(f"  {obj_path} - error: {e}")
                instances[obj_path] = []
        
        return GetInstancesResponse(
            msg_id=request.msg_id,
            instances=instances
        )
    
    # ===== Data model helpers =====
    
    def _build_data_model_tree(self):
        """Build hierarchical tree from flat dm.json structure"""
        objects = {}
        
        for path, access in self._data_model.items():
            # Split path into components
            parts = path.split('.')
            
            # Build object path (everything except last component)
            obj_path = '.'.join(parts[:-1]) + '.'
            param_name = parts[-1]
            
            if obj_path not in objects:
                objects[obj_path] = {
                    'params': {},
                    'is_multi_instance': False,
                    'children': set()
                }
            
            # Add parameter
            objects[obj_path]['params'][param_name] = access
            
            # Check if this path contains {i} (multi-instance marker)
            if '{i}' in path:
                for i, part in enumerate(parts):
                    if '{i}' in part:
                        mi_obj_path = '.'.join(parts[:i+1]) + '.'
                        if mi_obj_path not in objects:
                            objects[mi_obj_path] = {
                                'params': {},
                                'is_multi_instance': True,
                                'children': set()
                            }
                        else:
                            objects[mi_obj_path]['is_multi_instance'] = True
                        break
        
        return objects
    
    def _get_first_level_children(self, obj_path, objects):
        """Get immediate child objects of a given path"""
        children = set()
        
        # Normalize path
        if not obj_path.endswith('.'):
            obj_path += '.'
        
        # Count depth of requested path
        requested_depth = obj_path.count('.')
        
        for path in objects.keys():
            # Check if this is a child of requested path
            if path.startswith(obj_path) and path != obj_path:
                # Count depth
                path_depth = path.count('.')
                
                # First level means exactly one level deeper
                if path_depth == requested_depth + 1:
                    children.add(path)
        
        return sorted(children)
    
    # ===== BaseAgent transport method implementations =====
    
    async def _send_bytes(self, data, writer):
        """Send bytes on connection"""
        await self._mtp_binding.send_bytes(data, writer)
    
    async def _send_notification_bytes(self, data, socket_path):
        """Send notification bytes to controller"""
        # Create temporary connection for notification
        temp_transport = UdsTransport(socket_path, 'connect')
        try:
            await temp_transport.connect()
            await temp_transport.send_message(data)
        finally:
            await temp_transport.close()
    
    # ===== Subscription Management =====
    
    async def _init_subscriptions(self):
        """Initialize and start handlers for all enabled subscriptions"""
        logger.info("Initializing subscriptions...")
        
        try:
            subscription_instances = self._db.find_instances("Device.LocalAgent.Subscription.")
            
            for sub_path in subscription_instances:
                if self._db.get(sub_path + "Enable"):
                    await self._handle_subscription(sub_path)
                else:
                    subscription_id = self._db.get(sub_path + "ID")
                    logger.info(f"Skipping disabled Subscription [{subscription_id}]")
                    
        except Exception as e:
            logger.error(f"Error initializing subscriptions: {e}", exc_info=True)
    
    async def _handle_subscription(self, subscription_path):
        """Handle a single subscription - start appropriate notification handler"""
        subscription_id = self._db.get(subscription_path + "ID")
        notif_type = self._db.get(subscription_path + "NotifType")
        recipient_path = self._db.get(subscription_path + "Recipient")
        
        logger.info(f"Processing Subscription [{subscription_id}], Type: {notif_type}")
        
        # Check if controller is enabled
        if not self._db.get(recipient_path + "Enable"):
            logger.warning(f"Skipping Subscription [{subscription_id}] - controller is disabled")
            return
        
        # Get controller details
        controller_id = self._db.get(recipient_path + "EndpointID")
        
        # Find matching UDS MTP for this controller
        mtp_info = self._find_controller_uds_mtp(recipient_path)
        if not mtp_info:
            logger.warning(f"Skipping Subscription [{subscription_id}] - no enabled UDS MTP found")
            return
        
        mtp_path, socket_path = mtp_info
        
        # Handle based on notification type
        if notif_type == "Event":
            await self._handle_event_subscription(
                subscription_path, subscription_id, controller_id, socket_path, mtp_path
            )
        elif notif_type == "ValueChange":
            logger.warning(f"Subscription [{subscription_id}] - ValueChange not implemented yet")
        else:
            logger.warning(f"Subscription [{subscription_id}] - unsupported NotifType: {notif_type}")
    
    def _find_controller_uds_mtp(self, controller_path):
        """Find enabled UDS MTP for a controller"""
        try:
            mtp_instances = self._db.find_instances(controller_path + "MTP.")
            
            for mtp_path in mtp_instances:
                if self._db.get(mtp_path + "Enable"):
                    protocol = self._db.get(mtp_path + "Protocol")
                    
                    if protocol == "UDS":
                        socket_path = self._db.get(mtp_path + "UDS.UnixSocketPath")
                        return (mtp_path, socket_path)
            
            return None
        except Exception as e:
            logger.error(f"Error finding controller MTP: {e}")
            return None
    
    async def _handle_event_subscription(self, subscription_path, subscription_id, 
                                        controller_id, controller_socket, mtp_path):
        """Handle Event-type subscription (Boot!, Periodic!)"""
        ref_list = self._db.get(subscription_path + "ReferenceList")
        ref_events = [e.strip() for e in ref_list.split(",") if e.strip()]
        
        for event_path in ref_events:
            if event_path == "Device.Boot!":
                # Send Boot! notification immediately
                await self._send_boot_notification(subscription_id, controller_id, controller_socket)
                
            elif event_path == "Device.LocalAgent.Periodic!":
                # Start periodic notification task
                recipient_path = self._db.get(subscription_path + "Recipient")
                task = asyncio.create_task(
                    self._periodic_notification_loop(
                        subscription_id, recipient_path, controller_id, controller_socket
                    )
                )
                self._periodic_tasks.append(task)
                self._subscription_handlers[subscription_id] = {
                    'type': 'periodic',
                    'task': task,
                    'controller_id': controller_id
                }
                logger.info(f"Started Periodic! handler for Subscription [{subscription_id}]")
                
            else:
                logger.warning(f"Subscription [{subscription_id}] - unsupported event: {event_path}")
    
    async def _send_boot_notification(self, subscription_id, controller_id, controller_socket):
        """Send Boot! notification to controller"""
        try:
            logger.info(f"Sending Boot! notification to {controller_socket}")
            logger.info(f"  Subscription: {subscription_id}, Controller: {controller_id}")
            
            # Create Boot notification
            boot_notif = notify.BootNotification(
                self.endpoint_id,
                controller_id,
                subscription_id,
                self._db
            )
            
            # Generate notification message
            notif_msg = boot_notif.generate_notif_msg()
            
            # Send via binding
            await self.notify(notif_msg, controller_id, controller_socket)
            
            logger.info("✓ Boot! notification sent successfully")
            
        except Exception as e:
            logger.error(f"Failed to send Boot notification: {e}", exc_info=True)
    
    # ===== Periodic Notifications =====
    
    async def _periodic_notification_loop(self, subscription_id, recipient_path, 
                                         controller_id, controller_socket):
        """
        Send periodic notifications at configured interval for a specific subscription
        
        Args:
            subscription_id (str): Subscription ID
            recipient_path (str): Path to controller (e.g., Device.LocalAgent.Controller.1.)
            controller_id (str): Controller endpoint ID
            controller_socket (str): UDS socket path for controller
        """
        interval_param = recipient_path + "PeriodicNotifInterval"
        
        try:
            # Wait a moment for everything to initialize
            await asyncio.sleep(1)
            
            while True:
                try:
                    # Get current interval from database
                    interval_str = self._db.get(interval_param)
                    interval = int(interval_str) if interval_str else 30
                    
                    if interval > 0:
                        # Send periodic notification
                        await self._send_periodic_notification(
                            subscription_id, controller_id, controller_socket
                        )
                        
                        # Wait for the interval
                        await asyncio.sleep(interval)
                    else:
                        # If interval is 0, periodic notifications are disabled
                        logger.info(f"Periodic notifications disabled for [{subscription_id}] (interval=0)")
                        await asyncio.sleep(10)  # Check again in 10 seconds
                        
                except agent_db.NoSuchPathError:
                    logger.error(f"Periodic interval parameter not found: {interval_param}")
                    break
                except Exception as e:
                    logger.error(f"Error in periodic loop for [{subscription_id}]: {e}", exc_info=True)
                    await asyncio.sleep(30)  # Wait and retry
                    
        except asyncio.CancelledError:
            logger.info(f"Periodic notification task cancelled for [{subscription_id}]")
        except Exception as e:
            logger.error(f"Fatal error in periodic notification loop: {e}", exc_info=True)
    
    async def _send_periodic_notification(self, subscription_id, controller_id, controller_socket):
        """Send Periodic! notification to controller"""
        try:
            logger.info(f"Sending Periodic! notification to controller...")
            logger.info(f"  Subscription: {subscription_id}, Controller: {controller_id}")
            
            # Create Periodic notification
            periodic_notif = notify.PeriodicNotification(
                self.endpoint_id,
                controller_id,
                subscription_id,
                self._db
            )
            
            # Generate notification message
            notif_msg = periodic_notif.generate_notif_msg()
            
            # Send via notify method
            await self.notify(notif_msg, controller_id, controller_socket)
            
            logger.info("✓ Periodic! notification sent successfully")
            
        except Exception as e:
            logger.error(f"Failed to send Periodic notification: {e}", exc_info=True)
    
    async def stop(self):
        """Stop the agent and clean up"""
        logger.info("Stopping agent...")
        
        # Cancel all periodic tasks
        for task in self._periodic_tasks:
            task.cancel()
        
        # Wait for all tasks to complete
        if self._periodic_tasks:
            await asyncio.gather(*self._periodic_tasks, return_exceptions=True)
            
        if self._mtp_binding:
            await self._mtp_binding.close()
        
        logger.info("Agent stopped")
