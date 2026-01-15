#!/usr/bin/env python3
"""Test WebSocket MTP with actual USP message exchange"""

import logging
import asyncio
import websockets
from message import usp_msg_pb2, usp_record_pb2

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_websocket_usp():
    uri = 'ws://localhost:8080/usp'
    agent_id = 'test::websocket-agent-001'
    controller_id = 'proto::controller-01'
    
    logger.info(f'Connecting to {uri}...')
    
    async with websockets.connect(uri, subprotocols=['v1.usp']) as websocket:
        logger.info(f'✓ Connected! Subprotocol: {websocket.subprotocol}')
        
        # Create a simple Notify message (simulating Boot!)
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = 'test-boot-001'
        msg.header.msg_type = usp_msg_pb2.Header.NOTIFY
        
        notify_req = msg.body.request.notify
        notify_req.subscription_id = 'sub-boot-websocket-ctrl-1'
        notify_req.send_resp = True
        
        # Add Boot! event
        event = notify_req.event
        event.obj_path = 'Device.'
        event.event_name = 'Boot!'
        event.params['FirmwareUpdated'] = 'false'
        
        # Wrap in USP Record
        record = usp_record_pb2.Record()
        record.version = '1.3'
        record.to_id = controller_id
        record.from_id = agent_id
        record.no_session_context.payload = msg.SerializeToString()
        
        # Send the message
        data = record.SerializeToString()
        logger.info(f'Sending Boot! notification ({len(data)} bytes)...')
        await websocket.send(data)
        logger.info('✓ Boot! notification sent')
        
        # Wait for response
        logger.info('Waiting for NotifyResp...')
        try:
            response_data = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            logger.info(f'✓ Received response ({len(response_data)} bytes)')
            
            # Parse response
            resp_record = usp_record_pb2.Record()
            resp_record.ParseFromString(response_data)
            logger.info(f'  From: {resp_record.from_id}')
            logger.info(f'  To: {resp_record.to_id}')
            
            resp_msg = usp_msg_pb2.Msg()
            resp_msg.ParseFromString(resp_record.no_session_context.payload)
            logger.info(f'  Message Type: {resp_msg.header.msg_type}')
            logger.info(f'  Message ID: {resp_msg.header.msg_id}')
            
            if resp_msg.body.response.notify_resp:
                logger.info('✓ Got NotifyResp - WebSocket USP exchange successful!')
                logger.info(f'  Subscription ID: {resp_msg.body.response.notify_resp.subscription_id}')
        except asyncio.TimeoutError:
            logger.error('✗ Timeout waiting for response')
        
        await asyncio.sleep(1)

if __name__ == '__main__':
    asyncio.run(test_websocket_usp())
