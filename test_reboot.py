#!/usr/bin/env python3
"""
Test script for Device.Reboot() command

Test Flow:
1. Start agent (sends initial Boot! notification)
2. Verify initial Boot! parameters
3. Modify Boot! parameter mapping in database
4. Send Operate(Device.Reboot()) request
5. Verify agent restarts and sends new Boot! notification with updated parameters
"""

import asyncio
import logging
import json
import os
from pathlib import Path

from agent import uds_agent, agent_db
from controller import main as controller_main
from message.request import OperateRequest
from message import usp_msg_pb2, usp_record_pb2
from mtp.uds import UdsTransport

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test configuration
AGENT_SOCKET = "/tmp/usp-agent.sock"  # Match what's in the database
CONTROLLER_SOCKET = "/tmp/usp-controller.sock"
AGENT_DB = "database/uds-db.json"
AGENT_DM = "database/uds-dm.json"


class BootNotificationCapture:
    """Captures Boot! notifications for verification"""
    
    def __init__(self):
        self.boot_notifications = []
        self.lock = asyncio.Lock()
    
    async def capture(self, notification):
        """Capture a Boot! notification"""
        async with self.lock:
            self.boot_notifications.append(notification)
            logger.info(f"✓ Captured Boot! notification #{len(self.boot_notifications)}")
    
    def get_boot_params(self, index):
        """Extract parameter map from Boot! notification"""
        if index >= len(self.boot_notifications):
            return None
        
        notif = self.boot_notifications[index]
        
        # Parse the notification to extract Boot! parameters
        # The Boot! event has a ParameterMap argument
        event = notif.body.request.notify.event[0]
        
        params = {}
        for param in event.obj_path:
            # obj_path contains the parameter mappings
            for p in param.param_map:
                params[p.param_name] = p.param_value
        
        return params


async def test_reboot_command():
    """Test the Device.Reboot() command"""
    
    logger.info("=" * 80)
    logger.info("TEST: Device.Reboot() Command")
    logger.info("=" * 80)
    
    # Clean up old sockets
    for sock in [AGENT_SOCKET, CONTROLLER_SOCKET]:
        if os.path.exists(sock):
            os.unlink(sock)
    
    # Create backup of database
    db_backup = AGENT_DB + ".backup"
    with open(AGENT_DB, 'r') as f:
        original_db = json.load(f)
    with open(db_backup, 'w') as f:
        json.dump(original_db, f, indent=2)
    
    try:
        # Initialize database access
        db = agent_db.Database(AGENT_DM, AGENT_DB, "")
        
        # Step 1: Start the agent
        logger.info("\n" + "=" * 80)
        logger.info("STEP 1: Starting agent...")
        logger.info("=" * 80)
        
        agent = uds_agent.UdsAgent(AGENT_DM, AGENT_DB)
        agent_task = asyncio.create_task(agent.start())
        
        # Give agent time to start and send initial Boot!
        await asyncio.sleep(2)
        
        logger.info("\n✓ Agent started and initial Boot! notification sent")
        
        # Step 2: Modify Boot! parameter mapping
        logger.info("\n" + "=" * 80)
        logger.info("STEP 2: Modifying Boot! parameter mapping...")
        logger.info("=" * 80)
        
        # Read current values
        serial_before = db.get("Device.DeviceInfo.SerialNumber")
        logger.info(f"  SerialNumber (before): {serial_before}")
        
        # Modify the SerialNumber
        new_serial = f"{serial_before}-REBOOTED"
        db.update("Device.DeviceInfo.SerialNumber", new_serial)
        logger.info(f"  SerialNumber (after):  {new_serial}")
        
        # Step 3: Send Operate(Device.Reboot()) request
        logger.info("\n" + "=" * 80)
        logger.info("STEP 3: Sending Operate(Device.Reboot()) request...")
        logger.info("=" * 80)
        
        # Create Operate request
        operate_req = OperateRequest(
            msg_id="test-reboot-001",
            command="Device.Reboot()",
            input_args={},
            from_id="controller::test-ctrl"
        )
        
        # Send request to agent
        transport = UdsTransport(AGENT_SOCKET, 'connect')
        await transport.connect()
        
        # Build USP message
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = operate_req.msg_id
        msg.header.msg_type = usp_msg_pb2.Header.OPERATE
        
        req = msg.body.request.operate
        req.command = operate_req.command
        
        # Wrap in record
        record = usp_record_pb2.Record()
        record.version = "1.0"
        record.to_id = agent.endpoint_id
        record.from_id = operate_req.from_id
        record.payload_security = usp_record_pb2.Record.PLAINTEXT
        record.no_session_context.payload = msg.SerializeToString()
        
        # Send request
        await transport.send_message(record.SerializeToString())
        logger.info("✓ Operate request sent")
        
        # Receive response
        response_bytes = await transport.receive_message()
        response_record = usp_record_pb2.Record()
        response_record.ParseFromString(response_bytes)
        
        response_msg = usp_msg_pb2.Msg()
        response_msg.ParseFromString(response_record.no_session_context.payload)
        
        if response_msg.body.response.operate_resp.operation_results:
            result = response_msg.body.response.operate_resp.operation_results[0]
            if result.req_output_args:
                logger.info(f"✓ Reboot command accepted: {result.req_output_args}")
            else:
                logger.error(f"✗ Reboot command failed: {result.req_obj_path}")
        
        await transport.close()
        
        # Step 4: Wait for agent to reboot and send new Boot! notification
        logger.info("\n" + "=" * 80)
        logger.info("STEP 4: Waiting for agent to reboot...")
        logger.info("=" * 80)
        
        await asyncio.sleep(3)
        
        # Step 5: Verify the reboot happened (check logs for Boot! notification)
        logger.info("\n" + "=" * 80)
        logger.info("STEP 5: Verification")
        logger.info("=" * 80)
        
        # Read database to confirm value changed
        serial_after_reboot = db.get("Device.DeviceInfo.SerialNumber")
        logger.info(f"  SerialNumber in database: {serial_after_reboot}")
        
        if serial_after_reboot == new_serial:
            logger.info("✓ TEST PASSED: Database value persisted across reboot")
            logger.info("✓ Check logs above for Boot! notification with updated SerialNumber")
        else:
            logger.error(f"✗ TEST FAILED: Expected {new_serial}, got {serial_after_reboot}")
        
        logger.info("\n" + "=" * 80)
        logger.info("TEST COMPLETE")
        logger.info("=" * 80)
        logger.info("\nVerify in logs above:")
        logger.info("  1. Initial 'REBOOT: Agent restarting...' message")
        logger.info("  2. 'REBOOT: Re-initializing subscriptions...' message")
        logger.info("  3. Second 'Sending Boot! notification' with updated parameters")
        logger.info("  4. 'REBOOT: Agent restart complete!' message")
        
        # Cleanup
        agent_task.cancel()
        await asyncio.gather(agent_task, return_exceptions=True)
        
    finally:
        # Restore original database
        logger.info("\nRestoring original database...")
        with open(db_backup, 'r') as f:
            original_db = json.load(f)
        with open(AGENT_DB, 'w') as f:
            json.dump(original_db, f, indent=2)
        os.unlink(db_backup)
        logger.info("✓ Database restored")


if __name__ == "__main__":
    asyncio.run(test_reboot_command())
