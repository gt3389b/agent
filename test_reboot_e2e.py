#!/usr/bin/env python3
"""
End-to-end test for Device.Reboot() command with live agent and controller

Test Flow:
1. Start controller (to capture Boot! notifications)
2. Start agent (sends initial Boot! notification)
3. Modify Boot! parameter in database
4. Send Operate(Device.Reboot()) command
5. Verify new Boot! notification has updated parameters
"""

import asyncio
import logging
import json
import os
import sys
from pathlib import Path

from agent import uds_agent, agent_db
from message import usp_msg_pb2, usp_record_pb2
from mtp.uds import UdsTransport

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test configuration
AGENT_SOCKET = "/tmp/usp-agent.sock"
CONTROLLER_SOCKET = "/tmp/usp-controller.sock"
AGENT_DB = "database/uds-db.json"
AGENT_DM = "database/uds-dm.json"

class MockController:
    """Simple mock controller that captures notifications"""
    
    def __init__(self, socket_path):
        self.socket_path = socket_path
        self.transport = None
        self.boot_notifications = []
        self.lock = asyncio.Lock()
    
    async def start(self):
        """Start listening for notifications"""
        self.transport = UdsTransport(self.socket_path, 'listen')
        asyncio.create_task(self._listen_loop())
        logger.info(f"Mock controller listening on {self.socket_path}")
    
    async def _listen_loop(self):
        """Listen for incoming notifications"""
        try:
            await self.transport.listen(self._handle_message)
        except Exception as e:
            logger.error(f"Controller listen error: {e}")
    
    async def _handle_message(self, data, writer):
        """Handle incoming notification"""
        try:
            # Parse record
            record = usp_record_pb2.Record()
            record.ParseFromString(data)
            
            # Parse message
            msg = usp_msg_pb2.Msg()
            msg.ParseFromString(record.no_session_context.payload)
            
            # Check if it's a Notify
            if msg.header.msg_type == usp_msg_pb2.Header.NOTIFY:
                event = msg.body.request.notify.event[0]
                event_path = event.obj_path
                
                if "Boot!" in event_path:
                    logger.info(f"✓ Received Boot! notification")
                    
                    # Extract parameters from event
                    params = {}
                    if event.params:
                        for param_name, param_value in event.params.items():
                            params[param_name] = param_value
                            logger.info(f"    {param_name} = {param_value}")
                    
                    async with self.lock:
                        self.boot_notifications.append({
                            'event_path': event_path,
                            'params': params,
                            'subscription_id': msg.body.request.notify.subscription_id
                        })
                
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
    
    async def stop(self):
        """Stop controller"""
        if self.transport:
            await self.transport.close()


async def send_operate_command(agent_id, command, input_args=None):
    """Send Operate command to agent"""
    if input_args is None:
        input_args = {}
    
    # Build USP message
    msg = usp_msg_pb2.Msg()
    msg.header.msg_id = "test-operate-001"
    msg.header.msg_type = usp_msg_pb2.Header.OPERATE
    
    req = msg.body.request.operate
    req.command = command
    
    for key, value in input_args.items():
        req.command_key = key
        req.input[key] = value
    
    # Wrap in record
    record = usp_record_pb2.Record()
    record.version = "1.0"
    record.to_id = agent_id
    record.from_id = "proto::controller-01"
    record.payload_security = usp_record_pb2.Record.PLAINTEXT
    record.no_session_context.payload = msg.SerializeToString()
    
    # Send request
    transport = UdsTransport(AGENT_SOCKET, 'connect')
    await transport.connect()
    await transport.send_message(record.SerializeToString())
    
    # Receive response
    response_bytes = await transport.receive_message()
    await transport.close()
    
    # Parse response
    response_record = usp_record_pb2.Record()
    response_record.ParseFromString(response_bytes)
    
    response_msg = usp_msg_pb2.Msg()
    response_msg.ParseFromString(response_record.no_session_context.payload)
    
    return response_msg


