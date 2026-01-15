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

# File Name: base_agent.py
#
# Description: Abstract Base Agent with Clean API
#
# Provides a clean callback-based API for USP agents:
# - on_request() - Handle incoming requests
# - respond() - Send responses
# - notify() - Send notifications
"""

import logging
import asyncio
from abc import ABC, abstractmethod
from message.request import GetRequest, SetRequest, OperateRequest, GetSupportedDMRequest, GetInstancesRequest
from message.response import GetResponse, SetResponse, OperateResponse, GetSupportedDMResponse, GetInstancesResponse

logger = logging.getLogger(__name__)


class RequestContext:
    """
    Encapsulates the context of a USP request
    
    Contains all information needed to send a response back to the controller,
    including the MTP writer and endpoint IDs. This enables proper handling
    of concurrent requests without instance state.
    """
    def __init__(self, from_id, to_id, writer, mtp_type=None):
        self.from_id = from_id      # Controller endpoint ID
        self.to_id = to_id          # Agent endpoint ID
        self.writer = writer        # Where to send response (MTP-specific)
        self.mtp_type = mtp_type    # Optional: 'uds', 'coap', 'websocket', 'stomp'


class BaseAgent(ABC):
    """
    Abstract base class for USP agents
    
    Provides clean callback API that hides USP protocol complexity:
    - Receives Pythonic message objects (not protobuf)
    - Business logic only deals with dicts and simple types
    - MTP handling is abstracted away
    """
    
    def __init__(self, endpoint_id):
        """
        Initialize base agent
        
        Args:
            endpoint_id (str): Agent's USP endpoint ID
        """
        self.endpoint_id = endpoint_id
        self._logger = logging.getLogger(self.__class__.__name__)
        
        # These are set by subclass - don't overwrite if already set
        if not hasattr(self, '_mtp_binding'):
            self._mtp_binding = None
        if not hasattr(self, '_db'):
            self._db = None
        if not hasattr(self, '_data_model'):
            self._data_model = None
    
    async def handle_incoming_request(self, request, from_id, to_id, writer):
        """
        Handle incoming request (called by MTP layer)
        
        Args:
            request: Python request object
            from_id (str): Controller endpoint ID
            to_id (str): Agent endpoint ID (should match self.endpoint_id)
            writer: Stream writer for sending response
        """
        # Create request context
        context = RequestContext(from_id, to_id, writer)
        
        try:
            # Dispatch to appropriate handler based on request type
            if isinstance(request, GetRequest):
                response = await self.on_get_request(request)
            elif isinstance(request, SetRequest):
                response = await self.on_set_request(request)
            elif isinstance(request, OperateRequest):
                response = await self.on_operate_request(request)
            elif isinstance(request, GetSupportedDMRequest):
                response = await self.on_get_supported_dm_request(request)
            elif isinstance(request, GetInstancesRequest):
                response = await self.on_get_instances_request(request)
            else:
                self._logger.warning(f"Unhandled request type: {type(request)}")
                response = None
            
            # Send response if generated
            if response:
                await self.respond(response, context)
                
        except Exception as e:
            self._logger.error(f"Error handling request: {e}", exc_info=True)
            # Send error response
            if hasattr(self, '_mtp_binding') and self._mtp_binding:
                error_bytes = self._mtp_binding.create_error_response(request, 9000, str(e))
                await self._send_bytes(error_bytes, context.writer)
    
    async def on_connect(self):
        """
        Called when agent is connected and ready - sends Boot! notification
        This is MTP-agnostic and should be called by all agent implementations
        after their transport is ready.
        """
        if not self._db:
            self._logger.warning("Database not initialized, skipping Boot! notification")
            return
        
        try:
            from agent import notify
            
            # Get all enabled controllers
            num_controllers = int(self._db.get("Device.LocalAgent.ControllerNumberOfEntries"))
            
            for i in range(1, num_controllers + 1):
                ctrl_path = f"Device.LocalAgent.Controller.{i}."
                
                # Check if controller is enabled
                try:
                    enabled_val = self._db.get(ctrl_path + "Enable")
                    enabled = enabled_val if isinstance(enabled_val, bool) else str(enabled_val).lower() == "true"
                except:
                    enabled = False
                
                if not enabled:
                    continue
                
                controller_id = self._db.get(ctrl_path + "EndpointID")
                
                # Send Boot! notification to this controller
                self._logger.info(f"Sending Boot! notification to {controller_id}")
                
                boot_notif = notify.BootNotification(
                    self.endpoint_id,
                    controller_id,
                    "sub-boot-websocket-ctrl-1",  # Standard subscription ID
                    self._db,
                    self._data_model
                )
                
                notif_msg = boot_notif.generate_notif_msg()
                await self.notify(notif_msg, controller_id)
                
                self._logger.info(f"✓ Boot! notification sent to {controller_id}")
                
        except Exception as e:
            self._logger.error(f"Failed to send Boot! notification: {e}", exc_info=True)
    
    # ===== Default USP Request Handlers =====
    # These provide standard implementations that work for most agents
    # Agents can override these if they need custom behavior
    
    async def on_get_request(self, request):
        """
        Handle Get request - Default implementation queries database
        
        Args:
            request (GetRequest): Request with .paths attribute
            
        Returns:
            GetResponse: Response with .results dict {path: value}
        """
        from message.response import GetResponse
        
        self._logger.info(f"Processing Get request for {len(request.paths)} paths")
        results = {}
        
        for path in request.paths:
            try:
                value = self._db.get(path)
                results[path] = value
                self._logger.debug(f"  {path} = {value}")
            except Exception as e:
                self._logger.warning(f"  {path} - error: {e}")
                results[path] = {'error': (7004, f"Invalid parameter: {path}")}
        
        return GetResponse(msg_id=request.msg_id, results=results)
    
    async def on_set_request(self, request):
        """
        Handle Set request - Default implementation updates database
        
        Args:
            request (SetRequest): Request with .parameters dict
            
        Returns:
            SetResponse: Response with .updated_params and .failed_params
        """
        from message.response import SetResponse
        
        self._logger.info(f"Processing Set request for {len(request.parameters)} parameters")
        updated_params = {}
        failed_params = {}
        
        for path, value in request.parameters.items():
            try:
                self._db.update(path, value)
                updated_params[path] = value
                self._logger.info(f"  ✓ {path} = {value}")
            except Exception as e:
                self._logger.warning(f"  ✗ {path} - error: {e}")
                failed_params[path] = (7004, f"Failed to set {path}: {str(e)}")
        
        return SetResponse(msg_id=request.msg_id, updated_params=updated_params, failed_params=failed_params)
    
    async def on_operate_request(self, request):
        """
        Handle Operate request - Default implementation returns not supported
        
        Args:
            request (OperateRequest): Request with .command and .input_args
            
        Returns:
            OperateResponse: Response with .output_args or .error
        """
        from message.response import OperateResponse
        
        self._logger.info(f"Processing Operate request: {request.command}")
        return OperateResponse(msg_id=request.msg_id, command=request.command, error=(7004, "Command not supported"))
    
    async def on_get_supported_dm_request(self, request):
        """
        Handle GetSupportedDM request - Default implementation uses data model
        
        Args:
            request (GetSupportedDMRequest): Request with .obj_paths
            
        Returns:
            GetSupportedDMResponse: Response with .supported_objects dict
        """
        from message.response import GetSupportedDMResponse
        
        self._logger.info(f"Processing GetSupportedDM request for {request.obj_paths}")
        objects = self._build_data_model_tree(self._data_model)
        supported_objects = {}
        
        for req_path in request.obj_paths:
            if not req_path.endswith('.'):
                req_path += '.'
            
            obj_paths = [p for p in objects.keys() if p.startswith(req_path)]
            self._logger.info(f"  Returning {len(obj_paths)} objects for {req_path}")
            
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
        
        return GetSupportedDMResponse(msg_id=request.msg_id, supported_objects=supported_objects)
    
    async def on_get_instances_request(self, request):
        """
        Handle GetInstances request - Default implementation queries database
        
        Args:
            request (GetInstancesRequest): Request with .obj_paths
            
        Returns:
            GetInstancesResponse: Response with .instances dict
        """
        from message.response import GetInstancesResponse
        
        self._logger.info(f"Processing GetInstances request for {request.obj_paths}")
        instances = {}
        
        for obj_path in request.obj_paths:
            try:
                instance_paths = self._db.find_instances(obj_path)
                instances[obj_path] = instance_paths
                self._logger.info(f"  {obj_path}: {len(instance_paths)} instances")
            except Exception as e:
                self._logger.warning(f"  {obj_path} - error: {e}")
                instances[obj_path] = []
        
        return GetInstancesResponse(msg_id=request.msg_id, instances=instances)
    
    async def respond(self, response, context):
        """
        Send response message
        
        Args:
            response: Python response object
            context (RequestContext): Request context with writer and endpoint IDs
        """
        if not self._mtp_binding:
            raise RuntimeError("MTP binding not initialized")
        
        # Set response IDs
        response.from_id = self.endpoint_id
        response.to_id = context.from_id
        
        # Serialize
        data = self._mtp_binding.serialize_message(response, context.from_id)
        
        # Send on the writer from context (explicit, not instance state)
        await self._send_bytes(data, context.writer)
    
    async def notify(self, notification, to_id):
        """
        Send notification to controller
        
        Args:
            notification: Protobuf notification message
            to_id (str): Controller endpoint ID
        """
        if not self._mtp_binding:
            raise RuntimeError("MTP binding not initialized")
        
        # Serialize notification
        data = self._mtp_binding.serialize_message(notification, to_id, self.endpoint_id)
        
        # Send via MTP-specific implementation (routing handled by subclass)
        await self._send_notification_bytes(data, to_id)
    
    @abstractmethod
    async def _send_bytes(self, data, writer):
        """
        Send bytes on connection (implemented by subclass)
        
        Args:
            data (bytes): Serialized message
            writer: Stream writer
        """
        pass
    
    @abstractmethod
    async def _send_notification_bytes(self, data, to_id):
        """
        Send notification bytes (implemented by subclass)
        
        Args:
            data (bytes): Serialized notification
            to_id (str): Controller endpoint ID (routing handled by subclass)
        """
        pass
    
    # ===== Common Data Model Helpers =====
    
    def _load_data_model(self, dm_file):
        """Load data model from JSON file"""
        import json
        try:
            with open(dm_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self._logger.error(f"Failed to load data model from {dm_file}: {e}")
            return {}
    
    def _build_data_model_tree(self, data_model):
        """Build hierarchical tree from flat dm.json structure"""
        objects = {}
        
        for path, access in data_model.items():
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
