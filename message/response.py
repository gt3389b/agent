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

# File Name: response.py
#
# Description: Pythonic USP Response Message Wrappers
#
# Provides clean Python objects for USP response messages that hide
# protobuf complexity from agent business logic.
"""

from message import usp_msg_pb2
from message.request import UspMessage


class GetResponse(UspMessage):
    """USP Get Response - parameter values"""
    
    def __init__(self, results, **kwargs):
        """
        Initialize Get response
        
        Args:
            results (dict): {path: value} or {path: {'error': (code, msg)}}
            **kwargs: msg_id, from_id, to_id
        """
        super().__init__(**kwargs)
        self.results = results
    
    def to_protobuf(self):
        """Convert to protobuf GetResp message"""
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = self.msg_id
        msg.header.msg_type = usp_msg_pb2.Header.GET_RESP
        
        # Group results by requested path
        path_results = {}
        for full_path, value in self.results.items():
            # For simplicity, use full path as requested path
            if full_path not in path_results:
                path_results[full_path] = {}
            path_results[full_path][full_path] = value
        
        # Build response
        for req_path, params in path_results.items():
            path_result = msg.body.response.get_resp.req_path_results.add()
            path_result.requested_path = req_path
            
            resolved = path_result.resolved_path_results.add()
            resolved.resolved_path = req_path
            
            for param_path, value in params.items():
                if isinstance(value, dict) and 'error' in value:
                    # Error case
                    err_code, err_msg = value['error']
                    path_result.err_code = err_code
                    path_result.err_msg = err_msg
                else:
                    # Success case - extract parameter name
                    param_name = param_path.split('.')[-1]
                    resolved.result_params[param_name] = str(value)
        
        return msg
    
    @classmethod
    def from_protobuf(cls, pb_msg, from_id=None, to_id=None):
        """Create GetResponse from protobuf"""
        results = {}
        
        for path_result in pb_msg.body.response.get_resp.req_path_results:
            if path_result.err_code:
                # Error
                results[path_result.requested_path] = {
                    'error': (path_result.err_code, path_result.err_msg)
                }
            else:
                # Success - extract parameters
                for resolved in path_result.resolved_path_results:
                    for param_name, value in resolved.result_params.items():
                        param_path = resolved.resolved_path + param_name
                        results[param_path] = value
        
        return cls(
            msg_id=pb_msg.header.msg_id,
            from_id=from_id,
            to_id=to_id,
            results=results
        )
    
    def __repr__(self):
        return f"GetResponse(msg_id={self.msg_id}, results={len(self.results)} params)"


class SetResponse(UspMessage):
    """USP Set Response - update results"""
    
    def __init__(self, updated_params=None, failed_params=None, **kwargs):
        """
        Initialize Set response
        
        Args:
            updated_params (dict): {path: value} successfully updated
            failed_params (dict): {path: (err_code, err_msg)} failed updates
            **kwargs: msg_id, from_id, to_id
        """
        super().__init__(**kwargs)
        self.updated_params = updated_params or {}
        self.failed_params = failed_params or {}
    
    def to_protobuf(self):
        """Convert to protobuf SetResp message"""
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = self.msg_id
        msg.header.msg_type = usp_msg_pb2.Header.SET_RESP
        
        # Group by object path
        obj_results = {}
        
        # Add successful updates
        for param_path, value in self.updated_params.items():
            parts = param_path.rsplit('.', 1)
            if len(parts) == 2:
                obj_path, param_name = parts
                obj_path += '.'
                if obj_path not in obj_results:
                    obj_results[obj_path] = {'success': {}, 'failures': {}}
                obj_results[obj_path]['success'][param_name] = value
        
        # Add failures
        for param_path, (err_code, err_msg) in self.failed_params.items():
            parts = param_path.rsplit('.', 1)
            if len(parts) == 2:
                obj_path, param_name = parts
                obj_path += '.'
                if obj_path not in obj_results:
                    obj_results[obj_path] = {'success': {}, 'failures': {}}
                obj_results[obj_path]['failures'][param_name] = (err_code, err_msg)
        
        # Build response
        set_resp = msg.body.response.set_resp
        
        for obj_path, results in obj_results.items():
            updated_obj = set_resp.updated_obj_results.add()
            updated_obj.requested_path = obj_path
            
            if results['success']:
                # Success
                oper_success = updated_obj.oper_status.oper_success
                updated_inst = oper_success.updated_inst_results.add()
                updated_inst.affected_path = obj_path
                
                for param_name, value in results['success'].items():
                    updated_inst.updated_params[param_name] = str(value)
            
            if results['failures']:
                # Failures
                oper_failure = updated_obj.oper_status.oper_failure
                for param_name, (err_code, err_msg) in results['failures'].items():
                    param_err = oper_failure.updated_inst_failures.add()
                    param_err.affected_path = obj_path
                    param_err_item = param_err.param_errs.add()
                    param_err_item.param = param_name
                    param_err_item.err_code = err_code
                    param_err_item.err_msg = err_msg
        
        return msg
    
    @classmethod
    def from_protobuf(cls, pb_msg, from_id=None, to_id=None):
        """Create SetResponse from protobuf"""
        updated_params = {}
        failed_params = {}
        
        for updated_obj in pb_msg.body.response.set_resp.updated_obj_results:
            obj_path = updated_obj.requested_path
            
            if updated_obj.oper_status.HasField('oper_success'):
                # Extract successful updates
                for updated_inst in updated_obj.oper_status.oper_success.updated_inst_results:
                    for param_name, value in updated_inst.updated_params.items():
                        param_path = obj_path + param_name
                        updated_params[param_path] = value
            
            if updated_obj.oper_status.HasField('oper_failure'):
                # Extract failures
                for inst_failure in updated_obj.oper_status.oper_failure.updated_inst_failures:
                    for param_err in inst_failure.param_errs:
                        param_path = obj_path + param_err.param
                        failed_params[param_path] = (param_err.err_code, param_err.err_msg)
        
        return cls(
            msg_id=pb_msg.header.msg_id,
            from_id=from_id,
            to_id=to_id,
            updated_params=updated_params,
            failed_params=failed_params
        )
    
    def __repr__(self):
        return f"SetResponse(msg_id={self.msg_id}, updated={len(self.updated_params)}, failed={len(self.failed_params)})"


class OperateResponse(UspMessage):
    """USP Operate Response - command execution results"""
    
    def __init__(self, command, output_args=None, error=None, **kwargs):
        """
        Initialize Operate response
        
        Args:
            command (str): Command that was executed
            output_args (dict): Output arguments {name: value}
            error (tuple): (err_code, err_msg) if failed
            **kwargs: msg_id, from_id, to_id
        """
        super().__init__(**kwargs)
        self.command = command
        self.output_args = output_args or {}
        self.error = error  # (code, msg) or None
    
    def to_protobuf(self):
        """Convert to protobuf OperateResp message"""
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = self.msg_id
        msg.header.msg_type = usp_msg_pb2.Header.OPERATE_RESP
        
        operate_resp = msg.body.response.operate_resp
        
        op_result = operate_resp.operation_results.add()
        op_result.executed_command = self.command
        
        if self.error:
            # Command failed
            err_code, err_msg = self.error
            op_result.cmd_failure.err_code = err_code
            op_result.cmd_failure.err_msg = err_msg
        else:
            # Command succeeded
            for name, value in self.output_args.items():
                op_result.req_output_args.output_args[name] = str(value)
        
        return msg
    
    @classmethod
    def from_protobuf(cls, pb_msg, from_id=None, to_id=None):
        """Create OperateResponse from protobuf"""
        operate_resp = pb_msg.body.response.operate_resp
        
        if operate_resp.operation_results:
            op_result = operate_resp.operation_results[0]
            command = op_result.executed_command

            # cmd_failure is a oneof field at the op_result level
            oper_field = op_result.WhichOneof('operation_resp')
            if oper_field == 'cmd_failure':
                error = (op_result.cmd_failure.err_code, op_result.cmd_failure.err_msg)
                output_args = None
            elif oper_field == 'req_output_args':
                error = None
                output_args = dict(op_result.req_output_args.output_args)
            else:
                error = None
                output_args = {}
        else:
            command = ""
            output_args = {}
            error = None
        
        return cls(
            msg_id=pb_msg.header.msg_id,
            from_id=from_id,
            to_id=to_id,
            command=command,
            output_args=output_args,
            error=error
        )
    
    def __repr__(self):
        status = "failed" if self.error else "success"
        return f"OperateResponse(msg_id={self.msg_id}, command={self.command}, status={status})"


class GetSupportedDMResponse(UspMessage):
    """USP GetSupportedDM Response - data model structure"""
    
    def __init__(self, supported_objects=None, **kwargs):
        """
        Initialize GetSupportedDM response
        
        Args:
            supported_objects (dict): {
                'obj_path': {
                    'access': 'read-only'|'add-delete',
                    'is_multi_instance': bool,
                    'parameters': {
                        'param_name': {'access': 'read-only'|'read-write', 'type': 'string'},
                        ...
                    }
                }
            }
            **kwargs: msg_id, from_id, to_id
        """
        super().__init__(**kwargs)
        self.supported_objects = supported_objects or {}
    
    def to_protobuf(self):
        """Convert to protobuf GetSupportedDMResp message"""
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = self.msg_id
        msg.header.msg_type = usp_msg_pb2.Header.GET_SUPPORTED_DM_RESP
        
        # For now, assume single requested path "Device."
        result = msg.body.response.get_supported_dm_resp.req_obj_results.add()
        result.req_obj_path = "Device."
        
        for obj_path, obj_info in self.supported_objects.items():
            supported_obj = result.supported_objs.add()
            supported_obj.supported_obj_path = obj_path
            
            # Map access type
            access_str = obj_info.get('access', 'read-only')
            if access_str == 'add-delete':
                supported_obj.access = usp_msg_pb2.GetSupportedDMResp.OBJ_ADD_DELETE
            else:
                supported_obj.access = usp_msg_pb2.GetSupportedDMResp.OBJ_READ_ONLY
            
            supported_obj.is_multi_instance = obj_info.get('is_multi_instance', False)
            
            # Add parameters
            for param_name, param_info in obj_info.get('parameters', {}).items():
                param = supported_obj.supported_params.add()
                param.param_name = param_name
                
                param_access = param_info.get('access', 'read-only')
                if param_access == 'read-write':
                    param.access = usp_msg_pb2.GetSupportedDMResp.PARAM_READ_WRITE
                else:
                    param.access = usp_msg_pb2.GetSupportedDMResp.PARAM_READ_ONLY
                
                # Default to string type
                param.value_type = usp_msg_pb2.GetSupportedDMResp.PARAM_STRING
                param.value_change = usp_msg_pb2.GetSupportedDMResp.VALUE_CHANGE_ALLOWED
        
        return msg
    
    @classmethod
    def from_protobuf(cls, pb_msg, from_id=None, to_id=None):
        """Create GetSupportedDMResponse from protobuf"""
        supported_objects = {}
        
        for req_obj_result in pb_msg.body.response.get_supported_dm_resp.req_obj_results:
            for supported_obj in req_obj_result.supported_objs:
                obj_path = supported_obj.supported_obj_path
                
                # Map access type
                if supported_obj.access == usp_msg_pb2.GetSupportedDMResp.OBJ_ADD_DELETE:
                    access = 'add-delete'
                else:
                    access = 'read-only'
                
                # Extract parameters
                parameters = {}
                for param in supported_obj.supported_params:
                    if param.access == usp_msg_pb2.GetSupportedDMResp.PARAM_READ_WRITE:
                        param_access = 'read-write'
                    else:
                        param_access = 'read-only'
                    
                    parameters[param.param_name] = {
                        'access': param_access,
                        'type': 'string'  # Simplified
                    }
                
                supported_objects[obj_path] = {
                    'access': access,
                    'is_multi_instance': supported_obj.is_multi_instance,
                    'parameters': parameters
                }
        
        return cls(
            msg_id=pb_msg.header.msg_id,
            from_id=from_id,
            to_id=to_id,
            supported_objects=supported_objects
        )
    
    def __repr__(self):
        return f"GetSupportedDMResponse(msg_id={self.msg_id}, objects={len(self.supported_objects)})"


class GetInstancesResponse(UspMessage):
    """USP GetInstances Response - multi-instance object instances"""
    
    def __init__(self, instances=None, **kwargs):
        """
        Initialize GetInstances response
        
        Args:
            instances (dict): {
                'obj_path': ['Device.Controller.1.', 'Device.Controller.2.'],
                ...
            }
            **kwargs: msg_id, from_id, to_id
        """
        super().__init__(**kwargs)
        self.instances = instances or {}
    
    def to_protobuf(self):
        """Convert to protobuf GetInstancesResp message"""
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = self.msg_id
        msg.header.msg_type = usp_msg_pb2.Header.GET_INSTANCES_RESP
        
        for req_path, instance_paths in self.instances.items():
            req_path_result = msg.body.response.get_instances_resp.req_path_results.add()
            req_path_result.requested_path = req_path
            
            for instance_path in instance_paths:
                curr_inst = req_path_result.curr_insts.add()
                curr_inst.instantiated_obj_path = instance_path
        
        return msg
    
    @classmethod
    def from_protobuf(cls, pb_msg, from_id=None, to_id=None):
        """Create GetInstancesResponse from protobuf"""
        instances = {}
        
        for req_path_result in pb_msg.body.response.get_instances_resp.req_path_results:
            req_path = req_path_result.requested_path
            instance_paths = [inst.instantiated_obj_path for inst in req_path_result.curr_insts]
            instances[req_path] = instance_paths
        
        return cls(
            msg_id=pb_msg.header.msg_id,
            from_id=from_id,
            to_id=to_id,
            instances=instances
        )
    
    def __repr__(self):
        total_instances = sum(len(v) for v in self.instances.values())
        return f"GetInstancesResponse(msg_id={self.msg_id}, total_instances={total_instances})"


# Response type mapping for deserialization
RESPONSE_TYPES = {
    usp_msg_pb2.Header.GET_RESP: GetResponse,
    usp_msg_pb2.Header.SET_RESP: SetResponse,
    usp_msg_pb2.Header.OPERATE_RESP: OperateResponse,
    usp_msg_pb2.Header.GET_SUPPORTED_DM_RESP: GetSupportedDMResponse,
    usp_msg_pb2.Header.GET_INSTANCES_RESP: GetInstancesResponse,
}


class AddResponse(UspMessage):
    """USP Add Response - results of object creation"""

    def __init__(self, created_obj_results, **kwargs):
        """
        Args:
            created_obj_results (list): List of dicts:
                On success: {'requested_path', 'instantiated_path', 'unique_keys', 'param_errs'}
                On failure: {'requested_path', 'error': (err_code, err_msg)}
        """
        super().__init__(**kwargs)
        self.created_obj_results = created_obj_results

    def to_protobuf(self):
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = self.msg_id
        msg.header.msg_type = usp_msg_pb2.Header.ADD_RESP

        add_resp = msg.body.response.add_resp
        for result in self.created_obj_results:
            obj_result = add_resp.created_obj_results.add()
            obj_result.requested_path = result['requested_path']

            if 'error' in result:
                err_code, err_msg = result['error']
                obj_result.oper_status.oper_failure.err_code = err_code
                obj_result.oper_status.oper_failure.err_msg = err_msg
            else:
                success = obj_result.oper_status.oper_success
                success.instantiated_path = result.get('instantiated_path', '')
                for k, v in result.get('unique_keys', {}).items():
                    success.unique_keys[k] = v
                for pe in result.get('param_errs', []):
                    param_err = success.param_errs.add()
                    param_err.param = pe['param']
                    param_err.err_code = pe['err_code']
                    param_err.err_msg = pe['err_msg']

        return msg

    @classmethod
    def from_protobuf(cls, pb_msg, from_id=None, to_id=None):
        results = []
        for obj_result in pb_msg.body.response.add_resp.created_obj_results:
            if obj_result.oper_status.HasField('oper_failure'):
                f = obj_result.oper_status.oper_failure
                results.append({
                    'requested_path': obj_result.requested_path,
                    'error': (f.err_code, f.err_msg),
                })
            else:
                s = obj_result.oper_status.oper_success
                results.append({
                    'requested_path': obj_result.requested_path,
                    'instantiated_path': s.instantiated_path,
                    'unique_keys': dict(s.unique_keys),
                    'param_errs': [
                        {'param': e.param, 'err_code': e.err_code, 'err_msg': e.err_msg}
                        for e in s.param_errs
                    ],
                })
        return cls(msg_id=pb_msg.header.msg_id, from_id=from_id, to_id=to_id,
                   created_obj_results=results)

    def __repr__(self):
        return f"AddResponse(msg_id={self.msg_id}, results={len(self.created_obj_results)})"


class DeleteResponse(UspMessage):
    """USP Delete Response - results of object deletion"""

    def __init__(self, deleted_obj_results, **kwargs):
        """
        Args:
            deleted_obj_results (list): List of dicts:
                On success: {'requested_path', 'affected_paths': [...]}
                On failure: {'requested_path', 'error': (err_code, err_msg)}
        """
        super().__init__(**kwargs)
        self.deleted_obj_results = deleted_obj_results

    def to_protobuf(self):
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = self.msg_id
        msg.header.msg_type = usp_msg_pb2.Header.DELETE_RESP

        delete_resp = msg.body.response.delete_resp
        for result in self.deleted_obj_results:
            obj_result = delete_resp.deleted_obj_results.add()
            obj_result.requested_path = result['requested_path']

            if 'error' in result:
                err_code, err_msg = result['error']
                obj_result.oper_status.oper_failure.err_code = err_code
                obj_result.oper_status.oper_failure.err_msg = err_msg
            else:
                success = obj_result.oper_status.oper_success
                success.affected_paths.extend(result.get('affected_paths', []))

        return msg

    @classmethod
    def from_protobuf(cls, pb_msg, from_id=None, to_id=None):
        results = []
        for obj_result in pb_msg.body.response.delete_resp.deleted_obj_results:
            if obj_result.oper_status.HasField('oper_failure'):
                f = obj_result.oper_status.oper_failure
                results.append({
                    'requested_path': obj_result.requested_path,
                    'error': (f.err_code, f.err_msg),
                })
            else:
                s = obj_result.oper_status.oper_success
                results.append({
                    'requested_path': obj_result.requested_path,
                    'affected_paths': list(s.affected_paths),
                })
        return cls(msg_id=pb_msg.header.msg_id, from_id=from_id, to_id=to_id,
                   deleted_obj_results=results)

    def __repr__(self):
        return f"DeleteResponse(msg_id={self.msg_id}, results={len(self.deleted_obj_results)})"


class GetSupportedProtocolResponse(UspMessage):
    """USP GetSupportedProtocol Response - agent's supported versions"""

    def __init__(self, agent_supported_protocol_versions="1.3", **kwargs):
        super().__init__(**kwargs)
        self.agent_supported_protocol_versions = agent_supported_protocol_versions

    def to_protobuf(self):
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = self.msg_id
        msg.header.msg_type = usp_msg_pb2.Header.GET_SUPPORTED_PROTO_RESP
        msg.body.response.get_supported_protocol_resp.agent_supported_protocol_versions = \
            self.agent_supported_protocol_versions
        return msg

    @classmethod
    def from_protobuf(cls, pb_msg, from_id=None, to_id=None):
        resp = pb_msg.body.response.get_supported_protocol_resp
        return cls(
            msg_id=pb_msg.header.msg_id, from_id=from_id, to_id=to_id,
            agent_supported_protocol_versions=resp.agent_supported_protocol_versions,
        )

    def __repr__(self):
        return f"GetSupportedProtocolResponse(msg_id={self.msg_id}, versions={self.agent_supported_protocol_versions})"


