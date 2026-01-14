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

# File Name: uds_controller_async.py
#
# Description: Async UDS Controller implementation
#
"""

import logging
import json

from mtp.uds_async import UdsAsyncTransport
from message import usp_record_pb2
from message import usp_msg_pb2

logger = logging.getLogger(__name__)


class UdsControllerAsync:
    """Async UDS Controller for USP communication"""
    
    def __init__(self, config_file):
        """
        Initialize UDS Controller
        
        Args:
            config_file (str): Path to configuration file
        """
        # Load configuration
        with open(config_file, 'r') as f:
            self._config = json.load(f)
        
        self._endpoint_id = self._config['endpoint_id']
        self._socket_path = self._config['socket_path']
        self._mode = self._config.get('mode', 'listen')
        self._transport = None
        
        logger.info("=" * 60)
        logger.info("Async UDS Controller Initialized")
        logger.info(f"  Endpoint ID: {self._endpoint_id}")
        logger.info(f"  Socket Path: {self._socket_path}")
        logger.info(f"  Mode: {self._mode}")
        logger.info("=" * 60)
    
    async def start(self):
        """Start the async UDS controller"""
        self._transport = UdsAsyncTransport(self._socket_path, self._mode)
        
        logger.info(f"Controller starting on {self._socket_path}")
        logger.info("Waiting for agent messages...")
        
        await self._transport.start_server(self._handle_message)
        
        # Keep server running
        async with self._transport.server:
            await self._transport.server.serve_forever()
    
    async def _handle_message(self, data, writer):
        """
        Handle received USP message
        
        Args:
            data (bytes): Raw message data
            writer: Stream writer for sending responses
        """
        try:
            # Parse USP Record
            record = usp_record_pb2.Record()
            record.ParseFromString(data)
            
            logger.info("=" * 60)
            logger.info("RECEIVED USP RECORD:")
            logger.info(f"  From: {record.from_id}")
            logger.info(f"  To: {record.to_id}")
            logger.info(f"  Version: {record.version}")
            
            # Parse USP Message from payload
            msg = usp_msg_pb2.Msg()
            if record.HasField('no_session_context'):
                msg.ParseFromString(record.no_session_context.payload)
            elif record.HasField('session_context'):
                msg.ParseFromString(record.session_context.payload[0])
            
            # Determine message type
            msg_type = msg.header.msg_type
            logger.info(f"  Message Type: {msg_type}")
            
            if msg.body.request.HasField('notify'):
                await self._handle_notify(record, msg, writer)
            else:
                logger.info(f"  Payload size: {len(record.no_session_context.payload)} bytes")
            
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
    
    async def _handle_notify(self, record, msg, writer):
        """
        Handle Notify message
        
        Args:
            record: USP Record
            msg: USP Message
            writer: Stream writer
        """
        notify = msg.body.request.notify
        subscription_id = notify.subscription_id
        
        logger.info(f"  Subscription ID: {subscription_id}")
        
        if notify.HasField('event'):
            event = notify.event
            logger.info(f"  Event: {event.obj_path}{event.event_name}")
            logger.info(f"  Parameters:")
            for param_name, param_value in event.params.items():
                logger.info(f"    {param_name}: {param_value}")
            
            # Check if it's a Boot notification
            if event.event_name == "Boot!":
                logger.info("✓ Boot! notification received successfully!")
        else:
            logger.info("  Notify type: (other)")
    
    async def stop(self):
        """Stop the controller and clean up"""
        if self._transport:
            await self._transport.close()
        
        logger.info("Controller stopped")
