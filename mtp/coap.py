import re
import logging

import aiocoap
import aiocoap.resource as resource

from message import usp_msg_pb2 as usp_msg
from message import usp_record_pb2 as usp_record
from message import utils
import threading
import queue
import asyncio

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

class CoapResponseThread(threading.Thread):
    """A Thread that executes the AsyncIO Event Loop Processing to receive CoAP messages"""
    def __init__(self, q, resource_tree, listening_port, debug=False):
        """Initialize the CoAP Response Thread"""
        threading.Thread.__init__(self, name="CoAP Response Thread")
        self._debug = debug
        self._resource_tree = resource_tree
        self._listening_port = listening_port
        self._logger = logging.getLogger(self.__class__.__name__)
        self.q = q

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

        try:
            my_event_loop.run_until_complete(self._issue_request(self._to_addr, self._serialized_msg))
        except Exception as e:
            print("CoapTransport:  CoapSendingThread exception: "+str(e))
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

        self._logger.info("Sending a CoAP message to the following address: %s", to_addr)
        self._logger.debug("Payload being sent: [%s]", serialized_msg)
        try:
            resp = yield from context.request(msg).response
            self._logger.info("CoAP Message Sent and [%s] Response received", resp.code)
        except aiocoap.error.RequestTimedOut:
            self._logger.warning("CoAP Message Sent, but no Response received due to a Timeout Error")

class CoapTransport(object):
    def __init__(self, serialized_pb=None, msg_type=None, to_id=None, from_id=None):
        logging.basicConfig(level=logging.INFO)
        self._log = logging.getLogger("usp-coap-transport")

        # Set up server
        resource_tree = resource.Site()

        resource_tree.add_resource(('.well-known', 'core'),
                resource.WKCResource(resource_tree.get_resources_as_linkheader))
        resource_tree.add_resource(('usp',), UspResource())
        
        # An Endpoint needs a Server Context for the Resource Tree
        logging.info("Starting the CoAP Response Thread at 25683")
        _listen_thread = CoapResponseThread(resource_tree, 25683, False)
        _listen_thread.start()

    def send(self, controller_name, m, timeout=5):
        q = queue.Queue()

        #coap_send_thr = CoapSendingThread("coap://127.0.0.1:3683", record.SerializeToString(), "coap://127.0.0.1:15683/usp", logging)
        self._log.info("SENDING")
        coap_send_thr = CoapSendingThread("coap://127.0.0.1:3683", m.SerializeToString(), "coap://127.0.0.1:15683/usp", self._log)
        coap_send_thr.start()
        coap_send_thr.join(timeout)
