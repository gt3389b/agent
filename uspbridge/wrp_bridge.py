"""
WRP Bridge Implementation - USP ↔ WRP Bidirectional Translation

Concrete implementation of UspBridge for WRP (Web Routing Protocol) used
in the Xfinity/RDK ecosystem via Parodus.

Provides complete USP ↔ WRP translation including:
1. WRP message encoding/decoding (Python objects ↔ msgpack bytes)
2. USP-WRP protocol translation (USP messages ↔ WRP JSON-RPC)
3. Context preservation via metadata and structured transaction IDs
4. Operation type differentiation (get/set/operate all use JSON-RPC methods)

This module handles both message serialization and protocol translation,
making it a complete bridge for USP agents communicating with WRP services.

Compatible with wrp-c library used in Xfinity/RDK ecosystem.
"""

import json
import logging
import time
import uuid
from typing import Union, Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import IntEnum

import msgpack
from message.request import (
    UspMessage, GetRequest, SetRequest, OperateRequest, 
    GetSupportedDMRequest, GetInstancesRequest
)
from uspbridge.base import UspBridge, BridgeError

logger = logging.getLogger(__name__)


# =============================================================================
# WRP Message Protocol Definition
# =============================================================================

class MessageType(IntEnum):
    """WRP message types (per xmidt.io spec)"""
    AUTH = 2
    SIMPLE_REQUEST_RESPONSE = 3
    SIMPLE_EVENT = 4
    CREATE = 5
    RETRIEVE = 6
    UPDATE = 7
    DELETE = 8
    SERVICE_REGISTRATION = 9
    SERVICE_ALIVE = 10
    UNKNOWN = 11


