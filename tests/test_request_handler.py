"""
Copyright (c) 2016 John Blackford

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

# File Name: test_agent_db.py
#
# Description: Unit tests for the Database Class
#
"""

import unittest.mock as mock
import pytest

from agent import agent_db
from agent import request_handler


@pytest.fixture(autouse=True)
def mock_db_file_exists():
    """Patch os.path.exists in agent_db so Database() accepts mock filenames."""
    with mock.patch("agent.agent_db.os.path.exists", return_value=True):
        yield


"""
 Tests for _is_set_path_static
"""


def test_is_set_path_static():
    endpoint_id = "ENDPOINT-ID"
    mock_db = mock.create_autospec(agent_db.Database)
    req_handler = request_handler.UspRequestHandler(endpoint_id, mock_db)

    assert req_handler._is_partial_path_static("Device.LocalAgent."), "Static Path Failure"
    assert not req_handler._is_partial_path_static("Device.Controller.1."), "Instance Number Addressing Path Failure"
    assert not req_handler._is_partial_path_static("Device.Controller.*."), "Wildcard-based Searching Path Failure"


"""
 Tests for _is_set_path_searching
"""


def test_is_set_path_searching():
    endpoint_id = "ENDPOINT-ID"
    mock_db = mock.create_autospec(agent_db.Database)
    req_handler = request_handler.UspRequestHandler(endpoint_id, mock_db)

    assert not req_handler._is_partial_path_searching("Device.LocalAgent."), "Static Path Failure"
    assert not req_handler._is_partial_path_searching("Device.Controller.1."), "Instance Number Addressing Path Failure"
    assert req_handler._is_partial_path_searching("Device.Controller.*."), "Wildcard-based Searching Path Failure"


"""
 Tests for _split_path
"""


def test_split_path_full_path():
    endpoint_id = "ENDPOINT-ID"
    mock_db = mock.create_autospec(agent_db.Database)
    req_handler = request_handler.UspRequestHandler(endpoint_id, mock_db)
    path = "Device.LocalAgent.Controller.1.MTP.1.Protocol"

    partial_path, param_name = req_handler._split_path(path)

    assert partial_path == "Device.LocalAgent.Controller.1.MTP.1.", "Partial Path Failure"
    assert param_name == "Protocol", "Parameter Name Failure"

def test_split_path_partial_path():
    endpoint_id = "ENDPOINT-ID"
    mock_db = mock.create_autospec(agent_db.Database)
    req_handler = request_handler.UspRequestHandler(endpoint_id, mock_db)
    path = "Device.LocalAgent.Controller.1.MTP.1."

    partial_path, param_name = req_handler._split_path(path)

    assert partial_path == "Device.LocalAgent.Controller.1.MTP.1.", "Partial Path Failure"
    assert param_name is None, "Parameter Name Failure, should be None"

def test_split_path_wildcard_path():
    endpoint_id = "ENDPOINT-ID"
    mock_db = mock.create_autospec(agent_db.Database)
    req_handler = request_handler.UspRequestHandler(endpoint_id, mock_db)
    path = "Device.LocalAgent.Controller.*.MTP.*."

    partial_path, param_name = req_handler._split_path(path)

    assert partial_path == "Device.LocalAgent.Controller.*.MTP.*.", "Partial Path Failure"
    assert param_name is None, "Parameter Name Failure, should be None"



"""
 Tests for _diff_paths
"""


def test_diff_paths_partial_path_req():
    endpoint_id = "ENDPOINT-ID"
    mock_db = mock.create_autospec(agent_db.Database)
    req_handler = request_handler.UspRequestHandler(endpoint_id, mock_db)
    req_path = "Device.LocalAgent.Controller."
    param_path = "Device.LocalAgent.Controller.1.EndpointID"

    diff_path = req_handler._diff_paths(req_path, param_path)

    assert diff_path == "1.EndpointID"

def test_diff_paths_wildcard_path_req():
    endpoint_id = "ENDPOINT-ID"
    mock_db = mock.create_autospec(agent_db.Database)
    req_handler = request_handler.UspRequestHandler(endpoint_id, mock_db)
    req_path = "Device.LocalAgent.Controller.*."
    param_path = "Device.LocalAgent.Controller.1.EndpointID"

    diff_path = req_handler._diff_paths(req_path, param_path)

    assert diff_path == "1.EndpointID"

