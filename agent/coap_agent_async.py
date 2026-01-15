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

# File Name: coap_agent_async.py
#
# Description: Async CoAP USP Agent using new 3-layer architecture
#
"""

import logging
import asyncio

from agent.base_agent import BaseAgent
from agent import agent_db
from agent import notify
from mtp.coap_binding import CoapUspBinding
from message.request import GetRequest, SetRequest, OperateRequest, GetSupportedDMRequest, GetInstancesRequest
from message.response import GetResponse, SetResponse, OperateResponse, GetSupportedDMResponse, GetInstancesResponse

logger = logging.getLogger(__name__)


class CoapAgent(BaseAgent):
    """Async CoAP-based USP Agent using new architecture"""
    
    def __init__(self, dm_file, db_file, cfg_file='cfg/agent.json'):
        """
        Initialize Async CoAP Agent
        
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
        
        # Find CoAP MTP configuration
        mtp_path, host, port, resource_path = self._find_coap_mtp()
        
        # Create CoAP binding with host and port
        self._mtp_binding = CoapUspBinding(agent_id, host, port, resource_path)
        
        logger.info(f"Async CoAP Agent initialized: {agent_id}")
        logger.info(f"  Host: {host}, Port: {port}, Path: /{resource_path}")
        
        self._host = host
        self._port = port
        self._resource_path = resource_path
        self._periodic_tasks = []  # List of periodic notification tasks
        self._subscription_handlers = {}  # Track active subscription handlers
        
        # Load data model for GetSupportedDM responses
        self._dm_file = dm_file
        self._data_model = self._load_data_model(dm_file)
        
    def _find_coap_mtp(self):
        """Find CoAP MTP configuration"""
        num_mtps = int(self._db.get("Device.LocalAgent.MTPNumberOfEntries"))
        
        for i in range(1, num_mtps + 1):
            mtp_path = f"Device.LocalAgent.MTP.{i}."
            protocol = self._db.get(mtp_path + "Protocol")
            
            if protocol == "CoAP":
                host = self._db.get(mtp_path + "CoAP.Host")
                port = int(self._db.get(mtp_path + "CoAP.Port"))
                path = self._db.get(mtp_path + "CoAP.Path")
                
                logger.info(f"Found CoAP MTP: {host}:{port}/{path}")
                return mtp_path, host, port, path
        
        raise ValueError("No CoAP MTP found in database")
    
    async def start(self):
        """Start the async CoAP agent"""
        logger.info(f"Agent starting on {self._host}:{self._port}/{self._resource_path}")
        
        # IMPORTANT: Start CoAP server FIRST before sending Boot! notification
        # This ensures the agent is ready to receive controller requests
        await self._mtp_binding.start_server(self.handle_incoming_request)
        logger.info(f"✓ CoAP server listening on {self._host}:{self._port}/{self._resource_path}")
        
        # Now initialize subscriptions and send Boot! notification
        # Controller can now immediately query the agent
        await self._init_subscriptions()
        
        logger.info("Agent ready - waiting for controller messages...")
        
        # Keep server running forever
        await asyncio.Event().wait()
    
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
        logger.info(f"  Input args: {request.input_args}")
        
        # Parse command path
        if request.command.endswith(')'):
            command_path = request.command[:-2]
        else:
            command_path = request.command
        
        parts = command_path.rsplit('.', 1)
        if len(parts) == 2:
            obj_path, cmd_name = parts
            obj_path += '.'
        else:
            return OperateResponse(
                msg_id=request.msg_id,
                command=request.command,
                error=(7004, f"Invalid command path: {request.command}")
            )
        
        # Handle Device.Reboot()
        if command_path == "Device.Reboot":
            logger.info("Executing Device.Reboot() command...")
            
            # Schedule the reboot asynchronously
            asyncio.create_task(self._perform_reboot())
            
            return OperateResponse(
                msg_id=request.msg_id,
                command=request.command,
                output_args={}
            )
        
        # Unknown command
        return OperateResponse(
            msg_id=request.msg_id,
            command=request.command,
            error=(7004, f"Command not supported: {request.command}")
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
        
        objects = self._build_data_model_tree()
        supported_objects = {}
        
        for req_path in request.obj_paths:
            if not req_path.endswith('.'):
                req_path += '.'
            
            if request.first_level_only:
                obj_paths = self._get_first_level_children(req_path, objects)
            else:
                obj_paths = [p for p in objects.keys() if p.startswith(req_path)]
            
            logger.info(f"  Returning {len(obj_paths)} objects for {req_path}")
            
            for obj_path in obj_paths:
                obj_data = objects.get(obj_path, {})
                
                parameters = {}
                if request.return_params:
                    for param_name, access in obj_data.get('params', {}).items():
                        parameters[param_name] = {
                            'access': 'read-write' if access == 'readWrite' else 'read-only',
                            'type': 'string'
                        }
                
                supported_objects[obj_path] = {
                    'access': 'read-only',
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
        return super()._build_data_model_tree(self._data_model)
    
    # ===== BaseAgent transport method implementations =====
    
    async def _send_bytes(self, data, writer):
        """
        Send bytes on connection
        
        For CoAP, the writer is the CoAP request object that we need to respond to
        """
        await self._mtp_binding.send_bytes(data, writer)
    
    async def _send_notification_bytes(self, data, coap_url):
        """
        Send notification bytes to controller
        
        Args:
            data (bytes): Serialized USP Record
            coap_url (str): CoAP URL (e.g., 'coap://localhost:5683/usp')
        """
        await self._mtp_binding.send_bytes(data, coap_url)
    
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
        
        # Find matching CoAP MTP for this controller
        mtp_info = self._find_controller_coap_mtp(recipient_path)
        if not mtp_info:
            logger.warning(f"Skipping Subscription [{subscription_id}] - no enabled CoAP MTP found")
            return
        
        mtp_path, coap_url = mtp_info
        
        # Handle based on notification type
        if notif_type == "Event":
            await self._handle_event_subscription(
                subscription_path, subscription_id, controller_id, coap_url, mtp_path
            )
        elif notif_type == "ValueChange":
            logger.warning(f"Subscription [{subscription_id}] - ValueChange not implemented yet")
        else:
            logger.warning(f"Subscription [{subscription_id}] - unsupported NotifType: {notif_type}")
    
    def _find_controller_coap_mtp(self, controller_path):
        """Find enabled CoAP MTP for a controller"""
        try:
            mtp_instances = self._db.find_instances(controller_path + "MTP.")
            
            for mtp_path in mtp_instances:
                if self._db.get(mtp_path + "Enable"):
                    protocol = self._db.get(mtp_path + "Protocol")
                    
                    if protocol == "CoAP":
                        host = self._db.get(mtp_path + "CoAP.Host")
                        port = self._db.get(mtp_path + "CoAP.Port")
                        path = self._db.get(mtp_path + "CoAP.Path")
                        coap_url = f"coap://{host}:{port}/{path}"
                        return (mtp_path, coap_url)
            
            return None
        except Exception as e:
            logger.error(f"Error finding controller MTP: {e}")
            return None
    
    async def _handle_event_subscription(self, subscription_path, subscription_id, 
                                        controller_id, coap_url, mtp_path):
        """Handle Event-type subscription (Boot!, Periodic!)"""
        ref_list = self._db.get(subscription_path + "ReferenceList")
        ref_events = [e.strip() for e in ref_list.split(",") if e.strip()]
        
        for event_path in ref_events:
            if event_path == "Device.Boot!":
                # Send Boot! notification immediately
                await self._send_boot_notification(subscription_id, controller_id, coap_url)
                
            elif event_path == "Device.LocalAgent.Periodic!":
                # Start periodic notification task
                recipient_path = self._db.get(subscription_path + "Recipient")
                task = asyncio.create_task(
                    self._periodic_notification_loop(
                        subscription_id, recipient_path, controller_id, coap_url
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
    
    async def _send_boot_notification(self, subscription_id, controller_id, coap_url):
        """Send Boot! notification to controller"""
        try:
            logger.info(f"Sending Boot! notification to {coap_url}")
            logger.info(f"  Subscription: {subscription_id}, Controller: {controller_id}")
            
            # Create Boot notification
            boot_notif = notify.BootNotification(
                self.endpoint_id,
                controller_id,
                subscription_id,
                self._db,
                self._data_model
            )
            
            # Generate notification message
            notif_msg = boot_notif.generate_notif_msg()
            
            # Send via binding
            await self.notify(notif_msg, controller_id, coap_url)
            
            logger.info("✓ Boot! notification sent successfully")
            
        except Exception as e:
            logger.warning(f"Controller not available at {coap_url}: {e}")
    
    # ===== Periodic Notifications =====
    
    async def _periodic_notification_loop(self, subscription_id, recipient_path, 
                                         controller_id, coap_url):
        """
        Send periodic notifications at configured interval for a specific subscription
        
        Args:
            subscription_id (str): Subscription ID
            recipient_path (str): Path to controller (e.g., Device.LocalAgent.Controller.1.)
            controller_id (str): Controller endpoint ID
            coap_url (str): CoAP URL for controller (e.g., 'coap://localhost:5683/usp')
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
                            subscription_id, controller_id, coap_url
                        )
                        
                        # Wait for the interval
                        await asyncio.sleep(interval)
                    else:
                        # If interval is 0, periodic notifications are disabled
                        logger.info(f"Periodic notifications disabled for [{subscription_id}] (interval=0)")
                        await asyncio.sleep(10)
                        
                except agent_db.NoSuchPathError:
                    logger.error(f"Periodic interval parameter not found: {interval_param}")
                    break
                except Exception as e:
                    logger.error(f"Error in periodic loop for [{subscription_id}]: {e}", exc_info=True)
                    await asyncio.sleep(30)
                    
        except asyncio.CancelledError:
            logger.info(f"Periodic notification task cancelled for [{subscription_id}]")
        except Exception as e:
            logger.error(f"Fatal error in periodic notification loop: {e}", exc_info=True)
    
    async def _send_periodic_notification(self, subscription_id, controller_id, coap_url):
        """Send Periodic! notification to controller"""
        try:
            logger.info(f"Sending Periodic! notification to controller...")
            logger.info(f"  Subscription: {subscription_id}, Controller: {controller_id}")
            
            # Create Periodic notification
            periodic_notif = notify.PeriodicNotification(
                self.endpoint_id,
                controller_id,
                subscription_id,
                self._data_model
            )
            
            # Generate notification message
            notif_msg = periodic_notif.generate_notif_msg()
            
            # Send via notify method
            await self.notify(notif_msg, controller_id, coap_url)
            
            logger.info("✓ Periodic! notification sent successfully")
            
        except Exception as e:
            logger.warning(f"Controller not available at {coap_url}: {e}")
    
    async def _perform_reboot(self):
        """
        Perform agent reboot - restart with fresh subscription handlers
        
        This simulates a device reboot by:
        1. Stopping periodic tasks
        2. Clearing subscription handlers
        3. Re-initializing subscriptions (which will re-send Boot! events)
        """
        try:
            logger.info("=" * 60)
            logger.info("REBOOT: Agent restarting...")
            logger.info("=" * 60)
            
            # Give response time to be sent
            await asyncio.sleep(0.5)
            
            # Step 1: Cancel all periodic notification tasks
            logger.info("REBOOT: Cancelling periodic tasks...")
            for task in self._periodic_tasks:
                task.cancel()
            
            # Wait for cancellation to complete
            if self._periodic_tasks:
                await asyncio.gather(*self._periodic_tasks, return_exceptions=True)
            
            # Step 2: Clear subscription handlers
            self._periodic_tasks.clear()
            self._subscription_handlers.clear()
            logger.info("REBOOT: Cleared subscription handlers")
            
            # Step 3: Re-initialize subscriptions (this will re-send Boot! events)
            logger.info("REBOOT: Re-initializing subscriptions...")
            await self._init_subscriptions()
            
            logger.info("=" * 60)
            logger.info("REBOOT: Agent restart complete!")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"Error during reboot: {e}", exc_info=True)
    
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
