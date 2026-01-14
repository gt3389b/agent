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

# File Name: uds_controller.py
#
# Description: Async UDS Controller implementation
#
"""

import logging
import json

from mtp.uds import UdsTransport
from message import usp_record_pb2
from message import usp_msg_pb2
from message import Set, Get

logger = logging.getLogger(__name__)


class UdsController:
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
        self._transport = UdsTransport(self._socket_path, self._mode)
        
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
                # Send Set request to configure periodic heartbeat
                # Don't use writer as the agent connection is closed
                await self._configure_periodic_heartbeat(record.from_id, record.to_id)
            elif event.event_name == "Periodic!":
                logger.info("✓ Periodic! notification received successfully!")
        else:
            logger.info("  Notify type: (other)")
    
    async def _send_request_and_wait(self, request_msg, request_type, agent_socket="/tmp/usp-agent.sock"):
        """
        Generic method to send a USP request and wait for response
        
        Args:
            request_msg: USP message object (Set, Get, or Operate)
            request_type: Type of request ('set', 'get', 'operate')
            agent_socket: Path to agent socket
            
        Returns:
            tuple: (resp_record, resp_msg) or (None, None) if error
        """
        transport = None
        try:
            logger.info(f"Sending {request_type.upper()} request to agent...")
            
            # Connect to agent's socket and send the request
            transport = UdsTransport(agent_socket, mode='connect')
            await transport.connect()
            request_record = request_msg.SerializeToString()
            await transport.send_message(request_record)
            
            logger.info(f"✓ {request_type.upper()} request sent")
            logger.info(f"Waiting for {request_type.upper()} response from agent...")
            
            # Wait for response
            response_data = await transport.receive_message()
            if response_data:
                # Parse the response
                resp_record = usp_record_pb2.Record()
                resp_record.ParseFromString(response_data)
                
                resp_msg = usp_msg_pb2.Msg()
                resp_msg.ParseFromString(resp_record.no_session_context.payload)
                
                logger.info(f"✓ {request_type.upper()} response received from agent")
                return resp_record, resp_msg
            else:
                logger.warning(f"No {request_type.upper()} response received")
                return None, None
                
        except Exception as e:
            logger.error(f"Error sending {request_type.upper()} request: {e}", exc_info=True)
            return None, None
        finally:
            if transport:
                await transport.close()
    
    async def _handle_set_response(self, resp_msg):
        """Handle Set response"""
        if resp_msg and resp_msg.body.response.HasField('set_resp'):
            set_resp = resp_msg.body.response.set_resp
            
            # Log updated objects
            for updated_obj in set_resp.updated_obj_results:
                logger.info(f"  Updated: {updated_obj.requested_path}")
                if updated_obj.oper_status.HasField('oper_success'):
                    for inst_result in updated_obj.oper_status.oper_success.updated_inst_results:
                        # updated_params is a map/dict
                        for param_name, param_value in inst_result.updated_params.items():
                            logger.info(f"    {param_name} = {param_value}")
                elif updated_obj.oper_status.HasField('oper_failure'):
                    err = updated_obj.oper_status.oper_failure
                    logger.error(f"    Error {err.err_code}: {err.err_msg}")
        else:
            logger.warning("Invalid Set response")
    
    async def _handle_get_response(self, resp_msg):
        """Handle Get response"""
        if resp_msg and resp_msg.body.response.HasField('get_resp'):
            get_resp = resp_msg.body.response.get_resp
            
            # Log retrieved objects
            for req_path_result in get_resp.req_path_results:
                logger.info(f"  Requested Path: {req_path_result.requested_path}")
                if req_path_result.HasField('resolved_path_results'):
                    for resolved in req_path_result.resolved_path_results:
                        logger.info(f"    Resolved Path: {resolved.resolved_path}")
                        for param_name, param_value in resolved.result_params.items():
                            logger.info(f"      {param_name} = {param_value}")
                elif req_path_result.HasField('err_msg'):
                    logger.error(f"    Error {req_path_result.err_code}: {req_path_result.err_msg}")
        else:
            logger.warning("Invalid Get response")
    
    async def _handle_operate_response(self, resp_msg):
        """Handle Operate response"""
        if resp_msg and resp_msg.body.response.HasField('operate_resp'):
            operate_resp = resp_msg.body.response.operate_resp
            
            # Log operation results
            for operation in operate_resp.operation_results:
                logger.info(f"  Operation: {operation.executed_command}")
                if operation.HasField('req_obj_path'):
                    logger.info(f"    Object Path: {operation.req_obj_path}")
                if operation.HasField('req_output_args'):
                    logger.info(f"    Output Args: {operation.req_output_args}")
        else:
            logger.warning("Invalid Operate response")
    
    async def _configure_periodic_heartbeat(self, agent_id, controller_id):
        """
        Send Set request to configure periodic heartbeat on the agent
        
        Args:
            agent_id: Agent endpoint ID
            controller_id: Controller endpoint ID
        """
        try:
            logger.info("Configuring periodic heartbeat on agent...")
            
            # Find agent's socket path from config
            agent_socket = "/tmp/usp-agent.sock"  # TODO: Get from database or config
            
            # Create Set message to configure PeriodicNotifInterval
            set_msg = Set(
                to_id=agent_id,
                from_id=controller_id,
                objects=[{
                    "obj_path": "Device.LocalAgent.Controller.1.",
                    "param_settings": [
                        {"param": "PeriodicNotifInterval", "value": "30"}
                    ]
                }],
                allow_partial=True
            )
            
            # Send request and wait for response
            resp_record, resp_msg = await self._send_request_and_wait(set_msg, 'set', agent_socket)
            
            if resp_msg:
                await self._handle_set_response(resp_msg)
                logger.info("✓ Periodic heartbeat configured: PeriodicNotifInterval=30 seconds")
            else:
                logger.error("Failed to configure periodic heartbeat")
                
        except Exception as e:
            logger.error(f"Error configuring periodic heartbeat: {e}", exc_info=True)
    
    async def stop(self):
        """Stop the controller and clean up"""
        if self._transport:
            await self._transport.close()
        
        logger.info("Controller stopped")
