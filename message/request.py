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

# File Name: request.py
#
# Description: Pythonic USP Request Message Wrappers
#
# Provides clean Python objects for USP request messages that hide
# protobuf complexity from agent business logic.
"""

import random
from message import usp_msg_pb2


def generate_msg_id():
    """Generate a random message ID"""
    return str(random.randint(1000, 9999))


class UspMessage:
    """Base class for all USP messages"""
    
    def __init__(self, msg_id=None, from_id=None, to_id=None):
        """
        Initialize USP message
        
        Args:
            msg_id (str): Message ID (auto-generated if None)
            from_id (str): Sender endpoint ID
            to_id (str): Recipient endpoint ID
        """
        self.msg_id = msg_id or generate_msg_id()
        self.from_id = from_id
        self.to_id = to_id
    
    def to_protobuf(self):
        """
        Convert to protobuf Msg
        
        Returns:
            usp_msg_pb2.Msg: Protobuf message
        """
        raise NotImplementedError("Subclass must implement to_protobuf()")
    
    @classmethod
    def from_protobuf(cls, pb_msg, from_id=None, to_id=None):
        """
        Create from protobuf Msg
        
        Args:
            pb_msg (usp_msg_pb2.Msg): Protobuf message
            from_id (str): Override from_id (optional)
            to_id (str): Override to_id (optional)
            
        Returns:
            UspMessage: Python message object
        """
        raise NotImplementedError("Subclass must implement from_protobuf()")


class GetRequest(UspMessage):
    """USP Get Request - query parameter values"""
    
    def __init__(self, paths, **kwargs):
        """
        Initialize Get request
        
        Args:
            paths (list): List of parameter paths to query
            **kwargs: msg_id, from_id, to_id
        """
        super().__init__(**kwargs)
        self.paths = paths if isinstance(paths, list) else [paths]
    
    def to_protobuf(self):
        """Convert to protobuf Get message"""
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = self.msg_id
        msg.header.msg_type = usp_msg_pb2.Header.GET
        msg.body.request.get.param_paths.extend(self.paths)
        return msg
    
    @classmethod
    def from_protobuf(cls, pb_msg, from_id=None, to_id=None):
        """Create GetRequest from protobuf"""
        return cls(
            msg_id=pb_msg.header.msg_id,
            from_id=from_id,
            to_id=to_id,
            paths=list(pb_msg.body.request.get.param_paths)
        )
    
    def __repr__(self):
        return f"GetRequest(msg_id={self.msg_id}, paths={self.paths})"


class SetRequest(UspMessage):
    """USP Set Request - update parameter values"""
    
    def __init__(self, parameters, allow_partial=True, **kwargs):
        """
        Initialize Set request
        
        Args:
            parameters (dict): {path: value} to set
            allow_partial (bool): Allow partial updates on error
            **kwargs: msg_id, from_id, to_id
        """
        super().__init__(**kwargs)
        self.parameters = parameters
        self.allow_partial = allow_partial
    
    def to_protobuf(self):
        """Convert to protobuf Set message"""
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = self.msg_id
        msg.header.msg_type = usp_msg_pb2.Header.SET
        
        set_req = msg.body.request.set
        set_req.allow_partial = self.allow_partial
        
        # Group parameters by object path
        obj_paths = {}
        for path, value in self.parameters.items():
            # Extract object path (everything before last dot)
            parts = path.rsplit('.', 1)
            if len(parts) == 2:
                obj_path, param_name = parts
                obj_path += '.'
                if obj_path not in obj_paths:
                    obj_paths[obj_path] = {}
                obj_paths[obj_path][param_name] = value
        
        # Build update objects
        for obj_path, params in obj_paths.items():
            update_obj = set_req.update_objs.add()
            update_obj.obj_path = obj_path
            for param_name, value in params.items():
                update_obj.param_settings.add(
                    param=param_name,
                    value=str(value),
                    required=True
                )
        
        return msg
    
    @classmethod
    def from_protobuf(cls, pb_msg, from_id=None, to_id=None):
        """Create SetRequest from protobuf"""
        parameters = {}
        set_req = pb_msg.body.request.set
        
        for update_obj in set_req.update_objs:
            obj_path = update_obj.obj_path
            for param_setting in update_obj.param_settings:
                param_path = obj_path + param_setting.param
                parameters[param_path] = param_setting.value
        
        return cls(
            msg_id=pb_msg.header.msg_id,
            from_id=from_id,
            to_id=to_id,
            parameters=parameters,
            allow_partial=set_req.allow_partial
        )
    
    def __repr__(self):
        return f"SetRequest(msg_id={self.msg_id}, parameters={self.parameters})"


class OperateRequest(UspMessage):
    """USP Operate Request - invoke command/operation"""
    
    def __init__(self, command, input_args=None, **kwargs):
        """
        Initialize Operate request
        
        Args:
            command (str): Command path (e.g., "Device.Reboot()")
            input_args (dict): Input arguments {name: value}
            **kwargs: msg_id, from_id, to_id
        """
        super().__init__(**kwargs)
        self.command = command
        self.input_args = input_args or {}
    
    def to_protobuf(self):
        """Convert to protobuf Operate message"""
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = self.msg_id
        msg.header.msg_type = usp_msg_pb2.Header.OPERATE
        
        operate = msg.body.request.operate
        operate.command = self.command
        
        for name, value in self.input_args.items():
            arg = operate.input_args.add()
            arg[name] = str(value)
        
        return msg
    
    @classmethod
    def from_protobuf(cls, pb_msg, from_id=None, to_id=None):
        """Create OperateRequest from protobuf"""
        operate = pb_msg.body.request.operate
        
        input_args = {}
        for arg_map in operate.input_args:
            for name, value in arg_map.items():
                input_args[name] = value
        
        return cls(
            msg_id=pb_msg.header.msg_id,
            from_id=from_id,
            to_id=to_id,
            command=operate.command,
            input_args=input_args
        )
    
    def __repr__(self):
        return f"OperateRequest(msg_id={self.msg_id}, command={self.command})"


class GetSupportedDMRequest(UspMessage):
    """USP GetSupportedDM Request - query data model structure"""
    
    def __init__(self, obj_paths, first_level_only=False, 
                 return_commands=False, return_events=False, return_params=True,
                 **kwargs):
        """
        Initialize GetSupportedDM request
        
        Args:
            obj_paths (list): Object paths to query
            first_level_only (bool): Return only immediate children
            return_commands (bool): Include command information
            return_events (bool): Include event information
            return_params (bool): Include parameter information
            **kwargs: msg_id, from_id, to_id
        """
        super().__init__(**kwargs)
        self.obj_paths = obj_paths if isinstance(obj_paths, list) else [obj_paths]
        self.first_level_only = first_level_only
        self.return_commands = return_commands
        self.return_events = return_events
        self.return_params = return_params
    
    def to_protobuf(self):
        """Convert to protobuf GetSupportedDM message"""
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = self.msg_id
        msg.header.msg_type = usp_msg_pb2.Header.GET_SUPPORTED_DM
        
        gsdm = msg.body.request.get_supported_dm
        gsdm.obj_paths.extend(self.obj_paths)
        gsdm.first_level_only = self.first_level_only
        gsdm.return_commands = self.return_commands
        gsdm.return_events = self.return_events
        gsdm.return_params = self.return_params
        
        return msg
    
    @classmethod
    def from_protobuf(cls, pb_msg, from_id=None, to_id=None):
        """Create GetSupportedDMRequest from protobuf"""
        gsdm = pb_msg.body.request.get_supported_dm
        
        return cls(
            msg_id=pb_msg.header.msg_id,
            from_id=from_id,
            to_id=to_id,
            obj_paths=list(gsdm.obj_paths),
            first_level_only=gsdm.first_level_only,
            return_commands=gsdm.return_commands,
            return_events=gsdm.return_events,
            return_params=gsdm.return_params
        )
    
    def __repr__(self):
        return f"GetSupportedDMRequest(msg_id={self.msg_id}, obj_paths={self.obj_paths})"


class GetInstancesRequest(UspMessage):
    """USP GetInstances Request - query multi-instance object instances"""
    
    def __init__(self, obj_paths, first_level_only=False, **kwargs):
        """
        Initialize GetInstances request
        
        Args:
            obj_paths (list): Object paths to query instances for
            first_level_only (bool): Return only immediate children
            **kwargs: msg_id, from_id, to_id
        """
        super().__init__(**kwargs)
        self.obj_paths = obj_paths if isinstance(obj_paths, list) else [obj_paths]
        self.first_level_only = first_level_only
    
    def to_protobuf(self):
        """Convert to protobuf GetInstances message"""
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = self.msg_id
        msg.header.msg_type = usp_msg_pb2.Header.GET_INSTANCES
        
        gi = msg.body.request.get_instances
        gi.obj_paths.extend(self.obj_paths)
        gi.first_level_only = self.first_level_only
        
        return msg
    
    @classmethod
    def from_protobuf(cls, pb_msg, from_id=None, to_id=None):
        """Create GetInstancesRequest from protobuf"""
        gi = pb_msg.body.request.get_instances
        
        return cls(
            msg_id=pb_msg.header.msg_id,
            from_id=from_id,
            to_id=to_id,
            obj_paths=list(gi.obj_paths),
            first_level_only=gi.first_level_only
        )
    
    def __repr__(self):
        return f"GetInstancesRequest(msg_id={self.msg_id}, obj_paths={self.obj_paths})"


# Request type mapping for deserialization
REQUEST_TYPES = {
    usp_msg_pb2.Header.GET: GetRequest,
    usp_msg_pb2.Header.SET: SetRequest,
    usp_msg_pb2.Header.OPERATE: OperateRequest,
    usp_msg_pb2.Header.GET_SUPPORTED_DM: GetSupportedDMRequest,
    usp_msg_pb2.Header.GET_INSTANCES: GetInstancesRequest,
}


def parse_request(pb_msg, from_id=None, to_id=None):
    """
    Parse protobuf message into appropriate request type
    
    Args:
        pb_msg (usp_msg_pb2.Msg): Protobuf message
        from_id (str): Override from_id
        to_id (str): Override to_id
        
    Returns:
        UspMessage: Appropriate request subclass
    """
    msg_type = pb_msg.header.msg_type
    request_class = REQUEST_TYPES.get(msg_type)
    
    if request_class:
        return request_class.from_protobuf(pb_msg, from_id, to_id)
    else:
        raise ValueError(f"Unknown request type: {msg_type}")