def test_diff_paths_multiple_wildcard_path_req():
    endpoint_id = "ENDPOINT-ID"
    mock_db = mock.create_autospec(agent_db.Database)
    req_handler = request_handler.UspRequestHandler(endpoint_id, mock_db)
    req_path = "Device.LocalAgent.Controller.*.MTP.*."
    param_path = "Device.LocalAgent.Controller.1.MTP.2.Protocol"

    diff_path = req_handler._diff_paths(req_path, param_path)

    assert diff_path == "1.MTP.2.Protocol"


"""
 Tests for _get_affected_paths_for_get
"""

def get_db_file_contents():
    db_contents = """{
        "Device.SubscriptionNumberOfEntries": "__NUM_ENTRIES__",
        "Device.Subscription.1.Enable": true,
        "Device.Subscription.1.ID": "sub-boot-stomp",
        "Device.Subscription.1.NotifType": "Boot",
        "Device.Subscription.1.ParamPath": "Device.LocalAgent.",
        "Device.Subscription.1.Controller": "Device.Controller.1.",
        "Device.Subscription.1.TimeToLive": -1,
        "Device.Subscription.1.Persistent": true,
        "Device.Subscription.2.Enable": true,
        "Device.Subscription.2.ID": "sub-periodic-stomp",
        "Device.Subscription.2.NotifType": "Periodic",
        "Device.Subscription.2.ParamPath": "Device.LocalAgent.",
        "Device.Subscription.2.Controller": "Device.Controller.1.",
        "Device.Subscription.2.TimeToLive": -1,
        "Device.Subscription.2.Persistent": true,
        "Device.Subscription.3.Enable": true,
        "Device.Subscription.3.ID": "sub-boot-coap",
        "Device.Subscription.3.NotifType": "Boot",
        "Device.Subscription.3.ParamPath": "Device.LocalAgent.",
        "Device.Subscription.3.Controller": "Device.Controller.2.",
        "Device.Subscription.3.TimeToLive": -1,
        "Device.Subscription.3.Persistent": true,
        "Device.Services.HomeAutomationNumberOfEntries": "__NUM_ENTRIES__",
        "Device.Services.HomeAutomation.1.CameraNumberOfEntries": "__NUM_ENTRIES__",
        "Device.Services.HomeAutomation.1.Camera.1.MaxNumberOfPics": 30,
        "Device.Services.HomeAutomation.1.Camera.1.PicNumberOfEntries": "__NUM_ENTRIES__",
        "Device.Services.HomeAutomation.1.Camera.1.Pic.__NextInstNum__": 11,
        "Device.Services.HomeAutomation.1.Camera.1.Pic.9.URL": "http://localhost:8080/pic1.png",
        "Device.Services.HomeAutomation.1.Camera.1.Pic.10.URL": "http://localhost:8080/pic2.png",
        "Device.Services.HomeAutomation.1.Camera.2.MaxNumberOfPics": 30,
        "Device.Services.HomeAutomation.1.Camera.2.PicNumberOfEntries": "__NUM_ENTRIES__",
        "Device.Services.HomeAutomation.1.Camera.2.Pic.__NextInstNum__": 11,
        "Device.Services.HomeAutomation.1.Camera.2.Pic.10.URL": "http://localhost:8080/pic5.png",
        "Device.Services.HomeAutomation.1.Camera.2.Pic.90.URL": "http://localhost:8080/pic9.png",
        "Device.Services.HomeAutomation.1.Camera.2.Pic.100.URL": "http://localhost:8080/pic20.png"
    }"""
    return db_contents


def get_dm_file_contents():
    dm_contents = """{
        "Device.SubscriptionNumberOfEntries": "readOnly",
        "Device.Subscription.{i}.Enable": "readWrite",
        "Device.Subscription.{i}.ID": "readWrite",
        "Device.Subscription.{i}.NotifType": "readWrite",
        "Device.Subscription.{i}.ParamPath": "readWrite",
        "Device.Subscription.{i}.Controller": "readWrite",
        "Device.Subscription.{i}.TimeToLive": "readWrite",
        "Device.Subscription.{i}.Persistent": "readWrite",
        "Device.Services.HomeAutomationNumberOfEntries": "readOnly",
        "Device.Services.HomeAutomation.{i}.CameraNumberOfEntries": "readOnly",
        "Device.Services.HomeAutomation.{i}.Camera.{i}.TakePicture()": "readWrite",
        "Device.Services.HomeAutomation.{i}.Camera.{i}.MaxNumberOfPics": "readWrite",
        "Device.Services.HomeAutomation.{i}.Camera.{i}.PicNumberOfEntries": "readOnly",
        "Device.Services.HomeAutomation.{i}.Camera.{i}.Pic.{i}.URL": "readOnly"
    }"""
    return dm_contents

