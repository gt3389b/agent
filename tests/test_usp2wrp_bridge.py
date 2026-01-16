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

# File Name: test_usp2wrp_bridge.py
#
# Description: Unit tests for USP-WRP Bridge
#
# Tests the bidirectional translation between USP and WRP protocols,
# including message encoding/decoding, context preservation, and
# proper operation type differentiation.
"""

import json
import msgpack
import pytest
from unittest.mock import Mock, patch

from uspbridge.wrp_bridge import (
    WrpMessage,
    MessageType,
    BridgeContext,
    WrpBridge
)
from message.request import (
    GetRequest,
    SetRequest,
    OperateRequest,
    GetSupportedDMRequest,
    GetInstancesRequest
)


# =============================================================================
# WrpMessage Tests
# =============================================================================

class TestWrpMessage:
    """Test WRP message encoding/decoding"""
    
    def test_create_simple_message(self):
        """Test creating a basic WRP message"""
        msg = WrpMessage(
            msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,
            source="mac:112233445566/usp",
            dest="mac:112233445566/usp2wrp",
            transaction_id="usp-1234:001:ctrl-01",
            payload=b"test payload"
        )
        
        assert msg.msg_type == MessageType.SIMPLE_REQUEST_RESPONSE
        assert msg.source == "mac:112233445566/usp"
        assert msg.dest == "mac:112233445566/usp2wrp"
        assert msg.transaction_id == "usp-1234:001:ctrl-01"
        assert msg.payload == b"test payload"
    
    def test_encode_decode_roundtrip(self):
        """Test WRP message msgpack encoding/decoding roundtrip"""
        original = WrpMessage(
            msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,
            source="mac:112233445566/usp",
            dest="mac:112233445566/usp2wrp",
            transaction_id="usp-1234:001:ctrl-01",
            content_type="application/json",
            payload=b'{"jsonrpc":"2.0","id":"usp-1234:001:ctrl-01","method":"get"}',
            metadata={
                "usp_msg_id": "usp-1234",
                "usp_operation": "get",
                "controller_endpoint": "proto::controller-1",
                "mtp_id": "coap",
                "timestamp": "1234567890"
            }
        )
        
        # Encode to msgpack
        msgpack_bytes = original.to_bytes()
        assert isinstance(msgpack_bytes, bytes)
        assert len(msgpack_bytes) > 0
        
        # Decode back
        decoded = WrpMessage.from_bytes(msgpack_bytes)
        
        # Verify all fields match
        assert decoded.msg_type == original.msg_type
        assert decoded.source == original.source
        assert decoded.dest == original.dest
        assert decoded.transaction_id == original.transaction_id
        assert decoded.content_type == original.content_type
        assert decoded.payload == original.payload
        assert decoded.metadata == original.metadata
    
    def test_encode_with_optional_fields(self):
        """Test encoding WRP message with all optional fields"""
        msg = WrpMessage(
            msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,
            source="mac:112233445566/usp",
            dest="mac:112233445566/usp2wrp",
            transaction_id="usp-1234:001:ctrl-01",
            payload=b"test",
            status=200,
            headers={"X-Custom": "value"},
            metadata={"key": "value"},
            partner_ids=["partner1", "partner2"],
            session_id="session-123",
            qos=1,
            rdr=True,
            path="/api/endpoint",
            service_name="test-service"
        )
        
        # Should encode without errors
        msgpack_bytes = msg.to_bytes()
        decoded = WrpMessage.from_bytes(msgpack_bytes)
        
        assert decoded.status == 200
        assert decoded.headers == {"X-Custom": "value"}
        assert decoded.metadata == {"key": "value"}
        assert decoded.partner_ids == ["partner1", "partner2"]
        assert decoded.session_id == "session-123"
        assert decoded.qos == 1
        assert decoded.rdr == True
        assert decoded.path == "/api/endpoint"
        assert decoded.service_name == "test-service"
    
    def test_invalid_msgpack_decode(self):
        """Test decoding invalid msgpack data"""
        with pytest.raises(Exception):
            WrpMessage.from_bytes(b"not valid msgpack")


# =============================================================================
# BridgeContext Tests
# =============================================================================

class TestBridgeContext:
    """Test bridge context and transaction ID generation"""
    
    def test_create_context(self):
        """Test creating bridge context"""
        context = BridgeContext(
            usp_msg_id="usp-5678",
            controller_endpoint="proto::controller-1",
            mtp_id="coap",
            mac_address="112233445566",
            controller_id="ctrl-01"
        )
        
        assert context.usp_msg_id == "usp-5678"
        assert context.controller_endpoint == "proto::controller-1"
        assert context.mtp_id == "coap"
        assert context.mac_address == "112233445566"
        assert context.controller_id == "ctrl-01"
        assert context.sequence == 0
    
    def test_transaction_id_generation(self):
        """Test structured transaction ID generation"""
        context = BridgeContext(
            usp_msg_id="usp-1234",
            controller_endpoint="proto::controller-1",
            mtp_id="coap",
            mac_address="112233445566",
            controller_id="ctrl-01"
        )
        
        # First ID
        tid1 = context.next_transaction_id()
        assert tid1 == "usp-1234:001:ctrl-01"
        
        # Second ID (sequence increments)
        tid2 = context.next_transaction_id()
        assert tid2 == "usp-1234:002:ctrl-01"
        
        # Third ID
        tid3 = context.next_transaction_id()
        assert tid3 == "usp-1234:003:ctrl-01"
    
    def test_to_metadata(self):
        """Test converting context to WRP metadata"""
        context = BridgeContext(
            usp_msg_id="usp-9999",
            controller_endpoint="proto::controller-1",
            mtp_id="stomp",
            mac_address="112233445566",
            controller_id="ctrl-01"
        )
        
        metadata = context.to_metadata("get", "Device.DeviceInfo.")
        
        assert metadata["usp_msg_id"] == "usp-9999"
        assert metadata["usp_operation"] == "get"
        assert metadata["controller_endpoint"] == "proto::controller-1"
        assert metadata["mtp_id"] == "stomp"
        assert metadata["usp_path"] == "Device.DeviceInfo."
        assert "timestamp" in metadata
    
    def test_metadata_without_path(self):
        """Test metadata generation without path"""
        context = BridgeContext(
            usp_msg_id="usp-1111",
            controller_endpoint="proto::controller-1",
            mtp_id="coap",
            mac_address="112233445566"
        )
        
        metadata = context.to_metadata("operate")
        
        assert metadata["usp_operation"] == "operate"
        assert "usp_path" not in metadata


# =============================================================================
# WrpBridge Tests - USP to WRP Translation
# =============================================================================

class TestUspToWrpTranslation:
    """Test translating USP requests to WRP messages"""
    
    @pytest.fixture
    def bridge(self):
        """Create bridge instance"""
        return WrpBridge(mac_address="112233445566")
    
    @pytest.fixture
    def context(self):
        """Create test context"""
        return BridgeContext(
            usp_msg_id="usp-test-1234",
            controller_endpoint="proto::controller-1",
            mtp_id="coap",
            mac_address="112233445566",
            controller_id="ctrl-test"
        )
    
    def test_get_request_translation(self, bridge, context):
        """Test translating USP GetRequest to WRP"""
        usp_req = GetRequest(
            paths=["Device.DeviceInfo.Manufacturer", "Device.DeviceInfo.SerialNumber"],
            msg_id="usp-test-1234"
        )
        
        wrp_msg = bridge.to_wrp(usp_req, context)
        
        # Verify WRP message structure
        assert wrp_msg.msg_type == MessageType.SIMPLE_REQUEST_RESPONSE
        assert wrp_msg.source == "mac:112233445566/usp"
        assert wrp_msg.dest == "mac:112233445566/usp2wrp"
        assert wrp_msg.content_type == "application/json"
        
        # Verify metadata contains operation type
        assert wrp_msg.metadata["usp_operation"] == "get"
        assert wrp_msg.metadata["usp_msg_id"] == "usp-test-1234"
        
        # Verify JSON-RPC payload
        payload = json.loads(wrp_msg.payload.decode('utf-8'))
        assert payload["jsonrpc"] == "2.0"
        assert payload["method"] == "get"
        assert payload["params"]["names"] == ["Device.DeviceInfo.Manufacturer", "Device.DeviceInfo.SerialNumber"]
        assert "id" in payload
    
    def test_set_request_translation(self, bridge, context):
        """Test translating USP SetRequest to WRP"""
        usp_req = SetRequest(
            parameters={
                "Device.WiFi.Radio.1.Enable": "true",
                "Device.WiFi.Radio.1.Channel": "6"
            },
            msg_id="usp-test-1234"
        )
        
        wrp_msg = bridge.to_wrp(usp_req, context)
        
        # Verify metadata contains operation type (CRITICAL for distinguishing from operate)
        assert wrp_msg.metadata["usp_operation"] == "set"
        
        # Verify JSON-RPC payload
        payload = json.loads(wrp_msg.payload.decode('utf-8'))
        assert payload["method"] == "set"
        assert len(payload["params"]["parameters"]) == 2
        
        # Check parameters have correct structure
        params = {p["name"]: p for p in payload["params"]["parameters"]}
        assert "Device.WiFi.Radio.1.Enable" in params
        assert params["Device.WiFi.Radio.1.Enable"]["value"] == "true"
        assert params["Device.WiFi.Radio.1.Enable"]["dataType"] == 3  # boolean
        
        assert "Device.WiFi.Radio.1.Channel" in params
        assert params["Device.WiFi.Radio.1.Channel"]["value"] == "6"
        assert params["Device.WiFi.Radio.1.Channel"]["dataType"] == 2  # int
    
    def test_operate_request_translation(self, bridge, context):
        """Test translating USP OperateRequest to WRP"""
        usp_req = OperateRequest(
            command="Device.Reboot()",
            input_args={"Delay": 10},
            msg_id="usp-test-1234"
        )
        
        wrp_msg = bridge.to_wrp(usp_req, context)
        
        # Verify metadata contains operation type (CRITICAL - distinguishes from get/set)
        assert wrp_msg.metadata["usp_operation"] == "operate"
        assert wrp_msg.metadata["usp_command"] == "Device.Reboot()"
        
        # Verify JSON-RPC payload uses direct method call
        payload = json.loads(wrp_msg.payload.decode('utf-8'))
        assert payload["method"] == "Device.Reboot"  # Stripped ()
        assert payload["params"] == {"Delay": 10}
    
    def test_get_supported_dm_translation(self, bridge, context):
        """Test translating USP GetSupportedDMRequest to WRP"""
        usp_req = GetSupportedDMRequest(
            obj_paths=["Device.WiFi."],
            first_level_only=False,
            return_commands=True,
            return_params=True,
            msg_id="usp-test-1234"
        )
        
        wrp_msg = bridge.to_wrp(usp_req, context)
        
        # Verify metadata
        assert wrp_msg.metadata["usp_operation"] == "get_supported_dm"
        assert wrp_msg.metadata["return_params"] == "true"
        assert wrp_msg.metadata["return_commands"] == "true"
        
        # Verify JSON-RPC payload
        payload = json.loads(wrp_msg.payload.decode('utf-8'))
        assert payload["method"] == "getAttributes"
        assert payload["params"]["names"] == ["Device.WiFi."]
        assert payload["params"]["recursive"] == True
        assert payload["params"]["includeParameters"] == True
        assert payload["params"]["includeCommands"] == True
    
    def test_get_instances_translation(self, bridge, context):
        """Test translating USP GetInstancesRequest to WRP"""
        usp_req = GetInstancesRequest(
            obj_paths=["Device.WiFi.Radio."],
            msg_id="usp-test-1234"
        )
        
        wrp_msg = bridge.to_wrp(usp_req, context)
        
        # Verify metadata
        assert wrp_msg.metadata["usp_operation"] == "get_instances"
        
        # Verify JSON-RPC payload
        payload = json.loads(wrp_msg.payload.decode('utf-8'))
        assert payload["method"] == "getInstances"
        assert payload["params"]["objectPath"] == "Device.WiFi.Radio."
    
    def test_transaction_id_in_payload(self, bridge, context):
        """Test that transaction ID appears in JSON-RPC payload"""
        usp_req = GetRequest(paths=["Device.DeviceInfo."], msg_id="usp-test-1234")
        
        wrp_msg = bridge.to_wrp(usp_req, context)
        
        payload = json.loads(wrp_msg.payload.decode('utf-8'))
        assert payload["id"] == "usp-test-1234:001:ctrl-test"
        assert payload["id"] == wrp_msg.transaction_id


# =============================================================================
# Complete Flow Tests - USP Message Objects to WRP Bytes
# =============================================================================

class TestCompleteUspToWrpBytesFlow:
    """Test complete flow: USP Message Objects → WRP msgpack bytes"""
    
    @pytest.fixture
    def bridge(self):
        """Create bridge instance"""
        return WrpBridge(mac_address="AABBCCDDEE FF")
    
    @pytest.fixture
    def context(self):
        """Create test context"""
        return BridgeContext(
            usp_msg_id="usp-complete-test",
            controller_endpoint="proto::controller-1",
            mtp_id="coap",
            mac_address="AABBCCDDEEFF",
            controller_id="ctrl-01"
        )
    
    def test_get_request_to_msgpack_bytes(self, bridge, context):
        """
        Test complete flow: GetRequest → WrpMessage → msgpack bytes
        
        This verifies the full translation pipeline for outgoing requests.
        """
        # Step 1: Create USP GetRequest object
        usp_get = GetRequest(
            paths=["Device.DeviceInfo.Manufacturer", "Device.DeviceInfo.ModelName"],
            msg_id="usp-complete-test"
        )
        
        # Step 2: Translate to WRP message
        wrp_msg = bridge.to_wrp(usp_get, context)
        
        # Verify WRP message is correct type
        assert isinstance(wrp_msg, WrpMessage)
        assert wrp_msg.msg_type == MessageType.SIMPLE_REQUEST_RESPONSE
        assert wrp_msg.metadata["usp_operation"] == "get"
        
        # Step 3: Encode to msgpack bytes
        msgpack_bytes = wrp_msg.to_bytes()
        
        # Verify we got bytes
        assert isinstance(msgpack_bytes, bytes)
        assert len(msgpack_bytes) > 0
        
        # Step 4: Decode msgpack bytes back to WRP message
        decoded_wrp = WrpMessage.from_bytes(msgpack_bytes)
        
        # Verify decoded message matches original
        assert decoded_wrp.msg_type == wrp_msg.msg_type
        assert decoded_wrp.source == wrp_msg.source
        assert decoded_wrp.dest == wrp_msg.dest
        assert decoded_wrp.transaction_id == wrp_msg.transaction_id
        assert decoded_wrp.metadata == wrp_msg.metadata
        
        # Verify JSON-RPC payload is intact
        payload = json.loads(decoded_wrp.payload.decode('utf-8'))
        assert payload["method"] == "get"
        assert payload["params"]["names"] == ["Device.DeviceInfo.Manufacturer", "Device.DeviceInfo.ModelName"]
    
    def test_set_request_to_msgpack_bytes(self, bridge, context):
        """
        Test complete flow: SetRequest → WrpMessage → msgpack bytes
        """
        # Create USP SetRequest
        usp_set = SetRequest(
            parameters={
                "Device.WiFi.Radio.1.Enable": "true",
                "Device.WiFi.Radio.1.Channel": "11"
            },
            msg_id="usp-complete-test"
        )
        
        # Translate and encode
        wrp_msg = bridge.to_wrp(usp_set, context)
        msgpack_bytes = wrp_msg.to_bytes()
        
        # Verify bytes
        assert isinstance(msgpack_bytes, bytes)
        assert len(msgpack_bytes) > 0
        
        # Decode and verify
        decoded_wrp = WrpMessage.from_bytes(msgpack_bytes)
        assert decoded_wrp.metadata["usp_operation"] == "set"
        
        payload = json.loads(decoded_wrp.payload.decode('utf-8'))
        assert payload["method"] == "set"
        assert len(payload["params"]["parameters"]) == 2
    
    def test_operate_request_to_msgpack_bytes(self, bridge, context):
        """
        Test complete flow: OperateRequest → WrpMessage → msgpack bytes
        
        CRITICAL: Verify usp_operation="operate" preserved in msgpack bytes
        """
        # Create USP OperateRequest
        usp_operate = OperateRequest(
            command="Device.Reboot()",
            input_args={"Delay": 10},
            msg_id="usp-complete-test"
        )
        
        # Translate and encode
        wrp_msg = bridge.to_wrp(usp_operate, context)
        msgpack_bytes = wrp_msg.to_bytes()
        
        # Verify bytes
        assert isinstance(msgpack_bytes, bytes)
        
        # Decode and verify operation type preserved
        decoded_wrp = WrpMessage.from_bytes(msgpack_bytes)
        assert decoded_wrp.metadata["usp_operation"] == "operate"
        assert decoded_wrp.metadata["usp_command"] == "Device.Reboot()"
        
        payload = json.loads(decoded_wrp.payload.decode('utf-8'))
        assert payload["method"] == "Device.Reboot"
        assert payload["params"] == {"Delay": 10}
    
    def test_get_supported_dm_to_msgpack_bytes(self, bridge, context):
        """
        Test complete flow: GetSupportedDMRequest → WrpMessage → msgpack bytes
        """
        # Create USP GetSupportedDMRequest
        usp_dm = GetSupportedDMRequest(
            obj_paths=["Device.WiFi."],
            first_level_only=False,
            return_commands=True,
            return_params=True,
            msg_id="usp-complete-test"
        )
        
        # Translate and encode
        wrp_msg = bridge.to_wrp(usp_dm, context)
        msgpack_bytes = wrp_msg.to_bytes()
        
        # Decode and verify
        decoded_wrp = WrpMessage.from_bytes(msgpack_bytes)
        assert decoded_wrp.metadata["usp_operation"] == "get_supported_dm"
        
        payload = json.loads(decoded_wrp.payload.decode('utf-8'))
        assert payload["method"] == "getAttributes"
    
    def test_get_instances_to_msgpack_bytes(self, bridge, context):
        """
        Test complete flow: GetInstancesRequest → WrpMessage → msgpack bytes
        """
        # Create USP GetInstancesRequest
        usp_instances = GetInstancesRequest(
            obj_paths=["Device.WiFi.Radio."],
            msg_id="usp-complete-test"
        )
        
        # Translate and encode
        wrp_msg = bridge.to_wrp(usp_instances, context)
        msgpack_bytes = wrp_msg.to_bytes()
        
        # Decode and verify
        decoded_wrp = WrpMessage.from_bytes(msgpack_bytes)
        assert decoded_wrp.metadata["usp_operation"] == "get_instances"
        
        payload = json.loads(decoded_wrp.payload.decode('utf-8'))
        assert payload["method"] == "getInstances"
    
    def test_all_usp_operations_msgpack_roundtrip(self, bridge, context):
        """
        Test that all USP operation types survive msgpack encoding/decoding
        
        CRITICAL: Verifies operation type differentiation is preserved through
        the complete msgpack serialization pipeline.
        """
        test_cases = [
            (GetRequest(paths=["Device.Test."], msg_id="msg-1"), "get"),
            (SetRequest(parameters={"Device.Test.Param": "value"}, msg_id="msg-2"), "set"),
            (OperateRequest(command="Device.Reboot()", input_args={}, msg_id="msg-3"), "operate"),
            (GetSupportedDMRequest(obj_paths=["Device."], first_level_only=True, 
                                   return_commands=True, return_params=True, msg_id="msg-4"), "get_supported_dm"),
            (GetInstancesRequest(obj_paths=["Device.WiFi.Radio."], msg_id="msg-5"), "get_instances"),
        ]
        
        for usp_req, expected_operation in test_cases:
            # Update context for each message
            context.usp_msg_id = usp_req.msg_id
            context.sequence = 0  # Reset sequence
            
            # USP Message → WRP Message
            wrp_msg = bridge.to_wrp(usp_req, context)
            
            # WRP Message → msgpack bytes
            msgpack_bytes = wrp_msg.to_bytes()
            assert isinstance(msgpack_bytes, bytes)
            
            # msgpack bytes → WRP Message
            decoded_wrp = WrpMessage.from_bytes(msgpack_bytes)
            
            # Verify operation type preserved in metadata
            assert decoded_wrp.metadata["usp_operation"] == expected_operation, \
                f"Operation type {expected_operation} not preserved through msgpack"
            
            # Verify JSON-RPC request structure preserved
            payload = json.loads(decoded_wrp.payload.decode('utf-8'))
            assert payload["jsonrpc"] == "2.0"
            assert "method" in payload
            assert "id" in payload
            
            # Verify complete message integrity
            assert decoded_wrp.msg_type == MessageType.SIMPLE_REQUEST_RESPONSE
            assert decoded_wrp.source == wrp_msg.source
            assert decoded_wrp.dest == wrp_msg.dest
            assert decoded_wrp.transaction_id == wrp_msg.transaction_id


# =============================================================================
# WrpBridge Tests - WRP to USP Translation  
# =============================================================================

class TestWrpToUspTranslation:
    """Test translating WRP responses to USP"""
    
    @pytest.fixture
    def bridge(self):
        """Create bridge instance"""
        return WrpBridge(mac_address="112233445566")
    
    def test_get_response_parsing(self, bridge):
        """Test parsing WRP response for Get operation"""
        json_rpc_response = {
            "jsonrpc": "2.0",
            "id": "usp-1234:001:ctrl-01",
            "result": {
                "parameters": [
                    {"name": "Device.DeviceInfo.Manufacturer", "value": "ACME"},
                    {"name": "Device.DeviceInfo.SerialNumber", "value": "123456"}
                ]
            }
        }
        
        wrp_msg = WrpMessage(
            msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,
            source="mac:112233445566/usp2wrp",
            dest="mac:112233445566/usp",
            transaction_id="usp-1234:001:ctrl-01",
            content_type="application/json",
            payload=json.dumps(json_rpc_response).encode('utf-8'),
            metadata={
                "usp_msg_id": "usp-1234",
                "usp_operation": "get",  # CRITICAL for determining response type
                "controller_endpoint": "proto::controller-1",
                "mtp_id": "coap"
            }
        )
        
        operation, data, context = bridge.from_wrp(wrp_msg)
        
        # Verify operation type was correctly extracted
        assert operation == "get"
        assert data["parameters"][0]["name"] == "Device.DeviceInfo.Manufacturer"
        assert data["parameters"][0]["value"] == "ACME"
        assert context.usp_msg_id == "usp-1234"
    
    def test_set_response_parsing(self, bridge):
        """Test parsing WRP response for Set operation"""
        json_rpc_response = {
            "jsonrpc": "2.0",
            "id": "usp-1234:002:ctrl-01",
            "result": {
                "parameters": [
                    {"name": "Device.WiFi.Radio.1.Enable", "status": 0}
                ]
            }
        }
        
        wrp_msg = WrpMessage(
            msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,
            source="mac:112233445566/usp2wrp",
            dest="mac:112233445566/usp",
            transaction_id="usp-1234:002:ctrl-01",
            content_type="application/json",
            payload=json.dumps(json_rpc_response).encode('utf-8'),
            metadata={
                "usp_msg_id": "usp-1234",
                "usp_operation": "set",  # CRITICAL - distinguishes from get/operate
                "controller_endpoint": "proto::controller-1",
                "mtp_id": "coap"
            }
        )
        
        operation, data, context = bridge.from_wrp(wrp_msg)
        
        # Verify operation type
        assert operation == "set"
        assert data["parameters"][0]["status"] == 0
    
    def test_operate_response_parsing(self, bridge):
        """Test parsing WRP response for Operate operation"""
        json_rpc_response = {
            "jsonrpc": "2.0",
            "id": "usp-1234:003:ctrl-01",
            "result": {
                "status": 0,
                "message": "Rebooting"
            }
        }
        
        wrp_msg = WrpMessage(
            msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,
            source="mac:112233445566/usp2wrp",
            dest="mac:112233445566/usp",
            transaction_id="usp-1234:003:ctrl-01",
            content_type="application/json",
            payload=json.dumps(json_rpc_response).encode('utf-8'),
            metadata={
                "usp_msg_id": "usp-1234",
                "usp_operation": "operate",  # CRITICAL - distinguishes from get/set
                "usp_command": "Device.Reboot()",
                "controller_endpoint": "proto::controller-1",
                "mtp_id": "coap"
            }
        )
        
        operation, data, context = bridge.from_wrp(wrp_msg)
        
        # Verify operation type was correctly identified
        assert operation == "operate"
        assert data["status"] == 0
        assert data["message"] == "Rebooting"
    
    def test_error_response_parsing(self, bridge):
        """Test parsing WRP error response"""
        json_rpc_error = {
            "jsonrpc": "2.0",
            "id": "usp-1234:001:ctrl-01",
            "error": {
                "code": -32600,
                "message": "Invalid Request"
            }
        }
        
        wrp_msg = WrpMessage(
            msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,
            source="mac:112233445566/usp2wrp",
            dest="mac:112233445566/usp",
            transaction_id="usp-1234:001:ctrl-01",
            content_type="application/json",
            payload=json.dumps(json_rpc_error).encode('utf-8'),
            metadata={
                "usp_msg_id": "usp-1234",
                "usp_operation": "get",
                "controller_endpoint": "proto::controller-1",
                "mtp_id": "coap"
            }
        )
        
        operation, data, context = bridge.from_wrp(wrp_msg)
        
        assert operation == "get"
        assert "error" in data
        assert data["error"]["code"] == -32600
    
    def test_missing_operation_metadata(self, bridge):
        """Test handling WRP response with missing usp_operation metadata"""
        json_rpc_response = {
            "jsonrpc": "2.0",
            "id": "usp-1234:001:ctrl-01",
            "result": {"data": "test"}
        }
        
        wrp_msg = WrpMessage(
            msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,
            source="mac:112233445566/usp2wrp",
            dest="mac:112233445566/usp",
            transaction_id="usp-1234:001:ctrl-01",
            content_type="application/json",
            payload=json.dumps(json_rpc_response).encode('utf-8'),
            metadata={
                "usp_msg_id": "usp-1234",
                # Missing usp_operation!
                "controller_endpoint": "proto::controller-1"
            }
        )
        
        # Should still parse but return "unknown" operation
        operation, data, context = bridge.from_wrp(wrp_msg)
        
        assert operation == "unknown"
        assert data["data"] == "test"


# =============================================================================
# Helper Method Tests
# =============================================================================

class TestHelperMethods:
    """Test bridge helper methods"""
    
    @pytest.fixture
    def bridge(self):
        """Create bridge instance"""
        return WrpBridge(mac_address="112233445566")
    
    def test_infer_data_type_string(self, bridge):
        """Test data type inference for string values"""
        assert bridge._infer_data_type("hello") == 1
        assert bridge._infer_data_type("192.168.1.1") == 1
        assert bridge._infer_data_type("") == 1
    
    def test_infer_data_type_int(self, bridge):
        """Test data type inference for integer values"""
        assert bridge._infer_data_type("42") == 2
        assert bridge._infer_data_type("0") == 2
        assert bridge._infer_data_type("-123") == 2
    
    def test_infer_data_type_boolean(self, bridge):
        """Test data type inference for boolean values"""
        assert bridge._infer_data_type("true") == 3
        assert bridge._infer_data_type("false") == 3
        assert bridge._infer_data_type("True") == 3
        assert bridge._infer_data_type("FALSE") == 3
    
    def test_get_source_endpoint(self, bridge):
        """Test source endpoint generation"""
        assert bridge.get_source() == "mac:112233445566/usp"
    
    def test_get_dest_endpoint(self, bridge):
        """Test destination endpoint generation"""
        assert bridge.get_dest() == "mac:112233445566/usp2wrp"
    
    def test_context_extraction_from_metadata(self, bridge):
        """Test extracting context from WRP metadata"""
        wrp_msg = WrpMessage(
            msg_type=MessageType.SIMPLE_REQUEST_RESPONSE,
            source="mac:112233445566/usp2wrp",
            dest="mac:112233445566/usp",
            transaction_id="usp-1234:001:ctrl-01",
            payload=b"test",
            metadata={
                "usp_msg_id": "usp-1234",
                "usp_operation": "get",
                "controller_endpoint": "proto::controller-1",
                "mtp_id": "coap",
                "controller_id": "ctrl-01"
            }
        )
        
        context = bridge._extract_context(wrp_msg)
        
        assert context.usp_msg_id == "usp-1234"
        assert context.controller_endpoint == "proto::controller-1"
        assert context.mtp_id == "coap"
        assert context.controller_id == "ctrl-01"
    
    def test_context_from_transaction_id(self, bridge):
        """Test parsing context from structured transaction ID"""
        context = bridge._context_from_transaction_id("usp-9876:042:ctrl-test")
        
        assert context.usp_msg_id == "usp-9876"
        assert context.controller_id == "ctrl-test"
        assert context.sequence == 42
        assert context.mac_address == "112233445566"


class TestSendMethod:
    """Test the send() method with transport integration"""
    
    def test_send_without_transport_raises_error(self):
        """Test send() raises error when no transport configured"""
        bridge = WrpBridge(mac_address="112233445566")
        request = GetRequest(
            msg_id="test-1",
            paths=["Device.DeviceInfo.Manufacturer"]
        )
        
        with pytest.raises(Exception) as exc_info:
            bridge.send(request)
        
        assert "No transport configured" in str(exc_info.value)
    
    def test_send_with_transport(self):
        """Test send() successfully calls transport"""
        sent_data = []
        
        def mock_transport_send(data: bytes):
            sent_data.append(data)
        
        bridge = WrpBridge(
            mac_address="112233445566",
            transport_send=mock_transport_send
        )
        
        request = GetRequest(
            msg_id="test-1",
            paths=["Device.DeviceInfo.Manufacturer"]
        )
        
        context = BridgeContext(
            usp_msg_id="test-1",
            controller_endpoint="proto::controller-1",
            mtp_id="coap",
            mac_address="112233445566"
        )
        
        # Send should not raise
        bridge.send(request, context)
        
        # Verify transport was called with bytes
        assert len(sent_data) == 1
        assert isinstance(sent_data[0], bytes)
        
        # Verify the bytes can be decoded back to WRP message
        wrp_msg = WrpMessage.from_bytes(sent_data[0])
        assert wrp_msg.source == "mac:112233445566/usp"
        assert wrp_msg.dest == "mac:112233445566/usp2wrp"
        
        # Verify payload contains JSON-RPC get request
        payload = json.loads(wrp_msg.payload)
        assert payload["method"] == "get"
        assert payload["params"]["names"] == ["Device.DeviceInfo.Manufacturer"]
    
    def test_send_creates_context_if_not_provided(self):
        """Test send() creates context if not provided"""
        sent_data = []
        
        def mock_transport_send(data: bytes):
            sent_data.append(data)
        
        bridge = WrpBridge(
            mac_address="112233445566",
            transport_send=mock_transport_send
        )
        
        request = GetRequest(
            msg_id="test-1",
            paths=["Device.DeviceInfo.Manufacturer"]
        )
        
        # Send without context
        bridge.send(request)
        
        # Verify transport was called
        assert len(sent_data) == 1
        assert isinstance(sent_data[0], bytes)
    
    def test_send_transport_error_raises_bridge_error(self):
        """Test send() raises BridgeError if transport fails"""
        def failing_transport(data: bytes):
            raise OSError("Connection refused")
        
        bridge = WrpBridge(
            mac_address="112233445566",
            transport_send=failing_transport
        )
        
        request = GetRequest(
            msg_id="test-1",
            paths=["Device.DeviceInfo.Manufacturer"]
        )
        
        with pytest.raises(Exception) as exc_info:
            bridge.send(request)
        
        assert "Transport send failed" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
