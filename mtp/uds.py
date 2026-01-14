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

# File Name: uds.py
#
# Description: Unix Domain Socket (UDS) MTP implementation for USP
#
# Functionality:
#   Class: UdsTransport
#     - Server and client socket handling
#     - Message framing with length prefix
#     - Thread-safe send/receive operations
"""

import os
import socket
import struct
import logging
import threading


logger = logging.getLogger(__name__)


class UdsTransport:
    """Unix Domain Socket transport for USP messages"""
    
    # Message framing: 4-byte length prefix (big-endian)
    HEADER_FORMAT = '!I'  # Network byte order, unsigned int (4 bytes)
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    MAX_MESSAGE_SIZE = 65536  # 64KB max message size
    
    def __init__(self, socket_path, mode='listen'):
        """
        Initialize UDS transport
        
        Args:
            socket_path (str): Path to Unix socket file
            mode (str): 'listen' for server, 'connect' for client
        """
        self._socket_path = socket_path
        self._mode = mode
        self._socket = None
        self._conn_socket = None  # For accepted connections in listen mode
        self._lock = threading.Lock()
        self._connected = False
        
    def start(self):
        """Start the UDS transport"""
        if self._mode == 'listen':
            self._start_server()
        else:
            self._start_client()
            
    def _start_server(self):
        """Start UDS server (listen mode)"""
        # Remove existing socket file if it exists
        if os.path.exists(self._socket_path):
            os.unlink(self._socket_path)
            logger.info(f"Removed existing socket file: {self._socket_path}")
        
        # Create Unix socket
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket.bind(self._socket_path)
        self._socket.listen(1)  # Single connection for now
        
        logger.info(f"UDS server listening on: {self._socket_path}")
        
        # Set appropriate permissions
        os.chmod(self._socket_path, 0o666)
        
    def _start_client(self):
        """Start UDS client (connect mode)"""
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        
        # Try to connect
        try:
            self._socket.connect(self._socket_path)
            self._conn_socket = self._socket
            self._connected = True
            logger.info(f"UDS client connected to: {self._socket_path}")
        except (FileNotFoundError, ConnectionRefusedError) as e:
            logger.error(f"Failed to connect to {self._socket_path}: {e}")
            raise
            
    def accept_connection(self, timeout=None):
        """
        Accept a connection (server mode only)
        
        Args:
            timeout (float): Timeout in seconds
            
        Returns:
            bool: True if connection accepted, False on timeout
        """
        if self._mode != 'listen':
            raise RuntimeError("accept_connection only valid in listen mode")
            
        if self._socket is None:
            raise RuntimeError("Server not started")
        
        # Set timeout
        self._socket.settimeout(timeout)
        
        try:
            self._conn_socket, _ = self._socket.accept()
            self._connected = True
            logger.info("UDS connection accepted")
            return True
        except socket.timeout:
            return False
            
    def is_connected(self):
        """Check if transport is connected"""
        return self._connected
        
    def send_message(self, data):
        """
        Send a message with length-prefix framing
        
        Args:
            data (bytes): Message data to send
            
        Raises:
            RuntimeError: If not connected
            ValueError: If message too large
        """
        if not self._connected or self._conn_socket is None:
            raise RuntimeError("Not connected")
            
        msg_len = len(data)
        if msg_len > self.MAX_MESSAGE_SIZE:
            raise ValueError(f"Message too large: {msg_len} > {self.MAX_MESSAGE_SIZE}")
        
        # Create length header
        header = struct.pack(self.HEADER_FORMAT, msg_len)
        
        with self._lock:
            try:
                # Send header + data
                self._conn_socket.sendall(header + data)
                logger.debug(f"Sent UDS message: {msg_len} bytes")
            except (BrokenPipeError, ConnectionResetError) as e:
                logger.error(f"Failed to send message: {e}")
                self._connected = False
                raise
                
    def receive_message(self, timeout=None):
        """
        Receive a message with length-prefix framing
        
        Args:
            timeout (float): Timeout in seconds
            
        Returns:
            bytes: Received message data, or None on timeout/error
        """
        if not self._connected or self._conn_socket is None:
            return None
            
        # Set timeout
        self._conn_socket.settimeout(timeout)
        
        try:
            # Read header (4 bytes)
            header_data = self._recv_exact(self.HEADER_SIZE)
            if not header_data:
                return None
                
            # Unpack message length
            msg_len, = struct.unpack(self.HEADER_FORMAT, header_data)
            
            if msg_len > self.MAX_MESSAGE_SIZE:
                logger.error(f"Message too large: {msg_len} > {self.MAX_MESSAGE_SIZE}")
                self._connected = False
                return None
            
            # Read message data
            msg_data = self._recv_exact(msg_len)
            if not msg_data:
                return None
                
            logger.debug(f"Received UDS message: {msg_len} bytes")
            return msg_data
            
        except socket.timeout:
            return None
        except (ConnectionResetError, BrokenPipeError) as e:
            logger.error(f"Connection error while receiving: {e}")
            self._connected = False
            return None
            
    def _recv_exact(self, num_bytes):
        """
        Receive exactly num_bytes from socket
        
        Args:
            num_bytes (int): Number of bytes to receive
            
        Returns:
            bytes: Received data, or None if connection closed
        """
        data = b''
        while len(data) < num_bytes:
            chunk = self._conn_socket.recv(num_bytes - len(data))
            if not chunk:
                logger.warning("Connection closed while receiving")
                self._connected = False
                return None
            data += chunk
        return data
        
    def close(self):
        """Close the transport and clean up"""
        logger.info("Closing UDS transport")
        
        self._connected = False
        
        # Close connection socket
        if self._conn_socket:
            try:
                self._conn_socket.close()
            except Exception as e:
                logger.error(f"Error closing connection socket: {e}")
            self._conn_socket = None
        
        # Close listening socket
        if self._socket:
            try:
                self._socket.close()
            except Exception as e:
                logger.error(f"Error closing socket: {e}")
            self._socket = None
        
        # Remove socket file (server mode only)
        if self._mode == 'listen' and os.path.exists(self._socket_path):
            try:
                os.unlink(self._socket_path)
                logger.info(f"Removed socket file: {self._socket_path}")
            except Exception as e:
                logger.error(f"Error removing socket file: {e}")
