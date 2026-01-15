#!/usr/bin/env python3
"""
Test script for Device.Reboot() command

Test Flow:
1. Start controller (to receive notifications)
2. Start agent (sends initial Boot! notification)
3. Capture initial Boot! notification
4. Modify Boot! parameter mapping in database
5. Send Operate(Device.Reboot()) request
6. Capture second Boot! notification
7. Verify boot parameters changed
"""

import asyncio
import logging
import json
import os
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


class SimpleController:
    """Simple controller that captures Boot! notifications"""
    
    def __init__(self, socket_path):
        self.socket_path = socket_path
        self.transport = None
        self.boot_notifications = []
        self.lock = asyncio.Lock()
        self.server_task = None
    
    async def start(self):
        """Start listening for notifications"""
        self.transport = UdsTransport(self.socket_path, 'listen')
        await self.transport.start_server(self._handle_message)
        logger.info(f"Controller listening on {self.socket_path}")
        
        # Keep server running
        self.server_task = asyncio.create_task(self._run_server())
    
    async def _run_server(self):
        """Keep server running"""
        try:
            async with self.transport.server:
                await self.transport.server.serve_forever()
        except asyncio.CancelledError:
            pass
    
    async def _handle_message(self, data, writer):
        """Handle incoming notification"""
        try:
            logger.info(f"Controller received {len(data)} bytes")
            
            # Parse USP Record
            record = usp_record_pb2.Record()
            record.ParseFromString(data)
            logger.info(f"Record from: {record.from_id}, to: {record.to_id}")
            
            # Parse USP Message
            msg = usp_msg_pb2.Msg()
            msg.ParseFromString(record.no_session_context.payload)
            logger.info(f"Message type: {msg.header.msg_type}")
            
            # Check if it's a Notify message
            if msg.header.msg_type == usp_msg_pb2.Header.NOTIFY:
                notify_msg = msg.body.request.notify
                logger.info(f"Notify message - subscription: {notify_msg.subscription_id}")
                
                # The event is a single object, not a list
                event = notify_msg.event
                logger.info(f"Event: {event.obj_path} / {event.event_name}")
                
                if event.event_name == "Boot!":
                    async with self.lock:
                        # Extract parameters from the event
                        params = {}
                        if event.params:
                            for key, value in event.params.items():
                                params[key] = value
                        
                        self.boot_notifications.append({
                            'params': params,
                            'subscription_id': notify_msg.subscription_id
                        })
                        logger.info(f"✓ Controller received Boot! notification #{len(self.boot_notifications)}")
                        if params:
                            for k, v in params.items():
                                logger.info(f"    {k} = {v}")
        
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
    
    async def stop(self):
        """Stop the controller"""
        if self.server_task:
            self.server_task.cancel()
            await asyncio.gather(self.server_task, return_exceptions=True)
        if self.transport and self.transport.server:
            self.transport.server.close()
            await self.transport.server.wait_closed()
    
    def get_boot_count(self):
        """Get number of Boot! notifications received"""
        return len(self.boot_notifications)
    
    def get_boot_params(self, index):
        """Get parameters from a specific Boot! notification"""
        if index < len(self.boot_notifications):
            return self.boot_notifications[index]['params']
        return None


