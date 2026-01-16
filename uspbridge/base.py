"""
Abstract USP Bridge Interface

Defines the contract that all USP bridge implementations must follow.
Bridges translate between USP protocol messages and target service protocols.
"""

from abc import ABC, abstractmethod
from typing import Optional, Any, Dict, List
from message.request import (
    UspMessage,
    GetRequest,
    SetRequest,
    OperateRequest,
    GetSupportedDMRequest,
    GetInstancesRequest
)
from message.response import (
    GetResponse,
    SetResponse,
    OperateResponse,
    GetSupportedDMResponse,
    GetInstancesResponse
)


class BridgeError(Exception):
    """Base exception for USP bridge errors"""
    pass


class UspBridge(ABC):
    """
    Abstract base class for USP protocol bridges
    
    A bridge translates between USP protocol messages and a target service's
    native protocol (e.g., WRP for RDK, MQTT, WebSockets, etc.).
    
    Implementations must provide:
    - Request/Response translation for all USP operations
    - Event handling (send/receive)
    - Subscription management
    - Wire format serialization/deserialization
    
    The bridge handles protocol translation only. Transport (network communication)
    is handled separately by transport adapters that use the bridge's to_bytes()
    and from_bytes() methods.
    """
    
    # =========================================================================
    # Core USP Operations (Request → Response)
    # =========================================================================
    
    @abstractmethod
    def get(self, request: GetRequest, context: Optional[Any] = None) -> GetResponse:
        """
        Handle USP Get request
        
        Retrieves parameter values from the target service.
        
        Args:
            request: USP GetRequest with parameter paths to query
            context: Optional bridge-specific context (routing, auth, etc.)
            
        Returns:
            GetResponse with parameter values and status
            
        Raises:
            BridgeError: If request translation or execution fails
        """
        pass
    
    @abstractmethod
    def set(self, request: SetRequest, context: Optional[Any] = None) -> SetResponse:
        """
        Handle USP Set request
        
        Sets parameter values in the target service.
        
        Args:
            request: USP SetRequest with parameters to set
            context: Optional bridge-specific context
            
        Returns:
            SetResponse with operation results for each parameter
            
        Raises:
            BridgeError: If request translation or execution fails
        """
        pass
    
    @abstractmethod
    def operate(self, request: OperateRequest, context: Optional[Any] = None) -> OperateResponse:
        """
        Handle USP Operate request
        
        Executes a command/operation on the target service.
        
        Args:
            request: USP OperateRequest with command and arguments
            context: Optional bridge-specific context
            
        Returns:
            OperateResponse with command results and output arguments
            
        Raises:
            BridgeError: If request translation or execution fails
        """
        pass
    
    @abstractmethod
    def get_supported_dm(self, request: GetSupportedDMRequest, context: Optional[Any] = None) -> GetSupportedDMResponse:
        """
        Handle USP GetSupportedDM request
        
        Retrieves data model metadata (supported parameters, commands, events).
        
        Args:
            request: USP GetSupportedDMRequest with object paths to query
            context: Optional bridge-specific context
            
        Returns:
            GetSupportedDMResponse with data model metadata
            
        Raises:
            BridgeError: If request translation or execution fails
        """
        pass
    
    @abstractmethod
    def get_instances(self, request: GetInstancesRequest, context: Optional[Any] = None) -> GetInstancesResponse:
        """
        Handle USP GetInstances request
        
        Retrieves object instance paths (e.g., "Device.WiFi.Radio.1.", "Device.WiFi.Radio.2.").
        
        Args:
            request: USP GetInstancesRequest with object paths to query
            context: Optional bridge-specific context
            
        Returns:
            GetInstancesResponse with instance paths
            
        Raises:
            BridgeError: If request translation or execution fails
        """
        pass
    
    @abstractmethod
    def add(self, request: UspMessage, context: Optional[Any] = None) -> UspMessage:
        """
        Handle USP Add request
        
        Creates new object instances in the data model.
        
        Args:
            request: USP AddRequest with object paths and parameters
            context: Optional bridge-specific context
            
        Returns:
            AddResponse with created instance paths and status
            
        Raises:
            BridgeError: If request translation or execution fails
            
        Example:
            # Add new WiFi SSID instance
            add_request = AddRequest(
                obj_path="Device.WiFi.SSID.",
                params={"SSID": "MyNetwork", "Enable": "true"}
            )
            response = bridge.add(add_request)
        """
        pass
    
    @abstractmethod
    def delete(self, request: UspMessage, context: Optional[Any] = None) -> UspMessage:
        """
        Handle USP Delete request
        
        Deletes object instances from the data model.
        
        Args:
            request: USP DeleteRequest with object instance paths to delete
            context: Optional bridge-specific context
            
        Returns:
            DeleteResponse with deletion status for each path
            
        Raises:
            BridgeError: If request translation or execution fails
            
        Example:
            # Delete WiFi SSID instance
            delete_request = DeleteRequest(
                obj_paths=["Device.WiFi.SSID.3."]
            )
            response = bridge.delete(delete_request)
        """
        pass
    
    @abstractmethod
    def get_supported_protocol(self, request: UspMessage, context: Optional[Any] = None) -> UspMessage:
        """
        Handle USP GetSupportedProtocol request
        
        Retrieves supported USP protocol versions.
        
        Args:
            request: USP GetSupportedProtocolRequest
            context: Optional bridge-specific context
            
        Returns:
            GetSupportedProtocolResponse with supported protocol versions
            
        Raises:
            BridgeError: If request translation or execution fails
        """
        pass
    
    # =========================================================================
    # Event Handling
    # =========================================================================
    
    @abstractmethod
    def send_event(self, notify: UspMessage, context: Optional[Any] = None) -> None:
        """
        Send event notification to target service
        
        Translates USP Notify message to target protocol format.
        Events are fire-and-forget notifications that don't expect responses.
        
        Common USP Events:
        - "Boot!": Device booted
        - "ValueChange!": Parameter value changed
        - "OperationComplete!": Async operation completed
        - "ObjectCreation!": Object instance created
        - "ObjectDeletion!": Object instance deleted
        
        Args:
            notify: USP Notify message containing event details
            context: Optional bridge-specific context
            
        Raises:
            BridgeError: If event translation or sending fails
            
        Example:
            # Create Notify message (implementation TBD)
            notify = NotifyMessage(
                subscription_id="sub-1",
                event="ValueChange!",
                obj_path="Device.WiFi.Radio.1.",
                params={
                    "ParamName": "Channel",
                    "ParamValue": "11"
                }
            )
            bridge.send_event(notify)
        """
        pass
    
    @abstractmethod
    def on_event(self, event_data: bytes, context: Optional[Any] = None) -> UspMessage:
        """
        Handle incoming event from target service
        
        Translates target protocol event to USP Notify message.
        Called when an event is received from the target service.
        
        Args:
            event_data: Raw event data from wire (protocol-specific format)
            context: Optional bridge-specific context
            
        Returns:
            USP Notify message containing event details
            
        Raises:
            BridgeError: If event parsing or translation fails
            
        Example:
            # Receive event from wire
            wrp_event_bytes = transport.receive()
            
            # Parse to USP Notify message
            notify = bridge.on_event(wrp_event_bytes)
            
            # Access event details
            # notify.subscription_id -> "sub-1"
            # notify.event -> "ValueChange!"
            # notify.obj_path -> "Device.WiFi.Radio.1."
            # notify.params -> {"ParamName": "Channel", ...}
        """
        pass
    
    # =========================================================================
    # Subscription Management
    # =========================================================================
    
    @abstractmethod
    def subscribe(self, subscription_id: str, reference_list: List[str], 
                  notification_type: str = "ValueChange",
                  context: Optional[Any] = None) -> bool:
        """
        Subscribe to notifications for specified paths
        
        Maps to USP Subscription mechanism. Sets up event delivery for
        parameter value changes, object creation/deletion, etc.
        
        Args:
            subscription_id: Unique subscription identifier
            reference_list: List of parameter/object paths to monitor
                Examples:
                - "Device.WiFi.Radio.1.Channel" (specific parameter)
                - "Device.WiFi.Radio.*." (all radios)
                - "Device.WiFi.SSID.*.SSID" (SSID parameter for all instances)
            notification_type: Type of notifications to receive
                - "ValueChange": Parameter value changes
                - "ObjectCreation": Object instance created
                - "ObjectDeletion": Object instance deleted
                - "OperationComplete": Async operation completed
                - "Event": Data model events (Boot!, etc.)
            context: Optional bridge-specific context
            
        Returns:
            True if subscription successful, False otherwise
            
        Raises:
            BridgeError: If subscription setup fails
            
        Example:
            # Subscribe to WiFi channel changes on all radios
            bridge.subscribe(
                subscription_id="sub-wifi-channels",
                reference_list=["Device.WiFi.Radio.*.Channel"],
                notification_type="ValueChange"
            )
        """
        pass
    
    @abstractmethod
    def unsubscribe(self, subscription_id: str, context: Optional[Any] = None) -> bool:
        """
        Unsubscribe from notifications
        
        Args:
            subscription_id: Subscription ID to cancel
            context: Optional bridge-specific context
            
        Returns:
            True if unsubscription successful, False otherwise
            
        Raises:
            BridgeError: If unsubscription fails
        """
        pass
    
    @abstractmethod
    def list_subscriptions(self, context: Optional[Any] = None) -> List[Dict[str, Any]]:
        """
        List active subscriptions
        
        Args:
            context: Optional bridge-specific context
            
        Returns:
            List of subscription dictionaries:
            [
                {
                    "subscription_id": "sub-1",
                    "reference_list": ["Device.WiFi.Radio.*.Channel"],
                    "notification_type": "ValueChange",
                    "enabled": True
                },
                ...
            ]
            
        Raises:
            BridgeError: If listing fails
        """
        pass
    
    # =========================================================================
    # Generic Request Handler
    # =========================================================================
    
    def handle_request(self, request: UspMessage, context: Optional[Any] = None) -> UspMessage:
        """
        Generic request handler that dispatches to specific operation handlers
        
        This is a convenience method that auto-detects the request type
        and calls the appropriate handler (get, set, operate, add, delete, etc.).
        
        Args:
            request: Any USP request message
            context: Optional bridge-specific context
            
        Returns:
            Corresponding USP response message (GetResponse, SetResponse, etc.)
            
        Raises:
            ValueError: If request type is not recognized
            BridgeError: If request handling fails
        """
        if isinstance(request, GetRequest):
            return self.get(request, context)
        elif isinstance(request, SetRequest):
            return self.set(request, context)
        elif isinstance(request, OperateRequest):
            return self.operate(request, context)
        elif isinstance(request, GetSupportedDMRequest):
            return self.get_supported_dm(request, context)
        elif isinstance(request, GetInstancesRequest):
            return self.get_instances(request, context)
        else:
            # Check request class name for Add, Delete, GetSupportedProtocol, etc.
            request_type = type(request).__name__
            if 'Add' in request_type:
                return self.add(request, context)
            elif 'Delete' in request_type:
                return self.delete(request, context)
            elif 'GetSupportedProtocol' in request_type:
                return self.get_supported_protocol(request, context)
            else:
                raise ValueError(f"Unsupported USP request type: {request_type}")
    
    # =========================================================================
    # Wire Format Serialization and Transmission
    # =========================================================================
    
    @abstractmethod
    def to_bytes(self, request: UspMessage, context: Optional[Any] = None) -> bytes:
        """
        Serialize USP request to wire format (protocol-specific bytes)
        
        Converts a USP request message into the target protocol's wire format.
        For example, WRP bridge would convert to msgpack-encoded WRP message.
        
        This is useful for testing, inspection, or when you want to control
        transmission separately from serialization.
        
        Args:
            request: USP request message to serialize
            context: Optional bridge-specific context
            
        Returns:
            Protocol-specific byte representation ready for network transmission
            
        Raises:
            BridgeError: If serialization fails
            
        Example:
            # Serialize for inspection/testing
            bytes_data = bridge.to_bytes(get_request, context)
            logger.debug(f"Serialized {len(bytes_data)} bytes")
        """
        pass
    
    @abstractmethod
    def send(self, request: UspMessage, context: Optional[Any] = None) -> None:
        """
        Send USP request over the transport
        
        Convenience method that serializes the request and transmits it over
        the configured transport. This is the primary method for sending
        USP requests in production code.
        
        Internally calls to_bytes() for serialization, then transmits the
        resulting bytes over the bridge's transport mechanism.
        
        Args:
            request: USP request message to send
            context: Optional bridge-specific context (routing, auth, etc.)
            
        Raises:
            BridgeError: If serialization or transmission fails
            
        Example:
            # Send a Get request
            get_request = GetRequest(
                param_paths=["Device.WiFi.Radio.1.Channel"]
            )
            bridge.send(get_request, context)
        """
        pass
    
    @abstractmethod
    def from_bytes(self, data: bytes, context: Optional[Any] = None) -> tuple:
        """
        Deserialize wire format to USP message components
        
        Parses protocol-specific bytes into USP message components that can
        be used to construct a response.
        
        Args:
            data: Protocol-specific byte data from network
            context: Optional bridge-specific context
            
        Returns:
            Tuple of (operation, data, context) where:
            - operation: Operation type ('get', 'set', 'operate', etc.)
            - data: Parsed request data (protocol-specific format)
            - context: Bridge context for correlating request/response
            
        Raises:
            BridgeError: If deserialization or parsing fails
        """
        pass
