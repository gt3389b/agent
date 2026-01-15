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
        self._mtp_binding = None  # Set by subclass
        self._current_writer = None  # Connection to send response on
        self._logger = logging.getLogger(self.__class__.__name__)
    
    async def handle_incoming_request(self, request, from_id, to_id, writer):
        """
        Handle incoming request (called by MTP layer)
        
        Args:
            request: Python request object
            from_id (str): Controller endpoint ID
            to_id (str): Agent endpoint ID (should match self.endpoint_id)
            writer: Stream writer for sending response
        """
        self._current_writer = writer
        
        # Store controller ID from request
        controller_id = from_id
        
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
                await self.respond(response, request.from_id)
                
        except Exception as e:
            self._logger.error(f"Error handling request: {e}", exc_info=True)
            # Send error response
            if hasattr(self, '_mtp_binding') and self._mtp_binding:
                error_bytes = self._mtp_binding.create_error_response(request, 9000, str(e))
                await self._send_bytes(error_bytes, writer)
        finally:
            self._current_writer = None
    
    @abstractmethod
    async def on_get_request(self, request):
        """
        Handle Get request
        
        Args:
            request (GetRequest): Request with .paths attribute
            
        Returns:
            GetResponse: Response with .results dict {path: value}
        """
        pass
    
    @abstractmethod
    async def on_set_request(self, request):
        """
        Handle Set request
        
        Args:
            request (SetRequest): Request with .parameters dict
            
        Returns:
            SetResponse: Response with .updated_params and .failed_params
        """
        pass
    
    @abstractmethod
    async def on_operate_request(self, request):
        """
        Handle Operate request
        
        Args:
            request (OperateRequest): Request with .command and .input_args
            
        Returns:
            OperateResponse: Response with .output_args or .error
        """
        pass
    
    @abstractmethod
    async def on_get_supported_dm_request(self, request):
        """
        Handle GetSupportedDM request
        
        Args:
            request (GetSupportedDMRequest): Request with .obj_paths
            
        Returns:
            GetSupportedDMResponse: Response with .supported_objects dict
        """
        pass
    
    @abstractmethod
    async def on_get_instances_request(self, request):
        """
        Handle GetInstances request
        
        Args:
            request (GetInstancesRequest): Request with .obj_paths
            
        Returns:
            GetInstancesResponse: Response with .instances dict
        """
        pass
    
    async def respond(self, response, to_id):
        """
        Send response message
        
        Args:
            response: Python response object
            to_id (str): Destination endpoint ID
        """
        if not self._mtp_binding:
            raise RuntimeError("MTP binding not initialized")
        
        # Set response IDs
        response.from_id = self.endpoint_id
        response.to_id = to_id
        
        # Serialize
        data = self._mtp_binding.serialize_message(response, to_id)
        
        # Send on current connection
        if self._current_writer:
            await self._send_bytes(data, self._current_writer)
        else:
            self._logger.warning("No active connection to send response")
    
    async def notify(self, notification, to_id, controller_socket):
        """
        Send notification to controller
        
        Args:
            notification: Protobuf notification message
            to_id (str): Controller endpoint ID
            controller_socket (str): Path to controller socket
        """
        if not self._mtp_binding:
            raise RuntimeError("MTP binding not initialized")
        
        # Serialize notification
        data = self._mtp_binding.serialize_message(notification, to_id, self.endpoint_id)
        
        # Connect and send (notifications are one-way)
        await self._send_notification_bytes(data, controller_socket)
    
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
    async def _send_notification_bytes(self, data, socket_path):
        """
        Send notification bytes (implemented by subclass)
        
        Args:
            data (bytes): Serialized notification
            socket_path (str): Controller socket path
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
