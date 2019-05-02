import logging
import json
from controller.controller import Controller
import message
from controller.response_handler import UspResponseHandler
from mtp.coap_usp_binding import CoapUspBinding

class DeviceManager(object):
    def __init__(self, controller_name, mtp, debug=True):
        logging.basicConfig(level=logging.INFO)
        self._log = logging.getLogger("usp-devicemanager")
        if debug:
            self._log.setLevel(logging.DEBUG)
            print("debug")
        self._controller_name = controller_name
        self._log.info("INITED")
        self.mtp = mtp
        self.handler = UspResponseHandler(controller_name)

    def add(self, deviceId, objects, allow_partial=False):
        """ https://usp.technology/specification/messages/#add """
        # Create new instances of a multi-instance object in the agents data model
        raise Exception("Not supported")

    def set(self, deviceId, objects, allow_partial=False):
        self._log.info("SET "+deviceId)
        m = message.Set(deviceId, self._controller_name, objects, allow_partial)
        #return self.mtp.send_msg(m.SerializeToString(), deviceId)
        self.mtp.send_msg(m.SerializeToString(), 'coap://127.0.0.1:15683/usp')
        reply = self.mtp.get_msg(10)
        #print(reply.get_payload())
        self.handler.handle_request(reply.get_payload())
    
    def delete(self, deviceId, obj_paths):
        self._log.info("DELETE "+deviceId+" "+obj_paths)
        raise Exception("Not supported")

    def get(self, deviceId, param_paths):
        self._log.info("GET "+deviceId+" "+str(param_paths))
        m = message.Get(deviceId, self._controller_name, param_paths)
        self.mtp.send_msg(m.SerializeToString(), 'coap://127.0.0.1:15683/usp')
        reply = self.mtp.get_msg(10)
        self.handler.handle_request(reply.get_payload())

def main():
    # instantiate a transport binding
    transport = CoapUspBinding('127.0.0.1', 'controller-coap-johnb')
    transport.listen('coap://127.0.0.1:25683')

    dev_manager = DeviceManager('controller-coap-johnb', transport)

    # set params
    deviceId = 'ops::00D09E-Test-T01'
    dev_manager.get(deviceId, ['Device.LocalAgent.Controller.2.PeriodicNotifInterval'])
    dev_manager.set(deviceId, [{'obj_path':'Device.LocalAgent.Controller.2.', 'param_settings': [{'param':'PeriodicNotifInterval', 'value':'1'}] }])

if __name__ == "__main__":
    main()
