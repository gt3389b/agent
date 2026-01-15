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

# File Name: multi_mtp_controller.py
#
# Description: Multi-MTP Controller supporting both UDS and CoAP
#
# This controller tracks which MTP each agent uses and routes messages
# appropriately using the correct transport.
"""

import logging
import json
import asyncio
from datetime import datetime
from typing import Dict, Optional, Tuple

import aiocoap
import aiocoap.resource as resource
import stomp

from mtp.uds import UdsTransport
from mtp.coap_binding import CoapUspBinding
from message import usp_record_pb2
from message import usp_msg_pb2
from message import Set, Get, GetSupportedDM, GetInstances

logger = logging.getLogger(__name__)


class MultiMtpController:
    """
    Multi-MTP Controller supporting UDS, CoAP, and STOMP transports
    
    This controller:
    - Listens on both UDS socket, CoAP port, and STOMP broker
    - Tracks which MTP each agent uses
    - Routes requests/responses using the correct transport
    """
    
    def __init__(self, config_file):
        """
        Initialize Multi-MTP Controller
        
        Args:
            config_file (str): Path to configuration file
        """
        # Load configuration
        with open(config_file, 'r') as f:
            self._config = json.load(f)
        
        self._endpoint_id = self._config['endpoint_id']
        
        # Get MTP configuration section
        mtp_config = self._config.get('mtp', {})
        
        # UDS configuration
        uds_config = mtp_config.get('uds', {})
        self._uds_enabled = uds_config.get('enabled', True)
        self._uds_socket_path = uds_config.get('socket_path')
        self._uds_mode = uds_config.get('mode', 'listen')
        self._uds_transport = None
        
        # CoAP configuration
        coap_config = mtp_config.get('coap', {})
        self._coap_enabled = coap_config.get('enabled', True)
        self._coap_host = coap_config.get('host', 'localhost')
        self._coap_port = coap_config.get('port', 5683)
        self._coap_path = coap_config.get('path', 'usp')
        self._coap_binding = None
        self._coap_context = None
        
        # STOMP configuration
        stomp_config = mtp_config.get('stomp', {})
        self._stomp_enabled = stomp_config.get('enabled', False)
        self._stomp_host = stomp_config.get('host', 'localhost')
        self._stomp_port = stomp_config.get('port', 61613)
        self._stomp_controller_queue = stomp_config.get('controller_queue', '/queue/usp-controller')
        self._stomp_agent_queue = stomp_config.get('agent_queue', '/queue/usp-agent')
        self._stomp_connection = None
        self._stomp_connected = False
        self._stomp_message_queue = asyncio.Queue()
        
        # Agent tracking - stores MTP info for each agent
        # Format: agent_id -> {
        #   'mtp_type': 'uds' | 'coap' | 'stomp',
        #   'mtp_info': socket_path | coap_url | stomp_reply_queue,
        #   'last_boot': timestamp,
        #   'last_heartbeat': timestamp,
        #   'metadata': {...}
        # }
        self._connected_agents: Dict[str, dict] = {}
        
        # Request/response tracking
        self._pending_requests = {}  # msg_id -> Future
        self._msg_id_counter = 0
        
        logger.info("=" * 60)
        logger.info("Multi-MTP Controller Initialized")
        logger.info(f"  Endpoint ID: {self._endpoint_id}")
        if self._uds_enabled and self._uds_socket_path:
            logger.info(f"  UDS: {self._uds_socket_path} (mode={self._uds_mode})")
        if self._coap_enabled:
            logger.info(f"  CoAP: {self._coap_host}:{self._coap_port}/{self._coap_path}")
        if self._stomp_enabled:
            logger.info(f"  STOMP: {self._stomp_host}:{self._stomp_port}")
            logger.info(f"    Controller Queue: {self._stomp_controller_queue}")
            logger.info(f"    Agent Queue: {self._stomp_agent_queue}")
        logger.info("=" * 60)
    
    async def start(self):
        """Start the multi-MTP controller"""
        tasks = []
        
        # Start UDS listener if enabled and configured
        if self._uds_enabled and self._uds_socket_path:
            self._uds_transport = UdsTransport(self._uds_socket_path, self._uds_mode)
            logger.info(f"Starting UDS listener on {self._uds_socket_path}")
            tasks.append(asyncio.create_task(self._run_uds_server()))
        
        # Start CoAP listener if enabled
        if self._coap_enabled:
            logger.info(f"Starting CoAP listener on {self._coap_host}:{self._coap_port}/{self._coap_path}")
            tasks.append(asyncio.create_task(self._run_coap_server()))
        
        # Start STOMP listener if enabled
        if self._stomp_enabled:
            logger.info(f"Starting STOMP listener on {self._stomp_host}:{self._stomp_port}")
            tasks.append(asyncio.create_task(self._run_stomp_server()))
        
        if not tasks:
            logger.error("No transports enabled! Enable at least one MTP in config.")
            return
        
        logger.info("Controller waiting for agent messages on multiple MTPs...")
        
        # Run all servers concurrently
        await asyncio.gather(*tasks)
    
    async def _run_uds_server(self):
        """Run UDS server"""
        try:
            await self._uds_transport.start_server(self._handle_uds_message)
            async with self._uds_transport.server:
                await self._uds_transport.server.serve_forever()
        except Exception as e:
            logger.error(f"UDS server error: {e}", exc_info=True)
    
    async def _run_coap_server(self):
        """Run CoAP server"""
        try:
            # Create and add USP resource
            root = resource.Site()
            usp_resource = CoapUspResource(self)
            root.add_resource([self._coap_path], usp_resource)
            
            # Create CoAP context with the site
            self._coap_context = await aiocoap.Context.create_server_context(
                root,
                bind=(self._coap_host, self._coap_port)
            )
            
            logger.info(f"✓ CoAP server listening on {self._coap_host}:{self._coap_port}/{self._coap_path}")
            
            # Keep server running
            await asyncio.Event().wait()
            
        except Exception as e:
            logger.error(f"CoAP server error: {e}", exc_info=True)
    
    async def _run_stomp_server(self):
        """Run STOMP server (connect to broker and subscribe)"""
        try:
            # Create STOMP listener with callback
            listener = StompMessageListener(self)
            
            # Connect to STOMP broker
            self._stomp_connection = stomp.Connection([(self._stomp_host, self._stomp_port)])
            self._stomp_connection.set_listener('', listener)
            self._stomp_connection.connect(wait=True)
            
            # Subscribe to controller queue
            self._stomp_connection.subscribe(
                destination=self._stomp_controller_queue,
                id=1,
                ack='auto'
            )
            
            logger.info(f"✓ STOMP connected to {self._stomp_host}:{self._stomp_port}")
            logger.info(f"✓ STOMP subscribed to {self._stomp_controller_queue}")
            
            self._stomp_connected = True
            
            # Process messages from queue
            while True:
                message_data = await self._stomp_message_queue.get()
                if message_data:
                    await self._handle_stomp_message(message_data)
            
        except Exception as e:
            logger.error(f"STOMP server error: {e}", exc_info=True)
        finally:
            if self._stomp_connection and self._stomp_connection.is_connected():
                self._stomp_connection.disconnect()
    
    async def _handle_uds_message(self, data, writer):
        """
        Handle received USP message from UDS transport
        
        Args:
            data (bytes): Raw message data
            writer: Stream writer for sending responses
        """
        try:
            # Parse USP Record
            record = usp_record_pb2.Record()
            record.ParseFromString(data)
            
            agent_id = record.from_id
            
            # Track this agent as using UDS transport
            if agent_id not in self._connected_agents:
                self._connected_agents[agent_id] = {
                    'mtp_type': 'uds',
                    'mtp_info': '/tmp/usp-agent.sock',  # TODO: Extract from DB
                    'last_heartbeat': datetime.now().isoformat(),
                    'metadata': {}
                }
            
            # Update last heartbeat
            self._connected_agents[agent_id]['last_heartbeat'] = datetime.now().isoformat()
            
            # Process the message
            await self._process_message(record, writer, 'uds')
            
        except Exception as e:
            logger.error(f"Error handling UDS message: {e}", exc_info=True)
    
    async def _handle_coap_message(self, data, coap_request):
        """
        Handle received USP message from CoAP transport
        
        Args:
            data (bytes): Raw message data
            coap_request: aiocoap Request object
        
        Returns:
            Optional[bytes]: Response data if needed
        """
        try:
            # Parse USP Record
            record = usp_record_pb2.Record()
            record.ParseFromString(data)
            
            agent_id = record.from_id
            
            # Extract agent's CoAP URL from request remote address
            # coap_request.remote can be various types depending on the transport
            # It's often an _Address object with a sockaddr attribute
            remote_addr = coap_request.remote
            
            logger.debug(f"CoAP request remote address: {remote_addr} (type={type(remote_addr)})")
            
            # Try to get sockaddr from _Address object
            if hasattr(remote_addr, 'sockaddr'):
                sockaddr = remote_addr.sockaddr
                logger.debug(f"  sockaddr: {sockaddr}")
                if isinstance(sockaddr, tuple) and len(sockaddr) >= 2:
                    remote_host_raw = sockaddr[0]
                    if isinstance(remote_host_raw, str):
                        remote_host = remote_host_raw
                    else:
                        remote_host = 'localhost'
                else:
                    remote_host = 'localhost'
            elif isinstance(remote_addr, tuple) and len(remote_addr) >= 2:
                # Try to get string representation of host
                remote_host_raw = remote_addr[0]
                if isinstance(remote_host_raw, str):
                    remote_host = remote_host_raw
                else:
                    # Socket object or other - default to localhost
                    remote_host = 'localhost'
            else:
                # Fallback to localhost if we can't determine
                remote_host = 'localhost'
            
            # Normalize IPv6 localhost
            if remote_host in ('::1', '::ffff:127.0.0.1'):
                remote_host = 'localhost'
            
            # Since we don't know the agent's exact listening port from a client request,
            # we should extract it from the agent database or use a known port
            # For now, assume agent is on port 5684 (from config)
            agent_url = f"coap://{remote_host}:5684/{self._coap_path}"
            
            logger.debug(f"Constructed agent URL: {agent_url}")
            
            # Track this agent as using CoAP transport
            if agent_id not in self._connected_agents:
                self._connected_agents[agent_id] = {
                    'mtp_type': 'coap',
                    'mtp_info': agent_url,
                    'last_heartbeat': datetime.now().isoformat(),
                    'metadata': {}
                }
            else:
                # Update MTP info in case agent moved
                self._connected_agents[agent_id]['mtp_type'] = 'coap'
                self._connected_agents[agent_id]['mtp_info'] = agent_url
            
            # Update last heartbeat
            self._connected_agents[agent_id]['last_heartbeat'] = datetime.now().isoformat()
            
            # Process the message
            response_data = await self._process_message(record, coap_request, 'coap')
            
            return response_data
            
        except Exception as e:
            logger.error(f"Error handling CoAP message: {e}", exc_info=True)
            return None
    
    async def _handle_stomp_message(self, message_data):
        """
        Handle received USP message from STOMP transport
        
        Args:
            message_data (dict): Message data from STOMP listener
                Contains 'body' (bytes) and 'headers' (dict)
        """
        try:
            # Extract message body
            data = message_data['body']
            headers = message_data.get('headers', {})
            
            # Parse USP Record
            record = usp_record_pb2.Record()
            record.ParseFromString(data)
            
            agent_id = record.from_id
            
            # Extract reply-to queue from headers (if present)
            reply_to = headers.get('reply-to', self._stomp_agent_queue)
            
            logger.debug(f"STOMP message from {agent_id}, reply-to: {reply_to}")
            
            # Track this agent as using STOMP transport
            if agent_id not in self._connected_agents:
                self._connected_agents[agent_id] = {
                    'mtp_type': 'stomp',
                    'mtp_info': reply_to,  # Store reply-to queue
                    'last_heartbeat': datetime.now().isoformat(),
                    'metadata': {}
                }
            else:
                # Update MTP info in case agent queue changed
                self._connected_agents[agent_id]['mtp_type'] = 'stomp'
                self._connected_agents[agent_id]['mtp_info'] = reply_to
            
            # Update last heartbeat
            self._connected_agents[agent_id]['last_heartbeat'] = datetime.now().isoformat()
            
            # Process the message (no response needed for STOMP - async)
            await self._process_message(record, None, 'stomp')
            
        except Exception as e:
            logger.error(f"Error handling STOMP message: {e}", exc_info=True)
    
    async def _process_message(self, record, writer_or_request, mtp_type):
        """
        Process USP message (common logic for UDS, CoAP, and STOMP)
        
        Args:
            record: USP Record protobuf
            writer_or_request: Stream writer (UDS) or CoAP request (or None for STOMP)
            mtp_type: 'uds' | 'coap' | 'stomp'
        
        Returns:
            Optional[bytes]: Response data for CoAP, None for UDS
        """
        logger.info("=" * 60)
        logger.info(f"RECEIVED USP RECORD via {mtp_type.upper()}:")
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
        
        response_data = None
        
        if msg.body.request.HasField('notify'):
            response_data = await self._handle_notify(record, msg, writer_or_request, mtp_type)
        elif msg.body.response.WhichOneof('resp_type'):
            # This is a response to a request we sent
            await self._handle_response(msg)
        else:
            logger.info(f"  Payload size: {len(record.no_session_context.payload)} bytes")
        
        logger.info("=" * 60)
        
        return response_data
    
    async def _handle_notify(self, record, msg, writer_or_request, mtp_type):
        """
        Handle Notify message
        
        Args:
            record: USP Record
            msg: USP Message
            writer_or_request: Stream writer (UDS) or CoAP request
            mtp_type: 'uds' or 'coap'
        
        Returns:
            Optional[bytes]: Response data for CoAP
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
                logger.info(f"✓ Boot! notification received via {mtp_type.upper()}")
                
                # Parse Boot! event parameters
                boot_params = self._parse_boot_notification(event)
                
                # Update agent metadata
                agent_id = record.from_id
                if agent_id in self._connected_agents:
                    self._connected_agents[agent_id]['last_boot'] = datetime.now().isoformat()
                    self._connected_agents[agent_id]['metadata'] = {
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
                logger.info(f"✓ Periodic! notification received via {mtp_type.upper()}")
                # Update heartbeat timestamp (already done above)
        else:
            logger.info("  Notify type: (other)")
        
        return None  # No response needed for notifications
    
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
            
            resp_record, resp_msg = await self._send_request(gsdm_msg, agent_id, 'GetSupportedDM')
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
            
            resp_record, resp_msg = await self._send_request(gi_msg, agent_id, 'GetInstances')
            if resp_msg:
                await self._handle_get_instances_response(resp_msg)
            
            logger.info("✓ Agent capability queries completed")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"Error querying agent capabilities: {e}", exc_info=True)
    
    async def _send_request(self, request_msg, agent_id, request_type):
        """
        Send request to agent using appropriate MTP
        
        Args:
            request_msg: Message object (GetSupportedDM, GetInstances, Set, Get, etc.)
            agent_id: Target agent endpoint ID
            request_type: Type of request for logging
            
        Returns:
            tuple: (resp_record, resp_msg) or (None, None) if error
        """
        if agent_id not in self._connected_agents:
            logger.error(f"Agent {agent_id} not connected")
            return None, None
        
        agent_info = self._connected_agents[agent_id]
        mtp_type = agent_info['mtp_type']
        mtp_info = agent_info['mtp_info']
        
        logger.info(f"Sending {request_type} to {agent_id} via {mtp_type.upper()}")
        
        if mtp_type == 'uds':
            return await self._send_request_uds(request_msg, mtp_info, request_type)
        elif mtp_type == 'coap':
            return await self._send_request_coap(request_msg, mtp_info, request_type)
        elif mtp_type == 'stomp':
            return await self._send_request_stomp(request_msg, mtp_info, request_type)
        else:
            logger.error(f"Unknown MTP type: {mtp_type}")
            return None, None
    
    async def _send_request_uds(self, request_msg, socket_path, request_type):
        """Send request via UDS"""
        transport = None
        try:
            transport = UdsTransport(socket_path, mode='connect')
            await transport.connect()
            request_record = request_msg.SerializeToString()
            await transport.send_message(request_record)
            
            logger.info(f"✓ {request_type} request sent via UDS")
            logger.info(f"Waiting for {request_type} response...")
            
            # Wait for response
            response_data = await transport.receive_message()
            if response_data:
                # Parse the response
                resp_record = usp_record_pb2.Record()
                resp_record.ParseFromString(response_data)
                
                resp_msg = usp_msg_pb2.Msg()
                resp_msg.ParseFromString(resp_record.no_session_context.payload)
                
                logger.info(f"✓ {request_type} response received via UDS")
                return resp_record, resp_msg
            else:
                logger.warning(f"No {request_type} response received")
                return None, None
            
        except Exception as e:
            logger.error(f"Error sending {request_type} via UDS: {e}", exc_info=True)
            return None, None
        finally:
            if transport:
                await transport.close()
    
    async def _send_request_coap(self, request_msg, coap_url, request_type):
        """Send request via CoAP"""
        try:
            # Serialize request
            request_record = request_msg.SerializeToString()
            
            # Create CoAP POST request
            coap_request = aiocoap.Message(
                code=aiocoap.POST,
                uri=coap_url,
                payload=request_record
            )
            
            # Create context if needed
            if not self._coap_context:
                self._coap_context = await aiocoap.Context.create_client_context()
            
            logger.info(f"✓ {request_type} request sent via CoAP to {coap_url}")
            
            # Send request and wait for response
            response = await self._coap_context.request(coap_request).response
            
            if response and response.payload:
                # Parse the response
                resp_record = usp_record_pb2.Record()
                resp_record.ParseFromString(response.payload)
                
                resp_msg = usp_msg_pb2.Msg()
                resp_msg.ParseFromString(resp_record.no_session_context.payload)
                
                logger.info(f"✓ {request_type} response received via CoAP")
                return resp_record, resp_msg
            else:
                logger.warning(f"No {request_type} response received via CoAP")
                return None, None
            
        except Exception as e:
            logger.error(f"Error sending {request_type} via CoAP: {e}", exc_info=True)
            return None, None
    
    async def _send_request_stomp(self, request_msg, agent_queue, request_type):
        """
        Send request via STOMP
        
        Note: STOMP is async/message-based, so we don't wait for immediate response
        Response will arrive via the STOMP listener callback
        """
        try:
            if not self._stomp_connected:
                logger.error("STOMP not connected")
                return None, None
            
            # Serialize request
            request_record = request_msg.SerializeToString()
            
            # Send to agent's queue
            self._stomp_connection.send(
                destination=agent_queue,
                body=request_record,
                headers={'reply-to': self._stomp_controller_queue}
            )
            
            logger.info(f"✓ {request_type} request sent via STOMP to {agent_queue}")
            logger.info(f"Note: STOMP response will arrive asynchronously via {self._stomp_controller_queue}")
            
            # For STOMP, we don't wait for response here - it's message-based
            # The response will be received via the STOMP listener
            return None, None
            
        except Exception as e:
            logger.error(f"Error sending {request_type} via STOMP: {e}", exc_info=True)
            return None, None
    
    async def _configure_periodic_heartbeat(self, agent_id, controller_id):
        """
        Send Set request to configure periodic heartbeat on the agent
        
        Args:
            agent_id: Agent endpoint ID
            controller_id: Controller endpoint ID
        """
        try:
            logger.info("Configuring periodic heartbeat on agent...")
            
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
            resp_record, resp_msg = await self._send_request(set_msg, agent_id, 'Set')
            
            if resp_msg:
                await self._handle_set_response(resp_msg)
                logger.info("✓ Periodic heartbeat configured: PeriodicNotifInterval=30 seconds")
            else:
                logger.error("Failed to configure periodic heartbeat")
                
        except Exception as e:
            logger.error(f"Error configuring periodic heartbeat: {e}", exc_info=True)
    
    async def _handle_response(self, msg):
        """
        Handle response message
        
        Args:
            msg: USP Message with response
        """
        msg_id = msg.header.msg_id
        
        # Check response type and log appropriately
        if msg.body.response.HasField('get_supported_dm_resp'):
            await self._handle_get_supported_dm_response(msg)
        elif msg.body.response.HasField('get_instances_resp'):
            await self._handle_get_instances_response(msg)
        elif msg.body.response.HasField('set_resp'):
            await self._handle_set_response(msg)
        elif msg.body.response.HasField('get_resp'):
            await self._handle_get_response(msg)
        else:
            logger.warning(f"Unhandled response type for msg_id: {msg_id}")
    
    async def _handle_get_supported_dm_response(self, msg):
        """Handle GetSupportedDM response"""
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
        """Handle GetInstances response"""
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
    
    async def _handle_set_response(self, resp_msg):
        """Handle Set response"""
        if resp_msg and resp_msg.body.response.HasField('set_resp'):
            set_resp = resp_msg.body.response.set_resp
            
            # Log updated objects
            for updated_obj in set_resp.updated_obj_results:
                logger.info(f"  Updated: {updated_obj.requested_path}")
                if updated_obj.oper_status.HasField('oper_success'):
                    for inst_result in updated_obj.oper_status.oper_success.updated_inst_results:
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
    
    async def send_operate_request(self, agent_id, command, args):
        """
        Send Operate request to agent
        
        Args:
            agent_id: Agent endpoint ID
            command: Command path (e.g., "Device.Reboot()")
            args: Command arguments (dict)
            
        Returns:
            dict: Operation result
        """
        if agent_id not in self._connected_agents:
            raise ValueError(f"Agent not connected: {agent_id}")
        
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
        
        # Send via appropriate MTP
        resp_record, resp_msg = await self._send_request(record, agent_id, 'Operate')
        
        if resp_msg and resp_msg.body.response.HasField('operate_resp'):
            return self._parse_operate_response(resp_msg)
        else:
            return None
    
    def _parse_operate_response(self, msg):
        """Parse Operate response"""
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
    
    def _generate_msg_id(self):
        """Generate unique message ID"""
        self._msg_id_counter += 1
        return str(self._msg_id_counter)
    
    def get_connected_agents(self):
        """
        Get list of connected agents with metadata
        
        Returns:
            list: Agent information including MTP details
        """
        agents = []
        for agent_id, info in self._connected_agents.items():
            agent_data = {
                'agent_id': agent_id,
                'mtp_type': info['mtp_type'],
                'mtp_info': info['mtp_info'],
                'last_heartbeat': info.get('last_heartbeat', ''),
                'last_boot': info.get('last_boot', '')
            }
            
            # Add metadata if available
            if 'metadata' in info:
                agent_data.update(info['metadata'])
            
            agents.append(agent_data)
        
        return agents
    
    async def stop(self):
        """Stop the controller and clean up"""
        if self._uds_transport:
            await self._uds_transport.close()
        
        if self._coap_context:
            await self._coap_context.shutdown()
        
        if self._stomp_connection and self._stomp_connection.is_connected():
            self._stomp_connection.disconnect()
        
        logger.info("Multi-MTP Controller stopped")