def test_get_affected_paths_for_get_partial_path():
    endpoint_id = "ENDPOINT-ID"
    my_mock = dm_mock = mock.mock_open(read_data=get_dm_file_contents())
    db_mock = mock.mock_open(read_data=get_db_file_contents())
    my_mock.side_effect = [dm_mock.return_value, db_mock.return_value]
    partial_path = "Device.Subscription."

    with mock.patch("builtins.open", my_mock):
        my_db = agent_db.Database("mock_dm.json", "mock_db.json", "intf")
        req_handler = request_handler.UspRequestHandler(endpoint_id, my_db)
        affected_path_list = req_handler._get_affected_paths_for_get(partial_path)

    assert len(affected_path_list) == 1, "expecting 1, found " + str(len(affected_path_list))
    assert affected_path_list[0] == "Device.Subscription."

def test_get_affected_paths_for_get_wildcard_path():
    endpoint_id = "ENDPOINT-ID"
    my_mock = dm_mock = mock.mock_open(read_data=get_dm_file_contents())
    db_mock = mock.mock_open(read_data=get_db_file_contents())
    my_mock.side_effect = [dm_mock.return_value, db_mock.return_value]
    partial_path = "Device.Subscription.*."

    with mock.patch("builtins.open", my_mock):
        my_db = agent_db.Database("mock_dm.json", "mock_db.json", "intf")
        req_handler = request_handler.UspRequestHandler(endpoint_id, my_db)
        affected_path_list = req_handler._get_affected_paths_for_get(partial_path)

    assert len(affected_path_list) == 3, "expecting 3, found " + str(len(affected_path_list))

def test_get_affected_paths_for_get_two_layers():
    endpoint_id = "ENDPOINT-ID"
    my_mock = dm_mock = mock.mock_open(read_data=get_dm_file_contents())
    db_mock = mock.mock_open(read_data=get_db_file_contents())
    my_mock.side_effect = [dm_mock.return_value, db_mock.return_value]
    partial_path = "Device.Services.HomeAutomation.*.Camera.*.Pic."

    with mock.patch("builtins.open", my_mock):
        my_db = agent_db.Database("mock_dm.json", "mock_db.json", "intf")
        req_handler = request_handler.UspRequestHandler(endpoint_id, my_db)
        affected_path_list = req_handler._get_affected_paths_for_get(partial_path)

    assert len(affected_path_list) == 2, "expecting 2, found " + str(len(affected_path_list))

def test_get_affected_paths_for_get_three_layers():
    endpoint_id = "ENDPOINT-ID"
    my_mock = dm_mock = mock.mock_open(read_data=get_dm_file_contents())
    db_mock = mock.mock_open(read_data=get_db_file_contents())
    my_mock.side_effect = [dm_mock.return_value, db_mock.return_value]
    partial_path = "Device.Services.HomeAutomation.*.Camera.*.Pic.*."

    with mock.patch("builtins.open", my_mock):
        my_db = agent_db.Database("mock_dm.json", "mock_db.json", "intf")
        req_handler = request_handler.UspRequestHandler(endpoint_id, my_db)
        affected_path_list = req_handler._get_affected_paths_for_get(partial_path)

    assert len(affected_path_list) == 5, "expecting 5, found " + str(len(affected_path_list))


# ---------------------------------------------------------------------------
# Helpers for building serialised USP protobuf payloads
# ---------------------------------------------------------------------------

from message import usp_msg_pb2 as usp_msg
from message import usp_record_pb2 as usp_record
from agent.agent_db import NoSuchPathError

AGENT_ENDPOINT = "proto::test-agent"
CONTROLLER_ENDPOINT = "proto::test-controller"


def _make_record(msg, to_id=AGENT_ENDPOINT, from_id=CONTROLLER_ENDPOINT):
    """Wrap a USP Msg in a USP Record and return serialized bytes."""
    record = usp_record.Record()
    record.version = "1.0"
    record.to_id = to_id
    record.from_id = from_id
    record.payload_security = usp_record.Record.PLAINTEXT
    record.no_session_context.payload = msg.SerializeToString()
    return record.SerializeToString()


