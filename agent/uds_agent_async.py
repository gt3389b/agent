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

# File Name: uds_agent_async.py
#
# Description: Async UDS USP Agent implementation
#
"""

import logging
import asyncio

from agent import agent_db
from agent import notify
from mtp.uds_async import UdsAsyncTransport
from message import usp_record_pb2

logger = logging.getLogger(__name__)


class UdsAgentAsync:
    """Async UDS-based USP Agent"""
    
    def __init__(self, dm_file, db_file, cfg_file='cfg/agent.json'):
        """
        Initialize Async UDS Agent
        
        Args:
            dm_file (str): Data model file path
            db_file (str): Database file path
            cfg_file (str): Config file path
        """
        # Initialize database
        self._db = agent_db.Database(dm_file, db_file, "")
        
        # Get agent endpoint ID
        self._agent_id = self._db.get("Device.LocalAgent.EndpointID")
        
        # Find UDS MTP configuration
        mtp_path, socket_path, mode = self._find_uds_mtp()
        
        logger.info(f"Async UDS Agent initialized: {self._agent_id}")
        logger.info(f"  Socket: {socket_path} (mode={mode})")
        
        self._socket_path = socket_path
        self._mode = mode
        self._transport = None
        
        # Get controller information for Boot notification
        self._controller_socket = self._db.get("Device.LocalAgent.Controller.1.MTP.1.UDS.UnixSocketPath")
        self._controller_id = self._db.get("Device.LocalAgent.Controller.1.EndpointID")
        
    def _find_uds_mtp(self):
        """Find UDS MTP configuration"""
        num_mtps = int(self._db.get("Device.LocalAgent.MTPNumberOfEntries"))
        
        for i in range(1, num_mtps + 1):
            mtp_path = f"Device.LocalAgent.MTP.{i}."
            protocol = self._db.get(mtp_path + "Protocol")
            
            if protocol == "UDS":
                socket_path = self._db.get(mtp_path + "UDS.UnixSocketPath")
                
                # Get mode from Device.UDS.UnixSocket table (optional)
                mode = "listen"  # Default
                try:
                    num_sockets = int(self._db.get("Device.UDS.UnixSocketNumberOfEntries"))
                    for j in range(1, num_sockets + 1):
                        sock_path = self._db.get(f"Device.UDS.UnixSocket.{j}.Path")
                        if sock_path == socket_path:
                            mode = self._db.get(f"Device.UDS.UnixSocket.{j}.Mode")
                            if mode:
                                mode = mode.lower()
                            break
                except:
                    pass
                
                logger.info(f"Found UDS MTP: socket={socket_path}")
                return mtp_path, socket_path, mode
        
        raise ValueError("No UDS MTP found in database")
    
    async def send_boot_notification(self):
        """Send Boot! notification to controller"""
        try:
            logger.info(f"Sending Boot! notification to {self._controller_socket}")
            
            # Create Boot notification
            boot_notif = notify.BootNotification(
                self._agent_id,
                self._controller_id,
                "sub-boot-uds-ctrl-1",
                self._db
            )
            
            # Generate notification message
            notif_msg = boot_notif.generate_notif_msg()
            notif_record = boot_notif.wrap_notif_in_record(notif_msg)
            
            # Connect to controller and send
            transport = UdsAsyncTransport(self._controller_socket, 'connect')
            await transport.connect()
            await transport.send_message(notif_record.SerializeToString())
            await transport.close()
            
            logger.info("✓ Boot! notification sent successfully")
            
        except Exception as e:
            logger.error(f"Failed to send Boot notification: {e}", exc_info=True)
    
    async def start(self):
        """Start the async UDS agent"""
        self._transport = UdsAsyncTransport(self._socket_path, self._mode)
        
        logger.info(f"Agent starting on {self._socket_path}")
        
        # Send Boot notification
        await self.send_boot_notification()
        
        # Start listening for controller messages
        await self._transport.start_server(self._handle_message)
        
        logger.info("Agent listening for controller messages...")
        
        # Keep server running
        async with self._transport.server:
            await self._transport.server.serve_forever()
    
    async def _handle_message(self, data, writer):
        """
        Handle received USP message from controller
        
        Args:
            data (bytes): Raw message data
            writer: Stream writer for responses
        """
        try:
            # Parse USP Record
            record = usp_record_pb2.Record()
            record.ParseFromString(data)
            
            logger.info("=" * 60)
            logger.info("RECEIVED USP MESSAGE FROM CONTROLLER:")
            logger.info(f"  From: {record.from_id}")
            logger.info(f"  To: {record.to_id}")
            logger.info("=" * 60)
            
            # TODO: Handle different message types (Get, Set, etc.)
            
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
    
    async def stop(self):
        """Stop the agent and clean up"""
        if self._transport:
            await self._transport.close()
        
        logger.info("Agent stopped")