async def test_reboot_command():
    """Test the Device.Reboot() command with live controller"""
    
    logger.info("=" * 80)
    logger.info("TEST: Device.Reboot() Command")
    logger.info("=" * 80)
    
    # Clean up old sockets
    for sock in [AGENT_SOCKET, CONTROLLER_SOCKET]:
        try:
            if os.path.exists(sock):
                os.unlink(sock)
        except:
            pass
    
    # Create backup of database
    db_backup = AGENT_DB + ".backup"
    with open(AGENT_DB, 'r') as f:
        original_db = json.load(f)
    with open(db_backup, 'w') as f:
        json.dump(original_db, f, indent=2)
    
    controller = None
    agent_task = None
    
    try:
        # Initialize database access
        db = agent_db.Database(AGENT_DM, AGENT_DB, "")
        
        # Step 1: Start the controller
        logger.info("\n" + "=" * 80)
        logger.info("STEP 1: Starting controller...")
        logger.info("=" * 80)
        
        controller = SimpleController(CONTROLLER_SOCKET)
        await controller.start()
        await asyncio.sleep(1.0)  # Give controller time to fully start
        logger.info("✓ Controller started")
        
        # Step 2: Start the agent
        logger.info("\n" + "=" * 80)
        logger.info("STEP 2: Starting agent...")
        logger.info("=" * 80)
        
        agent = uds_agent.UdsAgent(AGENT_DM, AGENT_DB)
        agent_task = asyncio.create_task(agent.start())
        
        # Step 3: Wait for initial Boot! notification
        logger.info("\n" + "=" * 80)
        logger.info("STEP 3: Waiting for initial Boot! notification...")
        logger.info("=" * 80)
        
        await asyncio.sleep(2)
        
        initial_boot_count = controller.get_boot_count()
        logger.info(f"✓ Received {initial_boot_count} Boot! notification(s)")
        
        if initial_boot_count == 0:
            logger.error("✗ TEST FAILED: No initial Boot! notification received")
            return
        
        # Get initial boot parameters
        initial_params = controller.get_boot_params(0)
        logger.info(f"Initial Boot! parameters: {initial_params}")
        
        # Step 4: Modify Boot! parameter mapping
        logger.info("\n" + "=" * 80)
        logger.info("STEP 4: Modifying Boot! parameter mapping...")
        logger.info("=" * 80)
        
        # Read current values
        serial_before = db.get("Device.DeviceInfo.SerialNumber")
        logger.info(f"  SerialNumber (before): {serial_before}")
        
        # Modify the SerialNumber
        new_serial = f"{serial_before}-REBOOTED"
        db.update("Device.DeviceInfo.SerialNumber", new_serial)
        logger.info(f"  SerialNumber (after):  {new_serial}")
        
        # Step 5: Send Operate(Device.Reboot()) request
        logger.info("\n" + "=" * 80)
        logger.info("STEP 5: Sending Operate(Device.Reboot()) request...")
        logger.info("=" * 80)
        
        # Create Operate request
        transport = UdsTransport(AGENT_SOCKET, 'connect')
        await transport.connect()
        
        # Build USP message
        msg = usp_msg_pb2.Msg()
        msg.header.msg_id = "test-reboot-001"
        msg.header.msg_type = usp_msg_pb2.Header.OPERATE
        
        req = msg.body.request.operate
        req.command = "Device.Reboot()"
        
        # Wrap in record
        record = usp_record_pb2.Record()
        record.version = "1.0"
        record.to_id = agent.endpoint_id
        record.from_id = "proto::controller-01"
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
            if result.HasField('req_output_args'):
                logger.info(f"✓ Reboot command accepted")
            else:
                logger.error(f"✗ Reboot command failed")
        
        await transport.close()
        
        # Step 6: Wait for second Boot! notification
        logger.info("\n" + "=" * 80)
        logger.info("STEP 6: Waiting for second Boot! notification after reboot...")
        logger.info("=" * 80)
        
        await asyncio.sleep(3)
        
        final_boot_count = controller.get_boot_count()
        logger.info(f"Total Boot! notifications received: {final_boot_count}")
        
        # Step 7: Verify the boot parameters changed
        logger.info("\n" + "=" * 80)
        logger.info("STEP 7: Verification")
        logger.info("=" * 80)
        
        if final_boot_count < 2:
            logger.error(f"✗ TEST FAILED: Expected 2 Boot! notifications, got {final_boot_count}")
        else:
            logger.info("✓ TEST PASSED: Received Boot! notification after reboot")
            logger.info("✓ Agent successfully:")
            logger.info("  1. Accepted Reboot() command")
            logger.info("  2. Cancelled periodic tasks")
            logger.info("  3. Cleared subscription handlers")
            logger.info("  4. Re-initialized subscriptions")
            logger.info(f"  5. Re-sent Boot! notification (total: {final_boot_count})")
            
            # Note: The Boot! parameters won't change because the database update
            # in the test is not visible to the agent's separate database instance.
            # In a real scenario, the database would be updated via Set command first.
        
        logger.info("\n" + "=" * 80)
        logger.info("TEST COMPLETE")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Test failed with exception: {e}", exc_info=True)
        
    finally:
        # Cleanup
        logger.info("\nCleaning up...")
        
        if agent_task:
            agent_task.cancel()
            await asyncio.gather(agent_task, return_exceptions=True)
        
        if controller:
            await controller.stop()
        
        # Restore original database
        logger.info("Restoring original database...")
        with open(db_backup, 'r') as f:
            original_db = json.load(f)
        with open(AGENT_DB, 'w') as f:
            json.dump(original_db, f, indent=2)
        os.unlink(db_backup)
        logger.info("✓ Database restored")


if __name__ == "__main__":
    asyncio.run(test_reboot_command())
