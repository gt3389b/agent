"""
Copyright (c) 2026

Northbound API for USP Controller
Provides JSON-RPC interface over Unix socket for management applications

"""
import asyncio
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ControllerNorthbound:
    """Northbound API server for controller commands"""
    
    def __init__(self, controller, socket_path="/tmp/usp-controller-api.sock"):
        """
        Initialize northbound API
        
        Args:
            controller: UdsController instance
            socket_path: Unix socket path for API
        """
        self.controller = controller
        self.socket_path = socket_path
        self.server = None
        
        logger.info(f"Northbound API initialized on {socket_path}")
    
    async def start(self):
        """Start northbound API server"""
        import os
        
        # Remove old socket if it exists
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        
        self.server = await asyncio.start_unix_server(
            self._handle_client,
            path=self.socket_path
        )
        
        logger.info(f"Northbound API listening on {self.socket_path}")
        
        async with self.server:
            await self.server.serve_forever()
    
    async def _handle_client(self, reader, writer):
        """Handle northbound client connection"""
        client_addr = writer.get_extra_info('peername', 'unknown')
        logger.debug(f"Northbound client connected: {client_addr}")
        
        try:
            while True:
                # Read line-delimited JSON
                data = await reader.readline()
                if not data:
                    break
                
                try:
                    request = json.loads(data.decode().strip())
                    logger.debug(f"Northbound request: {request.get('method')}")
                    
                    response = await self._process_request(request)
                    
                    # Send response
                    response_data = json.dumps(response) + '\n'
                    writer.write(response_data.encode())
                    await writer.drain()
                    
                except json.JSONDecodeError as e:
                    error_response = self._error_response(None, -32700, f"Parse error: {e}")
                    writer.write((json.dumps(error_response) + '\n').encode())
                    await writer.drain()
                    
        except Exception as e:
            logger.error(f"Error handling northbound client: {e}", exc_info=True)
        finally:
            logger.debug(f"Northbound client disconnected: {client_addr}")
            writer.close()
            await writer.wait_closed()
    
    async def _process_request(self, request):
        """
        Process JSON-RPC request
        
        Args:
            request: JSON-RPC request dict
            
        Returns:
            JSON-RPC response dict
        """
        method = request.get('method')
        params = request.get('params', {})
        req_id = request.get('id')
        
        try:
            if method == 'get':
                result = await self._cmd_get(params)
            elif method == 'set':
                result = await self._cmd_set(params)
            elif method == 'operate':
                result = await self._cmd_operate(params)
            elif method == 'get_supported_dm':
                result = await self._cmd_get_supported_dm(params)
            elif method == 'list_agents':
                result = await self._cmd_list_agents(params)
            else:
                return self._error_response(req_id, -32601, f"Method not found: {method}")
            
            return {
                "jsonrpc": "2.0",
                "result": result,
                "id": req_id
            }
            
        except Exception as e:
            logger.error(f"Error processing {method}: {e}", exc_info=True)
            return self._error_response(req_id, -32603, str(e))
    
    async def _cmd_get(self, params):
        """
        Execute Get command
        
        Args:
            params: {
                "agent_id": "self::uds-agent-001",
                "paths": ["Device.DeviceInfo.Manufacturer", ...]
            }
            
        Returns:
            dict: Parameter name -> value mapping
        """
        agent_id = params.get('agent_id')
        paths = params.get('paths', [])
        
        if not agent_id:
            raise ValueError("agent_id required")
        if not paths:
            raise ValueError("paths required")
        
        logger.info(f"Northbound Get: {agent_id} -> {paths}")
        
        result = await self.controller.send_get_request(agent_id, paths)
        return result
    
    async def _cmd_set(self, params):
        """
        Execute Set command
        
        Args:
            params: {
                "agent_id": "self::uds-agent-001",
                "parameters": [
                    {"path": "Device.LocalAgent.Controller.1.PeriodicNotifInterval", "value": "60"},
                    ...
                ]
            }
            
        Returns:
            dict: Updated parameters
        """
        agent_id = params.get('agent_id')
        parameters = params.get('parameters', [])
        
        if not agent_id:
            raise ValueError("agent_id required")
        if not parameters:
            raise ValueError("parameters required")
        
        logger.info(f"Northbound Set: {agent_id} -> {len(parameters)} params")
        
        result = await self.controller.send_set_request(agent_id, parameters)
        return result
    
    async def _cmd_operate(self, params):
        """
        Execute Operate command
        
        Args:
            params: {
                "agent_id": "self::uds-agent-001",
                "command": "Device.Reboot()",
                "args": {"Delay": "60"}
            }
            
        Returns:
            dict: Operation result
        """
        agent_id = params.get('agent_id')
        command = params.get('command')
        args = params.get('args', {})
        
        if not agent_id:
            raise ValueError("agent_id required")
        if not command:
            raise ValueError("command required")
        
        logger.info(f"Northbound Operate: {agent_id} -> {command}")
        
        result = await self.controller.send_operate_request(agent_id, command, args)
        return result
    
    async def _cmd_get_supported_dm(self, params):
        """
        Execute GetSupportedDM command
        
        Args:
            params: {
                "agent_id": "self::uds-agent-001",
                "obj_paths": ["Device.WiFi.", "Device.Ethernet."],
                "first_level_only": false,  # optional
                "return_commands": true,     # optional
                "return_events": true,       # optional
                "return_params": true        # optional
            }
            
        Returns:
            dict: Data model structure with parameters, commands, and events
        """
        agent_id = params.get('agent_id')
        obj_paths = params.get('obj_paths', ['Device.'])
        first_level_only = params.get('first_level_only', False)
        return_commands = params.get('return_commands', True)
        return_events = params.get('return_events', True)
        return_params = params.get('return_params', True)
        
        if not agent_id:
            raise ValueError("agent_id required")
        if not obj_paths:
            raise ValueError("obj_paths required")
        
        logger.info(f"Northbound GetSupportedDM: {agent_id} -> {obj_paths}")
        
        result = await self.controller.send_get_supported_dm_request(
            agent_id, obj_paths, first_level_only, return_commands, return_events, return_params
        )
        return result
    
    async def _cmd_list_agents(self, params):
        """
        List connected agents
        
        Returns:
            list: [
                {
                    "agent_id": "self::uds-agent-001",
                    "last_boot": "2026-01-15T05:20:00Z",
                    "last_heartbeat": "2026-01-15T05:20:30Z"
                },
                ...
            ]
        """
        logger.debug("Northbound list_agents")
        
        agents = self.controller.get_connected_agents()
        return agents
    
    def _error_response(self, req_id, code, message):
        """
        Create JSON-RPC error response
        
        Args:
            req_id: Request ID
            code: Error code
            message: Error message
            
        Returns:
            dict: JSON-RPC error response
        """
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": code,
                "message": message
            },
            "id": req_id
        }
    
    async def stop(self):
        """Stop the northbound API server"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Northbound API stopped")
