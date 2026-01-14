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

# File Name: coap_controller.py
#
# Description: CoAP Controller implementation
#
"""

import logging
import json
import asyncio
import threading

import aiocoap
import aiocoap.resource as resource
from message import usp_msg_pb2 as usp_msg
from message import usp_record_pb2 as usp_record
from message.message import Set

logger = logging.getLogger(__name__)

if hasattr(asyncio, 'ensure_future'):
    asyncio_ensure_future = asyncio.ensure_future
else:
    asyncio_ensure_future = getattr(asyncio, "async")


class UspResource(resource.Resource):
    """CoAP resource for handling USP messages"""

    def __init__(self):
        super().__init__()
        self.set_content(b"This is the resource's default content.")

    def set_content(self, content):
        self.content = content

    async def render_get(self, request):
        return aiocoap.Message(payload=self.content)

    async def render_put(self, request):
        print('PUT payload: %s' % request.payload)
        self.set_content(request.payload)
        return aiocoap.Message(code=aiocoap.CHANGED, payload=self.content)

    async def render_post(self, request):
        print('POST payload: %s' % request.payload)

        # Deserialize the USP Record
        req_as_record = usp_record.Record()
        req_as_msg = usp_msg.Msg()

        req_as_record.ParseFromString(request.payload)
        req_as_msg.ParseFromString(req_as_record.no_session_context.payload)
        
        debug_msg = "Incoming USP Record:\n{}".format(req_as_record)
        logger.info("%s", debug_msg)
        debug_msg = "Incoming USP Message:\n{}".format(req_as_msg)
        logger.info("%s", debug_msg)

        self.set_content(request.payload)
        return aiocoap.Message(code=aiocoap.CHANGED, payload=self.content)


class CoapReceivingThread(threading.Thread):
    """Thread that executes the AsyncIO Event Loop for receiving CoAP messages"""
    
    def __init__(self, resource_tree, listening_port, debug=False):
        threading.Thread.__init__(self, name="CoAP Receiving Thread")
        self._debug = debug
        self._resource_tree = resource_tree
        self._listening_port = listening_port
        self._logger = logging.getLogger(self.__class__.__name__)

    def run(self):
        """Listen for incoming CoAP messages"""
        my_event_loop = asyncio.new_event_loop()
        my_event_loop.set_debug(self._debug)
        asyncio.set_event_loop(my_event_loop)
        self._logger.info("Creating a Controller CoAP Server Context for the Resource Tree")
        asyncio_ensure_future(
            aiocoap.Context.create_server_context(self._resource_tree, bind=("::", self._listening_port)))

        self._logger.info("Starting the AsyncIO CoAP Event Loop")
        my_event_loop.run_forever()
        self._logger.info("The AsyncIO CoAP Event Loop has Terminated")
        my_event_loop.close()


class CoapController:
    """CoAP Controller for USP communication"""
    
    def __init__(self, config_file):
        """
        Initialize CoAP Controller
        
        Args:
            config_file (str): Path to configuration file
        """
        # Load configuration
        with open(config_file, 'r') as f:
            self._config = json.load(f)
        
        self._endpoint_id = self._config['endpoint_id']
        self._port = self._config['coap']['port']
        self._resource_name = self._config['coap']['resource']
        
        logger.info("=" * 60)
        logger.info("CoAP Controller Initialized")
        logger.info(f"  Endpoint ID: {self._endpoint_id}")
        logger.info(f"  CoAP Port: {self._port}")
        logger.info(f"  Resource: {self._resource_name}")
        logger.info("=" * 60)
    
    def start(self):
        """Start the CoAP controller"""
        # Set up server
        resource_tree = resource.Site()
        resource_tree.add_resource(('.well-known', 'core'),
                resource.WKCResource(resource_tree.get_resources_as_linkheader))
        resource_tree.add_resource((self._resource_name,), UspResource())
        
        # Start listening thread
        logger.info("Starting the CoAP Receiving Thread")
        logger.info(f"Listening at port: {self._port}")
        _listen_thread = CoapReceivingThread(resource_tree, self._port, False)
        _listen_thread.start()

        # Set params (example usage)
        msg = Set('ops::00D09E-Test-T01', self._endpoint_id)
        msg.add_objects(json.loads('[{"obj_path":"Device.LocalAgent.Controller.2.", "param_settings": [{"param":"PeriodicNotifInterval", "value":"1"}] }]'))
        msg.allow_partial = True
        msg.send()
        
        # Keep thread alive
        try:
            _listen_thread.join()
        except KeyboardInterrupt:
            logger.info("\nShutting down controller...")