def _make_get(param_paths, msg_id="msg-get-001"):
    msg = usp_msg.Msg()
    msg.header.msg_id = msg_id
    msg.header.msg_type = usp_msg.Header.GET
    for p in param_paths:
        msg.body.request.get.param_paths.append(p)
    return msg


def _make_set(obj_path, params, msg_id="msg-set-001", allow_partial=False):
    """params: list of (param_name, value, required)."""
    msg = usp_msg.Msg()
    msg.header.msg_id = msg_id
    msg.header.msg_type = usp_msg.Header.SET
    msg.body.request.set.allow_partial = allow_partial
    update_obj = msg.body.request.set.update_objs.add()
    update_obj.obj_path = obj_path
    for param_name, value, required in params:
        ps = update_obj.param_settings.add()
        ps.param = param_name
        ps.value = value
        ps.required = required
    return msg


def _make_operate(command, msg_id="msg-op-001"):
    msg = usp_msg.Msg()
    msg.header.msg_id = msg_id
    msg.header.msg_type = usp_msg.Header.OPERATE
    msg.body.request.operate.command = command
    return msg


def _handler(db=None):
    if db is None:
        db = mock.create_autospec(agent_db.Database)
    return request_handler.UspRequestHandler(AGENT_ENDPOINT, db)


# ---------------------------------------------------------------------------
# handle_request — GET
# ---------------------------------------------------------------------------

def test_handle_request_get_specific_param():
    """GET for a fully-qualified param path returns GET_RESP with that value."""
    db = mock.create_autospec(agent_db.Database)
    db.find_objects.return_value = ["Device.DeviceInfo."]
    db.get.return_value = "ACME"

    payload = _make_record(_make_get(["Device.DeviceInfo.Manufacturer"]))
    req_msg, _, resp_msg, _ = _handler(db).handle_request(payload)

    assert resp_msg.header.msg_type == usp_msg.Header.GET_RESP
    assert resp_msg.header.msg_id == "msg-get-001"
    results = resp_msg.body.response.get_resp.req_path_results
    assert results[0].resolved_path_results[0].result_params["Manufacturer"] == "ACME"


def test_handle_request_get_partial_path():
    """GET for a partial path returns all params under it."""
    db = mock.create_autospec(agent_db.Database)
    db.find_objects.return_value = ["Device.DeviceInfo."]
    db.find_params.return_value = [
        "Device.DeviceInfo.Manufacturer",
        "Device.DeviceInfo.ProductClass",
    ]
    db.get.side_effect = lambda p: {
        "Device.DeviceInfo.Manufacturer": "ACME",
        "Device.DeviceInfo.ProductClass": "Widget",
    }[p]

    payload = _make_record(_make_get(["Device.DeviceInfo."]))
    _, _, resp_msg, _ = _handler(db).handle_request(payload)

    assert resp_msg.header.msg_type == usp_msg.Header.GET_RESP
    rpr = resp_msg.body.response.get_resp.req_path_results[0]
    assert rpr.resolved_path_results[0].result_params["Manufacturer"] == "ACME"
    assert rpr.resolved_path_results[0].result_params["ProductClass"] == "Widget"


def test_handle_request_get_invalid_path():
    """GET for an unknown path sets err_code on the path result."""
    db = mock.create_autospec(agent_db.Database)
    db.find_objects.side_effect = NoSuchPathError("Device.Bad.")

    payload = _make_record(_make_get(["Device.Bad.Param"]))
    _, _, resp_msg, _ = _handler(db).handle_request(payload)

    assert resp_msg.header.msg_type == usp_msg.Header.GET_RESP
    path_result = resp_msg.body.response.get_resp.req_path_results[0]
    assert path_result.err_code == 11002


def test_handle_request_wrong_to_id_raises():
    """A record with the wrong to_id raises ProtocolViolationError."""
    payload = _make_record(_make_get(["Device.DeviceInfo."]), to_id="wrong-endpoint")
    with pytest.raises(request_handler.ProtocolViolationError):
        _handler().handle_request(payload)


# ---------------------------------------------------------------------------
# handle_request — SET
# ---------------------------------------------------------------------------

