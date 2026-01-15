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
import asyncio
from datetime import datetime

from mtp.uds import UdsTransport
from message import usp_record_pb2
from message import usp_msg_pb2
from message import Set, Get, GetSupportedDM, GetInstances

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
        
        # Agent tracking
        self._connected_agents = {}  # agent_id -> {last_boot, last_heartbeat, socket_path}
        
        # Request/response tracking
        self._pending_requests = {}  # msg_id -> Future
        self._msg_id_counter = 0
        
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
            msg_id = msg.header.msg_id
            logger.info(f"  Message Type: {msg_type}")
            logger.info(f"  Message ID: {msg_id}")
            
            if msg.body.request.HasField('notify'):
                await self._handle_notify(record, msg, writer)
            elif msg.body.response.WhichOneof('resp_type'):
                # This is a response to a request we sent
                await self._handle_response(msg)
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
                
                # Parse Boot! event parameters
                boot_params = self._parse_boot_notification(event)
                
                # Track agent connection with Boot! metadata
                self._connected_agents[record.from_id] = {
                    'last_boot': datetime.now().isoformat(),
                    'last_heartbeat': datetime.now().isoformat(),
                    'socket_path': '/tmp/usp-agent.sock',  # TODO: get from database
                    'manufacturer_oui': boot_params.get('manufacturer_oui', ''),
                    'product_class': boot_params.get('product_class', ''),
                    'serial_number': boot_params.get('serial_number', ''),
                    'ip_address': boot_params.get('ip_address', ''),
                    'boot_command_key': boot_params.get('command_key', ''),
                    'boot_cause': boot_params.get('cause', '')
                }
                
                logger.info(f"  Agent metadata: OUI={boot_params.get('manufacturer_oui')}, "
                          f"Product={boot_params.get('product_class')}, "
                          f"Serial={boot_params.get('serial_number')}")
                
                # Query agent capabilities and instances
                await self._query_agent_capabilities(record.from_id, record.to_id)
                
                # Send Set request to configure periodic heartbeat
                await self._configure_periodic_heartbeat(record.from_id, record.to_id)
            elif event.event_name == "Periodic!":
                logger.info("✓ Periodic! notification received successfully!")
                # Update heartbeat timestamp
                if record.from_id in self._connected_agents:
                    self._connected_agents[record.from_id]['last_heartbeat'] = datetime.now().isoformat()
        else:
            logger.info("  Notify type: (other)")
    
    def _parse_boot_notification(self, event):
        """
        Parse Boot! notification event parameters
        
        Args:
            event: USP Event message
            
        Returns:
            dict: Parsed boot parameters
        """
        boot_params = {}
        
        # Extract direct parameters
        if 'CommandKey' in event.params:
            boot_params['command_key'] = event.params['CommandKey']
        
        if 'Cause' in event.params:
            boot_params['cause'] = event.params['Cause']
        
        # Parse BootParameterMap (JSON string)
        if 'BootParameterMap' in event.params:
            try:
                boot_map = json.loads(event.params['BootParameterMap'])
                
                # Extract known parameters
                boot_params['manufacturer_oui'] = boot_map.get('Device.DeviceInfo.ManufacturerOUI', '')
                boot_params['product_class'] = boot_map.get('Device.DeviceInfo.ProductClass', '')
                boot_params['serial_number'] = boot_map.get('Device.DeviceInfo.SerialNumber', '')
                boot_params['ip_address'] = boot_map.get('Device.LocalAgent.X_ARRIS-COM_IPAddr', '')
                
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse BootParameterMap: {e}")
        
        return boot_params
    
    async def _query_agent_capabilities(self, agent_id, controller_id):
        """
        Query agent for supported data model and instances after Boot!
        
        Args:
            agent_id: Agent endpoint ID
            controller_id: Controller endpoint ID
        """
        try:
            logger.info("=" * 60)
            logger.info("Querying agent capabilities...")
            logger.info("=" * 60)
            
            agent_socket = "/tmp/usp-agent.sock"  # TODO: Get from database
            
            # 1. GetSupportedDM - Query top-level data model
            logger.info("Sending GetSupportedDM request for Device.")
            gsdm_msg = GetSupportedDM(
                to_id=agent_id,
                from_id=controller_id,
                obj_paths=["Device."],
                first_level_only=True,
                return_commands=True,
                return_events=True,
                return_params=True
            )
            
            resp_record, resp_msg = await self._send_dm_request(gsdm_msg, 'GetSupportedDM', agent_socket)
            if resp_msg:
                await self._handle_get_supported_dm_response(resp_msg)
            
            # 2. GetInstances - Query multi-instance objects
            logger.info("Sending GetInstances request...")
            gi_msg = GetInstances(
                to_id=agent_id,
                from_id=controller_id,
                obj_paths=[
                    "Device.LocalAgent.Controller.",
                    "Device.LocalAgent.MTP.",
                    "Device.LocalAgent.Subscription."
                ],
                first_level_only=False
            )
            
            resp_record, resp_msg = await self._send_dm_request(gi_msg, 'GetInstances', agent_socket)
            if resp_msg:
                await self._handle_get_instances_response(resp_msg)
            
            logger.info("✓ Agent capability queries completed")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"Error querying agent capabilities: {e}", exc_info=True)
    
    async def _send_dm_request(self, request_msg, request_type, agent_socket):
        """
        Send GetSupportedDM or GetInstances request and wait for response
        
        Args:
            request_msg: GetSupportedDM or GetInstances message
            request_type: Type of request
            agent_socket: Path to agent socket
            
        Returns:
            tuple: (resp_record, resp_msg) or (None, None) if error
        """
        transport = None
        try:
            logger.info(f"Sending {request_type} request...")
            
            # Connect to agent's socket and send the request
            transport = UdsTransport(agent_socket, mode='connect')
            await transport.connect()
            request_record = request_msg.SerializeToString()
            await transport.send_message(request_record)
            
            logger.info(f"✓ {request_type} request sent")
            logger.info(f"Waiting for {request_type} response from agent...")
            
            # Wait for response
            response_data = await transport.receive_message()
            if response_data:
                # Parse the response
                resp_record = usp_record_pb2.Record()
                resp_record.ParseFromString(response_data)
                
                resp_msg = usp_msg_pb2.Msg()
                resp_msg.ParseFromString(resp_record.no_session_context.payload)
                
                logger.info(f"✓ {request_type} response received from agent")
                return resp_record, resp_msg
            else:
                logger.warning(f"No {request_type} response received")
                return None, None
            
        except Exception as e:
            logger.error(f"Error sending {request_type}: {e}", exc_info=True)
            return None, None
        finally:
            if transport:
                await transport.close()
    
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
    
    def _generate_msg_id(self):
        """Generate unique message ID"""
        self._msg_id_counter += 1
        return str(self._msg_id_counter)
    
    async def _handle_response(self, msg):
        """
        Handle response message and complete pending future
        
        Args:
            msg: USP Message with response
        """
        msg_id = msg.header.msg_id
        
        # Check response type and log appropriately
        if msg.body.response.HasField('get_supported_dm_resp'):
            await self._handle_get_supported_dm_response(msg)
        elif msg.body.response.HasField('get_instances_resp'):
            await self._handle_get_instances_response(msg)
        elif msg_id in self._pending_requests:
            future = self._pending_requests[msg_id]
            
            # Parse response based on type
            if msg.body.response.HasField('get_resp'):
                result = self._parse_get_response(msg)
            elif msg.body.response.HasField('set_resp'):
                result = self._parse_set_response(msg)
            elif msg.body.response.HasField('operate_resp'):
                result = self._parse_operate_response(msg)
            else:
                result = None
            
            # Complete the future
            if not future.done():
                future.set_result(result)
        else:
            logger.warning(f"Received response for unknown msg_id: {msg_id}")
    
    async def _handle_get_supported_dm_response(self, msg):
        """
        Handle GetSupportedDM response
        
        Args:
            msg: USP Message with GetSupportedDMResp
        """
        gsdm_resp = msg.body.response.get_supported_dm_resp
        
        logger.info("=" * 60)
        logger.info("GetSupportedDM Response:")
        
        for req_obj_result in gsdm_resp.req_obj_results:
            logger.info(f"  Requested Object: {req_obj_result.req_obj_path}")
            
            if req_obj_result.err_code != 0:
                logger.error(f"    Error {req_obj_result.err_code}: {req_obj_result.err_msg}")
                continue
            
            logger.info(f"    Data Model URI: {req_obj_result.data_model_inst_uri}")
            logger.info(f"    Supported Objects: {len(req_obj_result.supported_objs)}")
            
            # Log first few supported objects as examples
            for i, obj in enumerate(req_obj_result.supported_objs[:5]):
                logger.info(f"      {obj.supported_obj_path}")
                logger.info(f"        Access: {obj.access}, Multi-instance: {obj.is_multi_instance}")
                if obj.supported_params:
                    logger.info(f"        Parameters: {len(obj.supported_params)}")
                if obj.supported_commands:
                    logger.info(f"        Commands: {len(obj.supported_commands)}")
                if obj.supported_events:
                    logger.info(f"        Events: {len(obj.supported_events)}")
            
            if len(req_obj_result.supported_objs) > 5:
                logger.info(f"      ... and {len(req_obj_result.supported_objs) - 5} more")
        
        logger.info("=" * 60)
    
    async def _handle_get_instances_response(self, msg):
        """
        Handle GetInstances response
        
        Args:
            msg: USP Message with GetInstancesResp
        """
        gi_resp = msg.body.response.get_instances_resp
        
        logger.info("=" * 60)
        logger.info("GetInstances Response:")
        
        for req_path_result in gi_resp.req_path_results:
            logger.info(f"  Requested Path: {req_path_result.requested_path}")
            
            if req_path_result.err_code != 0:
                logger.error(f"    Error {req_path_result.err_code}: {req_path_result.err_msg}")
                continue
            
            for curr_obj in req_path_result.curr_objs:
                logger.info(f"    Instance: {curr_obj.instantiated_obj_path}")
                if curr_obj.unique_keys:
                    for key, value in curr_obj.unique_keys.items():
                        logger.info(f"      {key} = {value}")
        
        logger.info("=" * 60)
    
    def _parse_get_response(self, msg):
        """Parse Get response into dict"""
        result = {}
        get_resp = msg.body.response.get_resp
        
        for req_path_result in get_resp.req_path_results:
            # Check if there's an error (err_code is non-zero for errors)
            if req_path_result.err_code != 0:
                # Error for this path
                result[req_path_result.requested_path] = {
                    'error': req_path_result.err_code,
                    'error_msg': req_path_result.err_msg
                }
            else:
                # Success - collect parameters
                for resolved in req_path_result.resolved_path_results:
                    for param_name, param_value in resolved.result_params.items():
                        result[param_name] = param_value
        
        return result
    
    def _parse_set_response(self, msg):
        """Parse Set response into dict"""
        result = {}
        set_resp = msg.body.response.set_resp
        
        for updated_obj in set_resp.updated_obj_results:
            if updated_obj.oper_status.HasField('oper_success'):
                for inst_result in updated_obj.oper_status.oper_success.updated_inst_results:
                    for param_name, param_value in inst_result.updated_params.items():
                        result[param_name] = param_value
            elif updated_obj.oper_status.HasField('oper_failure'):
                err = updated_obj.oper_status.oper_failure
                result['error'] = {
                    'code': err.err_code,
                    'message': err.err_msg
                }
        
        return result
    
    def _parse_operate_response(self, msg):
        """Parse Operate response into dict"""
        # TODO: Implement when Operate is needed
        return {}
    
    async def send_get_request(self, agent_id, paths):
        """
        Send Get request to agent and wait for response
        
        Args:
            agent_id: Agent endpoint ID
            paths: List of parameter paths to get
            
        Returns:
            dict: Parameter name -> value mapping
        """
        if agent_id not in self._connected_agents:
            raise ValueError(f"Agent not connected: {agent_id}")
        
        agent_socket = self._connected_agents[agent_id]['socket_path']
        msg_id = self._generate_msg_id()
        
        # Create Get message
        get_msg = Get(
            to_id=agent_id,
            from_id=self._endpoint_id,
            param_paths=paths
        )
        
        # Set custom msg_id
        get_msg._msg.header.msg_id = msg_id
        get_msg.generate_record()  # Regenerate record with new msg_id
        
        # Create future for response
        future = asyncio.Future()
        self._pending_requests[msg_id] = future
        
        try:
            # Send request and wait for response on same connection
            transport = UdsTransport(agent_socket, mode='connect')
            await transport.connect()
            request_record = get_msg.SerializeToString()
            await transport.send_message(request_record)
            
            logger.info(f"✓ Get request sent (msg_id={msg_id})")
            
            # Wait for response on the same connection
            response_data = await asyncio.wait_for(transport.receive_message(), timeout=10.0)
            
            if response_data:
                # Parse response
                resp_record = usp_record_pb2.Record()
                resp_record.ParseFromString(response_data)
                
                resp_msg = usp_msg_pb2.Msg()
                resp_msg.ParseFromString(resp_record.no_session_context.payload)
                
                # Parse and return result
                result = self._parse_get_response(resp_msg)
                return result
            else:
                raise RuntimeError("No response received")
            
        except asyncio.TimeoutError:
            raise TimeoutError("Get request timed out")
        finally:
            if msg_id in self._pending_requests:
                del self._pending_requests[msg_id]
            await transport.close()
    
    async def send_set_request(self, agent_id, parameters):
        """
        Send Set request to agent and wait for response
        
        Args:
            agent_id: Agent endpoint ID
            parameters: List of {path: ..., value: ...} dicts
            
        Returns:
            dict: Updated parameters
        """
        if agent_id not in self._connected_agents:
            raise ValueError(f"Agent not connected: {agent_id}")
        
        agent_socket = self._connected_agents[agent_id]['socket_path']
        msg_id = self._generate_msg_id()
        
        # Group parameters by object path
        obj_paths = {}
        for param in parameters:
            path = param['path']
            value = param['value']
            
            # Extract object path (everything before last parameter)
            if '.' in path:
                parts = path.rsplit('.', 1)
                obj_path = parts[0] + '.'
                param_name = parts[1]
            else:
                raise ValueError(f"Invalid parameter path: {path}")
            
            if obj_path not in obj_paths:
                obj_paths[obj_path] = []
            
            obj_paths[obj_path].append({"param": param_name, "value": value})
        
        # Build objects list
        objects = [
            {"obj_path": obj_path, "param_settings": settings}
            for obj_path, settings in obj_paths.items()
        ]
        
        # Create Set message
        set_msg = Set(
            to_id=agent_id,
            from_id=self._endpoint_id,
            objects=objects,
            allow_partial=True
        )
        
        # Set custom msg_id
        set_msg._msg.header.msg_id = msg_id
        set_msg.generate_record()  # Regenerate record with new msg_id
        
        try:
            # Send request and wait for response on same connection
            transport = UdsTransport(agent_socket, mode='connect')
            await transport.connect()
            request_record = set_msg.SerializeToString()
            await transport.send_message(request_record)
            
            logger.info(f"✓ Set request sent (msg_id={msg_id})")
            
            # Wait for response on the same connection
            response_data = await asyncio.wait_for(transport.receive_message(), timeout=10.0)
            
            if response_data:
                # Parse response
                resp_record = usp_record_pb2.Record()
                resp_record.ParseFromString(response_data)
                
                resp_msg = usp_msg_pb2.Msg()
                resp_msg.ParseFromString(resp_record.no_session_context.payload)
                
                # Parse and return result
                result = self._parse_set_response(resp_msg)
                return result
            else:
                raise RuntimeError("No response received")
            
        except asyncio.TimeoutError:
            raise TimeoutError("Set request timed out")
        finally:
            await transport.close()
    
    async def send_operate_request(self, agent_id, command, args):
        """
        Send Operate request to agent and wait for response
        
        Args:
            agent_id: Agent endpoint ID
            command: Command path (e.g., "Device.Reboot()")
            args: Command arguments (dict)
            
        Returns:
            dict: Operation result
        """
        if agent_id not in self._connected_agents:
            raise ValueError(f"Agent not connected: {agent_id}")
        
        agent_socket = self._connected_agents[agent_id]['socket_path']
        msg_id = self._generate_msg_id()
        
        # Create Operate request
        operate_msg = usp_msg_pb2.Msg()
        operate_msg.header.msg_id = msg_id
        operate_msg.header.msg_type = usp_msg_pb2.Header.OPERATE
        
        # Set command
        operate_req = operate_msg.body.request.operate
        operate_req.command = command
        
        # Set input arguments
        for key, value in args.items():
            operate_req.command_key = key
            operate_req.input[key] = str(value)
        
        # Wrap in USP Record
        record = usp_record_pb2.Record()
        record.version = "1.0"
        record.to_id = agent_id
        record.from_id = self._endpoint_id
        record.payload_security = usp_record_pb2.Record.PLAINTEXT
        record.no_session_context.payload = operate_msg.SerializeToString()
        
        # Store pending request
        future = asyncio.Future()
        self._pending_requests[msg_id] = future
        
        # Send request
        transport = UdsTransport(agent_socket, 'connect')
        
        try:
            await transport.connect()
            
            request_record = record.SerializeToString()
            await transport.send_message(request_record)
            
            logger.info(f"✓ Operate request sent: {command} (msg_id={msg_id})")
            
            # Wait for response on the same connection
            response_data = await asyncio.wait_for(transport.receive_message(), timeout=10.0)
            
            if response_data:
                # Parse response
                resp_record = usp_record_pb2.Record()
                resp_record.ParseFromString(response_data)
                
                resp_msg = usp_msg_pb2.Msg()
                resp_msg.ParseFromString(resp_record.no_session_context.payload)
                
                # Parse and return result
                result = self._parse_operate_response(resp_msg)
                return result
            else:
                raise RuntimeError("No response received")
            
        except asyncio.TimeoutError:
            raise TimeoutError("Operate request timed out")
        finally:
            if msg_id in self._pending_requests:
                del self._pending_requests[msg_id]
            await transport.close()
    
    def _parse_operate_response(self, msg):
        """
        Parse Operate response message
        
        Args:
            msg: USP Msg protobuf
            
        Returns:
            dict: Operation results
        """
        operate_resp = msg.body.response.operate_resp
        
        results = []
        for op_result in operate_resp.operation_results:
            if op_result.HasField('req_output_args'):
                # Success
                output = {}
                for key, value in op_result.req_output_args.output_args.items():
                    output[key] = value
                
                results.append({
                    'success': True,
                    'executed_command': op_result.executed_command,
                    'output_args': output
                })
            elif op_result.HasField('req_obj_path'):
                # Error
                cmd_failure = op_result.req_obj_path.cmd_failure
                results.append({
                    'success': False,
                    'command': op_result.req_obj_path.requested_path,
                    'error_code': cmd_failure.err_code,
                    'error_message': cmd_failure.err_msg
                })
        
        return results
    
    def get_connected_agents(self):
        """
        Get list of connected agents with metadata
        
        Returns:
            list: [{"agent_id": ..., "last_boot": ..., "last_heartbeat": ..., 
                   "manufacturer_oui": ..., "product_class": ..., "serial_number": ..., 
                   "ip_address": ..., "boot_cause": ...}, ...]
        """
        agents = []
        for agent_id, info in self._connected_agents.items():
            agents.append({
                'agent_id': agent_id,
                'last_boot': info['last_boot'],
                'last_heartbeat': info['last_heartbeat'],
                'manufacturer_oui': info.get('manufacturer_oui', ''),
                'product_class': info.get('product_class', ''),
                'serial_number': info.get('serial_number', ''),
                'ip_address': info.get('ip_address', ''),
                'boot_cause': info.get('boot_cause', ''),
                'boot_command_key': info.get('boot_command_key', '')
            })
        return agents
    
    async def stop(self):
        """Stop the controller and clean up"""
        if self._transport:
            await self._transport.close()
        
        logger.info("Controller stopped")
