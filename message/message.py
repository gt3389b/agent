import re
import logging
import prometheus_client

from message import usp_msg_pb2 as usp_msg
from message import usp_record_pb2 as usp_record
from message import utils
import threading
import asyncio
from enum import Enum

# pylint: disable-msg=no-value-for-parameter
NUM_GET_MSGS_METRIC = \
    prometheus_client.Counter("number_of_usp_get_msgs",
                              "Number of USP Get Messages")
# pylint: disable-msg=no-value-for-parameter
NUM_SET_MSGS_METRIC = \
    prometheus_client.Counter("number_of_usp_set_msgs",
                              "Number of USP Set Messages")
# pylint: disable-msg=no-value-for-parameter
NUM_OPERATE_MSGS_METRIC = \
    prometheus_client.Counter("number_of_usp_operate_msgs",
                              "Number of USP Operate Messages")
# pylint: disable-msg=no-value-for-parameter
NUM_UNKNOWN_MSGS_METRIC = \
    prometheus_client.Counter("number_of_usp_unknown_msgs",
                              "Number of Unknown USP Messages")

class CoapSendingThread(threading.Thread):
    """A Thread that executes the AsyncIO Event Loop Processing to send a single CoAP message"""
    def __init__(self, my_addr, serialized_msg, to_addr, debug=False):
        """Initialize the CoAP Sending Thread"""
        threading.Thread.__init__(self, name="CoAP Sending Thread - " + to_addr)
        self._debug = debug
        self._to_addr = to_addr
        self._serialized_msg = serialized_msg
        self._logger = logging.getLogger(self.__class__.__name__)

        self._reply_to = my_addr.split("://")[1]
        self._logger.debug("Using [%s] as the value of the reply-to URI Query Option", self._reply_to)

    def run(self):
        """Send an outgoing CoAP message to the specified CoAP Address"""
        self._logger.debug("Creating a new AsyncIO Event Loop")
        my_event_loop = asyncio.new_event_loop()
        my_event_loop.set_debug(self._debug)
        asyncio.set_event_loop(my_event_loop)

        my_event_loop.run_until_complete(self._issue_request(self._to_addr, self._serialized_msg))
        my_event_loop.close()

    @asyncio.coroutine
    def _issue_request(self, to_addr, serialized_msg):
        """Send a ProtoBuf Serialized USP Message to the specified CoAP URL via the POST Method"""
        msg = aiocoap.Message(code=aiocoap.Code.POST, payload=serialized_msg)

        # Per CoAP this is application/octet-stream
        msg.opt.content_format = 42
        msg.set_request_uri(to_addr + "?reply-to=" + self._reply_to)

        self._logger.debug("Creating a CoAP Client Context")
        context = yield from aiocoap.Context.create_client_context()

        self._logger.debug("Sending a CoAP message to the following address: %s", to_addr)
        self._logger.debug("Payload being sent: [%s]", serialized_msg)
        try:
            resp = yield from context.request(msg).response
            self._logger.debug("CoAP Message Sent and [%s] Response received", resp.code)
        except aiocoap.error.RequestTimedOut:
            self._logger.warning("CoAP Message Sent, but no Response received due to a Timeout Error")