def test_handle_request_set_success():
    """SET a writable param updates the DB and returns SET_RESP."""
    db = mock.create_autospec(agent_db.Database)
    db.find_objects.return_value = ["Device.LocalAgent.Controller.1."]
    db.is_param_writable.return_value = True
    db.get.return_value = "old-value"

    payload = _make_record(
        _make_set("Device.LocalAgent.Controller.1.", [("EndpointID", "new-ep", True)])
    )
    _, _, resp_msg, _ = _handler(db).handle_request(payload)

    assert resp_msg.header.msg_type == usp_msg.Header.SET_RESP
    db.update.assert_called_once_with(
        "Device.LocalAgent.Controller.1.EndpointID", "new-ep"
    )


def test_handle_request_set_same_value_no_update():
    """SET with the same value as the current one skips the DB update call."""
    db = mock.create_autospec(agent_db.Database)
    db.find_objects.return_value = ["Device.LocalAgent.Controller.1."]
    db.is_param_writable.return_value = True
    db.get.return_value = "same-value"

    payload = _make_record(
        _make_set("Device.LocalAgent.Controller.1.", [("EndpointID", "same-value", True)])
    )
    _, _, resp_msg, _ = _handler(db).handle_request(payload)

    assert resp_msg.header.msg_type == usp_msg.Header.SET_RESP
    db.update.assert_not_called()


def test_handle_request_set_required_not_writable_returns_error():
    """SET a required-but-not-writable param → Error (allow_partial=False)."""
    db = mock.create_autospec(agent_db.Database)
    db.find_objects.return_value = ["Device.LocalAgent.Controller.1."]
    db.is_param_writable.return_value = False

    payload = _make_record(
        _make_set(
            "Device.LocalAgent.Controller.1.",
            [("ReadOnly", "val", True)],
            allow_partial=False,
        )
    )
    _, _, resp_msg, _ = _handler(db).handle_request(payload)

    assert resp_msg.header.msg_type == usp_msg.Header.ERROR


def test_handle_request_set_optional_not_writable_returns_set_resp():
    """SET an optional-but-not-writable param → SET_RESP with param_errs in oper_success."""
    db = mock.create_autospec(agent_db.Database)
    db.find_objects.return_value = ["Device.LocalAgent.Controller.1."]
    db.is_param_writable.return_value = False

    payload = _make_record(
        _make_set(
            "Device.LocalAgent.Controller.1.",
            [("ReadOnly", "val", False)],
        )
    )
    _, _, resp_msg, _ = _handler(db).handle_request(payload)

    assert resp_msg.header.msg_type == usp_msg.Header.SET_RESP


def test_handle_request_set_required_failure_allow_partial_returns_oper_failure():
    """SET required param failure with allow_partial=True → SET_RESP with oper_failure."""
    db = mock.create_autospec(agent_db.Database)
    db.find_objects.return_value = ["Device.LocalAgent.Controller.1."]
    db.is_param_writable.return_value = False

    payload = _make_record(
        _make_set(
            "Device.LocalAgent.Controller.1.",
            [("ReadOnly", "val", True)],
            allow_partial=True,
        )
    )
    _, _, resp_msg, _ = _handler(db).handle_request(payload)

    assert resp_msg.header.msg_type == usp_msg.Header.SET_RESP
    result = resp_msg.body.response.set_resp.updated_obj_results[0]
    assert result.oper_status.WhichOneof("oper_status") == "oper_failure"


def test_handle_request_set_no_such_path_allow_partial_false():
    """NoSuchPathError on obj_path with allow_partial=False → Error."""
    db = mock.create_autospec(agent_db.Database)
    db.find_objects.side_effect = NoSuchPathError("Device.Bad.")

    payload = _make_record(
        _make_set("Device.Bad.", [("Foo", "bar", False)], allow_partial=False)
    )
    _, _, resp_msg, _ = _handler(db).handle_request(payload)

    assert resp_msg.header.msg_type == usp_msg.Header.ERROR


def test_handle_request_set_no_such_path_allow_partial_true():
    """NoSuchPathError on obj_path with allow_partial=True → SET_RESP with oper_failure."""
    db = mock.create_autospec(agent_db.Database)
    db.find_objects.side_effect = NoSuchPathError("Device.Bad.")

    payload = _make_record(
        _make_set("Device.Bad.", [("Foo", "bar", False)], allow_partial=True)
    )
    _, _, resp_msg, _ = _handler(db).handle_request(payload)

    assert resp_msg.header.msg_type == usp_msg.Header.SET_RESP
    result = resp_msg.body.response.set_resp.updated_obj_results[0]
    assert result.oper_status.WhichOneof("oper_status") == "oper_failure"


