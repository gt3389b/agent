"""
Interactive Bridge Agent Test with WRP Message Sniffing

This script demonstrates the BridgeAgent with a simple controller shell
and WRP message inspection. Perfect for understanding the two-channel flow.

Usage:
    python -m tests.test_bridge_agent_interactive
    
Commands:
    get <path>              - Get parameter value
    set <path> <value>      - Set parameter value
    operate <command>       - Execute command
    add <obj_path> <params> - Add object instance
    delete <obj_path>       - Delete object instance
    boot                    - Trigger Boot! event
    periodic                - Trigger Periodic! event
    help                    - Show commands
    quit                    - Exit
"""

import asyncio
import json
import sys
import logging
from typing import Optional
from dataclasses import dataclass

# Add parent directory to path for imports
sys.path.insert(0, '/Users/rleake939@cable.comcast.com/Development/Comcast/ai/pyagent-old')

from agent.bridge_agent import BridgeAgent
from uspbridge.wrp_bridge import WrpBridge, WrpMessage, BridgeContext
from message.request import GetRequest, SetRequest, OperateRequest
from tests.mock_wrp_service import MockWrpService


# Configure logging to see what's happening
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WrpMessageSniffer:
    """
    Transport layer that sniffs/logs WRP messages
    
    This is inserted between the bridge and the mock WRP service,
    allowing us to inspect messages on the wire.
    """
    
    def __init__(self, mock_service: MockWrpService):
        self.sent_messages = []
        self.received_messages = []
        self.mock_service = mock_service
        
    def send(self, data: bytes):
        """Intercept outbound WRP messages"""
        # Decode WRP message for inspection
        wrp_msg = WrpMessage.from_bytes(data)
        
        print("\n" + "="*80)
        print("📤 OUTBOUND WRP MESSAGE (TX Channel)")
        print("="*80)
        print(f"Source:         {wrp_msg.source}")
        print(f"Destination:    {wrp_msg.dest}")
        print(f"Message Type:   {wrp_msg.msg_type.name}")
        print(f"Transaction ID: {wrp_msg.transaction_id}")
        print(f"Content Type:   {wrp_msg.content_type}")
        
        # Decode JSON-RPC payload
        if wrp_msg.payload:
            try:
                payload = json.loads(wrp_msg.payload)
                print("\nJSON-RPC Payload:")
                print(json.dumps(payload, indent=2))
            except:
                print(f"\nRaw Payload: {wrp_msg.payload}")
        
        # Show metadata (contains USP operation type!)
        if wrp_msg.metadata:
            print("\nMetadata (USP Context):")
            for key, value in wrp_msg.metadata.items():
                print(f"  {key}: {value}")
        
        print("\nWire Format:")
        print(f"  Bytes: {len(data)} bytes")
        print(f"  Hex: {data[:64].hex()}..." if len(data) > 64 else f"  Hex: {data.hex()}")
        print("="*80 + "\n")
        
        self.sent_messages.append(wrp_msg)
        
        # Forward to mock WRP service
        self.mock_service.receive(data)
    
    def receive(self, response_bytes: bytes):
        """Receive response from mock service (for agent's RX channel)"""
        # Decode and display
        wrp_msg = WrpMessage.from_bytes(response_bytes)
        
        print("\n" + "="*80)
        print("📥 INBOUND WRP MESSAGE (RX Channel)")
        print("="*80)
        print(f"Source:         {wrp_msg.source}")
        print(f"Destination:    {wrp_msg.dest}")
        print(f"Message Type:   {wrp_msg.msg_type.name}")
        print(f"Transaction ID: {wrp_msg.transaction_id}")
        print(f"Content Type:   {wrp_msg.content_type}")
        
        # Decode JSON-RPC payload
        if wrp_msg.payload:
            try:
                payload = json.loads(wrp_msg.payload)
                print("\nJSON-RPC Response:")
                print(json.dumps(payload, indent=2))
            except:
                print(f"\nRaw Payload: {wrp_msg.payload}")
        
        # Show metadata
        if wrp_msg.metadata:
            print("\nMetadata (operation type preserved!):")
            for key, value in wrp_msg.metadata.items():
                print(f"  {key}: {value}")
        
        print("="*80 + "\n")
        
        self.received_messages.append(wrp_msg)
        
        # Deliver to agent's RX callback
        if hasattr(self, '_rx_callback'):
            asyncio.create_task(self._rx_callback(response_bytes))
    
    def set_rx_callback(self, callback):
        """Set callback for receiving messages (RX channel)"""
        self._rx_callback = callback


