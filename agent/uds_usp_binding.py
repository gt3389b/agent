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

# File Name: uds_usp_binding.py
#
# Description: Unix Domain Socket USP Binding
#
# Functionality:
#   Class: UdsUspBinding(GenericUspBinding)
#     - UDS-specific USP message handling
#     - Connection management
#     - Message serialization/deserialization
"""

import logging
import threading
import time

from agent import generic_usp_binding
from agent import usp_record_pb2
from mtp import uds


logger = logging.getLogger(__name__)


class UdsUspBinding(generic_usp_binding.GenericUspBinding):
    """UDS-specific USP Binding"""
    
    def __init__(self, socket_path, mode='listen', endpoint_id=''):
        """
        Initialize UDS USP Binding
        
        Args:
            socket_path (str): Path to Unix socket
            mode (str): 'listen' for server, 'connect' for client
            endpoint_id (str): Agent endpoint ID
        """
        super().__init__()
        self._socket_path = socket_path
        self._mode = mode
        self._endpoint_id = endpoint_id
        self._transport = None
        self._recv_thread = None
        self._running = False
        self._reconnect_interval = 5  # seconds
        
        logger.info(f"UDS USP Binding initialized: {socket_path} (mode={mode})")
        
    def start_listening(self):
        """Start listening for UDS messages"""
        self._running = True
        
        # Start transport
        try:
            self._transport = uds.UdsTransport(self._socket_path, self._mode)
            self._transport.start()
        except Exception as e:
            logger.error(f"Failed to start UDS transport: {e}")
            raise
        
        # Start receiver thread
        self._recv_thread = threading.Thread(
            target=self._receive_loop,
            name="UDS-Receiver"
        )
        self._recv_thread.daemon = True
        self._recv_thread.start()
        
        logger.info("UDS binding listening started")
        
    def _receive_loop(self):
        """Main receive loop"""
        while self._running:
            try:
                # If in listen mode and not connected, accept connection
                if self._mode == 'listen' and not self._transport.is_connected():
                    logger.info("Waiting for incoming messages...")
                    if self._transport.accept_connection(timeout=1.0):
                        logger.info("UDS connection established")
                    continue
                
                # If in connect mode and not connected, try to reconnect
                if self._mode == 'connect' and not self._transport.is_connected():
                    logger.info(f"Attempting to reconnect to {self._socket_path}...")
                    try:
                        self._transport.close()
                        self._transport = uds.UdsTransport(self._socket_path, self._mode)
                        self._transport.start()
                    except Exception as e:
                        logger.warning(f"Reconnect failed: {e}")
                        time.sleep(self._reconnect_interval)
                    continue
                
                # Receive message
                data = self._transport.receive_message(timeout=1.0)
                if data:
                    self._handle_received_data(data)
                    
            except Exception as e:
                logger.error(f"Error in receive loop: {e}", exc_info=True)
                time.sleep(0.1)
                
    def _handle_received_data(self, data):
        """
        Handle received USP Record
        
        Args:
            data (bytes): Received data
        """
        try:
            # Deserialize USP Record
            record = usp_record_pb2.Record()
            record.ParseFromString(data)
            
            # Validate record
            if not record.to_id:
                logger.warning("Received record without to_id, ignoring")
                return
                
            if not record.from_id:
                logger.warning("Received record without from_id, ignoring")
                return
            
            # Extract USP Message from record
            if record.HasField('no_session_context'):
                payload = record.no_session_context.payload
                
                # Add to queue using parent class method
                self.push(payload, record.from_id)
                logger.debug(f"Queued UDS message from {record.from_id}")
                
            elif record.HasField('session_context'):
                # Handle session context - payload is repeated field, take first
                if record.session_context.payload:
                    payload = record.session_context.payload[0]
                    self.push(payload, record.from_id)
                    logger.debug(f"Queued session-based UDS message from {record.from_id}")
            else:
                logger.warning("Received record without payload context")
                
        except Exception as e:
            logger.error(f"Error handling received data: {e}", exc_info=True)
            
    def send_msg(self, serialized_msg, to_addr):
        """
        Send a USP message via UDS (GenericUspBinding interface)
        
        Args:
            serialized_msg (bytes): Serialized USP Record
            to_addr (str): Socket path to send to
        """
        try:
            logger.info(f"Sending message to {to_addr}")
            
            # Create a new connection to the destination socket
            transport = uds.UdsTransport(to_addr, 'connect')
            transport.start()
            
            # Send the message
            transport.send_message(serialized_msg)
            
            # Close the connection
            transport.close()
            
            logger.info(f"Message sent successfully to {to_addr}")
            
        except Exception as e:
            logger.error(f"Error sending message to {to_addr}: {e}", exc_info=True)
    
    def send_response(self, to_id, usp_msg):
        """
        Send a USP response via existing connection
        
        Args:
            to_id (str): Destination endpoint ID
            usp_msg (bytes): Serialized USP message
        """
        if not self._transport or not self._transport.is_connected():
            logger.warning("Cannot send response: transport not connected")
            return
        
        try:
            # Create USP Record
            record = usp_record_pb2.Record()
            record.version = "1.4"
            record.to_id = to_id
            record.from_id = self._endpoint_id
            
            # Use no_session_context for simplicity
            record.no_session_context.payload = usp_msg
            
            # Serialize record
            record_bytes = record.SerializeToString()
            
            # Send via existing transport connection
            self._transport.send_message(record_bytes)
            logger.debug(f"Sent UDS response to {to_id}: {len(record_bytes)} bytes")
            
        except Exception as e:
            logger.error(f"Failed to send UDS response: {e}", exc_info=True)
            
    def listen_to_notifications(self, notification_q):
        """
        Not implemented for UDS (notifications use same connection as requests)
        
        Args:
            notification_q: Notification queue (ignored)
        """
        # UDS uses single bidirectional connection
        pass
        
    def clean_up(self):
        """Clean up UDS binding resources"""
        logger.info("Cleaning up UDS binding")
        
        self._running = False
        
        # Wait for receiver thread
        if self._recv_thread and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=2.0)
        
        # Close transport
        if self._transport:
            self._transport.close()
            self._transport = None
            
        logger.info("UDS binding cleaned up")
