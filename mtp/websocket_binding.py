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

# File Name: websocket_binding.py
#
# Description: WebSocket USP Binding
#
# WebSocket-specific implementation of USP message binding
"""

import asyncio
import websockets
from websockets.server import serve
from mtp.usp_binding import UspBinding


class WebSocketUspBinding(UspBinding):
    """WebSocket-specific USP Binding"""
    
    def __init__(self, endpoint_id, listen_host='localhost', listen_port=8080, resource_path='/usp'):
        """
        Initialize WebSocket USP Binding
        
        Args:
            endpoint_id (str): Agent endpoint ID
            listen_host (str): Host to bind to (default: localhost)
            listen_port (int): WebSocket listening port (default: 8080)
            resource_path (str): WebSocket path for USP (default: /usp)
        """
        super().__init__(endpoint_id)
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.resource_path = resource_path
        self.server = None
        self.client_websocket = None  # For client mode
        self._message_callback = None
        self._current_websocket = None  # For capturing WebSocket context in server mode
    
    async def start_server(self, message_callback):
        """
        Start WebSocket server
        
        Args:
            message_callback: Async callback(python_msg, from_id, to_id, websocket)
        """
        self._message_callback = message_callback
        
        async def handle_connection(websocket):
            """Handle WebSocket connection"""
            try:
                self._logger.info(f"WebSocket client connected from {websocket.remote_address}")
                
                async for message in websocket:
                    try:
                        # Deserialize USP message
                        python_msg, from_id, to_id = self.deserialize_bytes(message)
                        
                        # Store current websocket for response
                        self._current_websocket = websocket
                        
                        # Call message callback - it will send response via the binding
                        if self._message_callback:
                            await self._message_callback(python_msg, from_id, to_id, websocket)
                        
                    except Exception as e:
                        self._logger.error(f"Error handling WebSocket message: {e}", exc_info=True)
                
            except websockets.exceptions.ConnectionClosed:
                self._logger.info(f"WebSocket client disconnected from {websocket.remote_address}")
            except Exception as e:
                self._logger.error(f"WebSocket connection error: {e}", exc_info=True)
        
        # Start WebSocket server
        self.server = await serve(
            handle_connection,
            self.listen_host,
            self.listen_port,
            subprotocols=['v1.usp']
        )
        
        self._logger.info(f"WebSocket server listening on ws://{self.listen_host}:{self.listen_port}{self.resource_path}")
    
    async def connect(self, server_url):
        """
        Connect to WebSocket server (client mode)
        
        Args:
            server_url (str): WebSocket server URL (e.g., 'ws://localhost:8080/usp')
        """
        try:
            self.client_websocket = await websockets.connect(
                server_url,
                subprotocols=['v1.usp']
            )
            self._logger.info(f"WebSocket client connected to {server_url}")
            
            # Start receive loop
            asyncio.create_task(self._receive_loop())
            
        except Exception as e:
            self._logger.error(f"Failed to connect to WebSocket server: {e}", exc_info=True)
            raise
    
    async def _receive_loop(self):
        """Receive loop for client mode"""
        try:
            async for message in self.client_websocket:
                try:
                    # Deserialize USP message
                    python_msg, from_id, to_id = self.deserialize_bytes(message)
                    
                    # Call message callback
                    if self._message_callback:
                        await self._message_callback(python_msg, from_id, to_id, None)
                
                except Exception as e:
                    self._logger.error(f"Error in WebSocket receive loop: {e}", exc_info=True)
        
        except websockets.exceptions.ConnectionClosed:
            self._logger.info("WebSocket connection closed")
        except Exception as e:
            self._logger.error(f"WebSocket receive loop error: {e}", exc_info=True)
    
    async def send_bytes(self, data, destination):
        """
        Send bytes over WebSocket
        
        Args:
            data (bytes): Serialized USP Record
            destination: WebSocket connection object for server mode, or URL (str) for client mode
        """
        try:
            # Check if we're in server response mode (responding to an incoming request)
            if hasattr(destination, 'send') and hasattr(destination, 'remote_address'):
                # This is a WebSocket connection object - send response
                await destination.send(data)
                self._logger.debug(f"Sent {len(data)} bytes via WebSocket to {destination.remote_address}")
            else:
                # Client mode - use the connected client websocket
                if not self.client_websocket:
                    raise RuntimeError("Not connected to WebSocket server")
                
                await self.client_websocket.send(data)
                self._logger.debug(f"Sent {len(data)} bytes via WebSocket client")
        
        except Exception as e:
            self._logger.error(f"Error sending WebSocket message: {e}", exc_info=True)
            raise
    
    async def receive_bytes(self):
        """
        Receive bytes from WebSocket (client mode)
        
        Returns:
            bytes: Received data
        """
        if not self.client_websocket:
            raise RuntimeError("Not connected to WebSocket server")
        
        message = await self.client_websocket.recv()
        return message
    
    async def close(self):
        """Close WebSocket connection"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self._logger.info("WebSocket server closed")
        
        if self.client_websocket:
            await self.client_websocket.close()
            self._logger.info("WebSocket client connection closed")
