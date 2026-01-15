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

# File Name: usp_binding.py
#
# Description: USP Message Binding Layer
#
# Sits between MTP (wire format) and Agent (business logic)
# Handles serialization/deserialization of USP messages and records
# 
# This is the base class for all MTP bindings (UDS, CoAP, STOMP)
"""

import logging
from abc import ABC, abstractmethod
from message import usp_record_pb2, usp_msg_pb2
from message.request import parse_request
from message.response import parse_response

logger = logging.getLogger(__name__)


class UspBinding(ABC):
    """
    USP Message Binding - handles Record/Message serialization
    
    Base class for all MTP bindings (UDS, CoAP, STOMP, etc.)
    
    Responsibilities:
    - Bytes ↔ USP Record (protobuf)
    - USP Record ↔ USP Message (protobuf)
    - USP Message (protobuf) ↔ Python objects
    
    Subclasses implement transport-specific send/receive methods.
    """
    
    def __init__(self, endpoint_id):
        """
        Initialize USP binding
        
        Args:
            endpoint_id (str): Local endpoint ID
        """
        self.endpoint_id = endpoint_id
        self._logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    async def send_bytes(self, data, destination):
        """
        Send bytes over transport (implemented by subclass)
        
        Args:
            data (bytes): Serialized USP Record
            destination: Transport-specific destination (socket path, URL, queue name, etc.)
        """
        pass
    
    @abstractmethod
    async def receive_bytes(self):
        """
        Receive bytes from transport (implemented by subclass)
        
        Returns:
            bytes: Received USP Record
        """
        pass
    
    def deserialize_bytes(self, data):
        """
        Deserialize raw bytes into Python message object
        
        Args:
            data (bytes): Raw USP Record bytes
            
        Returns:
            tuple: (UspMessage, from_id, to_id)
        """
        # Parse USP Record
        record = usp_record_pb2.Record()
        record.ParseFromString(data)
        
        from_id = record.from_id
        to_id = record.to_id
        
        # Parse USP Message
        msg = usp_msg_pb2.Msg()
        msg.ParseFromString(record.no_session_context.payload)
        
        # Determine message category
        msg_type = msg.header.msg_type
        
        # Check if it's a request
        if msg.body.WhichOneof('msg_body') == 'request':
            python_msg = parse_request(msg, from_id, to_id)
        # Check if it's a response
        elif msg.body.WhichOneof('msg_body') == 'response':
            python_msg = parse_response(msg, from_id, to_id)
        # Check if it's a notification
        elif msg.body.WhichOneof('msg_body') == 'notify':
            # For now, return raw notify message
            # TODO: Create notification wrapper classes
            python_msg = msg
        else:
            raise ValueError(f"Unknown message body type: {msg.body.WhichOneof('msg_body')}")
        
        logger.debug(f"Deserialized {type(python_msg).__name__} from {from_id}")
        
        return python_msg, from_id, to_id
    
    async def receive_message(self):
        """
        Receive and deserialize message (convenience method)
        
        Returns:
            tuple: (python_msg, from_id, to_id)
        """
        data = await self.receive_bytes()
        return self.deserialize_bytes(data)
    
    def serialize_message(self, python_msg, to_id, from_id=None):
        """
        Serialize Python message object into bytes
        
        Args:
            python_msg: Python message object (Request/Response/Notification)
            to_id (str): Destination endpoint ID
            from_id (str): Source endpoint ID (defaults to self.endpoint_id)
            
        Returns:
            bytes: Serialized USP Record
        """
        if from_id is None:
            from_id = self.endpoint_id
        
        # Convert Python object to protobuf Msg
        if hasattr(python_msg, 'to_protobuf'):
            pb_msg = python_msg.to_protobuf()
        else:
            # Already a protobuf message (e.g., notification)
            pb_msg = python_msg
        
        # Wrap in USP Record
        record = usp_record_pb2.Record()
        record.version = "1.4"
        record.to_id = to_id
        record.from_id = from_id
        record.payload_security = usp_record_pb2.Record.PLAINTEXT
        record.no_session_context.payload = pb_msg.SerializeToString()
        
        logger.debug(f"Serialized {type(python_msg).__name__} to {to_id}")
        
        return record.SerializeToString()
    
    async def send_message(self, python_msg, to_id, destination, from_id=None):
        """
        Serialize and send message (convenience method)
        
        Args:
            python_msg: Python message object
            to_id (str): Destination endpoint ID
            destination: Transport-specific destination
            from_id (str): Source endpoint ID (defaults to self.endpoint_id)
        """
        data = self.serialize_message(python_msg, to_id, from_id)
        await self.send_bytes(data, destination)
    
    def create_error_response(self, request, err_code, err_msg):
        """
        Create an error response for a request
        
        Args:
            request: Original request message
            err_code (int): Error code
            err_msg (str): Error message
            
        Returns:
            bytes: Serialized error response
        """
        # Create error response message
        resp_msg = usp_msg_pb2.Msg()
        resp_msg.header.msg_id = request.msg_id
        resp_msg.header.msg_type = usp_msg_pb2.Header.ERROR
        
        error = resp_msg.body.error
        error.err_code = err_code
        error.err_msg = err_msg
        
        # Serialize
        return self.serialize_message(resp_msg, request.from_id, self.endpoint_id)