def test_handle_request_set_nonexistent_instance_path_returns_error():
    """Instance-addressed path with empty find_objects result → Error (allow_partial=False)."""
    db = mock.create_autospec(agent_db.Database)
    db.find_objects.return_value = []  # no match, not a static/search path

    payload = _make_record(
        _make_set("Device.LocalAgent.Controller.1.", [("Foo", "bar", False)], allow_partial=False)
    )
    _, _, resp_msg, _ = _handler(db).handle_request(payload)

    assert resp_msg.header.msg_type == usp_msg.Header.ERROR


# ---------------------------------------------------------------------------
# handle_request — OPERATE
# ---------------------------------------------------------------------------

def test_handle_request_operate_unknown_product_class():
    """OPERATE with unsupported product class returns Error."""
    db = mock.create_autospec(agent_db.Database)
    db.get.return_value = "Unknown_Product"

    payload = _make_record(_make_operate("Device.UnknownOp()"))
    _, _, resp_msg, _ = _handler(db).handle_request(payload)

    assert resp_msg.header.msg_type == usp_msg.Header.ERROR


def test_handle_request_operate_camera_invalid_command():
    """OPERATE on Camera with an invalid command returns Error."""
    db = mock.create_autospec(agent_db.Database)
    db.get.return_value = "RPi_Camera"

    payload = _make_record(_make_operate("Device.Services.HomeAutomation.1.Camera.1.BadOp()"))
    _, _, resp_msg, _ = request_handler.UspRequestHandler(
        AGENT_ENDPOINT, db, service_map={}
    ).handle_request(payload)

    assert resp_msg.header.msg_type == usp_msg.Header.ERROR


def test_handle_request_operate_camera_take_picture():
    """OPERATE TakePicture returns OperateResp with output args."""
    db = mock.create_autospec(agent_db.Database)
    db.get.return_value = "RPi_Camera"

    mock_camera = mock.Mock()
    mock_camera.take_picture.return_value = {"URL": "http://host/pic.png"}
    service_map = {"RPi_Camera": mock_camera}

    payload = _make_record(
        _make_operate("Device.Services.HomeAutomation.1.Camera.1.TakePicture()")
    )
    _, _, resp_msg, _ = request_handler.UspRequestHandler(
        AGENT_ENDPOINT, db, service_map=service_map
    ).handle_request(payload)

    assert resp_msg.header.msg_type == usp_msg.Header.OPERATE_RESP
    result = resp_msg.body.response.operate_resp.operation_results[0]
    assert result.req_output_args.output_args["URL"] == "http://host/pic.png"


# ---------------------------------------------------------------------------
# _get_affected_paths_for_set — direct unit tests
# ---------------------------------------------------------------------------

def test_get_affected_paths_for_set_instance_path_empty_raises():
    """Instance-addressed path with no matching instances raises SetValidationError."""
    db = mock.create_autospec(agent_db.Database)
    db.find_objects.return_value = []

    h = _handler(db)
    with pytest.raises(request_handler.SetValidationError):
        h._get_affected_paths_for_set("Device.LocalAgent.Controller.1.")


def test_get_affected_paths_for_set_static_path_empty_ok():
    """Static path with no instances returns empty list (no error)."""
    db = mock.create_autospec(agent_db.Database)
    db.find_objects.return_value = []

    h = _handler(db)
    result = h._get_affected_paths_for_set("Device.LocalAgent.")
    assert result == []


def test_get_affected_paths_for_set_wildcard_path_empty_ok():
    """Wildcard search path with no instances returns empty list (no error)."""
    db = mock.create_autospec(agent_db.Database)
    db.find_objects.return_value = []

    h = _handler(db)
    result = h._get_affected_paths_for_set("Device.LocalAgent.Controller.*.")
    assert result == []


def test_get_affected_paths_for_set_no_such_path_raises():
    """NoSuchPathError from find_objects is re-raised as SetValidationError."""
    db = mock.create_autospec(agent_db.Database)
    db.find_objects.side_effect = NoSuchPathError("bad")

    h = _handler(db)
    with pytest.raises(request_handler.SetValidationError):
        h._get_affected_paths_for_set("Device.Bad.")
