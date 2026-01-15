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
import json
import os

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
        
        # Load data model for GetSupportedDM responses
        self._dm_file = dm_file
        self._data_model = self._load_data_model(dm_file)
        
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
    
    def _load_data_model(self, dm_file):
        """Load data model from JSON file"""
        try:
            with open(dm_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load data model from {dm_file}: {e}")
            return {}
    
    def _build_data_model_tree(self):
        """
        Build a hierarchical tree from flat dm.json structure
        Returns dict of objects with their parameters
        """
        objects = {}
        
        for path, access in self._data_model.items():
            # Split path into components
            parts = path.split('.')
            
            # Build object path (everything except last component)
            obj_path = '.'.join(parts[:-1]) + '.'
            param_name = parts[-1]
            
            if obj_path not in objects:
                objects[obj_path] = {
                    'params': {},
                    'is_multi_instance': False,
                    'children': set()
                }
            
            # Add parameter
            objects[obj_path]['params'][param_name] = access
            
            # Check if this path contains {i} (multi-instance marker)
            if '{i}' in path:
                # Mark the object containing {i} as multi-instance
                # Extract the object path that has {i}
                for i, part in enumerate(parts):
                    if '{i}' in part:
                        mi_obj_path = '.'.join(parts[:i+1]) + '.'
                        if mi_obj_path not in objects:
                            objects[mi_obj_path] = {
                                'params': {},
                                'is_multi_instance': True,
                                'children': set()
                            }
                        else:
                            objects[mi_obj_path]['is_multi_instance'] = True
                        break
        
        # Build parent-child relationships
        for obj_path in sorted(objects.keys()):
            # Find parent
            parts = obj_path.rstrip('.').split('.')
            if len(parts) > 1:
                parent_path = '.'.join(parts[:-1]) + '.'
                if parent_path in objects:
                    objects[parent_path]['children'].add(obj_path)
        
        return objects
    
    def _get_first_level_children(self, obj_path, objects):
        """
        Get immediate child objects of a given path
        For "Device." with first_level_only, return Device.DeviceInfo., Device.LocalAgent., etc.
        """
        children = set()
        
        # Normalize path
        if not obj_path.endswith('.'):
            obj_path += '.'
        
        # Count depth of requested path
        requested_depth = obj_path.count('.')
        
        for path in objects.keys():
            # Check if this is a child of requested path
            if path.startswith(obj_path) and path != obj_path:
                # Count depth
                path_depth = path.count('.')
                
                # First level means exactly one level deeper
                if path_depth == requested_depth + 1:
                    children.add(path)
        
        return sorted(children)
    
    def _process_get_supported_dm(self, msg):
        """
        Process GetSupportedDM request and generate response
        
        Args:
            msg: USP GetSupportedDM message
            
        Returns:
            USP GetSupportedDMResp message
        """
        logger.info("Processing GetSupportedDM request...")
        
        # Build data model tree
        objects = self._build_data_model_tree()
        
        # Create response message
        resp_msg = usp_msg_pb2.Msg()
        resp_msg.header.msg_id = msg.header.msg_id
        resp_msg.header.msg_type = usp_msg_pb2.Header.GET_SUPPORTED_DM_RESP
        
        # Process each requested object path
        get_dm = msg.body.request.get_supported_dm
        
        logger.info(f"  Requested paths: {list(get_dm.obj_paths)}")
        logger.info(f"  First level only: {get_dm.first_level_only}")
        logger.info(f"  Return commands: {get_dm.return_commands}")
        logger.info(f"  Return events: {get_dm.return_events}")
        logger.info(f"  Return params: {get_dm.return_params}")
        
        for req_path in get_dm.obj_paths:
            result = resp_msg.body.response.get_supported_dm_resp.req_obj_results.add()
            result.req_obj_path = req_path
            
            # Normalize requested path
            if not req_path.endswith('.'):
                req_path += '.'
            
            # Get objects to return
            if get_dm.first_level_only:
                # Return only immediate children
                obj_paths = self._get_first_level_children(req_path, objects)
            else:
                # Return all descendants
                obj_paths = [p for p in objects.keys() if p.startswith(req_path)]
            
            logger.info(f"  Returning {len(obj_paths)} objects for {result.req_obj_path}")
            
            # Build supported objects
            for obj_path in obj_paths:
                obj_data = objects.get(obj_path, {})
                
                supported_obj = result.supported_objs.add()
                supported_obj.supported_obj_path = obj_path
                
                # Determine object access type
                # For now, all objects are read-only (no add/delete support yet)
                supported_obj.access = usp_msg_pb2.GetSupportedDMResp.OBJ_READ_ONLY
                
                # Set multi-instance flag
                supported_obj.is_multi_instance = obj_data.get('is_multi_instance', False)
                
                # Add parameters if requested
                if get_dm.return_params:
                    for param_name, access in obj_data.get('params', {}).items():
                        param = supported_obj.supported_params.add()
                        param.param_name = param_name
                        
                        # Map access type
                        if access == "readOnly":
                            param.access = usp_msg_pb2.GetSupportedDMResp.PARAM_READ_ONLY
                        elif access == "readWrite":
                            param.access = usp_msg_pb2.GetSupportedDMResp.PARAM_READ_WRITE
                        else:
                            param.access = usp_msg_pb2.GetSupportedDMResp.PARAM_READ_ONLY
                        
                        # Value type - default to STRING for now
                        param.value_type = usp_msg_pb2.GetSupportedDMResp.PARAM_STRING
                        
                        # Value change - parameters can be changed
                        param.value_change = usp_msg_pb2.GetSupportedDMResp.VALUE_CHANGE_ALLOWED
                
                # Commands and events not supported yet
                # (we would add them here if get_dm.return_commands or get_dm.return_events)
        
        logger.info("✓ GetSupportedDM response generated")
        return resp_msg
    
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
                    
            elif msg.header.msg_type == usp_msg_pb2.Header.GET:
                logger.info("  Message Type: GET")
                
                # Process Get request using request handler
                req_msg, req_record, resp_msg, resp_payload = self._request_handler.handle_request(data)
                
                logger.info("✓ Get request processed successfully")
                logger.info(f"  Response payload size: {len(resp_payload)} bytes")
                
                # Send response back to controller
                if writer:
                    await self._transport.send_message(resp_payload, writer)
                    logger.info("✓ Get response sent to controller")
                    
            elif msg.header.msg_type == usp_msg_pb2.Header.GET_SUPPORTED_DM:
                logger.info("  Message Type: GET_SUPPORTED_DM")
                
                # Process GetSupportedDM request
                resp_msg = self._process_get_supported_dm(msg)
                
                # Wrap response in USP Record
                resp_record = usp_record_pb2.Record()
                resp_record.version = "1.0"
                resp_record.to_id = record.from_id
                resp_record.from_id = self._agent_id
                resp_record.payload_security = usp_record_pb2.Record.PLAINTEXT
                resp_record.no_session_context.payload = resp_msg.SerializeToString()
                
                resp_payload = resp_record.SerializeToString()
                
                logger.info("✓ GetSupportedDM request processed successfully")
                logger.info(f"  Response payload size: {len(resp_payload)} bytes")
                
                # Send response back to controller
                if writer:
                    await self._transport.send_message(resp_payload, writer)
                    logger.info("✓ GetSupportedDM response sent to controller")
                    
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