def parse_response(pb_msg, from_id=None, to_id=None):
    """
    Parse protobuf message into appropriate response type

    Args:
        pb_msg (usp_msg_pb2.Msg): Protobuf message
        from_id (str): Override from_id
        to_id (str): Override to_id

    Returns:
        UspMessage: Appropriate response subclass
    """
    msg_type = pb_msg.header.msg_type
    type_map = {
        usp_msg_pb2.Header.GET_RESP: GetResponse,
        usp_msg_pb2.Header.SET_RESP: SetResponse,
        usp_msg_pb2.Header.OPERATE_RESP: OperateResponse,
        usp_msg_pb2.Header.GET_SUPPORTED_DM_RESP: GetSupportedDMResponse,
        usp_msg_pb2.Header.GET_INSTANCES_RESP: GetInstancesResponse,
        usp_msg_pb2.Header.ADD_RESP: AddResponse,
        usp_msg_pb2.Header.DELETE_RESP: DeleteResponse,
        usp_msg_pb2.Header.GET_SUPPORTED_PROTO_RESP: GetSupportedProtocolResponse,
    }
    response_class = type_map.get(msg_type)
    if response_class:
        return response_class.from_protobuf(pb_msg, from_id, to_id)
    else:
        raise ValueError(f"Unknown response type: {msg_type}")
