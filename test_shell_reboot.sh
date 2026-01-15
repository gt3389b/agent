#!/bin/bash
# Test Device.Reboot() via shell/API

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================================="
echo "Testing Device.Reboot() via Controller Shell/API"
echo "=================================================="
echo ""

# 1. Start controller in background
echo -e "${YELLOW}Step 1: Starting controller...${NC}"
python3 -m controller.main -t uds > /tmp/controller.log 2>&1 &
CONTROLLER_PID=$!
sleep 2
echo -e "${GREEN}✓ Controller started (PID: $CONTROLLER_PID)${NC}"
echo ""

# 2. Start agent in background
echo -e "${YELLOW}Step 2: Starting agent...${NC}"
python3 -m agent.main -t uds > /tmp/agent.log 2>&1 &
AGENT_PID=$!
sleep 2
echo -e "${GREEN}✓ Agent started (PID: $AGENT_PID)${NC}"
echo ""

# 3. Wait for Boot! notification
echo -e "${YELLOW}Step 3: Waiting for Boot! notification...${NC}"
sleep 2
echo -e "${GREEN}✓ Agent should have sent Boot! notification${NC}"
echo ""

# 4. List connected agents
echo -e "${YELLOW}Step 4: Listing connected agents...${NC}"
python3 << 'EOF'
import asyncio
import json
import sys

async def list_agents():
    reader, writer = await asyncio.open_unix_connection('/tmp/usp-controller-api.sock')
    
    request = {
        "jsonrpc": "2.0",
        "method": "list_agents",
        "params": {},
        "id": 1
    }
    
    writer.write((json.dumps(request) + '\n').encode())
    await writer.drain()
    
    response = await reader.readline()
    result = json.loads(response.decode())
    
    writer.close()
    await writer.wait_closed()
    
    if 'result' in result:
        agents = result['result']
        print(f"✓ Found {len(agents)} connected agent(s):")
        for agent in agents:
            print(f"  - {agent['agent_id']}")
            print(f"    Serial: {agent.get('serial_number', 'N/A')}")
            print(f"    Last Boot: {agent.get('last_boot', 'N/A')}")
        return agents[0]['agent_id'] if agents else None
    else:
        print(f"Error: {result.get('error', {}).get('message', 'Unknown error')}")
        return None

try:
    agent_id = asyncio.run(list_agents())
    if agent_id:
        with open('/tmp/agent_id.txt', 'w') as f:
            f.write(agent_id)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
EOF
echo ""

# Get agent ID from temp file
AGENT_ID=$(cat /tmp/agent_id.txt 2>/dev/null)
if [ -z "$AGENT_ID" ]; then
    echo "Error: No agent connected"
    kill $CONTROLLER_PID $AGENT_PID 2>/dev/null
    exit 1
fi

# 5. Send Reboot() command
echo -e "${YELLOW}Step 5: Sending Device.Reboot() command to ${AGENT_ID}...${NC}"
python3 << EOF
import asyncio
import json
import sys

async def send_reboot():
    reader, writer = await asyncio.open_unix_connection('/tmp/usp-controller-api.sock')
    
    request = {
        "jsonrpc": "2.0",
        "method": "operate",
        "params": {
            "agent_id": "${AGENT_ID}",
            "command": "Device.Reboot()",
            "args": {}
        },
        "id": 2
    }
    
    writer.write((json.dumps(request) + '\n').encode())
    await writer.drain()
    
    response = await reader.readline()
    result = json.loads(response.decode())
    
    writer.close()
    await writer.wait_closed()
    
    if 'result' in result:
        print("✓ Reboot command sent successfully!")
        print(f"  Result: {result['result']}")
    else:
        error = result.get('error', {})
        print(f"✗ Error: {error.get('message', 'Unknown error')}")
        sys.exit(1)

try:
    asyncio.run(send_reboot())
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
EOF
echo ""

# 6. Wait for agent to reboot and send new Boot!
echo -e "${YELLOW}Step 6: Waiting for agent reboot and new Boot! notification...${NC}"
sleep 3
echo -e "${GREEN}✓ Agent should have rebooted and sent second Boot!${NC}"
echo ""

# 7. Check controller logs for Boot! notifications
echo -e "${YELLOW}Step 7: Checking for Boot! notifications in controller log...${NC}"
BOOT_COUNT=$(grep -c "Boot! notification received successfully!" /tmp/controller.log)
echo -e "${GREEN}✓ Found ${BOOT_COUNT} Boot! notification(s) in controller log${NC}"
echo ""

# Show relevant log entries
echo "Recent controller log entries:"
echo "-----------------------------"
grep -E "Boot!|Reboot|REBOOT" /tmp/controller.log | tail -10
echo ""

# Show agent log
echo "Recent agent log entries:"
echo "------------------------"
grep -E "Boot!|Reboot|REBOOT" /tmp/agent.log | tail -10
echo ""

# Cleanup
echo -e "${YELLOW}Cleaning up...${NC}"
kill $CONTROLLER_PID $AGENT_PID 2>/dev/null
rm -f /tmp/agent_id.txt
sleep 1
echo -e "${GREEN}✓ Cleanup complete${NC}"
echo ""

if [ "$BOOT_COUNT" -ge "2" ]; then
    echo "=================================================="
    echo -e "${GREEN}✓ TEST PASSED: Agent rebooted successfully!${NC}"
    echo "=================================================="
else
    echo "=================================================="
    echo -e "✗ TEST FAILED: Expected 2 Boot! notifications, got ${BOOT_COUNT}"
    echo "=================================================="
    exit 1
fi
