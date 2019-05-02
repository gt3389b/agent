import logging

from message import usp_msg_pb2 as usp_msg
from message import usp_record_pb2 as usp_record
from message import utils
from enum import Enum

class Message(object):
    def __init__(self, to_id, from_id):
        self._msg = None
        self._record = None

        self._msg = usp_msg.Msg()
        self._msg.header.msg_id = utils.MessageIdHelper.get_message_id()
        self._to_id = to_id
        self._from_id = from_id

    def generate_record(self):
        """Wrap the USP Message in a USP Record"""
        self._record = usp_record.Record()

        self._record.version = "1.0"
        self._record.to_id = self._to_id
        self._record.from_id = self._from_id
        self._record.payload_security = usp_record.Record.PLAINTEXT
        self._record.no_session_context.payload = self._msg.SerializeToString()

    def SerializeToString(self):
        return self._record.SerializeToString()

    def __str__(self):
        return str(self._record) + str(self._msg)

class Get(Message):
    def __init__(self, to_id, from_id, param_paths):
        super().__init__(to_id=to_id, from_id=from_id)
        self.serialize(param_paths)

    def serialize(self, param_paths):
        self._msg.header.msg_type = usp_msg.Header.GET
        self._msg.body.request.get.param_paths.extend(param_paths)
        super().generate_record()

class Set(Message):
    def __init__(self, to_id, from_id, objects, allow_partial=False):
        super().__init__(to_id=to_id, from_id=from_id)
        self.serialize(objects, allow_partial)

    def check_objects(self, objects):
        print(objects)
        for obj in objects:
            if not 'obj_path' in obj:
                raise Exception("No obj_path found in object")

            if not 'param_settings' in obj:
                raise Exception("No param_settings found in object")

    def serialize(self, objects, allow_partial):
        self._msg.header.msg_type = usp_msg.Header.SET

        self._msg.body.request.set.allow_partial = allow_partial

        for obj in objects:
            update_obj = self._msg.body.request.set.update_objs.add()

            #update_obj.obj_path = "Device.LocalAgent.Controller.2."
            if 'obj_path' in obj:
                update_obj.obj_path = obj['obj_path']
            else:
                raise Exception("We need a obj_path here")

            if 'param_settings' in obj:
                for ps in obj['param_settings']:
                    update_param = update_obj.param_settings.add()
                    update_param.param = ps['param']
                    update_param.value = ps['value']
            else:
                raise Exception("I think we need some params here")

        super().generate_record()

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

def parse(message):
    print(message)
