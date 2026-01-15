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

# File Name: uds_binding.py
#
# Description: Unix Domain Socket USP Binding
#
# UDS-specific implementation of USP message binding
"""

import asyncio
from mtp.usp_binding import UspBinding
from mtp.uds import UdsTransport


class UdsUspBinding(UspBinding):
    """UDS-specific USP Binding"""
    
    def __init__(self, endpoint_id, socket_path, mode='listen'):
        """
        Initialize UDS USP Binding
        
        Args:
            endpoint_id (str): Agent endpoint ID
            socket_path (str): Path to Unix socket
            mode (str): 'listen' for server, 'connect' for client
        """
        super().__init__(endpoint_id)
        self.socket_path = socket_path
        self.mode = mode
        self.transport = UdsTransport(socket_path, mode)
        self._message_callback = None
    
    async def start_server(self, message_callback):
        """
        Start listening for connections
        
        Args:
            message_callback: Async callback(python_msg, from_id, to_id, writer)
        """
        self._message_callback = message_callback
        
        async def handle_usp_message(data, writer):
            """Handle incoming USP message"""
            try:
                # Deserialize bytes to Python object
                python_msg, from_id, to_id = self.deserialize_bytes(data)
                
                # Call agent's message callback
                await message_callback(python_msg, from_id, to_id, writer)
                
            except Exception as e:
                self._logger.error(f"Error handling USP message: {e}", exc_info=True)
        
        await self.transport.start_server(handle_usp_message)
    
    async def connect(self):
        """Connect to UDS server"""
        await self.transport.connect()
    
    async def send_bytes(self, data, destination):
        """
        Send bytes over UDS
        
        Args:
            data (bytes): Serialized USP Record
            destination: StreamWriter or None (uses transport's writer)
        """
        await self.transport.send_message(data, destination)
    
    async def receive_bytes(self):
        """
        Receive bytes from UDS
        
        Returns:
            bytes: Received USP Record
        """
        return await self.transport.receive_message()
    
    async def close(self):
        """Close transport"""
        await self.transport.close()