class Message(object):
    def __init__(self, serialized_pb=None, msg_type=None, to_id=None, from_id=None):
        self._msg = None

        if not serialized_pb:
            self._msg = usp_msg.Msg()
            self._msg.header.msg_id = utils.MessageIdHelper.get_message_id()
            self._msg_type = msg_type
            self._to_id = to_id
            self._from_id = from_id
            print("Set type to: ", self._msg_type)
        else:
            self.handle_request(serialized_pb)

    def send(self, timeout=5):
        #coap_send_thr = CoapSendingThread("coap://127.0.0.1:3683", record.SerializeToString(), "coap://127.0.0.1:15683/usp", logging)
        self.serialize()
        coap_send_thr = CoapSendingThread("coap://127.0.0.1:3683", self._msg, "coap://127.0.0.1:15683/usp", logging)
        coap_send_thr.start()
        coap_send_thr.join(timeout)

    def serialize(self):
        self.wrap_msg_in_record()

    def wrap_msg_in_record(self):
        """Wrap the USP Message in a USP Record"""
        record = usp_record.Record()

        record.version = "1.0"
        record.to_id = self._to_id
        record.from_id = self._from_id
        record.payload_security = usp_record.Record.PLAINTEXT
        record.no_session_context.payload = self._msg.SerializeToString()

        return record

    def handle_request(self, msg_payload):
        """Handle a Request/Response interaction"""
        req_record = self._handle_usp_record(msg_payload)

        try:
            # Validate the payload before processing it
            self._validate_usp_record_request(req_record)
            req_msg = self._handle_usp_msg(req_record)
            self._validate_usp_msg_request(req_msg)
            self._logger.debug("Received a [%s] Request",
                              req_msg.body.request.WhichOneof("req_type"))

            #TODO:  We need a binding here
            #resp_msg, resp_record = self._process_request(req_record, req_msg)
            #if self._debug:
            #    print("Outgoing Response:\n{}".format(resp_msg))
        except ProtocolValidationError as err:
            err_msg = "USP Message validation failed: {}".format(err)
            self._logger.error("%s", err_msg)
            raise ProtocolViolationError(err_msg)

        return req_msg, req_record, resp_msg, resp_record.SerializeToString()

    def _handle_usp_record(self, msg_payload):
        """Deserialize the USP Record in the Incoming Request"""
        req_as_record = usp_record.Record()

        # De-Serialize the payload into a USP Record
        req_as_record.ParseFromString(msg_payload)
        self._logger.debug("Incoming payload parsed as a USP Record via Protocol Buffers")

        if self._debug:
            debug_msg = "Incoming USP Record:\n{}".format(req_as_record)
            self._logger.debug("%s", debug_msg)

        return req_as_record

    def _validate_usp_record_request(self, req_as_record):
        """Validate the USP Record from the Incoming Request"""
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

        self._logger.debug("Incoming USP Record passed validation")

    def _handle_usp_msg(self, req_as_record):
        """Deserialize the USP Record in the Incoming Request"""
        req_as_msg = usp_msg.Msg()

        # De-Serialize the payload into a USP Record
        req_as_msg.ParseFromString(req_as_record.no_session_context.payload)
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

        if not req_as_msg.body.WhichOneof("msg_body") == "request":
            raise ProtocolValidationError("USP Message Body doesn't contain a Request element")

        self._logger.debug("Incoming USP Message passed validation")


class MessageType(Enum):
    SET = 1

class Set(Message):
    def __init__(self, to_id, from_id):
        super().__init__(msg_type=MessageType.SET, to_id=to_id, from_id=from_id)
        self._objects = []

        """Set the Header Information of the Notification"""
        self._msg.header.msg_type = usp_msg.Header.SET
        self.allow_partial = False

    def check_objects(self, objects):
        print(objects)
        for obj in objects:
            if not 'obj_path' in obj:
                raise Exception("No obj_path found in object")

    def add_objects(self, objects):
        self.check_objects(objects)
        self._objects = self._objects + objects

    def serialize(self):
        self._msg.body.request.set.allow_partial = self.allow_partial

        for obj in self._objects:
            update_obj = self._msg.body.request.set.update_objs.add()

            #update_obj.obj_path = "Device.LocalAgent.Controller.2."
            update_obj.obj_path = obj['obj_path']

            if ['param_settings'] in obj:
                for ps in obj['param_settings']:
                    update_param = update_obj.param_settings.add()
                    update_param.param = ps['param']
                    update_param.value = ps['value']
		    #update_param.param = "PeriodicNotifInterval"
		    #update_param.value = b'1'
            else:
                raise Exception("I think we need some params here")

        super().serialize()

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
        self._objects = self._objects + objects