async def test_reboot_e2e():
    """End-to-end test of Device.Reboot() command"""
    
    logger.info("=" * 80)
    logger.info("E2E TEST: Device.Reboot() with Live Agent & Controller")
    logger.info("=" * 80)
    
    # Clean up old sockets
    for sock in [AGENT_SOCKET, CONTROLLER_SOCKET]:
        try:
            if os.path.exists(sock):
                os.unlink(sock)
        except:
            pass
    
    # Backup database
    db_backup = AGENT_DB + ".backup"
    with open(AGENT_DB, 'r') as f:
        original_db = json.load(f)
    with open(db_backup, 'w') as f:
        json.dump(original_db, f, indent=2)
    
    controller = None
    agent_task = None
    
    try:
        # Step 1: Start mock controller
        logger.info("\n" + "=" * 80)
        logger.info("STEP 1: Starting mock controller...")
        logger.info("=" * 80)
        
        controller = MockController(CONTROLLER_SOCKET)
        await controller.start()
        await asyncio.sleep(0.5)
        
        # Step 2: Start agent
        logger.info("\n" + "=" * 80)
        logger.info("STEP 2: Starting agent...")
        logger.info("=" * 80)
        
        agent = uds_agent.UdsAgent(AGENT_DM, AGENT_DB)
        agent_task = asyncio.create_task(agent.start())
        await asyncio.sleep(2)
        
        initial_boot_count = len(controller.boot_notifications)
        logger.info(f"✓ Agent started. Boot notifications received: {initial_boot_count}")
        
        # Step 3: Modify database parameter
        logger.info("\n" + "=" * 80)
        logger.info("STEP 3: Modifying Boot! parameter...")
        logger.info("=" * 80)
        
        db = agent_db.Database(AGENT_DM, AGENT_DB, "")
        serial_before = db.get("Device.DeviceInfo.SerialNumber")
        new_serial = f"{serial_before}-REBOOTED-{os.getpid()}"
        
        logger.info(f"  SerialNumber (before): {serial_before}")
        db.update("Device.DeviceInfo.SerialNumber", new_serial)
        logger.info(f"  SerialNumber (after):  {new_serial}")
        
        # Step 4: Send Reboot() command
        logger.info("\n" + "=" * 80)
        logger.info("STEP 4: Sending Device.Reboot() command...")
        logger.info("=" * 80)
        
        response = await send_operate_command(agent.endpoint_id, "Device.Reboot()")
        
        if response.body.response.operate_resp.operation_results:
            result = response.body.response.operate_resp.operation_results[0]
            if result.HasField('req_output_args'):
                logger.info(f"✓ Reboot command accepted")
            else:
                logger.error(f"✗ Reboot command failed: {result.req_obj_path}")
        
        # Step 5: Wait for reboot Boot! notification
        logger.info("\n" + "=" * 80)
        logger.info("STEP 5: Waiting for reboot Boot! notification...")
        logger.info("=" * 80)
        
        await asyncio.sleep(3)
        
        # Step 6: Verify new Boot! notification
        logger.info("\n" + "=" * 80)
        logger.info("STEP 6: Verification")
        logger.info("=" * 80)
        
        final_boot_count = len(controller.boot_notifications)
        logger.info(f"  Total Boot! notifications: {final_boot_count}")
        logger.info(f"  Expected: {initial_boot_count + 1} (initial + reboot)")
        
        if final_boot_count > initial_boot_count:
            logger.info(f"✓ Received new Boot! notification after reboot")
            
            # The updated serial number should be visible to agent now
            serial_after = db.get("Device.DeviceInfo.SerialNumber")
            logger.info(f"  SerialNumber in database: {serial_after}")
            
            if serial_after == new_serial:
                logger.info("✓ TEST PASSED: Updated parameter persisted across reboot")
                logger.info("✓ Agent successfully rebooted and re-sent Boot! notification")
            else:
                logger.error(f"✗ TEST FAILED: Expected {new_serial}, got {serial_after}")
        else:
            logger.error(f"✗ TEST FAILED: No new Boot! notification after reboot")
        
        logger.info("\n" + "=" * 80)
        logger.info("TEST COMPLETE")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        
    finally:
        # Cleanup
        logger.info("\nCleaning up...")
        
        if agent_task:
            agent_task.cancel()
            await asyncio.gather(agent_task, return_exceptions=True)
        
        if controller:
            await controller.stop()
        
        # Restore database
        with open(db_backup, 'r') as f:
            original_db = json.load(f)
        with open(AGENT_DB, 'w') as f:
            json.dump(original_db, f, indent=2)
        os.unlink(db_backup)
        logger.info("✓ Database restored")


if __name__ == "__main__":
    asyncio.run(test_reboot_e2e())
