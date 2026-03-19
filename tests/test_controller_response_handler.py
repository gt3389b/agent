"""Unit tests for controller/response_handler.py"""

import pytest

from controller import response_handler
from message import usp_msg_pb2 as usp_msg
from message import usp_record_pb2 as usp_record

CONTROLLER_ENDPOINT = "proto::test-controller"
AGENT_ENDPOINT = "proto::test-agent"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(msg, to_id=CONTROLLER_ENDPOINT, from_id=AGENT_ENDPOINT):
    """Wrap a USP Msg in a USP Record and return serialized bytes."""
    record = usp_record.Record()
    record.version = "1.0"
    record.to_id = to_id
    record.from_id = from_id
    record.payload_security = usp_record.Record.PLAINTEXT
    record.no_session_context.payload = msg.SerializeToString()
    return record.SerializeToString()


def _make_get_resp(msg_id="msg-001"):
    msg = usp_msg.Msg()
    msg.header.msg_id = msg_id
    msg.header.msg_type = usp_msg.Header.GET_RESP
    result = msg.body.response.get_resp.req_path_results.add()
    result.requested_path = "Device.DeviceInfo."
    return msg


def _make_set_resp(msg_id="msg-002"):
    msg = usp_msg.Msg()
    msg.header.msg_id = msg_id
    msg.header.msg_type = usp_msg.Header.SET_RESP
    return msg


def _make_notify(msg_id="msg-003"):
    msg = usp_msg.Msg()
    msg.header.msg_id = msg_id
    msg.header.msg_type = usp_msg.Header.NOTIFY
    return msg


def _handler():
    return response_handler.UspResponseHandler(CONTROLLER_ENDPOINT)


# ---------------------------------------------------------------------------
# Successful response handling
# ---------------------------------------------------------------------------

def test_handle_get_resp():
    """handle_request processes a GET_RESP without raising."""
    payload = _make_record(_make_get_resp())
    req_msg, req_record, resp_msg, resp_bytes = _handler().handle_request(payload)
    assert req_msg.header.msg_type == usp_msg.Header.GET_RESP
    assert req_msg.header.msg_id == "msg-001"


def test_handle_set_resp():
    """handle_request processes a SET_RESP without raising."""
    payload = _make_record(_make_set_resp())
    req_msg, _, _, _ = _handler().handle_request(payload)
    assert req_msg.header.msg_type == usp_msg.Header.SET_RESP


def test_handle_notify():
    """handle_request processes a NOTIFY without raising."""
    payload = _make_record(_make_notify())
    req_msg, _, _, _ = _handler().handle_request(payload)
    assert req_msg.header.msg_type == usp_msg.Header.NOTIFY


# ---------------------------------------------------------------------------
# Validation failures → ProtocolViolationError
# ---------------------------------------------------------------------------

def test_wrong_to_id_raises():
    """Record addressed to someone else raises ProtocolViolationError."""
    payload = _make_record(_make_get_resp(), to_id="wrong-endpoint")
    with pytest.raises(response_handler.ProtocolViolationError):
        _handler().handle_request(payload)


def test_missing_version_raises():
    """Record without a version field raises ProtocolViolationError."""
    record = usp_record.Record()
    # version defaults to "" which is falsy
    record.to_id = CONTROLLER_ENDPOINT
    record.from_id = AGENT_ENDPOINT
    record.payload_security = usp_record.Record.PLAINTEXT
    record.no_session_context.payload = _make_get_resp().SerializeToString()
    with pytest.raises(response_handler.ProtocolViolationError):
        _handler().handle_request(record.SerializeToString())


def test_missing_from_id_raises():
    """Record without from_id raises ProtocolViolationError."""
    record = usp_record.Record()
    record.version = "1.0"
    record.to_id = CONTROLLER_ENDPOINT
    # from_id defaults to ""
    record.payload_security = usp_record.Record.PLAINTEXT
    record.no_session_context.payload = _make_get_resp().SerializeToString()
    with pytest.raises(response_handler.ProtocolViolationError):
        _handler().handle_request(record.SerializeToString())


def test_non_plaintext_security_raises():
    """Record with non-PLAINTEXT payload_security raises ProtocolViolationError."""
    record = usp_record.Record()
    record.version = "1.0"
    record.to_id = CONTROLLER_ENDPOINT
    record.from_id = AGENT_ENDPOINT
    record.payload_security = usp_record.Record.TLS12
    record.no_session_context.payload = _make_get_resp().SerializeToString()
    with pytest.raises(response_handler.ProtocolViolationError):
        _handler().handle_request(record.SerializeToString())


def test_missing_msg_id_raises():
    """USP Message without msg_id raises ProtocolViolationError."""
    msg = usp_msg.Msg()
    msg.header.msg_type = usp_msg.Header.GET_RESP
    # msg_id defaults to ""
    payload = _make_record(msg)
    with pytest.raises(response_handler.ProtocolViolationError):
        _handler().handle_request(payload)


# ---------------------------------------------------------------------------
# Debug mode (covers the debug print branch)
# ---------------------------------------------------------------------------

def test_handle_get_resp_debug_mode():
    """handle_request in debug mode still processes correctly."""
    handler = response_handler.UspResponseHandler(CONTROLLER_ENDPOINT, debug=True)
    payload = _make_record(_make_get_resp())
    req_msg, _, _, _ = handler.handle_request(payload)
    assert req_msg.header.msg_type == usp_msg.Header.GET_RESP


# ---------------------------------------------------------------------------
# SetValidationError helper class
# ---------------------------------------------------------------------------

def test_set_validation_error_accessors():
    err = response_handler.SetValidationError(9001, "bad path")
    assert err.get_error_code() == 9001
    assert err.get_error_message() == "bad path"
    assert "9001" in str(err)