class CoapUspResource(resource.Resource):
    """CoAP resource that handles USP messages for the controller"""
    
    def __init__(self, controller):
        """
        Initialize CoAP USP resource
        
        Args:
            controller (MultiMtpController): Parent controller
        """
        super().__init__()
        self.controller = controller
    
    async def render_post(self, request):
        """Handle POST requests with USP messages"""
        try:
            # Handle message and get response
            response_data = await self.controller._handle_coap_message(request.payload, request)
            
            if response_data:
                return aiocoap.Message(code=aiocoap.CHANGED, payload=response_data)
            else:
                return aiocoap.Message(code=aiocoap.CHANGED)
            
        except Exception as e:
            logger.error(f"Error handling CoAP POST: {e}", exc_info=True)
            return aiocoap.Message(code=aiocoap.INTERNAL_SERVER_ERROR)


class StompMessageListener(stomp.ConnectionListener):
    """STOMP listener that queues messages for async processing"""
    
    def __init__(self, controller):
        """
        Initialize STOMP listener
        
        Args:
            controller (MultiMtpController): Parent controller
        """
        self.controller = controller
    
    def on_error(self, frame):
        """Handle STOMP errors"""
        logger.error(f"STOMP error: {frame.body}")
    
    def on_message(self, frame):
        """
        Handle incoming STOMP message
        
        Args:
            frame: STOMP frame containing message
        """
        try:
            # Queue the message for async processing
            message_data = {
                'body': frame.body.encode('latin-1') if isinstance(frame.body, str) else frame.body,
                'headers': frame.headers
            }
            
            # Use asyncio to put message in queue from sync context
            asyncio.get_event_loop().call_soon_threadsafe(
                self.controller._stomp_message_queue.put_nowait,
                message_data
            )
            
        except Exception as e:
            logger.error(f"Error in STOMP listener: {e}", exc_info=True)
    
    def on_connected(self, frame):
        """Handle successful STOMP connection"""
        logger.info("STOMP connection established")
    
    def on_disconnected(self):
        """Handle STOMP disconnection"""
        logger.warning("STOMP connection lost")
