import datetime
import logging

import asyncio
import threading

import aiocoap
import aiocoap.resource as resource
from message import usp_msg_pb2 as usp_msg
from message import usp_record_pb2 as usp_record
from controller import mdns
import json

from message.message import Set, Message

if hasattr(asyncio, 'ensure_future'):
    asyncio_ensure_future = asyncio.ensure_future
else:  # Deprecated since Python 3.4.4
    asyncio_ensure_future = getattr(asyncio, "async")


class UspResource(resource.Resource):
    """Example resource which supports the GET and PUT methods. It sends large
    responses, which trigger blockwise transfer."""

    def __init__(self):
        super().__init__()
        self.set_content(b"This is the resource's default content. It is padded "\
                b"with numbers to be large enough to trigger blockwise "\
                b"transfer.\n")

    def set_content(self, content):
        self.content = content
        #while len(self.content) <= 1024:
        #    self.content = self.content + b"0123456789\n"

    async def render_get(self, request):
        return aiocoap.Message(payload=self.content)

    async def render_put(self, request):
        print('PUT payload: %s' % request.payload)
        self.set_content(request.payload)
        return aiocoap.Message(code=aiocoap.CHANGED, payload=self.content)

    async def render_post(self, request):
        print('POST payload: %s' % request.payload)

        """Deserialize the USP Record in the Incoming Request"""
        req_as_record = usp_record.Record()
        req_as_msg = usp_msg.Msg()

        # De-Serialize the payload into a USP Record
        req_as_record.ParseFromString(request.payload)
        #logging.info("Incoming payload parsed as a USP Message via Protocol Buffers")

        req_as_msg.ParseFromString(req_as_record.no_session_context.payload)
        debug_msg = "Incoming USP Record:\n{}".format(req_as_record)
        logging.info("%s", debug_msg)
        debug_msg = "Incoming USP Message:\n{}".format(req_as_msg)
        logging.info("%s", debug_msg)

        self.set_content(request.payload)
        return aiocoap.Message(code=aiocoap.CHANGED, payload=self.content)

class CoapReceivingThread(threading.Thread):
    """A Thread that executes the AsyncIO Event Loop Processing to receive CoAP messages"""
    def __init__(self, resource_tree, listening_port, debug=False):
        """Initialize the CoAP Receiving Thread"""
        threading.Thread.__init__(self, name="CoAP Receiving Thread")
        self._debug = debug
        self._resource_tree = resource_tree
        self._listening_port = listening_port
        self._logger = logging.getLogger(self.__class__.__name__)

    def run(self):
        """Listen for incoming CoAP messages for the Resources provided"""
        # The server context contains the "usp" resource, which ties back to our MyCoapResource, so when
        #  the event loop receives a message against the "usp" resource the render_XXX method in the
        #  MyCoapResource instance is called, which will push the message onto the binding (if appropriate)
        #self._logger.debug("Creating a new AsyncIO Event Loop")
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

# logging setup

logging.basicConfig(level=logging.INFO)
logging.getLogger("coap-server").setLevel(logging.DEBUG)

def main():
    # Set up server
    resource_tree = resource.Site()

    resource_tree.add_resource(('.well-known', 'core'),
            resource.WKCResource(resource_tree.get_resources_as_linkheader))
    resource_tree.add_resource(('usp',), UspResource())
    
    # An Endpoint needs a Server Context for the Resource Tree
    logging.info("Starting the CoAP Receiving Thread")
    logging.info("Listening at URL: %s", 25683)
    _listen_thread = CoapReceivingThread(resource_tree, 25683, False)
    _listen_thread.start()

    # set params
    msg = Set('ops::00D09E-Test-T01', 'controller-coap-johnb')
    msg.add_objects(json.loads('[{"obj_path":"Device.LocalAgent.Controller.2.", "param_settings": [{"param":"PeriodicNotifInterval", "value":"1"}] }]'))
    msg.allow_partial = True
    msg.send()

    # announce presence
    #_mdns_announcer = mdns.Announcer("127.0.0.1", 5683, "/usp", "controller-coap-johnb")
    #_mdns_announcer.announce()

if __name__ == "__main__":
    main()
