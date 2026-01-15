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

# File Name: coap_binding.py
#
# Description: CoAP USP Binding
#
# CoAP-specific implementation of USP message binding
"""

import asyncio
import aiocoap
import aiocoap.resource as resource
from mtp.usp_binding import UspBinding


class CoapUspResource(resource.Resource):
    """CoAP resource that handles USP messages"""
    
    def __init__(self, binding):
        """
        Initialize CoAP USP resource
        
        Args:
            binding (CoapUspBinding): Parent binding
        """
        super().__init__()
        self.binding = binding
    
    async def render_post(self, request):
        """Handle POST requests with USP messages"""
        try:
            # Deserialize USP message
            python_msg, from_id, to_id = self.binding.deserialize_bytes(request.payload)
            
            # Call message callback - it will send response via the binding
            if self.binding._message_callback:
                # Store the request so the callback can send response back
                self.binding._current_coap_request = request
                self.binding._coap_response_data = None
                
                await self.binding._message_callback(python_msg, from_id, to_id, request)
                
                # Check if a response was generated
                if self.binding._coap_response_data:
                    return aiocoap.Message(code=aiocoap.CHANGED, payload=self.binding._coap_response_data)
            
            return aiocoap.Message(code=aiocoap.CHANGED)
            
        except Exception as e:
            self.binding._logger.error(f"Error handling CoAP POST: {e}", exc_info=True)
            return aiocoap.Message(code=aiocoap.INTERNAL_SERVER_ERROR)


class CoapUspBinding(UspBinding):
    """CoAP-specific USP Binding"""
    
    def __init__(self, endpoint_id, listen_host='localhost', listen_port=5683, resource_path='usp'):
        """
        Initialize CoAP USP Binding
        
        Args:
            endpoint_id (str): Agent endpoint ID
            listen_host (str): Host to bind to (default: localhost)
            listen_port (int): CoAP listening port
            resource_path (str): CoAP resource path for USP
        """
        super().__init__(endpoint_id)
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.resource_path = resource_path
        self.context = None
        self._message_callback = None
        self._client_context = None
        self._current_coap_request = None  # For capturing CoAP request context
        self._coap_response_data = None     # For capturing response data
    
    async def start_server(self, message_callback):
        """
        Start CoAP server
        
        Args:
            message_callback: Async callback(python_msg, from_id, to_id, request)
        """
        self._message_callback = message_callback
        
        # Create resource tree
        root = resource.Site()
        root.add_resource([self.resource_path], CoapUspResource(self))
        
        # Start CoAP server
        # Use specific host binding instead of '::' which may not work on all systems
        self.context = await aiocoap.Context.create_server_context(
            root,
            bind=(self.listen_host, self.listen_port)
        )
        
        self._logger.info(f"CoAP server listening on {self.listen_host}:{self.listen_port}, resource /{self.resource_path}")
    
    async def connect(self, server_url):
        """
        Create CoAP client context
        
        Args:
            server_url (str): CoAP server URL (e.g., 'coap://localhost/usp')
        """
        self._client_context = await aiocoap.Context.create_client_context()
        self._logger.info(f"CoAP client connected to {server_url}")
    
    async def send_bytes(self, data, destination):
        """
        Send bytes over CoAP
        
        Args:
            data (bytes): Serialized USP Record
            destination: CoAP URL (str) for client mode, or CoAP request object for server response mode
        """
        # Check if we're in server response mode (responding to an incoming request)
        if self._current_coap_request is not None and destination == self._current_coap_request:
            # This is a response to an incoming request - capture it for render_post to return
            self._coap_response_data = data
            self._logger.debug("Captured CoAP response for request")
            return
        
        # Otherwise, we're in client mode - send as a POST request
        if not self._client_context:
            self._client_context = await aiocoap.Context.create_client_context()
        
        request = aiocoap.Message(
            code=aiocoap.POST,
            uri=destination,
            payload=data
        )
        
        response = await self._client_context.request(request).response
        self._logger.debug(f"CoAP POST response: {response.code}")
    
    async def receive_bytes(self):
        """
        Receive bytes from CoAP (not used in server mode)
        
        CoAP server receives via POST handler, not polling
        """
        raise NotImplementedError("CoAP server receives via POST handler")
    
    async def close(self):
        """Shutdown CoAP context"""
        if self.context:
            await self.context.shutdown()
        if self._client_context:
            await self._client_context.shutdown()
