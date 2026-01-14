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

# File Name: uds_async.py
#
# Description: Async Unix Domain Socket transport for USP
#
"""

import os
import asyncio
import logging
import struct

logger = logging.getLogger(__name__)

# Maximum message size (64KB)
MAX_MESSAGE_SIZE = 65536


class UdsTransport:
    """Async Unix Domain Socket transport with 4-byte length prefix framing"""
    
    def __init__(self, socket_path, mode='listen'):
        """
        Initialize UDS transport
        
        Args:
            socket_path (str): Path to Unix socket
            mode (str): 'listen' or 'connect'
        """
        self.socket_path = socket_path
        self.mode = mode
        self.server = None
        self.reader = None
        self.writer = None
        
    async def start_server(self, message_callback):
        """
        Start listening for connections (server mode)
        
        Args:
            message_callback: Async callback function(data) for received messages
        """
        if self.mode != 'listen':
            raise ValueError("start_server() only valid in listen mode")
        
        # Remove old socket if exists
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        
        async def handle_client(reader, writer):
            """Handle individual client connection"""
            addr = writer.get_extra_info('peername')
            logger.info(f"UDS connection accepted from {addr}")
            
            try:
                while True:
                    # Read 4-byte length prefix
                    length_data = await reader.readexactly(4)
                    msg_length = struct.unpack('!I', length_data)[0]
                    
                    if msg_length > MAX_MESSAGE_SIZE:
                        logger.error(f"Message too large: {msg_length} bytes")
                        break
                    
                    # Read message payload
                    data = await reader.readexactly(msg_length)
                    logger.debug(f"Received {len(data)} bytes")
                    
                    # Process message
                    await message_callback(data, writer)
                    
            except asyncio.IncompleteReadError:
                logger.debug("Connection closed by peer")
            except Exception as e:
                logger.error(f"Error handling client: {e}", exc_info=True)
            finally:
                writer.close()
                await writer.wait_closed()
        
        # Start Unix socket server
        self.server = await asyncio.start_unix_server(
            handle_client,
            path=self.socket_path
        )
        
        logger.info(f"UDS server listening on: {self.socket_path}")
        
    async def connect(self):
        """Connect to UDS server (client mode)"""
        if self.mode != 'connect':
            raise ValueError("connect() only valid in connect mode")
        
        self.reader, self.writer = await asyncio.open_unix_connection(
            path=self.socket_path
        )
        logger.info(f"Connected to UDS server: {self.socket_path}")
        
    async def send_message(self, data, writer=None):
        """
        Send message with length prefix
        
        Args:
            data (bytes): Message to send
            writer: StreamWriter (if None, uses self.writer)
        """
        target_writer = writer or self.writer
        
        if not target_writer:
            raise RuntimeError("No connection available")
        
        # Prepare message with 4-byte length prefix
        msg_length = len(data)
        length_prefix = struct.pack('!I', msg_length)
        
        # Send length + data
        target_writer.write(length_prefix + data)
        await target_writer.drain()
        
        logger.debug(f"Sent {msg_length} bytes")
    
    async def receive_message(self, reader=None):
        """
        Receive message with length prefix
        
        Args:
            reader: StreamReader (if None, uses self.reader)
            
        Returns:
            bytes: Received message data
        """
        target_reader = reader or self.reader
        
        if not target_reader:
            raise RuntimeError("No connection available")
        
        try:
            # Read 4-byte length prefix
            length_data = await target_reader.readexactly(4)
            msg_length = struct.unpack('!I', length_data)[0]
            
            if msg_length > MAX_MESSAGE_SIZE:
                raise ValueError(f"Message too large: {msg_length} bytes")
            
            # Read message data
            data = await target_reader.readexactly(msg_length)
            logger.debug(f"Received {msg_length} bytes")
            
            return data
            
        except asyncio.IncompleteReadError:
            logger.debug("Connection closed by peer")
            return None
        
    async def close(self):
        """Close connection and clean up"""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            
        if os.path.exists(self.socket_path) and self.mode == 'listen':
            os.unlink(self.socket_path)
            logger.info(f"Removed socket file: {self.socket_path}")
        
        logger.info("UDS transport closed")
