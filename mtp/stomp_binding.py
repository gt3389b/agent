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

# File Name: stomp_binding.py
#
# Description: STOMP USP Binding
#
# STOMP-specific implementation of USP message binding
"""

import asyncio
import stomper
from mtp.usp_binding import UspBinding


class StompUspBinding(UspBinding):
    """STOMP-specific USP Binding"""
    
    def __init__(self, endpoint_id, host='localhost', port=61613, 
                 subscribe_dest='/queue/usp-agent', send_dest='/queue/usp-controller'):
        """
        Initialize STOMP USP Binding
        
        Args:
            endpoint_id (str): Agent endpoint ID
            host (str): STOMP broker host
            port (int): STOMP broker port
            subscribe_dest (str): Queue/topic to subscribe to
            send_dest (str): Queue/topic to send to
        """
        super().__init__(endpoint_id)
        self.host = host
        self.port = port
        self.subscribe_dest = subscribe_dest
        self.send_dest = send_dest
        self.connection = None
        self.reader = None
        self.writer = None
        self._message_callback = None
        self._running = False
    
    async def connect(self):
        """Connect to STOMP broker"""
        try:
            self.reader, self.writer = await asyncio.open_connection(
                self.host, self.port
            )
            
            # Send CONNECT frame
            connect_frame = stomper.connect(login='', passcode='')
            self.writer.write(connect_frame.encode('utf-8'))
            await self.writer.drain()
            
            # Read CONNECTED response
            response = await self.reader.read(1024)
            
            self._logger.info(f"Connected to STOMP broker at {self.host}:{self.port}")
            
        except Exception as e:
            self._logger.error(f"Failed to connect to STOMP broker: {e}", exc_info=True)
            raise
    
    async def start_server(self, message_callback):
        """
        Start STOMP subscriber
        
        Args:
            message_callback: Async callback(python_msg, from_id, to_id, None)
        """
        self._message_callback = message_callback
        
        await self.connect()
        
        # Subscribe to destination
        sub_frame = stomper.subscribe(self.subscribe_dest, 1)
        self.writer.write(sub_frame.encode('utf-8'))
        await self.writer.drain()
        
        self._logger.info(f"Subscribed to {self.subscribe_dest}")
        
        # Start receive loop
        self._running = True
        asyncio.create_task(self._receive_loop())
    
    async def _receive_loop(self):
        """Receive loop for STOMP messages"""
        buffer = b''
        
        while self._running:
            try:
                # Read data
                data = await self.reader.read(4096)
                if not data:
                    break
                
                buffer += data
                
                # Check for complete frame (ends with \x00)
                if b'\x00' in buffer:
                    frames = buffer.split(b'\x00')
                    buffer = frames[-1]  # Keep incomplete frame
                    
                    for frame_data in frames[:-1]:
                        if not frame_data:
                            continue
                        
                        # Parse STOMP frame
                        try:
                            frame_str = frame_data.decode('utf-8')
                            
                            # Extract message body (after headers)
                            if '\n\n' in frame_str:
                                _, body = frame_str.split('\n\n', 1)
                                
                                # Deserialize USP message
                                python_msg, from_id, to_id = self.deserialize_bytes(body.encode('utf-8'))
                                
                                # Call message callback
                                if self._message_callback:
                                    await self._message_callback(python_msg, from_id, to_id, None)
                        
                        except Exception as e:
                            self._logger.error(f"Error parsing STOMP frame: {e}", exc_info=True)
                
            except Exception as e:
                self._logger.error(f"Error in STOMP receive loop: {e}", exc_info=True)
                break
    
    async def send_bytes(self, data, destination=None):
        """
        Send bytes over STOMP
        
        Args:
            data (bytes): Serialized USP Record
            destination (str): STOMP destination (defaults to self.send_dest)
        """
        if destination is None:
            destination = self.send_dest
        
        if not self.writer:
            await self.connect()
        
        # Create STOMP SEND frame
        send_frame = stomper.send(destination, data)
        self.writer.write(send_frame.encode('utf-8'))
        await self.writer.drain()
        
        self._logger.debug(f"Sent {len(data)} bytes to {destination}")
    
    async def receive_bytes(self):
        """
        Receive bytes from STOMP (not used - we use callback pattern)
        
        STOMP uses subscription callbacks, not polling
        """
        raise NotImplementedError("STOMP uses subscription callbacks")
    
    async def close(self):
        """Close STOMP connection"""
        self._running = False
        
        if self.writer:
            # Send DISCONNECT frame
            try:
                disconnect_frame = stomper.disconnect()
                self.writer.write(disconnect_frame.encode('utf-8'))
                await self.writer.drain()
            except:
                pass
            
            self.writer.close()
            await self.writer.wait_closed()
        
        self._logger.info("STOMP connection closed")
