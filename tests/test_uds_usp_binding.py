"""
Copyright (c) 2026

Unit tests for UDS USP Binding
"""

import unittest
from unittest import mock
import queue

from agent import uds_usp_binding
from agent import usp_record_pb2


class TestUdsUspBinding(unittest.TestCase):
    """Test cases for UdsUspBinding"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.socket_path = "/tmp/test-usp-agent.sock"
        self.endpoint_id = "self::test-agent"
        
    def test_binding_initialization(self):
        """Test binding initialization"""
        binding = uds_usp_binding.UdsUspBinding(
            self.socket_path,
            mode='listen',
            endpoint_id=self.endpoint_id
        )
        
        self.assertEqual(binding._socket_path, self.socket_path)
        self.assertEqual(binding._mode, 'listen')
        self.assertEqual(binding._endpoint_id, self.endpoint_id)
        self.assertFalse(binding._running)
        
    @mock.patch('mtp.uds.UdsTransport')
    def test_start_listening_server_mode(self, mock_transport_class):
        """Test start listening in server mode"""
        mock_transport = mock.MagicMock()
        mock_transport_class.return_value = mock_transport
        
        binding = uds_usp_binding.UdsUspBinding(
            self.socket_path,
            mode='listen',
            endpoint_id=self.endpoint_id
        )
        
        binding.start_listening()
        
        # Verify transport created and started
        mock_transport_class.assert_called_once_with(self.socket_path, 'listen')
        mock_transport.start.assert_called_once()
        self.assertTrue(binding._running)
        
        # Clean up
        binding.clean_up()
        
    @mock.patch('mtp.uds.UdsTransport')
    def test_start_listening_client_mode(self, mock_transport_class):
        """Test start listening in client mode"""
        mock_transport = mock.MagicMock()
        mock_transport_class.return_value = mock_transport
        
        binding = uds_usp_binding.UdsUspBinding(
            self.socket_path,
            mode='connect',
            endpoint_id=self.endpoint_id
        )
        
        binding.start_listening()
        
        # Verify transport created with connect mode
        mock_transport_class.assert_called_once_with(self.socket_path, 'connect')
        mock_transport.start.assert_called_once()
        
        # Clean up
        binding.clean_up()
        
    def test_handle_received_data_valid_record(self):
        """Test handling valid USP Record"""
        binding = uds_usp_binding.UdsUspBinding(
            self.socket_path,
            mode='listen',
            endpoint_id=self.endpoint_id
        )
        
        # Create test record
        record = usp_record_pb2.Record()
        record.version = "1.4"
        record.to_id = "self::test-agent"
        record.from_id = "self::test-controller"
        record.no_session_context.payload = b"test_payload"
        
        record_bytes = record.SerializeToString()
        
        # Handle the data
        binding._handle_received_data(record_bytes)
        
        # Verify message was queued
        queue_item = binding.pop()
        self.assertIsNotNone(queue_item)
        payload = queue_item.get_payload()
        from_id = queue_item.get_reply_to_addr()
        self.assertEqual(payload, b"test_payload")
        self.assertEqual(from_id, "self::test-controller")
        
    def test_handle_received_data_session_context(self):
        """Test handling USP Record with session context"""
        binding = uds_usp_binding.UdsUspBinding(
            self.socket_path,
            mode='listen',
            endpoint_id=self.endpoint_id
        )
        
        # Create test record with session context
        record = usp_record_pb2.Record()
        record.version = "1.4"
        record.to_id = "self::test-agent"
        record.from_id = "self::test-controller"
        record.session_context.session_id = 123
        record.session_context.sequence_id = 1
        record.session_context.expected_id = 2
        # payload is a repeated field - add to the list
        record.session_context.payload.append(b"session_payload")
        
        record_bytes = record.SerializeToString()
        
        # Handle the data
        binding._handle_received_data(record_bytes)
        
        # Verify message was queued
        queue_item = binding.pop()
        self.assertIsNotNone(queue_item)
        payload = queue_item.get_payload()
        from_id = queue_item.get_reply_to_addr()
        self.assertEqual(payload, b"session_payload")
        self.assertEqual(from_id, "self::test-controller")
        
    def test_handle_received_data_invalid_no_to_id(self):
        """Test handling record without to_id"""
        binding = uds_usp_binding.UdsUspBinding(
            self.socket_path,
            mode='listen',
            endpoint_id=self.endpoint_id
        )
        
        # Create invalid record (no to_id)
        record = usp_record_pb2.Record()
        record.version = "1.4"
        record.from_id = "self::test-controller"
        record.no_session_context.payload = b"test_payload"
        
        record_bytes = record.SerializeToString()
        
        # Handle the data - should be ignored
        binding._handle_received_data(record_bytes)
        
        # Verify nothing was queued
        queue_item = binding.pop()
        self.assertIsNone(queue_item)
        
    def test_handle_received_data_invalid_no_from_id(self):
        """Test handling record without from_id"""
        binding = uds_usp_binding.UdsUspBinding(
            self.socket_path,
            mode='listen',
            endpoint_id=self.endpoint_id
        )
        
        # Create invalid record (no from_id)
        record = usp_record_pb2.Record()
        record.version = "1.4"
        record.to_id = "self::test-agent"
        record.no_session_context.payload = b"test_payload"
        
        record_bytes = record.SerializeToString()
        
        # Handle the data - should be ignored
        binding._handle_received_data(record_bytes)
        
        # Verify nothing was queued
        queue_item = binding.pop()
        self.assertIsNone(queue_item)
        
    @mock.patch('mtp.uds.UdsTransport')
    def test_send_msg_connected(self, mock_transport_class):
        """Test sending message when connected"""
        mock_transport = mock.MagicMock()
        mock_transport.is_connected.return_value = True
        mock_transport_class.return_value = mock_transport
        
        binding = uds_usp_binding.UdsUspBinding(
            self.socket_path,
            mode='listen',
            endpoint_id=self.endpoint_id
        )
        binding._transport = mock_transport
        
        # Send a message
        to_id = "self::test-controller"
        usp_msg = b"test_usp_message"
        
        binding.send_msg(to_id, usp_msg)
        
        # Verify send_message was called
        self.assertEqual(mock_transport.send_message.call_count, 1)
        
        # Verify the record structure
        call_args = mock_transport.send_message.call_args[0]
        sent_record = usp_record_pb2.Record()
        sent_record.ParseFromString(call_args[0])
        
        self.assertEqual(sent_record.version, "1.4")
        self.assertEqual(sent_record.to_id, to_id)
        self.assertEqual(sent_record.from_id, self.endpoint_id)
        self.assertEqual(sent_record.no_session_context.payload, usp_msg)
        
    @mock.patch('mtp.uds.UdsTransport')
    def test_send_msg_not_connected(self, mock_transport_class):
        """Test sending message when not connected"""
        mock_transport = mock.MagicMock()
        mock_transport.is_connected.return_value = False
        mock_transport_class.return_value = mock_transport
        
        binding = uds_usp_binding.UdsUspBinding(
            self.socket_path,
            mode='listen',
            endpoint_id=self.endpoint_id
        )
        binding._transport = mock_transport
        
        # Try to send a message
        to_id = "self::test-controller"
        usp_msg = b"test_usp_message"
        
        binding.send_msg(to_id, usp_msg)
        
        # Verify send_message was NOT called
        mock_transport.send_message.assert_not_called()
        
    @mock.patch('mtp.uds.UdsTransport')
    def test_clean_up(self, mock_transport_class):
        """Test clean up"""
        mock_transport = mock.MagicMock()
        mock_transport_class.return_value = mock_transport
        
        binding = uds_usp_binding.UdsUspBinding(
            self.socket_path,
            mode='listen',
            endpoint_id=self.endpoint_id
        )
        
        binding.start_listening()
        
        # Clean up
        binding.clean_up()
        
        # Verify transport was closed
        mock_transport.close.assert_called_once()
        self.assertFalse(binding._running)


if __name__ == '__main__':
    unittest.main()
