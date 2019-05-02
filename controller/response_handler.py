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

# File Name: request_handler.py
#
# Description: USP Request Handler for Agents
#
# Functionality:
#   Class: USPResponseHandler(object)
#    - __init__(agent_endpoint_id, agent_database, service_map=None, debug=False)
#    - handle_request(msg_payload)
#   Class: ProtocolViolationError(Exception)
#   Class: ProtocolValidationError(Exception)
#
"""


import re
import logging

from controller import utils
from message import usp_msg_pb2 as usp_msg
from message import usp_record_pb2 as usp_record


class UspResponseHandler:
    """A USP Message Handler: to be used by a USP Agent"""
    def __init__(self, endpoint_id, debug=False):
        """Initialize the USP Request Handler"""
        self._debug = debug
        self._id = endpoint_id
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle_request(self, msg_payload):
        """Handle a Request/Response interaction"""
        req_record = self._handle_usp_record(msg_payload)

        try:
            # Validate the payload before processing it
            self._validate_usp_record_request(req_record)
            req_msg = self._handle_usp_msg(req_record)
            self._validate_usp_msg_request(req_msg)
            self._logger.info("Received a [%s] Response",
                              req_msg.body.request.WhichOneof("req_type"))

            resp_msg, resp_record = self._process_request(req_record, req_msg)
            if self._debug:
                print("Outgoing Response:\n{}".format(resp_msg))
        except ProtocolValidationError as err:
            err_msg = "USP Message validation failed: {}".format(err)
            self._logger.error("%s", err_msg)
            raise ProtocolViolationError(err_msg)

        return req_msg, req_record, resp_msg, resp_record.SerializeToString()

    def _handle_usp_record(self, msg_payload):
        """Deserialize the USP Record in the Incoming Response"""
        req_as_record = usp_record.Record()

        # De-Serialize the payload into a USP Record
        req_as_record.ParseFromString(msg_payload)
        self._logger.debug("Incoming payload parsed as a USP Record via Protocol Buffers")

        if self._debug:
            debug_msg = "Incoming USP Record:\n{}".format(req_as_record)
            self._logger.debug("%s", debug_msg)

        return req_as_record

    def _validate_usp_record_request(self, req_as_record):
        """Validate the USP Record from the Incoming Response"""
        if not req_as_record.IsInitialized():
            raise ProtocolValidationError("USP Record missing Required Fields")

        if not req_as_record.version:
            raise ProtocolValidationError("USP Record missing version")

        if not req_as_record.to_id:
            raise ProtocolValidationError("USP Record missing to_id")

        if req_as_record.to_id != self._id:
            raise ProtocolValidationError("USP Record has incorrect to_id")

        if not req_as_record.from_id:
            raise ProtocolValidationError("Header missing from_id")

        if not req_as_record.payload_security == usp_record.Record.PLAINTEXT:
            raise ProtocolValidationError("USP Record has unsupported Payload Security")

        if not req_as_record.WhichOneof("record_type") == "no_session_context":
            raise ProtocolValidationError("USP Record has an unsupported Record Type")

        self._logger.info("Incoming USP Record passed validation")

    def _handle_usp_msg(self, req_as_record):
        """Deserialize the USP Record in the Incoming Response"""
        req_as_msg = usp_msg.Msg()

        # De-Serialize the payload into a USP Record
        req_as_msg.ParseFromString(req_as_record.no_session_context.payload)
        print(req_as_msg)
        self._logger.debug("Incoming payload parsed as a USP Message via Protocol Buffers")

        if self._debug:
            debug_msg = "Incoming USP Message:\n{}".format(req_as_msg)
            self._logger.debug("%s", debug_msg)

        return req_as_msg

    def _validate_usp_msg_request(self, req_as_msg):
        """Validate the USP Message from the Incoming USP Record"""
        if not req_as_msg.IsInitialized():
            raise ProtocolValidationError("USP Message missing Required Fields")

        if not req_as_msg.header.msg_id:
            raise ProtocolValidationError("USP Message Header missing msg_id")

        if not req_as_msg.body.WhichOneof("msg_body") == "response":
            raise ProtocolValidationError("USP Message Body doesn't contain a Response element")

        self._logger.info("Incoming USP Message passed validation")

    def _process_request(self, req_as_record, req_as_msg):
        """Processing the incoming Message and return a Response"""
        to_id = req_as_record.from_id
        resp_record = usp_record.Record()
        err_msg = "Message Failure: Response body does not match Header msg_type"
        usp_err_msg = utils.UspErrMsg(req_as_msg.header.msg_id)
        resp_msg = usp_err_msg.generate_error(9000, err_msg)

        if req_as_msg.header.msg_type == usp_msg.Header.GET_RESP:
            self._logger.info("Get response")
            # Validate that the Request body matches the Header's msg_type
            #if req_as_msg.body.request.WhichOneof("req_type") == "get":
            #    NUM_GET_MSGS_METRIC.inc()
            #    resp_msg = self._process_get(req_as_msg)
        elif req_as_msg.header.msg_type == usp_msg.Header.SET_RESP:
            self._logger.info("Set response")
        #    # Validate that the Request body matches the Header's msg_type
        #    if req_as_msg.body.request.WhichOneof("req_type") == "set":
        #        NUM_SET_MSGS_METRIC.inc()
        #        resp_msg = self._process_set(req_as_msg)
        #elif req_as_msg.header.msg_type == usp_msg.Header.OPERATE:
        #    # Validate that the Request body matches the Header's msg_type
        #    if req_as_msg.body.request.WhichOneof("req_type") == "operate":
        #        NUM_OPERATE_MSGS_METRIC.inc()
        #        resp_msg = self._process_operation(req_as_msg)
        #else:
        #    err_msg = "Invalid USP Message: unknown command"
        #    resp_msg = usp_err_msg.generate_error(9000, err_msg)
        #    NUM_UNKNOWN_MSGS_METRIC.inc()

        # Wrap the USP Message response into a USP Record
        resp_record.version = "1.0"
        resp_record.to_id = to_id
        resp_record.from_id = self._id
        resp_record.payload_security = usp_record.Record.PLAINTEXT
        resp_record.no_session_context.payload = resp_msg.SerializeToString()

        return resp_msg, resp_record

class ProtocolViolationError(Exception):
    """A USP Protocol Violation Error"""
    pass


class ProtocolValidationError(Exception):
    """A USP Protocol Violation Error"""
    pass


class SetValidationError(Exception):
    """A USP Validation Exception for the Set USP Message"""
    def __init__(self, err_code, err_msg):
        """Initialize the Set Validation Error"""
        self._err_msg = err_msg
        self._err_code = err_code
        Exception.__init__(self, "[{}] - {}".format(err_code, err_msg))

    def get_error_code(self):
        """Retrieve the Error Code"""
        return self._err_code

    def get_error_message(self):
        """Retrieve the Error Message"""
        return self._err_msg
