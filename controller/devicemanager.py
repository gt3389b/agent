import logging
import json
from controller.controller import Controller
#from message import Message
import message
from mtp.log import Log

class DeviceManager(object):
    def __init__(self, controller_name, mtp, debug=True):
        logging.basicConfig(level=logging.DEBUG)
        self._log = logging.getLogger("usp-devicemanager")
        if debug:
            self._log.setLevel(logging.DEBUG)
            print("debug")
        self._controller_name = controller_name
        self._log.info("INITED")
        self.mtp = mtp

    def add(self, deviceId, objects, allow_partial=False):
        """ https://usp.technology/specification/messages/#add """
        # Create new instances of a multi-instance object in the agents data model
        self._log.info("ADD "+deviceId)
        #self.mtp.add(deviceId, objects, allow_partial)

    def set(self, deviceId, objects, allow_partial=False):
        self._log.info("SET "+deviceId)
        m = message.Set(deviceId, self._controller_name, objects, allow_partial)
        print(m)
        #self.mtp.set(deviceId, objects, allow_partial)
    
    def delete(self, deviceId, obj_paths):
        self._log.info("DELETE "+deviceId+" "+obj_paths)
        self.mtp.delete(deviceId, obj_paths)

    def get(self, deviceId, obj_paths):
        self._log.info("GET "+deviceId+" "+obj_paths)
        self.mtp.get(deviceId, obj_paths)

    def get_instances(self):
        pass

    def get_supported_dm(self):
        pass

    def get_supported_dm(self):
        pass

def main():
    # instantiate a transport binding
    transport = Log()

    dev_manager = DeviceManager('controller-coap-johnb', transport)

    # set params
    deviceId = 'ops::00D09E-Test-T01'
    dev_manager.set(deviceId, [{'obj_path':'Device.LocalAgent.Controller.2.', 'param_settings': [{'param':'PeriodicNotifInterval', 'value':'1'}] }])

if __name__ == "__main__":
    main()
