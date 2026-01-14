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

# File Name: uds_agent.py
#
# Description: Async UDS USP Agent implementation
#
"""

import logging
import asyncio

from agent import agent_db
from agent import notify
from agent import request_handler
from mtp.uds import UdsTransport
from message import usp_record_pb2
from message import usp_msg_pb2

logger = logging.getLogger(__name__)


class UdsAgent:
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
        
        # Initialize request handler
        self._request_handler = request_handler.UspRequestHandler(
            self._agent_id,
            self._db
        )
        
        # Find UDS MTP configuration
        mtp_path, socket_path, mode = self._find_uds_mtp()
        
        logger.info(f"Async UDS Agent initialized: {self._agent_id}")
        logger.info(f"  Socket: {socket_path} (mode={mode})")
        
        self._socket_path = socket_path
        self._mode = mode
        self._transport = None
        self._periodic_task = None
        
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
            transport = UdsTransport(self._controller_socket, 'connect')
            await transport.connect()
            await transport.send_message(notif_record.SerializeToString())
            await transport.close()
            
            logger.info("✓ Boot! notification sent successfully")
            
        except Exception as e:
            logger.error(f"Failed to send Boot notification: {e}", exc_info=True)
    
    async def start(self):
        """Start the async UDS agent"""
        self._transport = UdsTransport(self._socket_path, self._mode)
        
        logger.info(f"Agent starting on {self._socket_path}")
        
        # Send Boot notification
        await self.send_boot_notification()
        
        # Start periodic notification task
        self._periodic_task = asyncio.create_task(self._periodic_notification_loop())
        
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
            
            # Parse the USP Message
            msg = usp_msg_pb2.Msg()
            msg.ParseFromString(record.no_session_context.payload)
            
            # Check message type
            if msg.header.msg_type == usp_msg_pb2.Header.SET:
                logger.info("  Message Type: SET")
                
                # Process Set request using request handler
                req_msg, req_record, resp_msg, resp_payload = self._request_handler.handle_request(data)
                
                logger.info("✓ Set request processed successfully")
                logger.info(f"  Response payload size: {len(resp_payload)} bytes")
                
                # Send response back to controller
                if writer:
                    await self._transport.send_message(resp_payload, writer)
                    logger.info("✓ Set response sent to controller")
            else:
                msg_type = msg.header.msg_type
                logger.warning(f"Unhandled message type: {msg_type}")
            
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
    
    async def _periodic_notification_loop(self):
        """Send periodic notifications at configured interval"""
        try:
            # Wait a moment for everything to initialize
            await asyncio.sleep(1)
            
            while True:
                # Get current interval from database
                interval_str = self._db.get("Device.LocalAgent.Controller.1.PeriodicNotifInterval")
                interval = int(interval_str) if interval_str else 30
                
                if interval > 0:
                    # Send periodic notification
                    await self._send_periodic_notification()
                    
                    # Wait for the interval
                    await asyncio.sleep(interval)
                else:
                    # If interval is 0, periodic notifications are disabled
                    await asyncio.sleep(10)  # Check again in 10 seconds
                    
        except asyncio.CancelledError:
            logger.info("Periodic notification task cancelled")
        except Exception as e:
            logger.error(f"Error in periodic notification loop: {e}", exc_info=True)
    
    async def _send_periodic_notification(self):
        """Send Periodic! notification to controller"""
        try:
            logger.info("Sending Periodic! notification to controller...")
            
            # Create Periodic notification
            periodic_notif = notify.PeriodicNotification(
                self._agent_id,
                self._controller_id,
                "sub-periodic-uds-ctrl-1",
                self._db
            )
            
            # Generate notification message
            notif_msg = periodic_notif.generate_notif_msg()
            notif_record = periodic_notif.wrap_notif_in_record(notif_msg)
            
            # Connect to controller and send
            transport = UdsTransport(self._controller_socket, 'connect')
            await transport.connect()
            await transport.send_message(notif_record.SerializeToString())
            await transport.close()
            
            logger.info("✓ Periodic! notification sent successfully")
            
        except Exception as e:
            logger.error(f"Failed to send Periodic notification: {e}", exc_info=True)
    
    async def stop(self):
        """Stop the agent and clean up"""
        if self._periodic_task:
            self._periodic_task.cancel()
            
        if self._transport:
            await self._transport.close()
        
        logger.info("Agent stopped")