class SimpleBridgeAgent(BridgeAgent):
    """Extended BridgeAgent with mock RX channel for testing"""
    
    def set_transport(self, transport):
        """Set transport and wire up RX callback"""
        self._transport = transport
        transport.set_rx_callback(self._handle_backend_response)
    
    async def _handle_backend_response(self, response_bytes: bytes):
        """Handle response from backend (RX channel)"""
        # Deserialize using bridge
        operation, data, context = self.bridge.from_bytes(response_bytes)
        
        print(f"\n✅ Bridge parsed response: operation={operation}")
        print(f"   USP Message ID: {context.usp_msg_id}")
        print(f"   Controller Endpoint: {context.controller_endpoint}")
        print(f"   MTP ID: {context.mtp_id}")
        print(f"   Data: {json.dumps(data, indent=2)}\n")
        
        # Find and fulfill pending request
        pending = self._pending.get(context.usp_msg_id)
        if pending and pending.future and not pending.future.done():
            response = self._build_response(operation, data, pending.request)
            pending.future.set_result(response)
    
    async def _receive_from_backend(self) -> Optional[bytes]:
        """Override to prevent actual backend polling in test"""
        # RX handled by callback instead
        await asyncio.sleep(1)
        return None


async def interactive_shell():
    """Interactive shell for testing bridge agent"""
    
    print("\n" + "="*80)
    print("🚀 USP Bridge Agent Interactive Test")
    print("="*80)
    print("\nThis demonstrates:")
    print("  • BridgeAgent routing (local vs remote paths)")
    print("  • Two-channel bridge pattern (TX/RX)")
    print("  • WRP message encoding/decoding")
    print("  • Metadata preservation (operation type)")
    print("  • Single MockWrpService with full data model")
    print("  • Endpoint-based routing (agent ID for internal, controller ID for external)")
    print("\nType 'help' for commands\n")
    
    # Create single mock WRP service with full data model
    service = MockWrpService(
        dm_file="database/test-dm.json",
        db_file="database/test-db.json"
    )
    
    # Create WRP message sniffer
    sniffer = WrpMessageSniffer(service)
    
    # Wire up mock service response
    service.response_callback = sniffer.receive
    
    # Create single WRP bridge
    bridge = WrpBridge(
        mac_address="112233445566",
        transport_send=sniffer.send
    )
    
    # Create bridge agent with single bridge
    agent = SimpleBridgeAgent(
        endpoint_id="proto::test-agent",
        bridge=bridge
    )
    
    # Wire up transport
    agent.set_transport(sniffer)
    
    # Start agent (background tasks)
    await agent.start()
    
    # Controller context (simulates incoming MTP context)
    controller_ctx = type('Context', (), {
        'endpoint': 'proto::controller-1',
        'mtp_id': 'websocket',
        'controller_id': 'ctrl-001'
    })()
    
    msg_counter = 0
    
    # Interactive loop
    while True:
        try:
            cmd = input("bridge-agent> ").strip()
            
            if not cmd:
                continue
            
            parts = cmd.split()
            command = parts[0].lower()
            
            if command == 'quit' or command == 'exit':
                print("Shutting down agent...")
                await agent.stop()
                break
            
            elif command == 'help':
                print("\nAvailable commands:")
                print("  get <path>              - Get parameter (e.g., get Device.WiFi.Radio.1.Channel)")
                print("  set <path> <value>      - Set parameter (e.g., set Device.WiFi.Radio.1.Channel 6)")
                print("  local <path>            - Get local parameter (Device.LocalAgent.*)")
                print("  boot                    - Show Boot! event (agent-owned)")
                print("  stats                   - Show message statistics")
                print("  dm                      - Show mock service data model")
                print("  help                    - Show this help")
                print("  quit                    - Exit\n")
            
            elif command == 'get':
                if len(parts) < 2:
                    print("Usage: get <path>")
                    continue
                
                path = parts[1]
                msg_counter += 1
                
                print(f"\n▶️  Sending Get request for: {path}")
                print(f"   Routing: {'LOCAL (agent DB)' if agent._is_local_path(path) else 'REMOTE (bridged to backend)'}")
                
                request = GetRequest(
                    msg_id=f"get-{msg_counter}",
                    paths=[path]
                )
                
                print(f"\n📤 GetRequest:")
                print(f"   msg_id: {request.msg_id}")
                print(f"   paths: {request.paths}")
                
                response = await agent.handle_get(request, controller_ctx)
                
                print(f"\n📥 GetResponse:")
                print(f"   msg_id: {response.msg_id}")
                print(f"   results: {response.results}")
            
            elif command == 'set':
                if len(parts) < 3:
                    print("Usage: set <path> <value>")
                    continue
                
                path = parts[1]
                value = ' '.join(parts[2:])
                msg_counter += 1
                
                print(f"\n▶️  Sending Set request: {path} = {value}")
                print(f"   Routing: {'LOCAL' if agent._is_local_path(path) else 'REMOTE'}")
                
                request = SetRequest(
                    msg_id=f"set-{msg_counter}",
                    params=[{"path": path, "value": value}]
                )
                
                print(f"\n📤 SetRequest:")
                print(f"   msg_id: {request.msg_id}")
                print(f"   params: {request.params}")
                
                response = await agent.handle_set(request, controller_ctx)
                
                print(f"\n📥 SetResponse:")
                print(f"   msg_id: {response.msg_id}")
                print(f"   results: {response.results}")
            
            elif command == 'local':
                if len(parts) < 2:
                    print("Usage: local <path>")
                    print("Example: local Device.LocalAgent.SoftwareVersion")
                    continue
                
                path = parts[1]
                msg_counter += 1
                
                print(f"\n▶️  Getting local parameter: {path}")
                print(f"   Routing: via bridge using agent's own endpoint")
                
                request = GetRequest(
                    msg_id=f"local-{msg_counter}",
                    paths=[path]
                )
                
                print(f"\n📤 GetRequest:")
                print(f"   msg_id: {request.msg_id}")
                print(f"   paths: {request.paths}")
                
                response = await agent.handle_get(request, controller_ctx)
                
                print(f"\n📥 GetResponse:")
                print(f"   msg_id: {response.msg_id}")
                print(f"   results: {response.results}")
            
            elif command == 'boot':
                print("\n▶️  Boot! event (agent-owned, not bridged)")
                await agent._send_boot_event()
                print("   Boot event generated by agent")
            
            elif command == 'stats':
                print(f"\n📊 Message Statistics:")
                print(f"   WRP sent:     {len(sniffer.sent_messages)} messages")
                print(f"   WRP received: {len(sniffer.received_messages)} messages")
                print(f"   Agent pending: {len(agent._pending)} requests")
                
                stats = service.get_stats()
                
                print(f"\n   Service:")
                print(f"   Requests:  {stats['requests']}")
                print(f"   Responses: {stats['responses']}")
                print(f"   DB Size:   {stats['db_size']} parameters")
            
            elif command == 'dm':
                print(f"\n📚 Service Data Model (first 20):")
                params = list(service.db._db.keys())[:20]
                for param in sorted(params):
                    value = service.db._db.get(param, "N/A")
                    print(f"   {param} = {value}")
            
            else:
                print(f"Unknown command: {command}")
                print("Type 'help' for available commands")
        
        except KeyboardInterrupt:
            print("\n\nShutting down...")
            await agent.stop()
            break
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(interactive_shell())
    except KeyboardInterrupt:
        print("\nExiting...")