@dataclass
class WrpMessage:
    """
    WRP message structure with msgpack encoding/decoding
    
    Attributes:
        msg_type: Type of WRP message
        source: Source endpoint (e.g., 'mac:112233445566/usp')
        dest: Destination endpoint (e.g., 'mac:112233445566/usp2wrp')
        payload: Message content (bytes)
        transaction_id: Unique transaction identifier
        content_type: MIME type of payload
        accept: Media type accepted in response
        status: HTTP-style status code (for responses)
        headers: Optional key-value headers
        metadata: Optional metadata (used for USP context)
        partner_ids: List of partner IDs for targeting
        session_id: Unique device connection session ID
        qos: Quality of service level (0-99)
        rdr: Request delivery response code
        spans: Timing/tracing data
        span_parent: Root parent for spans
        include_spans: Whether to include timing in response
        path: Path for CRUD operations
        service_name: Service name (for SERVICE_REGISTRATION)
        url: Service URL (for SERVICE_REGISTRATION)
    """
    msg_type: MessageType
    source: str
    dest: str
    payload: bytes = b''
    transaction_id: Optional[str] = None
    content_type: str = 'application/msgpack'
    accept: Optional[str] = None
    status: Optional[int] = None
    headers: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, str] = field(default_factory=dict)
    partner_ids: list = field(default_factory=list)
    session_id: Optional[str] = None
    qos: Optional[int] = None
    rdr: Optional[int] = None
    spans: Optional[list] = None
    span_parent: Optional[str] = None
    include_spans: Optional[bool] = None
    path: Optional[str] = None
    service_name: Optional[str] = None
    url: Optional[str] = None
    
    def __post_init__(self):
        """Generate transaction ID if not provided"""
        if self.transaction_id is None:
            self.transaction_id = str(uuid.uuid4())
        
        # Ensure msg_type is MessageType enum
        if isinstance(self.msg_type, int):
            self.msg_type = MessageType(self.msg_type)
    
    def to_bytes(self) -> bytes:
        """
        Encode WRP message to msgpack bytes
        
        Returns:
            bytes: Msgpack-encoded message
        """
        # Build msgpack-compatible dict with WRP field names
        msg_dict = {
            'msg_type': int(self.msg_type),
            'source': self.source,
            'dest': self.dest,
        }
        
        # Add transaction_uuid if present
        if self.transaction_id:
            msg_dict['transaction_uuid'] = self.transaction_id
        
        # Add payload if non-empty
        if self.payload:
            msg_dict['payload'] = self.payload
        
        # Add content_type if present
        if self.content_type:
            msg_dict['content_type'] = self.content_type
        
        # Add optional fields only if present
        if self.accept:
            msg_dict['accept'] = self.accept
        
        if self.status is not None:
            msg_dict['status'] = self.status
        
        if self.headers:
            msg_dict['headers'] = [f"{k}={v}" for k, v in self.headers.items()]
        
        if self.metadata:
            msg_dict['metadata'] = [f"{k}={v}" for k, v in self.metadata.items()]
        
        if self.partner_ids:
            msg_dict['partner_ids'] = self.partner_ids
        
        if self.session_id:
            msg_dict['session_id'] = self.session_id
        
        if self.qos is not None:
            msg_dict['qos'] = self.qos
        
        if self.rdr is not None:
            msg_dict['rdr'] = self.rdr
        
        if self.spans:
            msg_dict['spans'] = self.spans
        
        if self.span_parent:
            msg_dict['span_parent'] = self.span_parent
        
        if self.include_spans is not None:
            msg_dict['include_spans'] = self.include_spans
        
        if self.path:
            msg_dict['path'] = self.path
        
        if self.service_name:
            msg_dict['service_name'] = self.service_name
        
        if self.url:
            msg_dict['url'] = self.url
        
        return msgpack.packb(msg_dict, use_bin_type=True)
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'WrpMessage':
        """
        Decode msgpack bytes to WRP message
        
        Args:
            data: Msgpack-encoded bytes
            
        Returns:
            WrpMessage instance
            
        Raises:
            ValueError: If required fields are missing
        """
        msg_dict = msgpack.unpackb(data, raw=False)
        
        # Extract required fields
        msg_type = MessageType(msg_dict['msg_type'])
        source = msg_dict['source']
        dest = msg_dict['dest']
        payload = msg_dict.get('payload', b'')
        
        # Ensure payload is bytes
        if isinstance(payload, str):
            payload = payload.encode('utf-8')
        
        # Extract optional fields
        transaction_id = msg_dict.get('transaction_uuid')
        content_type = msg_dict.get('content_type', 'application/msgpack')
        accept = msg_dict.get('accept')
        status = msg_dict.get('status')
        partner_ids = msg_dict.get('partner_ids', [])
        session_id = msg_dict.get('session_id')
        qos = msg_dict.get('qos')
        rdr = msg_dict.get('rdr')
        spans = msg_dict.get('spans')
        span_parent = msg_dict.get('span_parent')
        include_spans = msg_dict.get('include_spans')
        path = msg_dict.get('path')
        service_name = msg_dict.get('service_name')
        url = msg_dict.get('url')
        
        # Parse headers from list of "key=value" strings
        headers = {}
        if 'headers' in msg_dict:
            for header in msg_dict['headers']:
                if '=' in header:
                    k, v = header.split('=', 1)
                    headers[k] = v
        
        # Parse metadata
        metadata = {}
        if 'metadata' in msg_dict:
            for meta in msg_dict['metadata']:
                if '=' in meta:
                    k, v = meta.split('=', 1)
                    metadata[k] = v
        
        return cls(
            msg_type=msg_type,
            source=source,
            dest=dest,
            payload=payload,
            transaction_id=transaction_id,
            content_type=content_type,
            accept=accept,
            status=status,
            headers=headers,
            metadata=metadata,
            partner_ids=partner_ids,
            session_id=session_id,
            qos=qos,
            rdr=rdr,
            spans=spans,
            span_parent=span_parent,
            include_spans=include_spans,
            path=path,
            service_name=service_name,
            url=url
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation for debugging"""
        return {
            'msg_type': self.msg_type.name,
            'source': self.source,
            'dest': self.dest,
            'payload_size': len(self.payload),
            'transaction_id': self.transaction_id,
            'content_type': self.content_type,
            'status': self.status,
            'headers': self.headers,
            'metadata': self.metadata
        }
    
    def __str__(self) -> str:
        """String representation for debugging"""
        status_str = f" [status={self.status}]" if self.status is not None else ""
        return (f"{self.msg_type.name}: {self.source} → {self.dest} "
                f"({len(self.payload)} bytes){status_str}")
    
    def __repr__(self) -> str:
        """Detailed representation"""
        return (f"WrpMessage(msg_type={self.msg_type.name}, "
                f"source={self.source!r}, dest={self.dest!r}, "
                f"payload_size={len(self.payload)}, "
                f"transaction_id={self.transaction_id!r})")


# =============================================================================
# USP-WRP Bridge Context
# =============================================================================


@dataclass
class BridgeContext:
    """
    Context for USP-WRP bridge operations
    
    Attributes:
        usp_msg_id: Original USP message ID
        controller_endpoint: Controller endpoint ID for routing responses
        mtp_id: MTP identifier for routing responses
        mac_address: Device MAC address for WRP addressing
        controller_id: Short controller identifier for transaction IDs
        sequence: Sequence counter for transaction IDs
    """
    usp_msg_id: str
    controller_endpoint: str
    mtp_id: str
    mac_address: str
    controller_id: str = "ctrl-01"
    sequence: int = 0
    
    def next_transaction_id(self) -> str:
        """
        Generate next transaction ID in format: {usp_msg_id}:{sequence}:{controller_id}
        
        Returns:
            Structured transaction ID string
        """
        self.sequence += 1
        return f"{self.usp_msg_id}:{self.sequence:03d}:{self.controller_id}"
    
    def to_metadata(self, operation: str, path: str = "") -> Dict[str, str]:
        """
        Convert context to WRP metadata format
        
        CRITICAL: The usp_operation field is essential for distinguishing request types
        when WRP responses come back. JSON-RPC "get" and "set" methods look identical
        to Operate commands (e.g., "Device.Reboot"), so we MUST preserve the original
        USP operation type in metadata.
        
        Valid operation values:
        - "get": USP GetRequest → Build GetResponse
        - "set": USP SetRequest → Build SetResponse  
        - "operate": USP OperateRequest → Build OperateResponse
        - "get_supported_dm": USP GetSupportedDMRequest → Build GetSupportedDMResponse
        - "get_instances": USP GetInstancesRequest → Build GetInstancesResponse
        
        Args:
            operation: USP operation type (MUST be one of the values above)
            path: Optional TR-181 path
            
        Returns:
            Metadata dictionary for WRP message
        """
        metadata = {
            "usp_msg_id": self.usp_msg_id,
            "usp_operation": operation,
            "controller_endpoint": self.controller_endpoint,
            "mtp_id": self.mtp_id,
            "timestamp": str(int(time.time()))
        }
        if path:
            metadata["usp_path"] = path
        return metadata


class WrpBridge(UspBridge):
    """
    WRP Bridge Implementation - USP ↔ WRP Translation
    
    Implements UspBridge interface for WRP (Web Routing Protocol) used in
    Xfinity/RDK ecosystem. Translates USP protocol messages to WRP JSON-RPC
    messages encoded in msgpack format.
    
    Key Features:
    - Structured transaction IDs: {usp_msg_id}:{sequence}:{controller_id}
    - Metadata-based context preservation
    - Operation type differentiation via metadata (critical!)
    - Complete msgpack encoding/decoding
    - Proper WRP endpoint addressing (mac:{MAC}/service)
    
    Usage:
        bridge = WrpBridge(mac_address="112233445566")
        
        # Method 1: Use specific operation methods
        get_req = GetRequest(paths=["Device.DeviceInfo.Manufacturer"])
        context = BridgeContext(...)
        get_resp = bridge.get(get_req, context)
        
        # Method 2: Use wire format methods
        request_bytes = bridge.to_bytes(get_req, context)
        # ... send bytes over transport ...
        operation, data, context = bridge.from_bytes(response_bytes)
    """
    
    def __init__(self, mac_address: str, source_service: str = "usp", 
                 dest_service: str = "usp2wrp", transport_send=None):
        """
        Initialize USP-WRP bridge
        
        Args:
            mac_address: Device MAC address (e.g., "112233445566")
            source_service: Source service name for WRP messages
            dest_service: Destination service name for WRP messages
            transport_send: Optional callable for sending bytes over transport.
                           Should accept bytes and return None.
                           Example: lambda data: socket.sendall(data)
        """
        self.mac_address = mac_address
        self.source_service = source_service
        self.dest_service = dest_service
        self._sequence = 0
        self._transport_send = transport_send
        
    def get_source(self) -> str:
        """Get WRP source address"""
        return f"mac:{self.mac_address}/{self.source_service}"
    
    def get_dest(self) -> str:
        """Get WRP destination address"""
        return f"mac:{self.mac_address}/{self.dest_service}"
    
    # =========================================================================
    # USP → WRP Translation (Requests)
    # =========================================================================
    
    def to_wrp(self, usp_msg: UspMessage, context: BridgeContext) -> WrpMessage:
        """
        Auto-detect USP message type and translate to WRP
        
        Args:
            usp_msg: USP message object (GetRequest, SetRequest, etc.)
            context: Bridge context for translation
            
        Returns:
            Translated WRP message
            
        Raises:
            ValueError: If USP message type is unsupported
        """
        # Detect request type and delegate to specific translator
        if isinstance(usp_msg, GetRequest):
            return self._translate_get_request(usp_msg, context)
        elif isinstance(usp_msg, SetRequest):
            return self._translate_set_request(usp_msg, context)
        elif isinstance(usp_msg, OperateRequest):
            return self._translate_operate_request(usp_msg, context)
        elif isinstance(usp_msg, GetSupportedDMRequest):
            return self._translate_get_supported_dm_request(usp_msg, context)
        elif isinstance(usp_msg, GetInstancesRequest):
            return self._translate_get_instances_request(usp_msg, context)
        else:
            raise ValueError(f"Unsupported USP request type: {type(usp_msg)}")
    
    def _translate_get_request(self, get_req: GetRequest, context: BridgeContext) -> WrpMessage:
        """
        Translate USP GetRequest → WRP JSON-RPC get
        
        Args:
            get_req: USP GetRequest object
            context: Bridge context
            
        Returns:
            WRP message with JSON-RPC get payload
        """
        # Build JSON-RPC payload
        json_rpc = {
            "jsonrpc": "2.0",
            "id": context.next_transaction_id(),
            "method": "get",
            "params": {
                "names": get_req.paths
            }
        }
        
        # Create WRP message
        return WrpMessage(
            msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,
            source=self.get_source(),
            dest=self.get_dest(),
            transaction_id=json_rpc["id"],
            content_type="application/json",
            metadata=context.to_metadata("get"),
            payload=json.dumps(json_rpc).encode('utf-8')
        )
    
    def _translate_set_request(self, set_req: SetRequest, context: BridgeContext) -> WrpMessage:
        """
        Translate USP SetRequest → WRP JSON-RPC set
        
        Args:
            set_req: USP SetRequest object
            context: Bridge context
            
        Returns:
            WRP message with JSON-RPC set payload
        """
        # Build parameters list
        parameters = []
        obj_path = ""
        
        for param_path, value in set_req.parameters.items():
            parameters.append({
                "name": param_path,
                "value": str(value),
                "dataType": self._infer_data_type(str(value))
            })
            # Track object path for metadata
            if not obj_path and '.' in param_path:
                obj_path = param_path.rsplit('.', 1)[0] + '.'
        
        # Build JSON-RPC payload
        json_rpc = {
            "jsonrpc": "2.0",
            "id": context.next_transaction_id(),
            "method": "set",
            "params": {
                "parameters": parameters
            }
        }
        
        # Create WRP message
        return WrpMessage(
            msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,
            source=self.get_source(),
            dest=self.get_dest(),
            transaction_id=json_rpc["id"],
            content_type="application/json",
            metadata=context.to_metadata("set", obj_path),
            payload=json.dumps(json_rpc).encode('utf-8')
        )
    
    def _translate_operate_request(self, operate_req: OperateRequest, context: BridgeContext) -> WrpMessage:
        """
        Translate USP OperateRequest → WRP JSON-RPC method call
        
        Preserves full TR-181 command path in metadata.
        
        Args:
            operate_req: USP OperateRequest object
            context: Bridge context
            
        Returns:
            WRP message with JSON-RPC method call payload
        """
        command = operate_req.command
        
        # Extract method name from command (e.g., "Device.Reboot()" → "Device.Reboot")
        method_name = command.rstrip("()")
        
        # Use input args directly
        params = operate_req.input_args
        
        # Build JSON-RPC payload (using direct method approach)
        json_rpc = {
            "jsonrpc": "2.0",
            "id": context.next_transaction_id(),
            "method": method_name,
            "params": params
        }
        
        # Create WRP message with command preserved in metadata
        # CRITICAL: usp_operation="operate" distinguishes this from get/set
        # when response comes back (all look like JSON-RPC method calls)
        metadata = context.to_metadata("operate")
        metadata["usp_command"] = command  # Full TR-181 path preserved
        
        return WrpMessage(
            msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,
            source=self.get_source(),
            dest=self.get_dest(),
            transaction_id=json_rpc["id"],
            content_type="application/json",
            metadata=metadata,
            payload=json.dumps(json_rpc).encode('utf-8')
        )
    
    def _translate_get_supported_dm_request(self, dm_req: GetSupportedDMRequest, context: BridgeContext) -> WrpMessage:
        """
        Translate USP GetSupportedDMRequest → WRP JSON-RPC getAttributes
        
        Args:
            dm_req: USP GetSupportedDMRequest object
            context: Bridge context
            
        Returns:
            WRP message with JSON-RPC getAttributes payload
        """
        obj_path = dm_req.obj_paths[0] if dm_req.obj_paths else ""
        
        # Build JSON-RPC payload
        json_rpc = {
            "jsonrpc": "2.0",
            "id": context.next_transaction_id(),
            "method": "getAttributes",
            "params": {
                "names": dm_req.obj_paths,
                "recursive": not dm_req.first_level_only,
                "includeParameters": dm_req.return_params,
                "includeCommands": dm_req.return_commands
            }
        }
        
        # Create WRP message
        metadata = context.to_metadata("get_supported_dm", obj_path)
        metadata["return_params"] = str(dm_req.return_params).lower()
        metadata["return_commands"] = str(dm_req.return_commands).lower()
        
        return WrpMessage(
            msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,
            source=self.get_source(),
            dest=self.get_dest(),
            transaction_id=json_rpc["id"],
            content_type="application/json",
            metadata=metadata,
            payload=json.dumps(json_rpc).encode('utf-8')
        )
    
    def _translate_get_instances_request(self, instances_req: GetInstancesRequest, context: BridgeContext) -> WrpMessage:
        """
        Translate USP GetInstancesRequest → WRP JSON-RPC getInstances
        
        Args:
            instances_req: USP GetInstancesRequest object
            context: Bridge context
            
        Returns:
            WRP message with JSON-RPC getInstances payload
        """
        obj_path = instances_req.obj_paths[0] if instances_req.obj_paths else ""
        
        # Build JSON-RPC payload
        json_rpc = {
            "jsonrpc": "2.0",
            "id": context.next_transaction_id(),
            "method": "getInstances",
            "params": {
                "objectPath": obj_path
            }
        }
        
        # Create WRP message
        return WrpMessage(
            msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,
            source=self.get_source(),
            dest=self.get_dest(),
            transaction_id=json_rpc["id"],
            content_type="application/json",
            metadata=context.to_metadata("get_instances", obj_path),
            payload=json.dumps(json_rpc).encode('utf-8')
        )
    
    # =========================================================================
    # WRP → USP Translation (Responses and Events)
    # =========================================================================
    
    def from_wrp(self, wrp_msg: WrpMessage) -> Tuple[str, Dict[str, Any], Optional[BridgeContext]]:
        """
        Auto-detect WRP message type and extract response data
        
        Args:
            wrp_msg: WRP message to translate
            
        Returns:
            Tuple of (operation_type, response_data, context)
            - operation_type: Type of operation (get, set, operate, etc.)
            - response_data: Parsed JSON-RPC result or event data
            - context: Reconstructed BridgeContext from metadata
            
        Raises:
            ValueError: If WRP message cannot be parsed
        """
        # Extract context from metadata
        context = self._extract_context(wrp_msg)
        
        # Parse payload
        try:
            payload_data = json.loads(wrp_msg.payload.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to parse WRP payload: {e}")
            raise ValueError(f"Invalid WRP payload: {e}")
        
        # Determine if this is a response or event
        if wrp_msg.msg_type == MessageType.SIMPLE_REQUEST_RESPONSE:
            # JSON-RPC response - Extract operation type from metadata
            # This is CRITICAL: we must know if this was a get, set, or operate
            # to build the correct USP response object
            operation = "unknown"
            if context and hasattr(context, 'usp_msg_id'):
                # Try to get operation from WRP metadata first
                if wrp_msg.metadata and "usp_operation" in wrp_msg.metadata:
                    operation = wrp_msg.metadata["usp_operation"]
                else:
                    logger.warning(f"WRP response missing usp_operation in metadata, transaction_id={wrp_msg.transaction_id}")
            
            if "result" in payload_data:
                return (operation, payload_data["result"], context)
            elif "error" in payload_data:
                return (operation, {"error": payload_data["error"]}, context)
            else:
                raise ValueError("WRP response missing result or error")
                
        elif wrp_msg.msg_type == MessageType.SIMPLE_EVENT:
            # WRP event → USP notification
            event_type = payload_data.get("event", "unknown")
            return (f"event:{event_type}", payload_data, None)
        
        else:
            raise ValueError(f"Unsupported WRP message type: {wrp_msg.msg_type}")
    
    def _extract_context(self, wrp_msg: WrpMessage) -> Optional[BridgeContext]:
        """
        Extract BridgeContext from WRP message metadata and transaction ID
        
        NOTE: Does NOT extract usp_operation - that must be read directly from
        wrp_msg.metadata["usp_operation"] in from_wrp() to determine response type
        
        Args:
            wrp_msg: WRP message
            
        Returns:
            Reconstructed BridgeContext or None if insufficient data
        """
        metadata = wrp_msg.metadata
        
        if not metadata or "usp_msg_id" not in metadata:
            # Try parsing from transaction ID
            return self._context_from_transaction_id(wrp_msg.transaction_id)
        
        # Reconstruct from metadata
        # Note: usp_operation is intentionally NOT stored in BridgeContext
        # It must be read directly from WRP metadata each time
        return BridgeContext(
            usp_msg_id=metadata.get("usp_msg_id", ""),
            controller_endpoint=metadata.get("controller_endpoint", ""),
            mtp_id=metadata.get("mtp_id", ""),
            mac_address=self.mac_address,
            controller_id=metadata.get("controller_id", "ctrl-01")
        )
    
    def _context_from_transaction_id(self, transaction_id: str) -> Optional[BridgeContext]:
        """
        Parse BridgeContext from structured transaction ID
        
        Format: {usp_msg_id}:{sequence}:{controller_id}
        
        Args:
            transaction_id: Structured transaction ID
            
        Returns:
            Partial BridgeContext or None
        """
        parts = transaction_id.split(':')
        if len(parts) >= 3:
            return BridgeContext(
                usp_msg_id=parts[0],
                controller_endpoint="unknown",
                mtp_id="unknown",
                mac_address=self.mac_address,
                controller_id=parts[2],
                sequence=int(parts[1])
            )
        return None
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _infer_data_type(self, value: str) -> int:
        """
        Infer TR-181 data type from string value
        
        DataType mapping:
        - 0: Auto-detect
        - 1: string
        - 2: int
        - 3: boolean
        - 4: dateTime
        - 5: base64
        
        Args:
            value: String value to analyze
            
        Returns:
            Data type code
        """
        # Check for boolean
        if value.lower() in ('true', 'false'):
            return 3
        
        # Check for int
        try:
            int(value)
            return 2
        except ValueError:
            pass
        
        # Default to string
        return 1
    
    def create_error_response(self, context: BridgeContext, 
                             usp_error_code: int, 
                             error_message: str) -> WrpMessage:
        """
        Create WRP error response from USP error
        
        Args:
            context: Bridge context
            usp_error_code: USP error code
            error_message: Error message
            
        Returns:
            WRP message with JSON-RPC error
        """
        # Map USP error to WRP status
        wrp_status = self._map_usp_error_to_wrp_status(usp_error_code)
        
        json_rpc = {
            "jsonrpc": "2.0",
            "id": context.usp_msg_id,
            "error": {
                "code": usp_error_code,
                "message": error_message
            }
        }
        
        return WrpMessage(
            msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,
            source=self.get_dest(),  # Swap for response
            dest=self.get_source(),
            transaction_id=context.usp_msg_id,
            content_type="application/json",
            status=wrp_status,
            metadata=context.to_metadata("error"),
            payload=json.dumps(json_rpc).encode('utf-8')
        )
    
    def _map_usp_error_to_wrp_status(self, usp_error: int) -> int:
        """
        Map USP error code to WRP HTTP-style status code
        
        Args:
            usp_error: USP error code
            
        Returns:
            HTTP-style status code
        """
        if usp_error == 0:
            return 200  # Success
        elif 7000 <= usp_error <= 7799:
            return 400  # Invalid arguments
        elif 7800 <= usp_error <= 7999:
            return 403  # Permission denied
        elif usp_error == 7001:
            return 507  # Resources exceeded
        else:
            return 500  # Internal error
    
    def _map_wrp_status_to_usp_error(self, wrp_status: int) -> Tuple[int, str]:
        """
        Map WRP HTTP-style status to USP error code and message
        
        Args:
            wrp_status: WRP status code
            
        Returns:
            Tuple of (usp_error_code, error_message)
        """
        mapping = {
            200: (0, "Success"),
            400: (7004, "Invalid arguments"),
            403: (7006, "Permission denied"),
            404: (7026, "Invalid path"),
            500: (7000, "Internal error"),
            503: (7024, "Resources exceeded")
        }
        return mapping.get(wrp_status, (7000, f"Unknown error (status {wrp_status})"))    
    # =========================================================================
    # UspBridge Interface Implementation
    # =========================================================================
    
    def get(self, request: GetRequest, context: Optional[BridgeContext] = None) -> Any:
        """
        Handle USP Get request - retrieve parameter values
        
        Translates GetRequest to WRP JSON-RPC 'get' method and returns response.
        Note: Currently returns raw (operation, data, context) tuple.
        TODO: Build and return GetResponse object.
        
        Args:
            request: USP GetRequest with parameter paths
            context: Bridge context (created if not provided)
            
        Returns:
            Tuple of (operation_type, response_data, context)
            TODO: Return GetResponse object
        """
        if context is None:
            context = BridgeContext(
                usp_msg_id=request.msg_id,
                controller_endpoint="unknown",
                mtp_id="unknown",
                mac_address=self.mac_address
            )
        
        # Translate to WRP and encode
        wrp_msg = self.to_wrp(request, context)
        # Caller must send wrp_msg.to_bytes() and receive response
        # This method would typically be async or blocking on transport
        raise NotImplementedError(
            "get() requires transport layer - use to_bytes()/from_bytes() directly"
        )
    
    def set(self, request: SetRequest, context: Optional[BridgeContext] = None) -> Any:
        """Handle USP Set request - set parameter values"""
        if context is None:
            context = BridgeContext(
                usp_msg_id=request.msg_id,
                controller_endpoint="unknown",
                mtp_id="unknown",
                mac_address=self.mac_address
            )
        
        wrp_msg = self.to_wrp(request, context)
        raise NotImplementedError(
            "set() requires transport layer - use to_bytes()/from_bytes() directly"
        )
    
    def operate(self, request: OperateRequest, context: Optional[BridgeContext] = None) -> Any:
        """Handle USP Operate request - execute command"""
        if context is None:
            context = BridgeContext(
                usp_msg_id=request.msg_id,
                controller_endpoint="unknown",
                mtp_id="unknown",
                mac_address=self.mac_address
            )
        
        wrp_msg = self.to_wrp(request, context)
        raise NotImplementedError(
            "operate() requires transport layer - use to_bytes()/from_bytes() directly"
        )
    
    def get_supported_dm(self, request: GetSupportedDMRequest, context: Optional[BridgeContext] = None) -> Any:
        """Handle USP GetSupportedDM request - query data model metadata"""
        if context is None:
            context = BridgeContext(
                usp_msg_id=request.msg_id,
                controller_endpoint="unknown",
                mtp_id="unknown",
                mac_address=self.mac_address
            )
        
        wrp_msg = self.to_wrp(request, context)
        raise NotImplementedError(
            "get_supported_dm() requires transport layer - use to_bytes()/from_bytes() directly"
        )
    
    def get_instances(self, request: GetInstancesRequest, context: Optional[BridgeContext] = None) -> Any:
        """Handle USP GetInstances request - query object instances"""
        if context is None:
            context = BridgeContext(
                usp_msg_id=request.msg_id,
                controller_endpoint="unknown",
                mtp_id="unknown",
                mac_address=self.mac_address
            )
        
        wrp_msg = self.to_wrp(request, context)
        raise NotImplementedError(
            "get_instances() requires transport layer - use to_bytes()/from_bytes() directly"
        )
    
    def add(self, request: UspMessage, context: Optional[BridgeContext] = None) -> UspMessage:
        """Handle USP Add request - create object instances"""
        if context is None:
            context = BridgeContext(
                usp_msg_id=request.msg_id,
                controller_endpoint="unknown",
                mtp_id="unknown",
                mac_address=self.mac_address
            )
        
        raise NotImplementedError(
            "add() requires transport layer - use to_bytes()/from_bytes() directly"
        )
    
    def delete(self, request: UspMessage, context: Optional[BridgeContext] = None) -> UspMessage:
        """Handle USP Delete request - delete object instances"""
        if context is None:
            context = BridgeContext(
                usp_msg_id=request.msg_id,
                controller_endpoint="unknown",
                mtp_id="unknown",
                mac_address=self.mac_address
            )
        
        raise NotImplementedError(
            "delete() requires transport layer - use to_bytes()/from_bytes() directly"
        )
    
    def get_supported_protocol(self, request: UspMessage, context: Optional[BridgeContext] = None) -> UspMessage:
        """Handle USP GetSupportedProtocol request - query supported protocol versions"""
        if context is None:
            context = BridgeContext(
                usp_msg_id=request.msg_id,
                controller_endpoint="unknown",
                mtp_id="unknown",
                mac_address=self.mac_address
            )
        
        raise NotImplementedError(
            "get_supported_protocol() requires transport layer - use to_bytes()/from_bytes() directly"
        )
    
    def to_bytes(self, request: UspMessage, context: Optional[BridgeContext] = None) -> bytes:
        """
        Serialize USP request to WRP msgpack bytes
        
        This is the primary method for outgoing requests. Translates USP request
        to WRP message and encodes to msgpack bytes ready for wire transmission.
        
        Args:
            request: USP request message (GetRequest, SetRequest, etc.)
            context: Bridge context (created if not provided)
            
        Returns:
            Msgpack-encoded WRP message bytes ready for transmission
            
        Example:
            bridge = WrpBridge(mac_address="112233445566")
            request = GetRequest(paths=["Device.DeviceInfo.Manufacturer"])
            context = BridgeContext(usp_msg_id=request.msg_id, ...)
            
            # Serialize to bytes
            wrp_bytes = bridge.to_bytes(request, context)
            
            # Send over transport (nanomsg, UDS, etc.)
            transport.send(wrp_bytes)
        """
        if context is None:
            context = BridgeContext(
                usp_msg_id=request.msg_id,
                controller_endpoint="unknown",
                mtp_id="unknown",
                mac_address=self.mac_address
            )
        
        # Translate USP → WRP
        wrp_msg = self.to_wrp(request, context)
        
        # Encode WRP → msgpack bytes
        return wrp_msg.to_bytes()
    
    def send(self, request: UspMessage, context: Optional[BridgeContext] = None) -> None:
        """
        Send USP request over the configured transport
        
        Convenience method that serializes the request and transmits it over
        the configured transport. This is the primary method for sending
        USP requests in production code.
        
        Args:
            request: USP request message to send
            context: Optional bridge context (created if not provided)
            
        Raises:
            BridgeError: If no transport configured or transmission fails
            
        Example:
            # Configure bridge with transport
            bridge = WrpBridge(
                mac_address="112233445566",
                transport_send=lambda data: socket.sendall(data)
            )
            
            # Send a Get request
            get_request = GetRequest(
                paths=["Device.DeviceInfo.Manufacturer"]
            )
            bridge.send(get_request, context)
        """
        if self._transport_send is None:
            raise BridgeError(
                "No transport configured. Either:\n"
                "1. Set transport_send in __init__: WrpBridge(..., transport_send=send_func)\n"
                "2. Use to_bytes() and send manually: transport.send(bridge.to_bytes(request))"
            )
        
        # Serialize request to bytes
        data = self.to_bytes(request, context)
        
        # Send over transport
        try:
            self._transport_send(data)
        except Exception as e:
            raise BridgeError(f"Transport send failed: {e}") from e
    
    def from_bytes(self, data: bytes) -> tuple:
        """
        Deserialize WRP msgpack bytes to USP response data
        
        This is the primary method for incoming responses. Decodes msgpack bytes
        to WRP message and extracts response data with operation type.
        
        Args:
            data: Msgpack-encoded WRP response bytes from wire
            
        Returns:
            Tuple of (operation_type, response_data, context)
            - operation_type: "get", "set", "operate", etc. (from metadata)
            - response_data: Parsed JSON-RPC result or error
            - context: Reconstructed BridgeContext
            
        Example:
            # Receive bytes from transport
            response_bytes = transport.receive()
            
            # Deserialize
            operation, data, context = bridge.from_bytes(response_bytes)
            
            # Handle based on operation type
            if operation == "get":
                # Build GetResponse from data
                params = data["parameters"]
            elif operation == "set":
                # Build SetResponse from data
                status = data["parameters"][0]["status"]
        """
        # Decode msgpack bytes → WRP message
        wrp_msg = WrpMessage.from_bytes(data)
        
        # Parse WRP → USP response data
        return self.from_wrp(wrp_msg)
    
    # =========================================================================
    # Event Handling - Stub implementations for WRP
    # =========================================================================
    
    def send_event(self, notify: UspMessage, context: Optional[BridgeContext] = None) -> None:
        """
        Send event notification via WRP SIMPLE_EVENT
        
        Stub implementation - event sending requires transport layer.
        In a real implementation, this would:
        1. Extract event details from Notify message
        2. Construct WRP SIMPLE_EVENT message
        3. Encode event data into payload
        4. Send via transport (nanomsg/UDS)
        
        Args:
            notify: USP Notify message with event details
            context: Optional bridge context
            
        Raises:
            NotImplementedError: Event sending requires transport layer
        """
        raise NotImplementedError(
            "send_event() requires transport layer - WRP events need SIMPLE_EVENT message type"
        )
    
    def on_event(self, event_data: bytes, context: Optional[BridgeContext] = None) -> UspMessage:
        """
        Handle incoming WRP SIMPLE_EVENT
        
        Stub implementation - event receiving requires transport layer.
        In a real implementation, this would:
        1. Decode WRP SIMPLE_EVENT from bytes
        2. Extract event data from payload
        3. Translate to USP Notify message
        
        Args:
            event_data: Raw WRP SIMPLE_EVENT msgpack bytes
            context: Optional bridge context
            
        Returns:
            USP Notify message with event details
            
        Raises:
            NotImplementedError: Event receiving requires transport layer
        """
        raise NotImplementedError(
            "on_event() requires transport layer - WRP events use SIMPLE_EVENT message type"
        )
    
    # =========================================================================
    # Subscription Management - Stub implementations for WRP
    # =========================================================================
    
    def subscribe(self, subscription_id: str, reference_list: List[str], 
                  notification_type: str = "ValueChange",
                  context: Optional[BridgeContext] = None) -> bool:
        """
        Subscribe to parameter/object notifications
        
        Stub implementation - subscriptions require persistent state and transport.
        In a real implementation, this would:
        1. Store subscription in persistent storage
        2. Register with data model for change notifications
        3. Send subscription confirmation
        
        Args:
            subscription_id: Unique subscription identifier
            reference_list: Paths to monitor (supports wildcards)
            notification_type: Type of notifications (ValueChange, etc.)
            context: Optional bridge context
            
        Returns:
            True if subscription successful
            
        Raises:
            NotImplementedError: Subscriptions require persistent state/transport
        """
        raise NotImplementedError(
            "subscribe() requires subscription manager and transport layer"
        )
    
    def unsubscribe(self, subscription_id: str, context: Optional[BridgeContext] = None) -> bool:
        """
        Unsubscribe from notifications
        
        Stub implementation - requires subscription manager.
        
        Args:
            subscription_id: Subscription ID to cancel
            context: Optional bridge context
            
        Returns:
            True if unsubscription successful
            
        Raises:
            NotImplementedError: Subscriptions require persistent state/transport
        """
        raise NotImplementedError(
            "unsubscribe() requires subscription manager and transport layer"
        )
    
    def list_subscriptions(self, context: Optional[BridgeContext] = None) -> List[Dict[str, Any]]:
        """
        List active subscriptions
        
        Stub implementation - requires subscription manager.
        
        Args:
            context: Optional bridge context
            
        Returns:
            List of subscription dictionaries
            
        Raises:
            NotImplementedError: Subscriptions require persistent state/transport
        """
        raise NotImplementedError(
            "list_subscriptions() requires subscription manager and transport layer"
        )


# Maintain backward compatibility
UspWrpBridge = WrpBridge