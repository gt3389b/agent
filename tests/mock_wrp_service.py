"""
Mock WRP Service - Simulates Backend Service with Real Database

This mock service:
- Receives WRP messages (msgpack bytes)
- Unwraps WRP → JSON-RPC
- Processes requests against REAL Database (agent_db)
- Preserves context (metadata)
- Generates WRP responses with JSON-RPC results
- Sends responses back

This fronts the existing Database architecture, making it accessible via WRP.
"""

import json
import logging
from typing import Dict, Any, Optional, Callable
from uspbridge.wrp_bridge import WrpMessage, MessageType
from agent.agent_db import Database


logger = logging.getLogger(__name__)


class MockWrpService:
    """
    Mock WRP/JSON-RPC service fronting real Database
    
    Simulates a backend service (like Parodus + device components)
    that speaks WRP-wrapped JSON-RPC, but uses the real Database
    architecture we have today.
    """
    
    def __init__(self, dm_file: str, db_file: str, 
                 response_callback: Optional[Callable] = None):
        """
        Initialize mock WRP service with real Database
        
        Args:
            dm_file: Data model definition file
            db_file: Runtime database file
            response_callback: Function to call with response bytes (agent's RX)
        """
        self.response_callback = response_callback
        
        # Use REAL Database architecture (not mock data!)
        self.db = Database(dm_file, db_file, "")
        
        self.request_count = 0
        self.response_count = 0
    
    def receive(self, wrp_bytes: bytes):
        """
        Receive WRP message from bridge agent (TX channel)
        
        This simulates the backend service receiving a request.
        """
        self.request_count += 1
        
        try:
            # Unwrap WRP message
            wrp_msg = WrpMessage.from_bytes(wrp_bytes)
            
            logger.info(f"📨 Mock Service received WRP message")
            logger.debug(f"   Transaction ID: {wrp_msg.transaction_id}")
            logger.debug(f"   Metadata: {wrp_msg.metadata}")
            
            # Parse JSON-RPC payload
            jsonrpc_request = json.loads(wrp_msg.payload)
            method = jsonrpc_request.get("method")
            
            logger.info(f"   JSON-RPC Method: {method}")
            
            # Process request based on method
            if method == "get":
                result = self._handle_get(jsonrpc_request)
            elif method == "set":
                result = self._handle_set(jsonrpc_request)
            elif method == "getAttributes":
                result = self._handle_get_attributes(jsonrpc_request)
            elif method == "getInstances":
                result = self._handle_get_instances(jsonrpc_request)
            elif method == "operate":
                result = self._handle_operate(jsonrpc_request)
            elif method.startswith("Device."):  # Direct command invocation (e.g., Device.FactoryReset)
                result = self._handle_command(method, jsonrpc_request)
            elif method == "add":
                result = self._handle_add(jsonrpc_request)
            elif method == "delete":
                result = self._handle_delete(jsonrpc_request)
            else:
                result = {"error": f"Unknown method: {method}"}
            
            # Build JSON-RPC response
            jsonrpc_response = {
                "jsonrpc": "2.0",
                "id": jsonrpc_request.get("id"),
                "result": result
            }
            
            # Wrap in WRP response (preserving context!)
            response_msg = self._build_wrp_response(wrp_msg, jsonrpc_response)
            
            # Send response back to agent
            if self.response_callback:
                self.response_callback(response_msg.to_bytes())
                self.response_count += 1
            
        except Exception as e:
            logger.error(f"Mock service error: {e}")
            import traceback
            traceback.print_exc()
    
    def _handle_get(self, request: Dict) -> Dict:
        """Handle JSON-RPC get request using real Database"""
        names = request.get("params", {}).get("names", [])
        
        parameters = []
        for name in names:
            try:
                # Use real Database.get()
                value = self.db.get(name)
                parameters.append({
                    "name": name,
                    "value": str(value),
                    "type": self._infer_type(value)
                })
                logger.info(f"   Get {name} = {value}")
            except Exception as e:
                parameters.append({
                    "name": name,
                    "error": "NoSuchPath",
                    "message": str(e)
                })
                logger.warning(f"   Get {name} failed: {e}")
        
        return {"parameters": parameters}
    
    def _handle_set(self, request: Dict) -> Dict:
        """Handle JSON-RPC set request using real Database"""
        params = request.get("params", {}).get("parameters", [])
        
        updated_params = {}
        failed_params = {}
        
        for param in params:
            name = param.get("name")
            value = param.get("value")
            
            try:
                # Use real Database.update()
                old_value = self.db.get(name)
                self.db.update(name, value)
                
                logger.info(f"   Set {name}: {old_value} → {value}")
                
                updated_params[name] = value
            except Exception as e:
                logger.warning(f"   Set {name} failed: {e}")
                failed_params[name] = (7002, str(e))  # 7002 = Invalid parameter
        
        return {
            "updated_params": updated_params,
            "failed_params": failed_params
        }
    
    def _handle_get_attributes(self, request: Dict) -> Dict:
        """Handle JSON-RPC getAttributes request (GetSupportedDM)"""
        params = request.get("params", {})
        names = params.get("names", [])
        include_params = params.get("includeParameters", True)
        
        logger.info(f"   GetAttributes for paths: {names}")
        
        # Build data model info from Database._dm
        supported_objects = {}
        
        for obj_path in names:
            # Find all parameters under this path
            obj_params = {}
            
            if include_params:
                for dm_path, access in self.db._dm.items():
                    if dm_path.startswith(obj_path):
                        # Extract parameter name
                        param_name = dm_path.split('.')[-1]
                        obj_params[param_name] = {
                            "access": access,
                            "type": "string"  # Simplified
                        }
            
            supported_objects[obj_path] = {
                "access": "readOnly",
                "is_multi_instance": "{i}" in obj_path,
                "parameters": obj_params
            }
            
            logger.info(f"   Found {len(obj_params)} parameters under {obj_path}")
        
        return {
            "supported_objects": supported_objects
        }
    
    def _handle_get_instances(self, request: Dict) -> Dict:
        """Handle JSON-RPC getInstances request"""
        params = request.get("params", {})
        obj_path = params.get("objectPath", "")
        
        logger.info(f"   GetInstances for path: {obj_path}")
        
        # Find instances in database
        instances = []
        if obj_path:
            # Look for instance numbers in database paths
            for db_path in self.db._db.keys():
                if db_path.startswith(obj_path):
                    # Extract instance path (e.g., Device.LocalAgent.MTP.1.)
                    parts = db_path[len(obj_path):].split('.')
                    if parts and parts[0].isdigit():
                        instance_path = obj_path + parts[0] + '.'
                        if instance_path not in instances:
                            instances.append(instance_path)
        
        logger.info(f"   Found {len(instances)} instances: {instances}")
        
        return {
            "instances": {obj_path: instances}
        }
    
    def _handle_operate(self, request: Dict) -> Dict:
        """Handle JSON-RPC operate request"""
        command = request.get("params", {}).get("command")
        args = request.get("params", {}).get("args", {})
        
        logger.info(f"   Operate: {command} with args {args}")
        
        # Simulate command execution
        if command == "Device.Reboot()":
            return {
                "status": "success",
                "output_args": {},
                "message": "Reboot scheduled"
            }
        elif command == "Device.FactoryReset()":
            return {
                "status": "success",
                "output_args": {},
                "message": "Factory reset initiated"
            }
        else:
            return {
                "status": "success",
                "output_args": {},
                "message": f"Command {command} executed"
            }
    
    def _handle_command(self, method_name: str, request: Dict) -> Dict:
        """Handle direct command invocation (WRP-style)"""
        params = request.get("params", {})
        
        logger.info(f"   Execute command: {method_name} with params {params}")
        
        # Factory Reset implementation
        if method_name == "Device.FactoryReset":
            logger.warning("   🔧 FACTORY RESET: Resetting all writable parameters to defaults")
            
            # Reset writable parameters to default values
            reset_count = 0
            for path, access in self.db._dm.items():
                if access == "readWrite" and path in self.db._db:
                    # Reset to reasonable defaults
                    if "Enable" in path:
                        self.db.update(path, "false")
                    elif "Alias" in path:
                        self.db.update(path, "")
                    elif "SoftwareVersion" in path:
                        self.db.update(path, "1.0.0")
                    else:
                        self.db.update(path, "")
                    reset_count += 1
            
            logger.warning(f"   ✅ Factory reset complete: {reset_count} parameters reset")
            
            return {
                "command": method_name + "()",
                "output_args": {
                    "ResetCount": str(reset_count)
                },
                "error": None
            }
        
        # Device Reboot
        elif method_name == "Device.Reboot":
            logger.info("   🔄 REBOOT: Device reboot scheduled")
            return {
                "command": method_name + "()",
                "output_args": {},
                "error": None
            }
        
        # Unknown command
        else:
            return {
                "command": method_name + "()",
                "output_args": {},
                "error": None
            }
    
    def _handle_add(self, request: Dict) -> Dict:
        """Handle JSON-RPC add request (create object instance)"""
        obj_path = request.get("params", {}).get("obj_path")
        params = request.get("params", {}).get("params", {})
        
        logger.info(f"   Add: creating instance at {obj_path}")
        
        # Simulate creating instance - find next available instance number
        instance_num = 1
        while True:
            test_path = f"{obj_path}{instance_num}."
            # Check if this instance exists
            exists = any(k.startswith(test_path) for k in self.db._db.keys())
            if not exists:
                break
            instance_num += 1
        
        created_path = f"{obj_path}{instance_num}."
        
        # Create minimal parameters for this instance
        if "Device.LocalAgent.MTP." in obj_path:
            # Create MTP instance
            self.db._db[created_path + "Enable"] = params.get("Enable", "false")
            self.db._db[created_path + "Alias"] = params.get("Alias", "")
            self.db._db[created_path + "Protocol"] = params.get("Protocol", "CoAP")
        elif "Device.LocalAgent.Controller." in obj_path:
            # Create Controller instance
            self.db._db[created_path + "Enable"] = params.get("Enable", "false")
            self.db._db[created_path + "Alias"] = params.get("Alias", "")
            self.db._db[created_path + "EndpointID"] = params.get("EndpointID", "")
        
        # Save to disk
        self.db._save()
        
        logger.info(f"   Created instance: {created_path}")
        
        return {
            "created_obj_path": created_path,
            "status": "success",
            "unique_keys": {}  # No unique keys in our simplified implementation
        }
    
    def _handle_delete(self, request: Dict) -> Dict:
        """Handle JSON-RPC delete request"""
        obj_paths = request.get("params", {}).get("obj_paths", [])
        
        results = []
        for path in obj_paths:
            logger.info(f"   Delete: {path}")
            
            # Delete all parameters under this path
            deleted_count = 0
            keys_to_delete = [k for k in self.db._db.keys() if k.startswith(path)]
            
            for key in keys_to_delete:
                del self.db._db[key]
                deleted_count += 1
            
            if deleted_count > 0:
                self.db._save()
                logger.info(f"   Deleted {deleted_count} parameters from {path}")
                results.append({
                    "path": path,
                    "status": "success"
                })
            else:
                logger.warning(f"   Path not found: {path}")
                results.append({
                    "path": path,
                    "status": "error",
                    "error": "NoSuchPath"
                })
        
        return {"results": results}
    
    def _build_wrp_response(self, request_msg: WrpMessage, 
                           jsonrpc_response: Dict) -> WrpMessage:
        """
        Build WRP response message
        
        CRITICAL: Preserves metadata (including operation type) from request!
        """
        return WrpMessage(
            msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,
            source=request_msg.dest,      # Swap source/dest
            dest=request_msg.source,
            transaction_id=request_msg.transaction_id,  # Preserve transaction ID
            content_type="application/json",
            payload=json.dumps(jsonrpc_response).encode('utf-8'),
            metadata=request_msg.metadata.copy()  # PRESERVE METADATA!
        )
    
    def _infer_type(self, value: Any) -> str:
        """Infer parameter type from value"""
        if isinstance(value, bool):
            return "boolean"
        elif isinstance(value, int):
            return "int"
        elif isinstance(value, float):
            return "decimal"
        else:
            return "string"
    
    def get_stats(self) -> Dict[str, int]:
        """Get service statistics"""
        return {
            "requests": self.request_count,
            "responses": self.response_count,
            "db_size": len(self.db._db)  # Access runtime DB
        }
    
    def get_db(self) -> Database:
        """Get underlying Database instance"""
        return self.db
    
    def get_value(self, path: str) -> Optional[Any]:
        """Get current value from database"""
        try:
            return self.db.get(path)
        except:
            return None
